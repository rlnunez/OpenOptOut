"""
Privacy-request forms nobody wrote steps for: hosted ones (OneTrust,
TrustArc) and companies' own request forms found by core/privacy_finder.py.

These forms differ in markup but not in meaning: name, email, address, "what
do you want us to do" (delete / do not sell), "who are you" (the consumer),
and a certification box. So instead of selectors, the `autofill` step reads
every visible field's label and plans what to put in it (plan_autofill, pure
and tested), and refuses when it isn't sure:

  * it never fills ID numbers, SSNs, dates of birth, passwords or uploads;
  * it never ticks marketing / newsletter boxes;
  * a required field it can't place, a missing email box, or a request-type
    question with no delete / opt-out answer stops the flow, and the opt-out
    goes on the checklist with the page instead.
"""

import json
import re

from .broker_spec import BrokerSpec, Step

# Field matchers: (field, regex over label/name/id/placeholder/autocomplete).
_FIELDS = [
    ("country", re.compile(r"country", re.I), ("country", "country-name")),
    ("contact_email", re.compile(r"\be-?mail\b|^email$|email[\s_-]*address", re.I), ("email",)),
    ("first_name", re.compile(r"first[\s_-]*name|\bfname\b|given[\s_-]*name|^first$", re.I), ("given-name",)),
    ("last_name", re.compile(r"last[\s_-]*name|\blname\b|surname|family[\s_-]*name|^last$", re.I), ("family-name",)),
    ("full_name", re.compile(r"full[\s_-]*name|^name$|your[\s_-]*name|^\s*name\s*\*?\s*$", re.I), ("name",)),
    ("phone", re.compile(r"phone|mobile|telephone|\btel\b", re.I), ("tel",)),
    ("street", re.compile(r"street|address[\s_-]*(line)?[\s_-]*1|^address$|mailing[\s_-]*address|"
                          r"home[\s_-]*address|^\s*address\s*\*?\s*$", re.I), ("address-line1", "street-address")),
    ("city", re.compile(r"\bcity\b|town", re.I), ("address-level2",)),
    ("state", re.compile(r"\bstate\b|province|region", re.I), ("address-level1",)),
    ("zip", re.compile(r"\bzip\b|postal|post[\s_-]*code|zipcode", re.I), ("postal-code",)),
    ("listing_url", re.compile(r"\burl\b|link to|profile[\s_-]*(url|link)|listing", re.I), ("url",)),
]
NEVER = re.compile(r"ssn|social[\s_-]*security|driver|licen[cs]e|passport|tax[\s_-]*id|\bid[\s_-]*number|"
                   r"date[\s_-]*of[\s_-]*birth|\bdob\b|birth|password|account[\s_-]*number|card[\s_-]*number|"
                   r"security[\s_-]*code|captcha|search", re.I)
CONFIRM_EMAIL = re.compile(r"confirm|re-?enter|repeat|verify", re.I)
MESSAGE = re.compile(r"message|comment|details|description|additional|request|explain", re.I)

DELETE_OPT = re.compile(r"delet|remov|erase|opt[\s_-]*out|do[\s_-]*not[\s_-]*sell|don.?t[\s_-]*sell|"
                        r"do[\s_-]*not[\s_-]*share|limit[\s_-]*(the[\s_-]*)?use|stop[\s_-]*(selling|sharing)|suppress", re.I)
OTHER_REQ = re.compile(r"\baccess\b|right[\s_-]*to[\s_-]*know|copy|correct|rectif|portab|update|"
                       r"information[\s_-]*about|categories|appeal", re.I)
REQ_QUESTION = re.compile(r"request[\s_-]*type|type[\s_-]*of[\s_-]*request|what[\s_-]*(would|do)[\s_-]*you|"
                          r"right|request|choose|select[\s_-]*(the|your)", re.I)
SELF_OPT = re.compile(r"myself|my[\s_-]*own|i[\s_-]*am[\s_-]*(the[\s_-]*)?(consumer|data[\s_-]*subject|individual)|"
                      r"^\s*(consumer|individual|self|data subject)\s*$", re.I)
AGENT_OPT = re.compile(r"agent|on[\s_-]*behalf|authori[sz]ed|someone[\s_-]*else|parent|guardian", re.I)
WHO_QUESTION = re.compile(r"who|relationship|submitting|requestor|requester|are[\s_-]*you", re.I)
CERTIFY = re.compile(r"certif|declare|affirm|attest|under[\s_-]*penalty|i[\s_-]*(confirm|agree|acknowledge|understand)|"
                     r"accept[\s_-]*the[\s_-]*(terms|privacy)", re.I)
MARKETING = re.compile(r"newsletter|marketing|offers|promotion|subscribe|updates|news|special", re.I)
US = re.compile(r"^(us|usa|united[\s_-]*states( of america)?)$", re.I)


