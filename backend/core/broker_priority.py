"""
Broker priority: default derivation, rules, and dispatch ordering.

Priority is a single 1..5 number per broker (5 = highest = dispatched first
within a member's daily throttle budget). There is ONE source of truth — the
`priority` column — plus a `priority_source` marker (default | rule | manual)
recording how it was last set.

Three ways a broker's priority gets written, all to the same field:
  1. DEFAULT   — derived from status/difficulty/property when a broker is created
                 or reset. A sensible starting point so nothing is ever unranked.
  2. RULE      — an admin runs a bulk rule ("all property brokers = 5"). Rules are
                 a destructive ACTION, not a live layer: they write priority into
                 the brokers they match and stop. Only matching brokers change.
  3. MANUAL    — an admin sets one broker (or a bulk-selected set) by hand.

Because rules overwrite, the UI previews a rule before applying it and warns how
many brokers it will change — broken down by how those values were set (manual
vs rule/default) — so an admin never silently loses hand-tuned values. A reset
action returns brokers to their derived default.

Dispatch ordering (used by the scheduler's throttle) sorts by the explicit
`priority` field, breaking ties with the derived score and then age.
"""

from dataclasses import dataclass, field
from typing import Optional

# ── Derived default (the starting value before any human touches it) ──────────

_STATUS_WEIGHT = {
    "resistant":    5,   # actively fights removal
    "inconsistent": 4,
    "undetermined": 3,
    "compliant":    2,
}
_DIFFICULTY_BUMP = {"hard": 1, "medium": 0, "easy": 0}


def _enum_val(v):
    return getattr(v, "value", None) or (v if isinstance(v, str) else None)


def derived_priority(broker) -> int:
    """
    Compute a 1..5 default priority from existing broker signals. Used as the
    initial value and by 'reset to default'. Property brokers (home address /
    ownership exposure) floor at 5; otherwise status drives it, nudged by
    difficulty. Always clamped to 1..5.
    """
    if getattr(broker, "is_property_broker", False):
        return 5
    base = _STATUS_WEIGHT.get(_enum_val(getattr(broker, "status", None)), 3)
    base += _DIFFICULTY_BUMP.get(_enum_val(getattr(broker, "difficulty", None)), 0)
    return max(1, min(5, base))


def priority_label(p: int) -> str:
    """Human label for a 1..5 priority, for UIs that prefer words."""
    return {1: "lowest", 2: "low", 3: "medium", 4: "high", 5: "highest"}.get(int(p or 3), "medium")


# ── Rules ─────────────────────────────────────────────────────────────────────

@dataclass
class PriorityRule:
    """
    A rule matches brokers on attributes we already have, plus a name keyword,
    and sets a priority. Matching is AND across whichever fields are provided;
    an empty rule matches nothing (guard against an accidental "match all").
    """
    set_priority: int                       # 1..5 to assign to matches
    status: Optional[str] = None            # compliant|resistant|inconsistent|undetermined
    difficulty: Optional[str] = None        # easy|medium|hard
    method: Optional[str] = None            # form|email|manual|phone
    is_property_broker: Optional[bool] = None
    name_contains: Optional[str] = None     # case-insensitive substring of broker name
    label: str = ""                         # optional human description

    def validate(self) -> list[str]:
        errs = []
        if not isinstance(self.set_priority, int) or not (1 <= self.set_priority <= 5):
            errs.append("set_priority must be an integer 1..5")
        if not any([self.status, self.difficulty, self.method,
                    self.is_property_broker is not None, self.name_contains]):
            errs.append("rule must match on at least one attribute (would otherwise match nothing)")
        return errs

    def matches(self, broker) -> bool:
        if self.status and _enum_val(getattr(broker, "status", None)) != self.status:
            return False
        if self.difficulty and _enum_val(getattr(broker, "difficulty", None)) != self.difficulty:
            return False
        if self.method and _enum_val(getattr(broker, "method", None)) != self.method:
            return False
        if self.is_property_broker is not None and \
                bool(getattr(broker, "is_property_broker", False)) != self.is_property_broker:
            return False
        if self.name_contains and self.name_contains.lower() not in (getattr(broker, "name", "") or "").lower():
            return False
        return True

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__
                if getattr(self, k) not in (None, "")}

    @classmethod
    def from_dict(cls, d: dict) -> "PriorityRule":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class RulePreview:
    """What running a rule WOULD do — computed before applying, for the warning."""
    total_matched: int = 0
    would_change: int = 0            # matched AND currently a different priority
    overwrites_manual: int = 0       # of would_change, how many were manually set
    overwrites_rule_or_default: int = 0
    matched_broker_ids: list = field(default_factory=list)


