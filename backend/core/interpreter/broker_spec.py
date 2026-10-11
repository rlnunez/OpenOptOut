"""
Broker description schema.

This is the heart of the "broker-as-add-on" reframe (roadmap item 2/3): a broker
becomes a *declarative description* of how its opt-out works, not broker-specific
code baked into the core. The core reads one of these specs and executes it; it
knows nothing about any particular broker.

A BrokerSpec answers: what method (form / email / manual), and for a form, what
ordered steps to take and which member fields go in which inputs; for an email,
what template and locale. Nothing here is executable — it is pure data that the
compiler (compiler.py) turns into a Job of primitive steps, which an executor
then runs. Keeping the spec declarative is what makes broker add-ons safe to
share, diff, and validate without running arbitrary code.

Versioned via `spec_version` so the format can evolve without breaking old
add-ons.
"""

from dataclasses import dataclass, field, fields
from typing import Optional, Any

SPEC_VERSION = "1.0"

# The member fields an add-on may reference. Kept as a fixed vocabulary so a
# spec can be validated without a live member, and so a spec can never ask for
# a field the system doesn't recognize. These map to values the engine resolves
# from a FamilyMember at execution time.
KNOWN_FIELDS = {
    "first_name", "last_name", "full_name", "formal_name",
    "email", "phone", "address", "city", "state", "zip",
    "age", "dob", "relatives",
    # Age and birth date in the shapes forms ask for (see core/age.py).
    # `dob` is MM/DD/YYYY; the rest exist only when a date of birth is saved,
    # except `age_range` ("40-49") and `birth_year`, which an age alone gives.
    "dob_iso", "birth_month", "birth_day", "age_range",
    # Where the broker should send its reply/confirmation for THIS submission:
    # a unique +address on the member's inbox when it supports one. Use this,
    # not `email`, for "email address for confirmation" fields. `email` is an
    # address the member wants removed.
    "contact_email",
    # The web address of the member's own listing on this broker, when someone
    # found it (discovery or "Find your listings"). Several brokers' forms ask for it.
    "listing_url",
    # Derived formats some forms insist on.
    "street",         # street line of the address only ("12 Oak St Apt 4")
    "state_name",     # full state name ("Texas") for dropdowns that list names
    "birth_year",     # from the member's age (approximate: ±1 year)
    "phone_digits",   # 10 digits, no punctuation ("5125550100")
    "phone_e164",     # with country code ("+15125550100"), for caller-ID apps
    "phone_dashed",   # "512-555-0100"
    "all_phones",     # every saved number, comma-separated (for instructions)
    "all_emails",     # every saved email address, comma-separated (for instructions)
}

# What a broker files its records under. Most file people by name. Phone
# lookup and caller-ID sites file them by phone number, and email-lookup and
# business contact sites by email address; those get one opt-out per saved
# number or address instead of the name/address combinations.
LOOKUP_KEYS = ("", "name", "phone", "email")

# Primitive step kinds an add-on can request in a form flow. The compiler maps
# these to executable job steps; the executor knows how to perform each. This
# small, closed vocabulary is deliberately not Turing-complete — an add-on
# describes a flow, it does not run logic.
STEP_KINDS = {
    "navigate",       # go to a URL
    "fill",           # put a member field (or literal) into a form input
    "type",           # like fill, but key by key, for React/MUI inputs that ignore fill
    "select",         # choose an option in a <select>
    "check",          # tick a checkbox / radio
    "click",          # click a button/element
    "click_matching", # click element matching text or field value
    "press",          # press a keyboard key (e.g. Enter, Tab)
    "frame",          # switch context to an iframe (or "main" / empty to exit)
    "scroll",         # scroll element into view or scroll page
    "wait_for",       # wait until a selector appears
    "wait",           # fixed delay (ms)
    "submit",         # submit the form
    "expect_success", # assert a success signal (selector/text) to confirm the opt-out
    "solve_captcha",  # hand off to the CAPTCHA layer (roadmap item 4)
    "autofill",       # fill a privacy-request form by its labels (hosted_forms.plan_autofill);
                      # stops for a person when unsure
    "pick_listing",   # on a page of search results, pick this person's listing and go to it.
                      # `selector` = each result's link (else links matching the spec's
                      # listing_pattern). Results showing only the name follow the
                      # unclear-matches setting (core/match_policy.py).
    "pause_for_human",# stop here; a person finishes the rest (pick a listing,
                      # answer a phone call). With a selector, pause only if it
                      # is on the page. `text` is the plain-language instruction.
}

