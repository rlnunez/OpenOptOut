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

The letters live in core/legal_templates/<id>.json, one file per law, with a
version per language. Every one is marked `review_status: "draft"` until a
lawyer has reviewed it; `review_note` says what to check. Pieces every letter
shares (identifier labels, the scope paragraph, the reference line) are in
_parts.json.

Nothing here sends anything; it only builds text.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "legal_templates")

# EU member states and the rest of the EEA: the GDPR letter.
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

_TEMPLATES: Optional[Dict[str, dict]] = None
_PARTS: Optional[Dict[str, dict]] = None


def _load() -> None:
    global _TEMPLATES, _PARTS
    templates = {}
    for name in sorted(os.listdir(TEMPLATE_DIR)):
        if not name.endswith(".json") or name.startswith("_"):
            continue
        with open(os.path.join(TEMPLATE_DIR, name), "r", encoding="utf-8") as f:
            t = json.load(f)
        templates[t["id"]] = t
    with open(os.path.join(TEMPLATE_DIR, "_parts.json"), "r", encoding="utf-8") as f:
        parts = {k: v for k, v in json.load(f).items() if not k.startswith("_")}
    _TEMPLATES, _PARTS = templates, parts


def templates() -> Dict[str, dict]:
    """id -> letter template, as stored."""
    if _TEMPLATES is None:
        _load()
    return _TEMPLATES  # type: ignore[return-value]


def parts() -> Dict[str, dict]:
    if _PARTS is None:
        _load()
    return _PARTS  # type: ignore[return-value]


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


def choose_template(jurisdiction: str, residence_state: str = "") -> dict:
    """The letter for a broker in `jurisdiction`, for a person living in
    `residence_state` (a US state code, used only for US brokers)."""
    t = templates()
    j = (jurisdiction or "US").upper().strip()
    country = j.split("-")[0]
    if country in ("UK", "GB"):
        return t["uk_gdpr"]
    if country in ("EU", "EEA") or country in EU_EEA:
        return t["gdpr"]
    if country == "BR":
        return t["lgpd"]
    if country == "CA":
        return t["pipeda"]
    if country == "US":
        state = (residence_state or "").upper().strip()
        if state in ("CA", "CALIFORNIA"):
            return t["ccpa"]
        return t["us"]
    return t["generic"]


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
                   template_id: str = "") -> Letter:
    """
    The opt-out letter to `broker` for the person described by `ids`.

    sites: [(name, url)] child sites of a parent company (url may be "").
    property_records: {"formal_name", "deed": [...], "mortgage": [...]} for
        brokers that publish property records.
    template_id: use this letter instead of choosing by jurisdiction.
    """
    t = templates()[template_id] if template_id else choose_template(jurisdiction, residence_state)
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
    """The letters, for an admin page or docs: id, title, law, languages,
    deadline and review status."""
    return [{
        "id": t["id"], "title": t.get("title", t["id"]), "law": t.get("law", ""),
        "languages": sorted(t["languages"]), "deadline_days": t.get("deadline_days", 0),
        "review_status": t.get("review_status", "draft"), "review_note": t.get("review_note", ""),
        "jurisdictions": t.get("jurisdictions", []),
    } for t in templates().values()]


def template_errors() -> list[str]:
    """Problems with the letter files (run by the test suite)."""
    errs = []
    placeholder = re.compile(r"\{(\w+)\}")
    for tid, t in templates().items():
        for k in ("title", "law", "default_language", "languages", "review_status", "review_note"):
            if k not in t:
                errs.append(f"{tid}: missing {k}")
        if t.get("default_language") not in t.get("languages", {}):
            errs.append(f"{tid}: no letter in its default language {t.get('default_language')}")
        if t.get("review_status") not in ("draft", REVIEWED):
            errs.append(f"{tid}: review_status must be draft or reviewed")
        for lang, v in t.get("languages", {}).items():
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
    want = set(parts()["en"])
    for lang, p in parts().items():
        if set(p) != want:
            errs.append(f"_parts.json {lang}: keys differ from en ({sorted(want ^ set(p))})")
        for k, text in p.items():
            if set(placeholder.findall(text)) != set(placeholder.findall(parts()["en"].get(k, ""))):
                errs.append(f"_parts.json {lang}.{k}: placeholders differ from en")
    return errs
