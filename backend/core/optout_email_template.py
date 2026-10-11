"""
Parent-company opt-out email composition.

Builds the strong opt-out email at the heart of the email-first strategy: one
message to a parent company demanding removal from that company AND all of its
listed child/affiliated sites, including the full identifier list needed to
match the person's records.

Design choices per project direction:
  - Include the FULL identifier list (names + variants, emails, phones,
    addresses) so the broker can actually locate every record.
  - For date of birth, provide AGE or an age RANGE, never the exact DOB — enough
    to disambiguate records without handing the broker more sensitive data than
    necessary.
  - Enumerate the known child sites explicitly ("remove from all of the
    following properties: ..."), which is what makes one email clear a whole
    family of listings.
  - Firm, rights-asserting wording. NOT legal advice and not a lawyer's letter —
    but strong, clear language that cites the applicable rights where known and
    makes an unambiguous demand. The wording lives in core/legal_templates/,
    one letter per law (CCPA, general US, GDPR, UK GDPR, LGPD, PIPEDA), each
    marked as a draft until a lawyer has reviewed it.
  - The letter is chosen by the parent company's jurisdiction and written in
    its legal language, never in the family's interface language.

The composer is pure/text-only and takes plain data, so it's fully testable
without a database or mail server. The email-method engine fills the To/subject/
body from what this returns.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Identifiers:
    """The person's identifiers to include for record matching. All optional;
    the template includes only what's provided."""
    full_name: str = ""
    name_variants: list = field(default_factory=list)   # maiden, nicknames, misspellings
    emails: list = field(default_factory=list)
    phones: list = field(default_factory=list)
    addresses: list = field(default_factory=list)       # current + prior
    age: Optional[int] = None
    age_range: str = ""                                 # e.g. "40-45" if exact age unknown
    city_state: str = ""                                # broad locale hint


@dataclass
class ComposedEmail:
    to: str
    cc: list
    subject: str
    body: str
    language: str = "en"          # the language the letter is written in
    template_id: str = ""         # which letter (core/legal_templates/<id>.json)
    review_status: str = "draft"  # "draft" until a lawyer has reviewed the letter


def _normalize_sites(child_sites):
    """Accept child_sites as plain names OR dicts/tuples carrying a discovered
    profile URL. Returns a list of (name, url) with url possibly ''."""
    out = []
    for s in (child_sites or []):
        if isinstance(s, dict):
            name = str(s.get("name", "")).strip()
            url = str(s.get("url", "")).strip()
        elif isinstance(s, (list, tuple)):
            name = str(s[0]).strip() if s else ""
            url = str(s[1]).strip() if len(s) > 1 and s[1] else ""
        else:
            name, url = str(s).strip(), ""
        if name or url:
            out.append((name, url))
    return out


def compose_optout_email(
    ids: Identifiers,
    parent_name: str,
    to_address: str,
    child_sites: list,
    cc: Optional[list] = None,
    locale: str = "",
    state: str = "",
    request_key: str = "",
    jurisdiction: str = "US",
) -> ComposedEmail:
    """
    Compose the opt-out email for one parent company.

    child_sites: known front-sites tied to the parent. Each entry may be a plain
        name string, or a dict/tuple carrying a discovered profile URL
        ({"name": "Site", "url": "https://.../profile/123"} or ("Site", url)).
        When a URL is present (found automatically by discovery), it is cited so
        the broker can locate the exact record — much stronger than name-matching.
    jurisdiction: where the parent company is ("US", "FR", "BR", ...). Picks the
        law the letter cites (core/legal_letters.py).
    locale: the parent's LEGAL language — the language its privacy team must
        be written to in — not the family's interface language. Empty means the
        usual language for the jurisdiction. A language with no letter for that
        law falls back to the letter's own language, with no note added.
    state: the requester's US state (2-letter). For a US parent it decides
        between the CCPA letter (California) and the general US letter.
    request_key: optional UUID tracking key. When provided, embedded in the
        subject line and body so incoming replies can be matched automatically.
    """
    from .legal_letters import compose_letter
    letter = compose_letter(
        ids, parent_name, jurisdiction=jurisdiction or "US", legal_language=locale or "",
        residence_state=state, sites=_normalize_sites(child_sites), request_key=request_key)
    return ComposedEmail(
        to=to_address,
        cc=list(cc or []),
        subject=letter.subject,
        body=letter.body,
        language=letter.language,
        template_id=letter.template_id,
        review_status=letter.review_status,
    )