# Privacy laws a spec may cite in `legal_basis`. Used for deadline tracking and
# for choosing which statute an opt-out request cites.
LEGAL_BASES = {
    "ccpa", "cpra",           # California
    "gdpr", "uk_gdpr",        # EU / UK
    "vcdpa", "cpa", "ctdpa", "ucpa", "tdpsa", "ocpa", "mcdpa",  # other US states
    "pipeda",                 # Canada
}

# What a person may have to do or provide for this broker. These become
# checklist labels, so a family can see up front what each opt-out will ask of
# them, and they let the engine plan around limits.
REQUIREMENTS = {
    "email_confirmation",   # broker emails a link that must be clicked
    "own_inbox_confirmation",  # the link goes to the address being removed (a work
                            # email, say), so whoever reads that inbox clicks it
    "sms_code",             # broker texts a code to the number being removed
    "listing_url",          # the URL of the person's own listing is required
    "listing_selection",    # a person must pick their listing from results
    "phone_call",           # broker calls with a code (BADBOOL 📞)
    "government_id",        # ID upload (BADBOOL 🎫) — redact the number
    "account",              # an account must be created
    "payment",              # access or removal costs money (BADBOOL 💰)
    "postal_mail",          # request must be mailed or faxed
}



def _require_types(obj, where: str) -> None:
    """Raise ValueError if a field loaded from an untrusted spec has the wrong JSON type.

    Specs arrive inside uploaded add-ons and imported catalogues. Without this,
    e.g. `"broker_id": 5` made validate() crash with AttributeError (a 500 on
    upload) instead of returning a readable error. from_dict()'s callers turn
    the ValueError into a validation message.
    """
    for f in fields(obj):
        v = getattr(obj, f.name)
        t = f.type
        if t is str and not isinstance(v, str):
            raise ValueError(f"{where}.{f.name} must be a string, not {type(v).__name__}")
        if t is int and (isinstance(v, bool) or not isinstance(v, int)):
            raise ValueError(f"{where}.{f.name} must be a whole number, not {type(v).__name__}")
        if t is bool and not isinstance(v, bool):
            raise ValueError(f"{where}.{f.name} must be true or false, not {type(v).__name__}")
        if t == list[str] and not (isinstance(v, list) and all(isinstance(x, str) for x in v)):
            raise ValueError(f"{where}.{f.name} must be a list of strings")

@dataclass
class Step:
    """One primitive action in a form flow."""
    kind: str
    selector: str = ""          # CSS/xpath target, where applicable
    field: str = ""             # a KNOWN_FIELDS name, for `fill` or `click_matching`
    value: str = ""             # a literal value (for fill/select/press when not a field)
    url: str = ""               # for `navigate`
    text: str = ""              # for expect_success / click_matching (text to look for)
    timeout_ms: int = 8000
    optional: bool = False      # if True, failure of this step doesn't fail the flow

    def validate(self) -> list[str]:
        errs = []
        if self.kind not in STEP_KINDS:
            errs.append(f"unknown step kind: {self.kind}")
            return errs
        if self.kind == "navigate" and not self.url:
            errs.append("navigate step requires a url")
        if self.kind == "navigate" and self.url:
            import re as _re
            for name in _re.findall(r"\{([a-z_]+)\}", self.url):
                if name not in KNOWN_FIELDS:
                    errs.append(f"navigate url references unknown field: {{{name}}}")
        if self.kind in ("fill", "type", "select") and not (self.field or self.value):
            errs.append(f"{self.kind} step requires a field or a value")
        if self.kind in ("fill", "type", "select") and self.field and self.field not in KNOWN_FIELDS:
            errs.append(f"{self.kind} references unknown field: {self.field}")
        if self.kind == "click_matching" and self.field and self.field not in KNOWN_FIELDS:
            errs.append(f"click_matching references unknown field: {self.field}")
        if self.kind == "click_matching" and not (self.selector or self.text or self.field):
            errs.append("click_matching requires a selector, text, or field")
        if self.kind == "press" and not self.value:
            errs.append("press requires a value (e.g. 'Enter', 'Tab')")
        if self.kind in ("fill", "type", "select", "check", "click", "wait_for") and not self.selector:
            errs.append(f"{self.kind} step requires a selector")
        if self.kind == "expect_success" and not (self.selector or self.text):
            errs.append("expect_success requires a selector or text to look for")
        if self.kind == "pause_for_human" and not self.text:
            errs.append("pause_for_human requires text: the instruction shown to the person")
        if self.timeout_ms < 0 or self.timeout_ms > 120_000:
            errs.append("timeout_ms out of range (0–120000)")
        return errs