def _parts(d: dict) -> list:
    return [str(d.get(k) or "").strip() for k in ("label", "aria", "placeholder", "name", "id") if d.get(k)]


def _hay(d: dict) -> str:
    return " ".join(_parts(d))


def _matches(rx, d: dict) -> bool:
    """Does any one of the control's names (label, placeholder, name...) match?"""
    return any(rx.search(p) for p in _parts(d))


def _opt_text(o: dict) -> str:
    return f"{o.get('label') or ''} {o.get('value') or ''}".strip()


def plan_autofill(fields_desc: list, values: dict) -> dict:
    """
    Decide what goes where. `fields_desc` is what the page reports for each
    visible control: {i, tag, type, name, id, label, aria, placeholder,
    autocomplete, required, group, group_label, options:[{value,label}]}.
    Returns {"actions": [{"op": fill|select|check, "i", "value"}], "mapped": [...],
    "ok": bool, "why": str}.
    """
    actions, mapped, problems = [], [], []
    have = {k: v for k, v in values.items() if v}
    if "full_name" not in have and have.get("first_name"):
        have["full_name"] = " ".join(filter(None, [have.get("first_name"), have.get("last_name")]))
    has_first_last = any(re.search(r"first|given|fname", _hay(d), re.I) for d in fields_desc)
    used_email = False

    # Radio / checkbox groups.
    groups = {}
    for d in fields_desc:
        if d.get("type") in ("radio", "checkbox"):
            groups.setdefault(d.get("group") or d.get("name") or f"#{d['i']}", []).append(d)

    request_question_seen = False
    request_answered = False
    for gname, items in groups.items():
        glabel = items[0].get("group_label") or ""
        opts = [(d, f"{d.get('label') or ''} {d.get('aria') or ''} {d.get('value') or ''}") for d in items]
        is_radio = items[0].get("type") == "radio"
        deletes = [d for d, t in opts if DELETE_OPT.search(t) and not OTHER_REQ.search(t)]
        others = [d for d, t in opts if OTHER_REQ.search(t)]
        if deletes or (others and REQ_QUESTION.search(glabel)):
            request_question_seen = True
            if deletes:
                chosen = deletes[:1] if is_radio else deletes
                for d in chosen:
                    actions.append({"op": "check", "i": d["i"]})
                request_answered = True
            continue
        selfs = [d for d, t in opts if SELF_OPT.search(t) and not AGENT_OPT.search(t)]
        if selfs and (WHO_QUESTION.search(glabel) or any(AGENT_OPT.search(t) for _, t in opts)):
            actions.append({"op": "check", "i": selfs[0]["i"]})
            continue
        for d, t in opts:
            if d.get("type") != "checkbox":
                continue
            if MARKETING.search(t):
                continue            # never sign anyone up for anything
            if CERTIFY.search(t) or CERTIFY.search(glabel):
                actions.append({"op": "check", "i": d["i"]})
            elif d.get("required"):
                problems.append(f"a required box we don't understand: {t.strip()[:60]!r}")
        if is_radio and any(d.get("required") for d in items) and not any(a["i"] in [d["i"] for d in items] for a in actions):
            problems.append(f"a required question we can't answer: {glabel[:60]!r}")

    for d in fields_desc:
        t, tag = (d.get("type") or "").lower(), (d.get("tag") or "").lower()
        if t in ("radio", "checkbox", "hidden", "submit", "button", "image", "reset"):
            continue
        hay = _hay(d)
        ac = (d.get("autocomplete") or "").lower()
        if t in ("file", "password") or _matches(NEVER, d):
            if d.get("required"):
                problems.append(f"it asks for something we never fill in ({(d.get('label') or d.get('name') or t)[:40]})")
            continue
        if tag == "select":
            opts = d.get("options") or []
            choice = None
            if any(DELETE_OPT.search(_opt_text(o)) and not OTHER_REQ.search(_opt_text(o)) for o in opts) \
                    or (REQ_QUESTION.search(hay) and any(OTHER_REQ.search(_opt_text(o)) for o in opts)):
                request_question_seen = True
                choice = next((o for o in opts if DELETE_OPT.search(_opt_text(o)) and not OTHER_REQ.search(_opt_text(o))), None)
                request_answered = request_answered or choice is not None
            elif re.search(r"country", hay, re.I):
                choice = next((o for o in opts if US.match((o.get("label") or "").strip()) or US.match((o.get("value") or "").strip())), None)
            elif re.search(r"\bstate\b|province|region", hay, re.I) and have.get("state"):
                st, sn = have.get("state", "").lower(), have.get("state_name", "").lower()
                choice = next((o for o in opts if (o.get("value") or "").strip().lower() in (st, sn)
                               or (o.get("label") or "").strip().lower() in (st, sn)), None)
            elif WHO_QUESTION.search(hay):
                choice = next((o for o in opts if SELF_OPT.search(_opt_text(o)) and not AGENT_OPT.search(_opt_text(o))), None)
            if choice is not None:
                actions.append({"op": "select", "i": d["i"], "value": choice.get("value") or choice.get("label")})
                mapped.append(d.get("label") or d.get("name") or "select")
            elif d.get("required"):
                problems.append(f"a required choice we can't make: {(d.get('label') or d.get('name') or '')[:60]!r}")
            continue
        # Text-like inputs.
        field = None
        for name, rx, acs in _FIELDS:
            if ac in acs or _matches(rx, d):
                field = name
                break
        if field == "full_name" and has_first_last:
            field = None
        if field is None and tag == "textarea" and MESSAGE.search(hay):
            if have.get("request_text"):
                actions.append({"op": "fill", "i": d["i"], "value": have["request_text"]})
                mapped.append("message")
            continue
        if field == "country":
            actions.append({"op": "fill", "i": d["i"], "value": "United States"}); mapped.append("country")
            continue
        val = have.get(field) if field else None
        if field == "state" and val and len(val) == 2 and re.search(r"name|full", hay, re.I):
            val = have.get("state_name") or val
        if val:
            actions.append({"op": "fill", "i": d["i"], "value": val})
            mapped.append(field)
            used_email = used_email or field == "contact_email"
        elif d.get("required"):
            problems.append(f"a required field we can't fill: {(d.get('label') or d.get('name') or '')[:60]!r}")

    if "contact_email" not in mapped:
        problems.insert(0, "no box for an email address")
    if not any(f in mapped for f in ("first_name", "last_name", "full_name")):
        problems.append("no box for the person's name")
    if request_question_seen and not request_answered:
        problems.append("its request types don't include deletion or opting out")
    return {"actions": actions, "mapped": mapped, "ok": not problems,
            "why": "; ".join(problems)}


