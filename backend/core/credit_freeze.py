"""
Credit freeze letters.

OpenOptOut never stores Social Security numbers. Instead of asking the credit
bureaus to freeze a file on someone's behalf, it prepares the request letters
with everything except the SSN filled in, plus the list of copies to enclose,
so a person can print, write the number in by hand, and mail them. Adults can
also freeze online or by phone in minutes; children under 16 can only be
frozen by a parent or guardian, by mail.

Addresses and rules are from each bureau's own freeze pages (checked
2026-10-11). Update `CHECKED` when they're re-checked.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

CHECKED = "2026-10-11"

BUREAUS = [
    {
        "key": "equifax", "name": "Equifax",
        "online": "https://www.equifax.com/personal/credit-report-services/credit-freeze/",
        "phone": "888-298-0045",
        "adult_mail": ["Equifax Information Services LLC", "P.O. Box 105788", "Atlanta, GA 30348-5788"],
        "minor_mail": ["Equifax Information Services LLC", "P.O. Box 105788", "Atlanta, GA 30348-5788"],
        "minor_online": "",
        "minor_form": "https://assets.equifax.com/assets/personal/Minor_Freeze_Request_Form.pdf",
        "minor_note": "Equifax asks for its Minor Freeze Request form to go with the letter. Print it from the link and send both together.",
        "source": "equifax.com credit freeze page and 'Freezing your child's credit report' FAQ",
    },
    {
        "key": "experian", "name": "Experian",
        "online": "https://www.experian.com/help/credit-freeze/",
        "phone": "888-397-3742",
        "adult_mail": ["Experian Security Freeze", "P.O. Box 9554", "Allen, TX 75013"],
        "minor_mail": ["Experian", "P.O. Box 9554", "Allen, TX 75013"],
        "minor_online": "https://www.experian.com/help/minor-request/",
        "minor_form": "",
        "minor_note": "Experian also takes child freeze requests online at its minor request page, with the same documents uploaded.",
        "source": "experian.com freeze center and 'How to freeze your child's credit report'",
    },
    {
        "key": "transunion", "name": "TransUnion",
        "online": "https://www.transunion.com/credit-freeze",
        "phone": "888-909-8872",
        "adult_mail": ["TransUnion", "P.O. Box 160", "Woodlyn, PA 19094"],
        "minor_mail": ["TransUnion", "P.O. Box 380", "Woodlyn, PA 19094"],
        "minor_online": "",
        "minor_form": "",
        "minor_note": "TransUnion calls this a \"Protected Consumer Freeze\" and only takes it by mail, for children 15 and under.",
        "source": "transunion.com 'Freeze by mail or phone' and Freeze Support Center FAQ",
    },
]

# Smaller consumer reporting agencies worth freezing too. Lenders, banks,
# landlords and phone companies check these. Only details confirmed from a
# source are listed; the rest say where to look.
OTHER_AGENCIES = [
    {"name": "Innovis", "how": "Fourth credit bureau. Freeze on its website's security freeze page, or call 800-245-1096."},
    {"name": "NCTUE (National Consumer Telecom & Utilities Exchange)", "how": "Phone, TV and utility accounts. Use \"Place a freeze\" in its consumer portal."},
    {"name": "ChexSystems", "how": "Checks and bank account openings. Freeze online, or call 800-428-9623."},
    {"name": "LexisNexis Risk Solutions", "how": "Insurance and identity checks (also handles SageStream). Freeze online at its consumer portal, or call 800-456-1244."},
]

ENCLOSE_ADULT = [
    "A copy of a government photo ID (driver's license or state ID)",
    "A copy of a recent utility bill or bank statement showing your name and current address",
]
ENCLOSE_MINOR = [
    "A copy of the child's birth certificate",
    "A copy of the child's Social Security card",
    "A copy of your government photo ID",
    "A copy of a recent utility bill or bank statement showing your name and current address",
    "If your name isn't on the birth certificate: a copy of the court order, guardianship papers or power of attorney",
]

SSN_BLANK = "____-__-____ (write it in by hand)"


def _addr_lines(member) -> list:
    from .combinations import _get_values
    vals = _get_values(member, "address", 3)
    return vals


def kind_for(member, today: Optional[date] = None) -> str:
    """'minor' for under-16s (a parent must ask), otherwise 'adult'."""
    from .age import current_age
    a = current_age(member, today)
    return "minor" if a is not None and a < 16 else "adult"


def _dob_text(member) -> str:
    from .age import member_dob
    d = member_dob(member)
    return f"{d:%B} {d.day}, {d.year}" if d else "__________ (write it in)"


def letters(member, requester=None, kind: Optional[str] = None, today: Optional[date] = None) -> dict:
    """
    One letter per bureau. `requester` is the parent or guardian sending a
    child's freeze (another FamilyMember); for an adult it's the person themself.
    Nothing here is saved: the letters are built fresh each time.
    """
    today = today or date.today()
    kind = kind or kind_for(member, today)
    addrs = _addr_lines(member)
    current = addrs[0] if addrs else "__________ (your street, city, state and ZIP)"
    past = addrs[1:]
    when = f"{today:%B} {today.day}, {today.year}"
    out = []
    for b in BUREAUS:
        if kind == "minor":
            parent = requester
            pname = parent.full_name if parent is not None else "__________ (your full name)"
            paddrs = _addr_lines(parent) if parent is not None else []
            paddr = paddrs[0] if paddrs else current
            body = "\n".join([
                pname, paddr, "", when, "",
                *b["minor_mail"], "",
                ("Re: Request for a Protected Consumer Freeze for my child" if b["key"] == "transunion"
                 else "Re: Request for a security freeze on my child's credit file"), "",
                "To whom it may concern,", "",
                f"I am the parent or legal guardian of the child named below, who is under 16. Under the "
                f"federal Fair Credit Reporting Act (15 U.S.C. § 1681c-1(j)), I ask you to create a credit file "
                f"for my child if one doesn't exist, and to place a security freeze on it.", "",
                "Child's details:",
                f"  Full name: {member.full_name}",
                f"  Date of birth: {_dob_text(member)}",
                f"  Social Security number: {SSN_BLANK}",
                f"  Address: {current}", "",
                "My details:",
                f"  Full name: {pname}",
                f"  Date of birth: {_dob_text(parent) if parent is not None else '__________ (write it in)'}",
                f"  Social Security number: {SSN_BLANK}",
                f"  Address: {paddr}", "",
                "I have enclosed copies of the documents that show my child's identity, my identity, and "
                "that I am authorized to act for my child. Please send written confirmation of the freeze "
                "to the address above.", "",
                "Sincerely,", "", "", "__________________________ (sign here)", pname,
            ])
            enclose = list(ENCLOSE_MINOR)
            note = b["minor_note"]
            online = b["minor_online"]
            extra = b["minor_form"]
        else:
            body = "\n".join([
                member.full_name, current, "", when, "",
                *b["adult_mail"], "",
                "Re: Request for a security freeze", "",
                "To whom it may concern,", "",
                "Please place a security freeze on my credit file. My details are below.", "",
                f"  Full name: {member.full_name}",
                f"  Date of birth: {_dob_text(member)}",
                f"  Social Security number: {SSN_BLANK}",
                f"  Current address: {current}",
                *([f"  Previous address: {a}" for a in past] or ["  Previous address (past two years, if you moved): __________"]),
                "",
                "I have enclosed a copy of my government ID and a recent bill showing my current address. "
                "Please send written confirmation of the freeze, and any PIN or password I'll need to lift it, "
                "to the address above.", "",
                "Sincerely,", "", "", "__________________________ (sign here)", member.full_name,
            ])
            enclose = list(ENCLOSE_ADULT)
            note = (f"Faster: freeze online at {b['online']} or by phone at {b['phone']}. "
                    f"It's free and usually takes effect right away. Mail takes about 3 business days after it arrives.")
            online = b["online"]
            extra = ""
        out.append({"bureau": b["name"], "key": b["key"], "mail_to": b["minor_mail" if kind == "minor" else "adult_mail"],
                    "letter": body, "enclose": enclose, "note": note, "online": online, "phone": b["phone"],
                    "form": extra, "source": b["source"]})
    return {
        "kind": kind,
        "person": member.full_name,
        "checked": CHECKED,
        "letters": out,
        "other_agencies": OTHER_AGENCIES,
        "never_stored": "OpenOptOut never saves Social Security numbers. Write them on the printed letters by hand.",
    }