@dataclass
class EmailSpec:
    """How to send an opt-out email for an email-method broker."""
    to_address: str = ""            # broker's opt-out inbox
    subject_template: str = ""      # may contain {full_name} etc.
    body_template: str = ""         # may contain {full_name}, {address}, ...
    locale: str = "en"              # language the email must be in
    require_fields: list[str] = field(default_factory=list)  # member fields the template needs

    def validate(self) -> list[str]:
        errs = []
        if not self.to_address or "@" not in self.to_address:
            errs.append("email to_address is missing or invalid")
        if not self.subject_template:
            errs.append("email subject_template is required")
        if not self.body_template:
            errs.append("email body_template is required")
        for f in self.require_fields:
            if f not in KNOWN_FIELDS:
                errs.append(f"email require_fields references unknown field: {f}")
        return errs


@dataclass
class BrokerSpec:
    """
    Declarative description of one broker's opt-out. This is what a broker
    add-on ships. It is data only — the compiler turns it into an executable Job.
    """
    broker_id: str                       # stable slug, e.g. "spokeo"
    name: str
    method: str                          # "form" | "email" | "manual"
    spec_version: str = SPEC_VERSION
    opt_out_url: str = ""
    # For form method:
    steps: list[Step] = field(default_factory=list)
    # For email method:
    email: Optional[EmailSpec] = None
    # Declared success signal for the whole opt-out (a form may also use
    # expect_success steps; this is the overall confirmation).
    success_selector: str = ""
    success_text: str = ""
    # Free-form notes for humans (never executed).
    notes: str = ""
    # For method "manual": what the person does, in plain words. May name
    # their details: {full_name}, {contact_email} (the address to give the
    # broker, so its reply and any confirmation link are handled for them),
    # {listing_url}, {city}, {state}, ...
    instructions: str = ""

    # ── Metadata (all optional; older specs without these stay valid) ──────
    # Which privacy laws apply, and how many days the broker has to respond.
    # Together these give a "response due" date for each request.
    legal_basis: list[str] = field(default_factory=list)
    statutory_response_days: int = 0          # 0 = unknown
    # Where a member's listing can be searched, for checking removal later.
    # `{first_name}`, `{last_name}`, `{state}`, `{city}` are filled in.
    # `listing_pattern` is a regular expression a listing page or result
    # link matches; together they let verification say "still listed".
    search_url: str = ""
    listing_pattern: str = ""
    # The broker accepts only one opt-out per email address, so a second
    # listing for the same person needs a different address.
    one_optout_per_email: bool = False
    # False when the broker's form refuses addresses with a "+" in them; the
    # engine then uses the inbox's plain address for contact_email. The engine
    # also learns this on its own when a form rejects a +address.
    accepts_plus_addresses: bool = True
    # What the person may have to do (see REQUIREMENTS).
    requires: list[str] = field(default_factory=list)
    # "phone" or "email" for sites that list people by that detail (see LOOKUP_KEYS).
    lookup_by: str = ""
    # Provenance. Every spec records where its opt-out details came from and
    # the date someone last confirmed the flow works against the live site
    # (YYYY-MM-DD; empty means "never confirmed by us").
    source: str = ""
    last_verified: str = ""

    def validate(self) -> list[str]:
        """Return a list of validation errors; empty means the spec is well-formed."""
        errs = []
        if not self.broker_id or not self.broker_id.replace("-", "").replace("_", "").isalnum():
            errs.append("broker_id must be a non-empty alphanumeric slug")
        if not self.name:
            errs.append("name is required")
        if self.method not in ("form", "email", "manual"):
            errs.append(f"unknown method: {self.method}")
        if self.lookup_by not in LOOKUP_KEYS:
            errs.append(f"lookup_by must be one of {[k for k in LOOKUP_KEYS if k]}")
        if self.spec_version != SPEC_VERSION:
            errs.append(f"unsupported spec_version {self.spec_version} (this core supports {SPEC_VERSION})")

        if self.method == "form":
            if not self.steps:
                errs.append("form method requires at least one step")
            if not self.opt_out_url and not any(s.kind == "navigate" for s in self.steps):
                errs.append("form method needs opt_out_url or a navigate step")
            for i, s in enumerate(self.steps):
                for e in s.validate():
                    errs.append(f"step[{i}] ({s.kind}): {e}")
        elif self.method == "email":
            if not self.email:
                errs.append("email method requires an email spec")
            else:
                errs.extend(f"email: {e}" for e in self.email.validate())
        # manual method needs nothing more — it just queues for a human.

        for b in self.legal_basis:
            if b.lower() not in LEGAL_BASES:
                errs.append(f"unknown legal_basis: {b} (known: {', '.join(sorted(LEGAL_BASES))})")
        if self.statutory_response_days < 0 or self.statutory_response_days > 365:
            errs.append("statutory_response_days must be between 0 and 365")
        for r in self.requires:
            if r not in REQUIREMENTS:
                errs.append(f"unknown requires entry: {r} (known: {', '.join(sorted(REQUIREMENTS))})")
        if self.search_url and not self.search_url.startswith("https://"):
            errs.append("search_url must start with https://")
        if self.listing_pattern:
            import re
            try:
                re.compile(self.listing_pattern)
            except re.error as e:
                errs.append(f"listing_pattern is not a valid regular expression: {e}")
            if not self.search_url:
                errs.append("listing_pattern needs a search_url to check against")
        if self.last_verified:
            from datetime import date
            try:
                date.fromisoformat(self.last_verified)
            except ValueError:
                errs.append("last_verified must be a date written YYYY-MM-DD")
        return errs

    def response_due(self, sent_at):
        """
        When the broker's legal response window closes for a request sent at
        `sent_at` (a date or datetime), or None if the spec doesn't say.
        """
        if not self.statutory_response_days or sent_at is None:
            return None
        from datetime import timedelta
        return sent_at + timedelta(days=self.statutory_response_days)

    def can_verify(self) -> bool:
        """True if removal can be checked automatically by searching the broker."""
        return bool(self.search_url and self.listing_pattern)

    # ---- (de)serialization ----

    @classmethod
    def from_dict(cls, d: dict) -> "BrokerSpec":
        raw_steps = d.get("steps", [])
        if not isinstance(raw_steps, list) or not all(isinstance(s, dict) for s in raw_steps):
            raise ValueError("steps must be a list of objects")
        steps = [Step(**{k: v for k, v in s.items() if k in Step.__dataclass_fields__})
                 for s in raw_steps]
        for i, s in enumerate(steps):
            _require_types(s, f"steps[{i}]")
        email = None
        if d.get("email"):
            ed = d["email"]
            if not isinstance(ed, dict):
                raise ValueError("email must be an object")
            email = EmailSpec(**{k: v for k, v in ed.items() if k in EmailSpec.__dataclass_fields__})
            _require_types(email, "email")
        spec = cls(
            broker_id=d.get("broker_id", ""),
            name=d.get("name", ""),
            method=d.get("method", ""),
            spec_version=d.get("spec_version", SPEC_VERSION),
            opt_out_url=d.get("opt_out_url", ""),
            steps=steps,
            email=email,
            success_selector=d.get("success_selector", ""),
            success_text=d.get("success_text", ""),
            notes=d.get("notes", ""),
            instructions=d.get("instructions", "") or "",
            legal_basis=[str(x).lower() if isinstance(x, str) else x
                         for x in d.get("legal_basis", [])] if isinstance(d.get("legal_basis", []), list)
                        else d.get("legal_basis"),
            statutory_response_days=d.get("statutory_response_days", 0),
            search_url=d.get("search_url", ""),
            listing_pattern=d.get("listing_pattern", ""),
            one_optout_per_email=d.get("one_optout_per_email", False),
            accepts_plus_addresses=d.get("accepts_plus_addresses", True),
            requires=d.get("requires", []),
            lookup_by=d.get("lookup_by", "") or "",
            source=d.get("source", ""),
            last_verified=d.get("last_verified", "") or "",
        )
        _require_types(spec, "spec")
        return spec

    def to_dict(self) -> dict:
        out: dict[str, Any] = {
            "broker_id": self.broker_id, "name": self.name, "method": self.method,
            "spec_version": self.spec_version, "opt_out_url": self.opt_out_url,
            "success_selector": self.success_selector, "success_text": self.success_text,
            "notes": self.notes,
        }
        if self.instructions:
            out["instructions"] = self.instructions
        for k in ("legal_basis", "statutory_response_days", "search_url", "listing_pattern",
                  "one_optout_per_email", "accepts_plus_addresses", "requires", "lookup_by",
                  "source", "last_verified"):
            v = getattr(self, k)
            if v not in ("", 0, False, []):
                out[k] = v
        if self.method == "form":
            out["steps"] = [
                {k: getattr(s, k) for k in Step.__dataclass_fields__ if getattr(s, k) not in ("", 0, False)}
                for s in self.steps
            ]
        if self.email:
            out["email"] = {k: getattr(self.email, k) for k in EmailSpec.__dataclass_fields__
                            if getattr(self.email, k) not in ("", [])}
        return out
