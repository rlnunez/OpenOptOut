"""
Opt-out letters, chosen by where the broker is and written in its legal language.

The letter a broker receives depends on the broker, not on the family: a
Spanish-speaking family in California writes to a US broker in English, and
anyone writing to a French broker writes in French under the GDPR
(docs/CATALOG_AND_LOCALIZATION_DESIGN.md §4). So the letter is picked from

    jurisdiction    the broker's (BrokerSpec.effective_jurisdiction(), or a
                    parent company's), e.g. "US", "FR", "BR"
    residence       the family member's US state, which decides between the
                    CCPA letter (California) and the general US letter
    legal language  the broker's (BrokerSpec.effective_legal_language()), never
                    the app's interface language

Each letter is a plugin of type "letters" (plugins/bundled/letters/letter-<law>/
holds the built-in ones): a manifest.json and a letter.json with one version
per language. Every one is marked `review_status: "draft"` until a lawyer has
reviewed it; `review_note` says what to check. Admins can turn a letter off,
replace a built-in one by uploading a plugin with the same letter id, or add
new ones. Pieces every letter shares (identifier labels, the scope paragraph,
the reference line) are in core/legal_templates/_parts.json.

Which letter a broker gets, first match wins (letter_choice()):

  1. the letter an admin picked for that broker or parent company
  2. the broker add-on's own wording (spec email_templates), when it has one
  3. the letter the broker add-on names (spec "letter")
  4. automatic: the enabled letter whose `jurisdictions` / `residents_of`
     fit the broker's jurisdiction and the person's state best; the general
     letter ("*") when nothing else fits

Nothing here sends anything; it only builds text.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "legal_templates")
FALLBACK_ID = "generic"     # always available, even if its plugin is turned off

# EU member states and the rest of the EEA: what "EU" / "EEA" in a letter's
# jurisdictions covers.
EU_EEA = {
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE",
    "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE",
    "IS", "LI", "NO",
}
# Placeholders every letter body must use, so no letter can leave out the
# identifiers (without them a broker can't find the records) or the signature.
REQUIRED_IN_BODY = {"broker", "scope", "identifiers", "reference", "full_name", "property_note"}
REQUIRED_IN_SUBJECT = {"full_name", "ref_tag"}
REVIEWED = "reviewed"
LETTER_FILE = "letter.json"
_ID = re.compile(r"^[a-z][a-z0-9_-]{1,40}$")

_CACHE: Dict[str, Any] = {"at": 0.0, "templates": None, "parts": None}
_TTL = 30.0


def _letter_dirs():
    """(plugin dir, built_in) for every letter plugin: the built-in sources,
    then installed copies and admins' own uploads under the plugins root,
    which win for the same letter id."""
    from ..plugins import layout
    out = []
    bundled = os.path.join(layout.BUNDLED_ROOT, "letters")
    if os.path.isdir(bundled):
        out += [(os.path.join(bundled, d), True) for d in sorted(os.listdir(bundled)) if not d.startswith(".")]
    try:
        root = os.path.join(layout.plugins_root(), "letters")
    except Exception:
        root = ""
    if root and os.path.isdir(root):
        for d in sorted(os.listdir(root)):
            full = os.path.join(root, d)
            if not d.startswith(".") and os.path.isdir(full):
                out.append((full, layout.is_bundled_copy(full)))
    return out


def _plugin_states() -> Dict[str, bool]:
    """plugin id -> enabled, for installed letter plugins (empty if there's
    no database yet)."""
    url = os.getenv("DATABASE_URL", "sqlite:///./privacy_pipeline.db")
    if url.startswith("sqlite:///") and not os.path.exists(url[len("sqlite:///"):]):
        return {}
    try:
        from ..models.database import SessionLocal, InstalledPlugin
        db = SessionLocal()
        try:
            return {r.plugin_id: bool(r.enabled) for r in db.query(InstalledPlugin).all()}
        finally:
            db.close()
    except Exception:
        return {}


def read_letter_plugin(plugin_dir: str) -> dict:
    """The letter in a plugin folder, with where it came from."""
    with open(os.path.join(plugin_dir, "manifest.json"), "r", encoding="utf-8") as f:
        manifest = json.load(f)
    with open(os.path.join(plugin_dir, LETTER_FILE), "r", encoding="utf-8") as f:
        t = json.load(f)
    t["_plugin_id"] = manifest.get("id", "")
    t["_plugin_version"] = manifest.get("version", "")
    return t


def _load() -> None:
    states = _plugin_states()
    found: Dict[str, dict] = {}
    for d, built_in in _letter_dirs():
        try:
            t = read_letter_plugin(d)
        except Exception:
            continue
        if not isinstance(t, dict) or not _ID.match(str(t.get("id", ""))):
            continue
        t["_built_in"] = built_in
        enabled = states.get(t["_plugin_id"], built_in)   # an upload counts once it's enabled
        t["_enabled"] = enabled
        prev = found.get(t["id"])
        # An admin's own letter replaces the built-in one with the same id.
        if prev is None or (not built_in and enabled) or (prev.get("_built_in") and built_in):
            found[t["id"]] = t
    with open(os.path.join(TEMPLATE_DIR, "_parts.json"), "r", encoding="utf-8") as f:
        parts_ = {k: v for k, v in json.load(f).items() if not k.startswith("_")}
    import time
    _CACHE.update(at=time.monotonic(), templates=found, parts=parts_)


def reload() -> None:
    """Forget the cached letters (after a letter plugin is added or switched)."""
    _CACHE["templates"] = None


def all_templates() -> Dict[str, dict]:
    """Every letter found, enabled or not (for the admin page)."""
    import time
    if _CACHE["templates"] is None or time.monotonic() - _CACHE["at"] > _TTL:
        _load()
    return _CACHE["templates"]  # type: ignore[return-value]


def templates() -> Dict[str, dict]:
    """id -> letter, for the letters that can be used now."""
    return {k: t for k, t in all_templates().items() if t.get("_enabled") or k == FALLBACK_ID}


def parts() -> Dict[str, dict]:
    if _CACHE["parts"] is None:
        _load()
    return _CACHE["parts"]  # type: ignore[return-value]


def _pick_language(available: Iterable[str], want: str, fallback: str) -> str:
    """The best of `available` for `want`: exact ("pt-BR"), then base ("pt"),
    then another variant of the base ("pt-BR" for "pt"), then `fallback`."""
    avail = list(available)
    by_lower = {a.lower(): a for a in avail}
    w = (want or "").replace("_", "-").lower()
    if w in by_lower:
        return by_lower[w]
    base = w.split("-")[0]
    if base in by_lower:
        return by_lower[base]
    for a in avail:
        if a.lower().split("-")[0] == base and base:
            return a
    return fallback


def _fit(t: dict, jurisdiction: str, residence_state: str) -> int:
    """How well letter `t` fits a broker in `jurisdiction` writing for a person
    living in `residence_state`; 0 = doesn't apply. Higher wins."""
    def norm(code: str) -> str:      # "UK" is written for Great Britain too
        code = str(code or "").upper().strip()
        return "GB" + code[2:] if code.startswith("UK") else code
    j = norm(jurisdiction or "US")
    country = j.split("-")[0]
    best = 0
    for raw in t.get("jurisdictions") or []:
        want = norm(raw)
        want_country = want.split("-")[0]
        if want == "*":
            score = 1
        elif want == j:
            score = 40
        elif "-" not in want and want_country == country:
            score = 30
        elif want in ("EU", "EEA") and country in (EU_EEA | {"EU", "EEA"}):
            score = 20
        else:
            score = 0
        best = max(best, score)
    if not best:
        return 0
    residents = [str(r).upper() for r in (t.get("residents_of") or [])]
    if residents:
        state = (residence_state or "").upper().strip()
        if state in ("CALIFORNIA",):
            state = "CA"
        if state not in residents:
            return 0
        best += 5
    return best


