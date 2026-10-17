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

import re
from dataclasses import dataclass, field, fields
from typing import Optional, Any
from urllib.parse import urlparse

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
    "lgpd",                   # Brazil
}

# Where a broker is, for choosing which law its opt-out letter cites and the
# language the letter is written in. "US", "EU", "EEA", "UK", or an ISO 3166
# country code, optionally with a region ("US-CA", "CA-QC").
JURISDICTION = re.compile(r"^(EU|EEA|UK|[A-Z]{2}(-[A-Z0-9]{1,3})?)$")
# A language code for a letter: "en", "fr", "pt-BR".
LANGUAGE_CODE = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$")

# The jurisdiction a spec is taken to have when it names a law but no
# jurisdiction. US state laws all mean "US"; the letter for a US broker then
# depends on where the person lives (core/legal_letters.py).
BASIS_JURISDICTION = {
    "gdpr": "EU", "uk_gdpr": "UK", "lgpd": "BR", "pipeda": "CA",
    "ccpa": "US", "cpra": "US", "vcdpa": "US", "cpa": "US", "ctdpa": "US",
    "ucpa": "US", "tdpsa": "US", "ocpa": "US", "mcdpa": "US",
}
# The language a broker's legal correspondence is in when the spec doesn't
# say. Anything not listed is English.
JURISDICTION_LANGUAGE = {
    "BR": "pt-BR", "FR": "fr", "BE": "fr", "LU": "fr", "MC": "fr", "CA-QC": "fr",
    "DE": "de", "AT": "de", "LI": "de", "ES": "es", "IT": "it", "NL": "nl", "PT": "pt",
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



def _keyed_text(v, path: str, keys: dict):
    """Text written as {"$t": key, "default": text} -> text, remembering the key."""
    if isinstance(v, dict) and "$t" in v:
        k, default = v.get("$t"), v.get("default", "")
        if not isinstance(k, str) or not k.strip() or not isinstance(default, str) or not default:
            raise ValueError(f'{path}: {{"$t": key, "default": text}} needs a text key and the default text')
        keys[path] = k.strip()
        return default
    return v


# A letter id (core/legal_letters): "ccpa", "gdpr", or one from a letters plugin.
LETTER_ID = re.compile(r"[a-z][a-z0-9_-]{1,40}")
# A bare domain for `covers`: lower case, no scheme, path or "www.".
DOMAIN = re.compile(r"(?!www\.)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}")

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
        # Both or neither: with neither, the broker gets the legal letter for
        # its jurisdiction (core/legal_letters.py), which is usually better.
        if bool(self.subject_template) != bool(self.body_template):
            errs.append("email needs both subject_template and body_template, or neither (to use the legal letter)")
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
    # Where the broker is and the language its legal team reads. They pick the
    # opt-out letter (CCPA, GDPR, LGPD, ...) and its language — never the
    # language a family uses the app in. Both may be left out: see
    # effective_jurisdiction() and effective_legal_language().
    jurisdiction: str = ""
    legal_language: str = ""
    # The broker's own opt-out letter per language: {"fr": {"subject", "body"}}.
    # The one in the legal language is used before the built-in letter.
    email_templates: dict = field(default_factory=dict)
    # Which opt-out letter this broker gets, by letter id ("ccpa", or one from
    # a letters plugin), when the automatic choice isn't right. An admin's
    # choice on the Opt-out letters page still wins.
    letter: str = ""
    # Other sites this one opt-out also removes the person from, by domain
    # ("truthfinder.com"), because the same company runs them and says one
    # request reaches all of them. Shown as "also covers N sites" (see
    # core/coverage.py, which adds the parent-company catalog's families).
    covers: list[str] = field(default_factory=list)

    # Set by whatever loaded the spec (not part of spec.json): the plugin it
    # came from, for looking up its translations, and the keys a spec gave its
    # translatable text with {"$t": key, "default": text}.
    plugin_id = ""
    plugin_dir = ""
    text_keys = None   # {key path: translation key}; a class attribute, not a field

    def effective_jurisdiction(self) -> str:
        """The spec's jurisdiction, or one implied by the first law it cites
        that has one, or "US" (where nearly every listed broker is)."""
        if self.jurisdiction:
            return self.jurisdiction.upper()
        for b in self.legal_basis:
            j = BASIS_JURISDICTION.get(str(b).lower())
            if j:
                return j
        return "US"

    def effective_legal_language(self) -> str:
        """The language opt-out letters to this broker are written in."""
        if self.legal_language:
            return self.legal_language
        if self.email and self.email.locale and self.email.locale != "en":
            return self.email.locale
        j = self.effective_jurisdiction()
        return JURISDICTION_LANGUAGE.get(j) or JURISDICTION_LANGUAGE.get(j.split("-")[0]) or "en"

    def letter_template(self, language: str = "") -> Optional[dict]:
        """This broker's own {"subject", "body"} for `language` (default: its
        legal language), matching "pt-BR" to "pt" if needed, or None."""
        want = (language or self.effective_legal_language()).lower()
        by_lang = {k.lower(): v for k, v in (self.email_templates or {}).items()}
        for code in (want, want.split("-")[0]):
            if code in by_lang:
                return by_lang[code]
        return None

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

        if self.opt_out_url:
            if not self.opt_out_url.startswith("https://"):
                errs.append("opt_out_url must start with https://")
            if "{" in self.opt_out_url:
                errs.append("opt_out_url must not contain placeholders")

        if self.method == "form":
            if not self.steps:
                errs.append("form method requires at least one step")
            if not self.opt_out_url and not any(s.kind == "navigate" for s in self.steps):
                errs.append("form method needs opt_out_url or a navigate step")
            for i, s in enumerate(self.steps):
                for e in s.validate():
                    errs.append(f"step[{i}] ({s.kind}): {e}")

            # Verify that navigate steps stay on the broker's site, declared covers, or a privacy platform
            try:
                from ..listing_finder import registrable_domain
                from ..privacy_finder import hosted_kind
            except (ImportError, ValueError):
                try:
                    from core.listing_finder import registrable_domain
                    from core.privacy_finder import hosted_kind
                except (ImportError, ValueError):
                    from app.core.listing_finder import registrable_domain
                    from app.core.privacy_finder import hosted_kind

            roots = set()
            for u in (self.opt_out_url, self.search_url):
                if u:
                    try:
                        h = (urlparse(u).hostname or "").lower()
                        if h:
                            roots.add(registrable_domain(h))
                    except Exception:
                        pass
            for d in self.covers:
                if d:
                    try:
                        roots.add(registrable_domain(d.lower()))
                    except Exception:
                        pass

            if not roots and self.steps:
                first_nav = next((s for s in self.steps if s.kind == "navigate" and s.url), None)
                if first_nav:
                    try:
                        fh = (urlparse(first_nav.url).hostname or "").lower()
                        if fh:
                            roots.add(registrable_domain(fh))
                    except Exception:
                        pass

            for i, s in enumerate(self.steps):
                if s.kind == "navigate" and s.url:
                    if not s.url.startswith("https://"):
                        errs.append(f"step[{i}] (navigate): url must start with https://")
                    else:
                        try:
                            nh = (urlparse(s.url).hostname or "").lower()
                            n_root = registrable_domain(nh) if nh else ""
                            if not (n_root in roots or hosted_kind(s.url)):
                                errs.append(
                                    f"step[{i}] (navigate): goes to {nh or s.url}, which isn't the broker's site or a privacy-request platform"
                                )
                        except Exception as ex:
                            errs.append(f"step[{i}] (navigate): invalid url: {ex}")
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
        if self.jurisdiction and not JURISDICTION.match(self.jurisdiction):
            errs.append("jurisdiction must be US, EU, EEA, UK or a country code like FR or US-CA")
        if self.legal_language and not LANGUAGE_CODE.match(self.legal_language):
            errs.append("legal_language must be a language code like en, fr or pt-BR")
        if not isinstance(self.email_templates, dict):
            errs.append("email_templates must be an object of language → {subject, body}")
        else:
            for code, t in self.email_templates.items():
                if not isinstance(code, str) or not LANGUAGE_CODE.match(code):
                    errs.append(f"email_templates: '{code}' isn't a language code")
                elif not isinstance(t, dict) or not isinstance(t.get("subject"), str) \
                        or not isinstance(t.get("body"), str) or not t.get("subject") or not t.get("body"):
                    errs.append(f"email_templates.{code} needs a subject and a body")
        if self.letter and not LETTER_ID.fullmatch(str(self.letter)):
            errs.append("letter must be a letter id like ccpa or gdpr")
        for d in self.covers:
            if not isinstance(d, str) or not DOMAIN.fullmatch(d):
                errs.append(f"covers: '{d}' isn't a bare domain like truthfinder.com")
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
        text_keys: dict = {}
        steps = [Step(**{k: (_keyed_text(v, f"steps.{i}.text", text_keys) if k == "text" else v)
                         for k, v in s.items() if k in Step.__dataclass_fields__})
                 for i, s in enumerate(raw_steps)]
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
            instructions=_keyed_text(d.get("instructions", ""), "instructions", text_keys) or "",
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
            jurisdiction=(d.get("jurisdiction", "") or "").upper() if isinstance(d.get("jurisdiction", ""), str)
                         else d.get("jurisdiction"),
            legal_language=d.get("legal_language", "") or "",
            email_templates=d.get("email_templates", {}) or {},
            letter=d.get("letter", "") or "",
            covers=d.get("covers", []) or [],
        )
        _require_types(spec, "spec")
        spec.text_keys = text_keys
        return spec

    def to_dict(self) -> dict:
        out: dict[str, Any] = {
            "broker_id": self.broker_id, "name": self.name, "method": self.method,
            "spec_version": self.spec_version, "opt_out_url": self.opt_out_url,
            "success_selector": self.success_selector, "success_text": self.success_text,
            "notes": self.notes,
        }
        keys = self.text_keys or {}

        def keyed(path, text):
            return {"$t": keys[path], "default": text} if path in keys else text
        if self.instructions:
            out["instructions"] = keyed("instructions", self.instructions)
        for k in ("legal_basis", "statutory_response_days", "search_url", "listing_pattern",
                  "one_optout_per_email", "accepts_plus_addresses", "requires", "lookup_by",
                  "source", "last_verified", "jurisdiction", "legal_language", "email_templates",
                  "letter", "covers"):
            v = getattr(self, k)
            if v not in ("", 0, False, [], {}):
                out[k] = v
        if self.method == "form":
            out["steps"] = [
                {k: (keyed(f"steps.{i}.text", getattr(s, k)) if k == "text" else getattr(s, k))
                 for k in Step.__dataclass_fields__ if getattr(s, k) not in ("", 0, False)}
                for i, s in enumerate(self.steps)
            ]
        if self.email:
            out["email"] = {k: getattr(self.email, k) for k in EmailSpec.__dataclass_fields__
                            if getattr(self.email, k) not in ("", [])}
        return out
