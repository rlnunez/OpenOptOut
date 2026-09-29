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
    makes an unambiguous demand. Wording is a starting point meant to be
    reviewed and strengthened by someone with legal expertise (see the note at
    the bottom of the composed email and docs).

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


def _age_line(ids: Identifiers) -> str:
    if ids.age:
        # Give a small range around the age rather than a precise DOB.
        return f"Approximate age: {ids.age} (±1 year)"
    if ids.age_range:
        return f"Approximate age range: {ids.age_range}"
    return ""


def _bullet_list(label: str, items: list) -> str:
    items = [str(i).strip() for i in items if str(i).strip()]
    if not items:
        return ""
    lines = "\n".join(f"  - {i}" for i in items)
    return f"{label}:\n{lines}\n"


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
    locale: str = "en",
    state: str = "",
    request_key: str = "",
) -> ComposedEmail:
    """
    Compose the opt-out email for one parent company.

    child_sites: known front-sites tied to the parent. Each entry may be a plain
        name string, or a dict/tuple carrying a discovered profile URL
        ({"name": "Site", "url": "https://.../profile/123"} or ("Site", url)).
        When a URL is present (found automatically by discovery), it is cited so
        the broker can locate the exact record — much stronger than name-matching.
    state: the requester's US state (2-letter), used to name the applicable law.
    request_key: optional UUID tracking key. When provided, embedded in the
        subject line and body so incoming replies can be matched automatically.

    locale is accepted for future localization; only 'en' is templated here.
    """
    key_tag = f" [{request_key}]" if request_key else ""
    subject = f"Data removal request — {ids.full_name or 'record removal'}{key_tag}"

    # Identifier block
    id_block = ""
    if ids.full_name:
        id_block += f"Full name: {ids.full_name}\n"
    id_block += _bullet_list("Name variants / other names", ids.name_variants)
    id_block += _bullet_list("Email addresses", ids.emails)
    id_block += _bullet_list("Phone numbers", ids.phones)
    id_block += _bullet_list("Addresses (current and prior)", ids.addresses)
    age = _age_line(ids)
    if age:
        id_block += age + "\n"
    if ids.city_state:
        id_block += f"General location: {ids.city_state}\n"
    if id_block:
        id_block += "\n"

    # Child-site enumeration, with discovered profile URLs where available.
    sites = _normalize_sites(child_sites)
    if sites:
        lines = []
        for name, url in sites:
            if name and url:
                lines.append(f"  - {name}: {url}")
            elif url:
                lines.append(f"  - {url}")
            else:
                lines.append(f"  - {name}")
        site_lines = "\n".join(lines)
        has_urls = any(url for _, url in sites)
        url_note = (" Direct links to my records are included where known."
                    if has_urls else "")
        sites_block = (
            f"This request applies to {parent_name} and to ALL of the following "
            f"websites, brands, and affiliated properties operated by or "
            f"associated with {parent_name}.{url_note}\n{site_lines}\n\n"
        )
    else:
        sites_block = (
            f"This request applies to {parent_name} and to all websites, brands, "
            f"and affiliated properties operated by or associated with "
            f"{parent_name}.\n\n"
        )

    # Law citation: CCPA named + general applicable-law catch-all. (CCPA governs
    # California residents; the general clause covers everyone else. This is
    # deliberately forceful but not a precise per-state claim — see the caveat in
    # docs; a lawyer should refine the specific statutes cited.)
    law_line = (
        "I am exercising my rights under applicable privacy and data-protection "
        "laws, including the California Consumer Privacy Act (CCPA) and any other "
        "applicable state privacy laws, including any right to deletion, to opt "
        "out of the sale or sharing of personal information, and to have my "
        "information suppressed from public-facing listings. This request covers "
        "all affiliated and successor properties under common ownership or "
        "operation."
    )
    if state:
        law_line = (
            f"As a resident of {state}, I am exercising my rights under applicable "
            "privacy and data-protection laws, including the California Consumer "
            "Privacy Act (CCPA) where applicable and any other applicable state "
            "privacy laws, including any right to deletion, to opt out of the sale "
            "or sharing of personal information, and to have my information "
            "suppressed from public-facing listings. This request covers all "
            "affiliated and successor properties under common ownership or operation."
        )

    ref_line = (
        f"Reference ID (include in all correspondence): {request_key}\n\n"
        if request_key else ""
    )

    body = (
        f"To the Privacy / Data Protection team at {parent_name},\n\n"
        f"I am writing to request the removal and deletion of my personal information from "
        f"your records and services, and to opt out of any sale, licensing, or sharing of that information.\n\n"
        f"{sites_block}"
        f"Please remove all records matching the following identifiers:\n\n"
        f"{id_block}"
        f"I am requesting that you:\n"
        f"  1. Delete and suppress all personal information associated with the identifiers above from {parent_name} and every property listed above.\n"
        f"  2. Do not sell, license, share, or otherwise disclose this information to any third party.\n"
        f"  3. Do not re-create, re-acquire, or re-list this information from other sources following this request.\n"
        f"  4. Confirm in writing, to the sending email address, once the removal has been completed, and identify any records you were unable to remove and why.\n\n"
        f"{law_line}\n\n"
        f"Please treat this as a formal request and respond within the timeframe required by applicable law. "
        f"If you require anything further from me to locate these records, reply to this email and I will provide what is reasonably necessary — "
        f"though I ask that you not require the creation of an account or the submission of additional sensitive information (such as a full date of birth or government ID).\n\n"
        f"{ref_line}"
        f"Thank you for your prompt attention.\n\n"
        f"Sincerely,\n"
        f"{ids.full_name or '[Requester]'}\n"
    )

    if locale and locale != "en":
        body = (f"[Note: a localized ({locale}) template is not yet available; "
                f"this request is in English.]\n\n") + body

    return ComposedEmail(
        to=to_address,
        cc=list(cc or []),
        subject=subject,
        body=body,
    )