def choose_template(jurisdiction: str, residence_state: str = "") -> dict:
    """The letter for a broker in `jurisdiction`, for a person living in
    `residence_state` (a US state code; only letters with `residents_of`
    look at it). The general letter when nothing else fits."""
    ranked = sorted(((_fit(t, jurisdiction, residence_state), not t.get("_built_in"), tid, t)
                     for tid, t in templates().items()), key=lambda x: (x[0], x[1], x[2]), reverse=True)
    if ranked and ranked[0][0] > 0:
        return ranked[0][3]
    return all_templates()[FALLBACK_ID]


def letter_choice(*, admin_choice: str = "", spec=None, jurisdiction: str = "US",
                  residence_state: str = "", legal_language: str = "") -> dict:
    """Which letter a broker gets, and why:
    {"template_id", "source": "admin" | "addon_text" | "addon" | "automatic",
     "missing": <an admin's or add-on's choice that isn't available>}"""
    avail = templates()
    out = {"template_id": "", "source": "automatic", "missing": ""}
    if admin_choice:
        if admin_choice in avail:
            return {**out, "template_id": admin_choice, "source": "admin"}
        out["missing"] = admin_choice
    if spec is not None and spec.letter_template(legal_language):
        return {**out, "source": "addon_text"}
    named = getattr(spec, "letter", "") if spec is not None else ""
    if named:
        if named in avail:
            return {**out, "template_id": named, "source": "addon"}
        out["missing"] = out["missing"] or named
    return {**out, "template_id": choose_template(jurisdiction, residence_state)["id"]}