def preview_rule(rule: PriorityRule, brokers) -> RulePreview:
    """
    Compute the effect of a rule without applying it. Drives the confirmation
    warning: how many brokers change, and how many of those had manual values
    (which the admin is about to overwrite).
    """
    pv = RulePreview()
    for b in brokers:
        if not rule.matches(b):
            continue
        pv.total_matched += 1
        pv.matched_broker_ids.append(getattr(b, "id", None))
        if int(getattr(b, "priority", 3) or 3) != rule.set_priority:
            pv.would_change += 1
            if getattr(b, "priority_source", "default") == "manual":
                pv.overwrites_manual += 1
            else:
                pv.overwrites_rule_or_default += 1
    return pv


def apply_rule(rule: PriorityRule, brokers) -> int:
    """
    Apply a rule: write set_priority into every matching broker and mark its
    source as 'rule'. Only matching brokers are touched. Returns the count
    changed. The caller commits the session.
    """
    changed = 0
    for b in brokers:
        if rule.matches(b):
            if int(getattr(b, "priority", 3) or 3) != rule.set_priority or \
                    getattr(b, "priority_source", "default") != "rule":
                b.priority = rule.set_priority
                b.priority_source = "rule"
                changed += 1
    return changed


def reset_to_default(broker) -> None:
    """Return one broker to its derived default priority."""
    broker.priority = derived_priority(broker)
    broker.priority_source = "default"


# ── Dispatch ordering (used by the scheduler throttle) ────────────────────────

def order_pending(pending: list, strategy: str = "priority") -> list:
    """
    Order pending RemovalRequest rows for dispatch.

    strategy:
      "priority" (default) — highest broker.priority first, then derived score,
                             then oldest. The explicit 1..5 field drives dispatch,
                             with the derived score only as a tiebreaker.
      "fifo"               — oldest pending first.
      "easy_first"         — lowest priority first (quick, low-stakes wins).
    """
    def created(req):
        return getattr(req, "created_at", None) or 0

    def prio(req):
        return int(getattr(req.broker, "priority", 3) or 3) if req.broker else 3

    def deriv(req):
        return derived_priority(req.broker) if req.broker else 3

    if strategy == "fifo":
        return sorted(pending, key=created)
    if strategy == "easy_first":
        return sorted(pending, key=lambda r: (prio(r), created(r)))
    return sorted(pending, key=lambda r: (-prio(r), -deriv(r), created(r)))


# ── Import / export (three artifacts: rankings, rules, or both) ───────────────

def export_rankings(brokers) -> dict:
    """A portable broker-name -> {priority, source} map. Final numbers, shareable
    regardless of how they were derived."""
    return {
        "kind": "priority_rankings",
        "version": 1,
        "rankings": [
            {"name": b.name, "priority": int(getattr(b, "priority", 3) or 3),
             "source": getattr(b, "priority_source", "default")}
            for b in brokers
        ],
    }


def export_rules(rules: list) -> dict:
    """A portable set of rules (methodology), shareable independent of any broker
    list — stays correct even as broker lists diverge between deployments."""
    return {"kind": "priority_rules", "version": 1,
            "rules": [r.to_dict() for r in rules]}


def export_both(brokers, rules: list) -> dict:
    return {"kind": "priority_bundle", "version": 1,
            "rankings": export_rankings(brokers)["rankings"],
            "rules": export_rules(rules)["rules"]}


def parse_import(data: dict) -> dict:
    """
    Parse an uploaded artifact into {'rankings': [...], 'rules': [PriorityRule]}.
    Accepts any of the three export kinds. Raises ValueError on a malformed file.
    """
    if not isinstance(data, dict) or "kind" not in data:
        raise ValueError("not a recognized priority export (missing 'kind')")
    out = {"rankings": [], "rules": []}
    kind = data.get("kind")
    if kind in ("priority_rankings", "priority_bundle"):
        out["rankings"] = data.get("rankings", [])
    if kind in ("priority_rules", "priority_bundle"):
        rules = []
        for rd in data.get("rules", []):
            r = PriorityRule.from_dict(rd)
            errs = r.validate()
            if errs:
                raise ValueError(f"invalid rule in import: {errs}")
            rules.append(r)
        out["rules"] = rules
    if kind not in ("priority_rankings", "priority_rules", "priority_bundle"):
        raise ValueError(f"unknown export kind: {kind}")
    return out


def apply_imported_rankings(rankings: list, brokers_by_name: dict) -> int:
    """
    Apply an imported rankings list (name -> priority) to existing brokers.
    Sets source to 'manual' (an imported curated ranking is an explicit human
    decision). Returns count applied. Unknown broker names are skipped.
    """
    changed = 0
    for row in rankings:
        b = brokers_by_name.get((row.get("name") or "").lower())
        if not b:
            continue
        p = max(1, min(5, int(row.get("priority", 3) or 3)))
        if b.priority != p or b.priority_source != "manual":
            b.priority = p
            b.priority_source = "manual"
            changed += 1
    return changed