# ── Specs for found pages ─────────────────────────────────────────────────────

PLATFORM_NAMES = {"hosted_onetrust": "OneTrust", "hosted_trustarc": "TrustArc", "request_form": "its own"}


def spec_for_page(broker, page) -> BrokerSpec:
    """Opt-out steps for a privacy-request form the finder found."""
    import re as _re
    slug = _re.sub(r"[^a-zA-Z0-9_-]", "_", str(getattr(broker, "id", "") or broker.name)).strip("_") or "broker"
    steps = [
        Step(kind="navigate", url=page.url, timeout_ms=30000),
        Step(kind="wait", timeout_ms=2500),     # hosted forms render with script
        Step(kind="frame", selector="iframe[src*='onetrust'], iframe[src*='trustarc']", optional=True)
        if page.kind == "request_form" else None,
        Step(kind="autofill"),
        Step(kind="solve_captcha", selector="iframe[src*='recaptcha'], .h-captcha", optional=True),
        Step(kind="click_matching", selector="button, input[type=submit]", text="Submit"),
        Step(kind="wait", timeout_ms=3000),
        Step(kind="expect_success", text="received", optional=True, timeout_ms=10000),
    ]
    return BrokerSpec(
        broker_id=slug, name=broker.name, method="form", opt_out_url=page.url,
        steps=[s for s in steps if s is not None],
        requires=["email_confirmation"] if page.kind.startswith("hosted_") else [],
        source=f"Found on {broker.name}'s website by the privacy-page finder ({page.kind}).",
        notes=f"{HOSTED_NOTE} ({page.kind})",
    )


HOSTED_NOTE = "Privacy-request form found on the broker's website"


def is_found_form(spec) -> bool:
    return (getattr(spec, "notes", "") or "").startswith(HOSTED_NOTE)


def request_text(fields: dict) -> str:
    """Words for a form's free-text box: what we're asking, in plain terms."""
    name = fields.get("full_name") or " ".join(filter(None, [fields.get("first_name"), fields.get("last_name")]))
    return (f"Please delete all personal information you hold about me ({name}), stop selling or sharing it, "
            f"and remove any profile or listing about me. Contact me at {fields.get('contact_email') or 'this email address'}.")


def autofill_values(fields: dict) -> str:
    """The values an autofill step may use, as the step's JSON payload."""
    keep = ("first_name", "last_name", "full_name", "contact_email", "phone", "street", "city",
            "state", "state_name", "zip", "listing_url")
    vals = {k: fields.get(k) for k in keep if fields.get(k)}
    if vals.get("contact_email"):
        vals["request_text"] = request_text(fields)
    return json.dumps(vals)