def default_language(jurisdiction: str) -> str:
    """The language a broker's legal team is written to in when nobody said:
    French for France, Portuguese for Brazil, English otherwise."""
    from .interpreter.broker_spec import JURISDICTION_LANGUAGE
    j = (jurisdiction or "").upper().strip()
    return JURISDICTION_LANGUAGE.get(j) or JURISDICTION_LANGUAGE.get(j.split("-")[0]) or ""


def letter_language(template: dict, legal_language: str = "", jurisdiction: str = "") -> str:
    """The language `template` will be written in for this broker."""
    want = legal_language or default_language(jurisdiction) or template["default_language"]
    return _pick_language(template["languages"], want, template["default_language"])


@dataclass
class Letter:
    subject: str
    body: str
    template_id: str
    language: str          # the language the letter is written in
    review_status: str     # "draft" until a lawyer has reviewed it
    deadline_days: int
    law: str


def _fill(text: str, values: Dict[str, Any]) -> str:
    def sub(m):
        k = m.group(1)
        return str(values[k]) if k in values and values[k] is not None else m.group(0)
    return re.sub(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", sub, text or "")


def _tidy(body: str) -> str:
    """Drop the blank paragraphs left by optional parts that were empty."""
    body = re.sub(r"[ \t]+\n", "\n", body)
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip() + "\n"


def _bullets(label: str, items, sep: str = ": ") -> str:
    items = [str(i).strip() for i in (items or []) if str(i).strip()]
    if not items:
        return ""
    return f"{label}{sep.rstrip()}\n" + "\n".join(f"  - {i}" for i in items) + "\n"


def identifier_block(ids, language: str = "en") -> str:
    """Every identifier the broker needs to find the records, labelled in
    `language`. `ids` has the fields of optout_email_template.Identifiers.
    Gives an age or age range, never an exact date of birth."""
    p = parts()[_pick_language(parts(), language, "en")]
    out, sep = "", p.get("sep", ": ")
    if getattr(ids, "full_name", ""):
        out += f"{p['full_name']}{sep}{ids.full_name}\n"
    out += _bullets(p["names"], getattr(ids, "name_variants", []), sep)
    out += _bullets(p["emails"], getattr(ids, "emails", []), sep)
    out += _bullets(p["phones"], getattr(ids, "phones", []), sep)
    out += _bullets(p["addresses"], getattr(ids, "addresses", []), sep)
    if getattr(ids, "age", None):
        out += _fill(p["age"], {"age": ids.age}) + "\n"
    elif getattr(ids, "age_range", ""):
        out += _fill(p["age_range"], {"age_range": ids.age_range}) + "\n"
    if getattr(ids, "city_state", ""):
        out += _fill(p["location"], {"location": ids.city_state}) + "\n"
    return out.rstrip("\n")


def _sites(broker: str, sites, p: dict) -> str:
    """The scope paragraph, listing child sites (with discovered links) if any."""
    if not sites:
        return _fill(p["scope_all"], {"broker": broker})
    lines = []
    for name, url in sites:
        lines.append(f"  - {name}: {url}" if name and url else f"  - {url or name}")
    has_urls = any(url for _, url in sites)
    head = _fill(p["scope_sites"], {"broker": broker, "urls_note": p["urls_note"] if has_urls else ""})
    return head + "\n" + "\n".join(lines)


def _property(prop: Optional[dict], p: dict) -> str:
    if not prop or not prop.get("formal_name"):
        return ""
    out = _fill(p["property_note"], {"formal_name": prop["formal_name"]})
    if prop.get("deed"):
        out += "\n" + _fill(p["deed"], {"list": ", ".join(prop["deed"])})
    if prop.get("mortgage"):
        out += "\n" + _fill(p["mortgage"], {"list": ", ".join(prop["mortgage"])})
    return out


def compose_letter(ids, broker: str, *, jurisdiction: str = "US", legal_language: str = "",
                   residence_state: str = "", sites=None, request_key: str = "",
                   property_records: Optional[dict] = None,
                   template_id: str = "", allow_disabled: bool = False) -> Letter:
    """
    The opt-out letter to `broker` for the person described by `ids`.

    sites: [(name, url)] child sites of a parent company (url may be "").
    property_records: {"formal_name", "deed": [...], "mortgage": [...]} for
        brokers that publish property records.
    template_id: use this letter instead of choosing by jurisdiction.
    allow_disabled: also use a letter that's turned off (previews only).
    """
    t = (all_templates() if allow_disabled else templates()).get(template_id) if template_id else None
    t = t or choose_template(jurisdiction, residence_state)
    lang = letter_language(t, legal_language, jurisdiction)
    v = t["languages"][lang]
    p = parts()[_pick_language(parts(), lang, "en")]
    state = (residence_state or "").strip()
    law = v.get("law_state") if state and v.get("law_state") else v.get("law", "")
    values = {
        "broker": broker,
        "full_name": getattr(ids, "full_name", "") or p["requester"],
        "state": state,
        "request_key": request_key,
        "ref_tag": f" [{request_key}]" if request_key else "",
        "deadline_days": t.get("deadline_days", 0),
    }
    values["law"] = _fill(law, values)
    values["scope"] = _sites(broker, sites or [], p)
    values["property_note"] = _property(property_records, p)
    values["identifiers"] = identifier_block(ids, lang)
    values["reference"] = _fill(p["reference"], values) if request_key else ""
    subject = _fill(v["subject"], {**values, "full_name": getattr(ids, "full_name", "") or ""})
    subject = re.sub(r"\s*—\s*$", "", re.sub(r"—\s+\[", "— [", subject)).strip()
    return Letter(
        subject=subject,
        body=_tidy(_fill(v["body"], values)),
        template_id=t["id"],
        language=lang,
        review_status=t.get("review_status", "draft"),
        deadline_days=int(t.get("deadline_days", 0) or 0),
        law=t.get("law", ""),
    )


def catalog() -> list[dict]:
    """Every letter, for the admin page and docs."""
    return [{
        "id": t["id"], "title": t.get("title", t["id"]), "law": t.get("law", ""),
        "languages": sorted(t["languages"]), "deadline_days": t.get("deadline_days", 0),
        "review_status": t.get("review_status", "draft"), "review_note": t.get("review_note", ""),
        "jurisdictions": t.get("jurisdictions", []), "residents_of": t.get("residents_of", []),
        "plugin_id": t.get("_plugin_id", ""), "version": t.get("_plugin_version", ""),
        "built_in": bool(t.get("_built_in")), "enabled": bool(t.get("_enabled")) or t["id"] == FALLBACK_ID,
    } for t in sorted(all_templates().values(), key=lambda t: (t["id"] != FALLBACK_ID, t.get("title", "")))]


def letter_errors(t: dict, where: str = "") -> list[str]:
    """Problems with one letter (a plugin's letter.json)."""
    errs = []
    tid = where or str(t.get("id", "?"))
    placeholder = re.compile(r"\{(\w+)\}")
    if not _ID.match(str(t.get("id", ""))):
        errs.append(f"{tid}: id must be 2-41 lowercase letters, digits, - or _")
    for k in ("title", "law", "default_language", "languages", "review_status", "review_note"):
        if k not in t:
            errs.append(f"{tid}: missing {k}")
    if not isinstance(t.get("languages", {}), dict) or not t.get("languages"):
        errs.append(f"{tid}: languages must hold at least one version")
        return errs
    if t.get("default_language") not in t.get("languages", {}):
        errs.append(f"{tid}: no letter in its default language {t.get('default_language')}")
    if t.get("review_status") not in ("draft", REVIEWED):
        errs.append(f"{tid}: review_status must be draft or reviewed")
    if not isinstance(t.get("jurisdictions", []), list) or not isinstance(t.get("residents_of", []), list):
        errs.append(f"{tid}: jurisdictions and residents_of must be lists")
    for lang, v in t.get("languages", {}).items():
        if not isinstance(v, dict):
            errs.append(f"{tid}/{lang}: must be an object with subject and body")
            continue
        body, subject = v.get("body", ""), v.get("subject", "")
        missing = REQUIRED_IN_BODY - set(placeholder.findall(body))
        if missing:
            errs.append(f"{tid}/{lang}: body doesn't use {sorted(missing)}")
        missing = REQUIRED_IN_SUBJECT - set(placeholder.findall(subject))
        if missing:
            errs.append(f"{tid}/{lang}: subject doesn't use {sorted(missing)}")
        if "{law}" in body and not v.get("law"):
            errs.append(f"{tid}/{lang}: body uses {{law}} but there's no law text")
        if _pick_language(parts(), lang, "") == "":
            errs.append(f"{tid}/{lang}: no shared parts for this language in _parts.json")
    return errs


def plugin_letter_errors(plugin_dir: str) -> list[str]:
    """Problems with a letter plugin's folder (checked when it's uploaded)."""
    path = os.path.join(plugin_dir, LETTER_FILE)
    if not os.path.isfile(path):
        return [f"a letters plugin needs a {LETTER_FILE}"]
    try:
        with open(path, "r", encoding="utf-8") as f:
            t = json.load(f)
    except Exception as e:
        return [f"{LETTER_FILE} couldn't be read: {e}"]
    if not isinstance(t, dict):
        return [f"{LETTER_FILE} must be an object"]
    return letter_errors(t)


def template_errors() -> list[str]:
    """Problems with the letters and shared parts (run by the test suite)."""
    errs = []
    placeholder = re.compile(r"\{(\w+)\}")
    for tid, t in all_templates().items():
        errs += letter_errors(t, tid)
    if FALLBACK_ID not in all_templates():
        errs.append(f"the general letter '{FALLBACK_ID}' is missing")
    want = set(parts()["en"])
    for lang, p in parts().items():
        if set(p) != want:
            errs.append(f"_parts.json {lang}: keys differ from en ({sorted(want ^ set(p))})")
        for k, text in p.items():
            if set(placeholder.findall(text)) != set(placeholder.findall(parts()["en"].get(k, ""))):
                errs.append(f"_parts.json {lang}.{k}: placeholders differ from en")
    return errs
