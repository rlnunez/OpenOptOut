"""
Opt-out engine — fires removal requests using the full combination matrix.

For each confirmed broker listing:
  - form brokers:  Playwright fills + submits opt-out form for EVERY combo
  - email brokers: one SMTP email listing ALL name/address/phone variants
  - manual:        queues an instruction card, skips automation

Pass 2 of the two-pass strategy:
  discovery found the broker → opt-out exhausts every combination.
"""

import asyncio, json, logging, smtplib, ssl, time, uuid, re, os
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from playwright.async_api import async_playwright, Page, BrowserContext, TimeoutError as PWTimeout

from ..models.database import (
    SessionLocal, FamilyMember, Broker, BrokerScript,
    RemovalRequest, RequestStatus, OptOutMethod,
    AutomationLog, EmailLog
)
from .settings_store import load_settings, decrypt_password
from .discovery import _launch_browser, _screenshot, _city_state
from .user_agents import get_random_agent, get_custom_uas_from_settings, rotation_enabled
from .combinations import (
    build_optout_combos, build_email_optout_combos,
    build_property_optout_combos,
    IdentityCombo, _get_values, get_vault_limits
)
VAULT_LIMITS = get_vault_limits()

log = logging.getLogger(__name__)
SCREENSHOTS_DIR = "/data/screenshots"


async def _fresh_context(browser):
    """
    Create a new browser context with a freshly randomized user agent AND
    a fresh proxy selection. Called per-broker, so in pool mode each broker
    is contacted from a different IP — the strongest evasion configuration.
    """
    from .proxy import get_proxy_for_context

    ctx_args = {"locale": "en-US"}
    proxy = get_proxy_for_context()
    if proxy:
        ctx_args["proxy"] = proxy

    if rotation_enabled():
        agent = get_random_agent(get_custom_uas_from_settings())
        ctx_args["user_agent"] = agent["ua"]
        ctx_args["viewport"]   = agent["viewport"]
    else:
        ctx_args["user_agent"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:124.0) Gecko/20100101 Firefox/124.0"
        ctx_args["viewport"]   = {"width": 1280, "height": 800}

    return await browser.new_context(**ctx_args)


# ── Email opt-out (sends ONE email listing all identity variants) ──────────────

def _build_exhaustive_email(
    member: FamilyMember,
    broker: Broker,
    request_key: str,
    script: Optional[BrokerScript],
    db = None,
) -> tuple[str, str]:
    """
    Build a single opt-out email listing ALL identity variants.
    For property brokers, leads with the formal legal name.
    """
    limits    = get_vault_limits()
    names     = _get_values(member, "name",    limits["name"])
    addresses = _get_values(member, "address", limits["address"])
    phones    = _get_values(member, "phone",   limits["phone"])
    emails    = _get_values(member, "email",   limits["email"])

    # For property brokers, use formal name as primary if set
    if broker.is_property_broker and member.formal_name:
        primary_name = member.formal_name
        # Include formal name first, then variants
        all_names = [member.formal_name] + [n for n in names if n != member.formal_name]
        # Only use deed + mortgage addresses
        prop_addresses = [
            i.value for i in member.identities
            if i.kind == "address" and (i.is_deed or i.is_mortgage)
        ]
        if prop_addresses:
            addresses = prop_addresses
    else:
        primary_name = names[0] if names else member.full_name
        all_names    = names

    from ..plugins.broker_addon import get_broker_spec_for_broker
    from .optout_email_template import Identifiers
    from .legal_letters import compose_letter, identifier_block
    addon_spec = get_broker_spec_for_broker(db, broker) if db else None
    addon_email = addon_spec.email if addon_spec else None

    # The letter is chosen by the broker's jurisdiction and written in its
    # legal language — never the family's interface language.
    jurisdiction = addon_spec.effective_jurisdiction() if addon_spec else "US"
    legal_language = addon_spec.effective_legal_language() if addon_spec else "en"
    residence = _residence_state(member)
    ids = Identifiers(
        full_name=primary_name or "",
        name_variants=[n for n in all_names if n and n != primary_name],
        emails=list(emails), phones=list(phones), addresses=list(addresses),
    )

    # Every identifier we hold, as one block. Custom templates can place it with
    # {identifiers}; if a custom body leaves it out, it is appended, because a
    # broker can't find (or remove) the records without it.
    identifiers_block = identifier_block(ids, legal_language)
    tpl_fields = _template_fields(
        member, primary_name, request_key, broker.name,
        addresses, phones, emails, identifiers_block,
    )

    # The broker's own letter, in order: one written for its legal language,
    # then the add-on's single template, then a recorded script's.
    own = addon_spec.letter_template(legal_language) if addon_spec else None
    custom_subject = ((own or {}).get("subject")
                      or (addon_email.subject_template if addon_email and addon_email.subject_template
                          else (script.email_subject_tpl if script and script.email_subject_tpl else "")))
    custom_body = ((own or {}).get("body")
                   or (addon_email.body_template if addon_email and addon_email.body_template
                       else (script.email_body_tpl if script and script.email_body_tpl else "")))

    prop = None
    if broker.is_property_broker and member.formal_name:
        prop = {
            "formal_name": member.formal_name,
            "deed": [i.value for i in member.identities if i.kind == "address" and i.is_deed],
            "mortgage": [i.value for i in member.identities if i.kind == "address" and i.is_mortgage],
        }
    letter = compose_letter(ids, broker.name, jurisdiction=jurisdiction,
                            legal_language=legal_language, residence_state=residence,
                            request_key=request_key, property_records=prop)

    subject = render_template(custom_subject, tpl_fields) if custom_subject else letter.subject
    if custom_body:
        body = render_template(custom_body, tpl_fields)
        if "{identifiers}" not in custom_body:
            body = body.rstrip() + "\n\n" + identifiers_block + "\n"
    else:
        body = letter.body
    return subject, body


def _extract_email_from_notes(notes: Optional[str]) -> Optional[str]:
    if not notes: return None
    m = re.search(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', notes)
    return m.group(0) if m else None


def _template_fields(member, primary_name, request_key, broker_name,
                     addresses, phones, emails, identifiers_block) -> dict:
    """
    Values a custom opt-out email template may use. This is the same vocabulary
    the declarative spec compiler uses ({full_name}, {email}, ...) plus the
    legacy names older templates use ({name}, {broker}, {request_key}).
    Exact date of birth is deliberately not offered.
    """
    parts = (primary_name or "").split()
    return {
        "name": primary_name or "",
        "full_name": primary_name or "",
        "formal_name": getattr(member, "formal_name", None) or primary_name or "",
        "first_name": parts[0] if parts else "",
        "last_name": " ".join(parts[1:]) if len(parts) > 1 else "",
        "email": emails[0] if emails else "",
        "phone": phones[0] if phones else "",
        "address": addresses[0] if addresses else "",
        "broker": broker_name or "",
        "request_key": request_key or "",
        "identifiers": identifiers_block,
    }


def render_template(template: str, fields: dict) -> str:
    """
    Fill {placeholders} from `fields`. Unknown placeholders are left as written
    instead of raising, so one unexpected placeholder in an add-on template can
    no longer make every send for that broker fail. Literal braces are safe.
    """
    def sub(m):
        key = m.group(1)
        return str(fields[key]) if key in fields and fields[key] is not None else m.group(0)
    return re.sub(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", sub, template or "")


def resolve_optout_address(broker: Broker, db=None) -> Optional[str]:
    """
    The broker's opt-out email address, from a source someone recorded:
    the installed add-on's spec first, then an address written in the broker's
    notes. Returns None when neither exists.

    There is deliberately no guessed fallback (the old code tried
    privacy@<name>.com): sending a member's full identifier list to an address
    nobody has verified can hand that data to the wrong party.
    """
    from ..plugins.broker_addon import get_broker_spec_for_broker
    addon_spec = get_broker_spec_for_broker(db, broker) if db else None
    addon_email = addon_spec.email if addon_spec else None
    if addon_email and addon_email.to_address:
        return addon_email.to_address
    return _extract_email_from_notes(broker.notes)


def send_opt_out_email(
    member: FamilyMember,
    broker: Broker,
    request_key: str,
    script: Optional[BrokerScript],
    cfg: dict,
    db,
) -> bool:
    """
    Send one exhaustive opt-out email to a single broker, FROM the member's own
    inbox (core/mailboxes.resolve_mailbox), with Reply-To set to this opt-out's
    own contact address (a unique +address when the inbox supports it). The
    system inbox is never used for opt-outs.

    Goes through core.email_send.send_email (provider plugin with OAuth token
    refresh, or SMTP for app-password inboxes). Returns True only on success.
    """
    from . import mailboxes as mbx
    to_email = resolve_optout_address(broker, db)
    if not to_email:
        log.error("No verified opt-out email address for %s; not sending", broker.name)
        return False
    mailbox = mbx.resolve_mailbox(db, member)
    if mailbox is None:
        log.error("No inbox for member_id=%s; not sending %s opt-out", member.id, broker.name)
        return False

    contact, reason = mbx.issue_contact_address(db, mailbox, member, broker=broker,
                                                request_key=request_key)
    if contact is None:
        log.info("Not sending %s opt-out for member_id=%s: %s", broker.name, member.id, reason)
        return False

    subject, body = _build_exhaustive_email(member, broker, request_key, script, db=db)
    try:
        result = mbx.send_from_mailbox(cfg, mailbox, [to_email], subject, body,
                                       reply_to=contact.address)
    except Exception as e:
        log.error("Email send failed for %s: %s", broker.name, type(e).__name__)
        return False

    if not result.get("ok"):
        log.error("Email send failed for %s via %s: %s", broker.name,
                  result.get("via", "?"), result.get("error") or "unknown error")
        return False

    try:
        db.add(EmailLog(
            request_id=None, direction="sent",
            subject=subject, body_snippet=body[:500],
            matched_key=request_key,
        ))
        db.commit()
    except Exception as e:
        db.rollback()
        log.warning("Email to %s sent but log write failed (%s); continuing", broker.name, e)
    log.info("Email opt-out sent via %s from mailbox_id=%s: %s (member_id=%s)",
             result.get("via", "?"), mailbox.id, broker.name, member.id)
    return True


def _residence_state(member) -> str:
    """The member's US state (two letters) from their primary address, or ""."""
    try:
        from .combinations import _get_values, _parse_address
        addrs = _get_values(member, "address", 1)
        st = (_parse_address(addrs[0]).get("state") or "") if addrs else ""
        return st.strip().upper() if len(st.strip()) == 2 else ""
    except Exception:
        return ""


def _member_identifiers(member):
    """Build the template Identifiers from a member's vault (no exact DOB)."""
    from .combinations import _get_values
    from .optout_email_template import Identifiers
    names = _get_values(member, "name", 10)
    variants = [n for n in names if n and n != member.full_name]
    age = None
    try:
        if getattr(member, "dob", None):
            from datetime import date
            d = member.dob
            age = date.today().year - d.year
    except Exception:
        age = None
    city_state = ""
    addrs = _get_values(member, "address", 10)
    return Identifiers(
        full_name=member.full_name or (names[0] if names else ""),
        name_variants=variants,
        emails=_get_values(member, "email", 10),
        phones=_get_values(member, "phone", 10),
        addresses=addrs,
        age=age,
        city_state=city_state,
    )


def send_parent_optout_detailed(member, parent, cfg, db, discovered_urls=None,
                                subject_prefix: str = "",
                                request_key: str = "") -> dict:
    """
    Send ONE opt-out email to a parent company, covering all its child sites,
    using the strong template. Returns a detail dict:
        {"ok", "via" ("provider"|"smtp"), "error", "to", "cc", "subject", "child_sites", "request_key"}
    so callers (e.g. the test-send button) can show exactly what happened.

    Transport is decided by core/email_send.send_email (provider plugin with
    OAuth auto-refresh, or SMTP fallback) — this function does NOT gate on SMTP
    settings, so OAuth-only deployments work. Records effectiveness on the parent.
    subject_prefix: e.g. "[OpenOptOut TEST] " for test sends.
    request_key: optional UUID tracking key embedded in email subject & body.
    """
    from .optout_email_template import compose_optout_email
    from . import parent_company as pcmod
    from .email_send import send_email

    ec = cfg.get("email", {})
    to_email = parent.optout_email
    detail = {"ok": False, "via": "", "error": "", "to": to_email or "",
              "cc": [], "subject": "", "child_sites": 0, "request_key": request_key or ""}

    if not to_email:
        detail["error"] = f"Parent '{parent.name}' has no opt-out email set"
        log.error(detail["error"])
        return detail

    # Child-site list, with discovered profile URLs where known.
    if discovered_urls is None:
        try:
            discovered_urls = pcmod.discovered_urls_for_parent(db, parent, member.id)
        except Exception:
            discovered_urls = {}
    discovered_urls = discovered_urls or {}
    child_sites = []
    for child in (parent.children or []):
        entry = {"name": child.name}
        url = discovered_urls.get(child.name)
        if url:
            entry["url"] = url
        child_sites.append(entry)

    ids = _member_identifiers(member)
    composed = compose_optout_email(
        ids, parent_name=parent.name, to_address=to_email,
        child_sites=child_sites,
        cc=[e.strip() for e in (parent.cc_emails or "").split(",") if e.strip()],
        locale=parent.locale or "", state=_residence_state(member),
        jurisdiction=getattr(parent, "jurisdiction", None) or "US",
        request_key=request_key,
    )
    subject = (subject_prefix or "") + composed.subject
    detail.update({"cc": list(composed.cc), "subject": subject,
                   "child_sites": len(child_sites)})

    # Opt-outs go out from the member's own inbox, with Reply-To set to a
    # contact address made for this email. Only the admin's test broker may
    # fall back to the system inbox (it tests the transport, not a family).
    from . import mailboxes as mbx
    mailbox = mbx.resolve_mailbox(db, member) if getattr(member, "id", None) else None
    if mailbox is not None:
        contact, reason = mbx.issue_contact_address(db, mailbox, member, parent=parent,
                                                    request_key=request_key)
        if contact is None:
            detail.update({"error": reason, "needs_mailbox": True})
            return detail
        detail["reply_to"] = contact.address
        result = mbx.send_from_mailbox(cfg, mailbox, [composed.to], subject, composed.body,
                                       reply_to=contact.address, cc=list(composed.cc))
    elif getattr(parent, "is_test", False):
        from ..routers.email_oauth import active_account_ref
        result = send_email(
            cfg, to=[composed.to], cc=list(composed.cc),
            subject=subject, body=composed.body,
            account_ref=active_account_ref(cfg),
            from_address=ec.get("from_address", ""),
        )
    else:
        detail.update({"error": mbx.missing_mailbox_instruction(member), "needs_mailbox": True})
        log.info("Parent opt-out to %s skipped: member_id=%s has no inbox", parent.name, member.id)
        return detail   # not a parent failure — nothing was sent
    detail["via"] = result.get("via", "")
    if result.get("ok"):
        detail["ok"] = True
        matched_key = request_key or f"parent:{parent.id}"
        try:
            db.add(EmailLog(request_id=None, direction="sent",
                            subject=subject, body_snippet=composed.body[:500],
                            matched_key=matched_key))
            db.commit()
        except Exception as e:
            db.rollback()
            log.warning("Parent send succeeded but email log write failed (%s); continuing", e)
        pcmod.record_send(db, parent.id, failed=False)
        log.info("Parent opt-out sent via %s: %s (member_id=%s, %d child sites, key=%s)",
                 detail["via"], parent.name, member.id, len(child_sites), matched_key)
    else:
        detail["error"] = result.get("error") or "send failed"
        log.error("Parent opt-out send failed for %s: %s", parent.name, detail["error"])
        try:
            pcmod.record_send(db, parent.id, failed=True)
        except Exception:
            pass
    return detail


def send_parent_optout_email(member, parent, cfg, db, discovered_urls=None) -> bool:
    """Bool wrapper around send_parent_optout_detailed (kept for existing callers)."""
    return send_parent_optout_detailed(member, parent, cfg, db, discovered_urls)["ok"]


def dispatch_parent_optout(
    member,
    parent,
    pending_requests: list,
    cfg: dict,
    db,
    discovered_urls: Optional[dict] = None,
) -> dict:
    """
    Dispatch ONE parent opt-out email covering all `pending_requests` for this member
    that belong to child brokers of `parent`. On success, transitions all requests to
    RequestStatus.sent with a shared UUID tracking key and writes AutomationLog entries.
    """
    import uuid
    from datetime import datetime, timedelta
    from ..models.database import RequestStatus, AutomationLog

    key = str(uuid.uuid4())
    result = send_parent_optout_detailed(
        member, parent, cfg, db, discovered_urls=discovered_urls, request_key=key
    )

    if result.get("ok"):
        recheck_days = cfg.get("scheduler", {}).get("recheck_interval_days", 90)
        recheck_dt = datetime.utcnow() + timedelta(days=recheck_days)
        now = datetime.utcnow()

        from .variant_report import record as _record_variants, identities_in_email
        email_ids = identities_in_email(member, limit=10)   # the parent email lists up to 10 of each
        for req in pending_requests:
            _record_variants(db, req.id, email_ids)
            req.status = RequestStatus.sent
            req.sent_at = now
            req.request_key = key
            req.recheck_after = recheck_dt
            req.updated_at = now

            db.add(AutomationLog(
                request_id=req.id,
                member_id=member.id,
                broker_id=req.broker_id,
                action="parent_email_send",
                status="success",
                detail=f"Sent via parent company '{parent.name}' ({parent.optout_email}) via {result.get('via')}",
                duration_ms=0,
            ))
        db.commit()
        result["covered_request_ids"] = [r.id for r in pending_requests]
        result["key"] = key
    return result


def process_pending_parent_company_optouts(
    db,
    cfg: dict,
    batch_request_ids: Optional[list] = None,
    member_id: Optional[int] = None,
    parent_id: Optional[int] = None,
) -> dict:
    """
    Automated batch trigger for email-first parent company opt-outs (Roadmap Item 10).
    Scans pending RemovalRequests:
    - Finds requests whose broker belongs to a ParentCompany with a valid optout_email
    - Excludes parents whose honor_status == 'bounces'
    - Groups requests by (member_id, parent_company_id)
    - Dispatches ONE email per (member, parent) group
    - Transitions all child requests to 'sent'
    Returns summary statistics:
      {"sent_emails": int, "covered_requests": int, "covered_request_ids": list, "errors": list}
    """
    from collections import defaultdict
    from ..models.database import RemovalRequest, RequestStatus, ParentCompany, Broker, EmailHonorStatus

    q = (
        db.query(RemovalRequest)
        .join(RemovalRequest.broker)
        .filter(
            RemovalRequest.status == RequestStatus.pending,
            RemovalRequest.broker.has(Broker.parent_company_id.isnot(None)),
        )
    )
    if batch_request_ids is not None:
        q = q.filter(RemovalRequest.id.in_(batch_request_ids))
    if member_id:
        q = q.filter(RemovalRequest.member_id == member_id)
    if parent_id:
        q = q.filter(Broker.parent_company_id == parent_id)

    pending = q.all()
    if not pending:
        return {"sent_emails": 0, "covered_requests": 0, "covered_request_ids": [], "errors": []}

    # Group by (member_id, parent_company_id)
    groups = defaultdict(list)
    parent_cache = {}
    for req in pending:
        pid = req.broker.parent_company_id
        if not pid:
            continue
        if pid not in parent_cache:
            parent_cache[pid] = db.query(ParentCompany).filter(ParentCompany.id == pid).first()
        parent = parent_cache[pid]
        if not parent or not parent.optout_email:
            continue
        # Skip bouncing email addresses
        if parent.honor_status == EmailHonorStatus.bounces:
            continue
        # Skip disabled or test brokers (and registry-only brokers DROP covers)
        from .broker_gate import request_allowed
        if not request_allowed(req, db):
            continue

        groups[(req.member_id, pid)].append(req)

    sent_emails = 0
    covered_requests = 0
    covered_ids = []
    errors = []

    for (m_id, p_id), req_list in groups.items():
        parent = parent_cache[p_id]
        member = req_list[0].member
        try:
            res = dispatch_parent_optout(member, parent, req_list, cfg, db)
            if res.get("ok"):
                sent_emails += 1
                covered_requests += len(req_list)
                covered_ids.extend([r.id for r in req_list])
            elif res.get("needs_mailbox"):
                pass   # left pending; the per-broker pass puts it on the checklist
            else:
                errors.append(f"Parent '{parent.name}' for {member.full_name}: {res.get('error')}")
        except Exception as e:
            errors.append(f"Parent '{parent.name}' for {member.full_name}: {e}")

    return {
        "sent_emails": sent_emails,
        "covered_requests": covered_requests,
        "covered_request_ids": covered_ids,
        "errors": errors,
    }



# ── Declarative Interpreter Form Fill ──────────────────────────────────────────

FIELD_LABELS = {
    "phone": "phone number", "phone_digits": "phone number", "address": "street address",
    "street": "street address", "zip": "ZIP code", "state": "state", "state_name": "state",
    "city": "city", "age": "age", "birth_year": "age", "dob": "date of birth",
    "first_name": "first name", "last_name": "last name", "email": "email address",
}


def _missing_field(msg: str) -> str:
    import re
    m = re.search(r"no value for (?:required field )?'([a-z_]+)'", msg)
    return m.group(1) if m else ""


async def _run_form_via_interpreter(
    request: RemovalRequest,
    page_or_context,
    cfg: dict,
    db,
    combo: Optional[IdentityCombo] = None,
    captcha_solver_override=None,
    preset_listing_url: Optional[str] = None,
):
    """
    Run a form opt-out through the unified declarative interpreter engine:
    resolve or generate the BrokerSpec, compile it for the member / combo,
    and execute it through PlaywrightExecutor with CAPTCHA-solver and fill_form
    dispatchers wired in.
    """
    from .interpreter import compile_job, PlaywrightExecutor
    from .interpreter.script_bridge import get_or_build_broker_spec
    from .combinations import _get_values, _parse_address

    broker = request.broker
    member = request.member
    script = db.query(BrokerScript).filter(BrokerScript.broker_id == broker.id).first() if db else None

    # Resolve authoritative spec (add-on -> script bridge -> heuristic fallback)
    spec = get_or_build_broker_spec(broker, script=script, db=db)
    from .interpreter.script_bridge import is_heuristic
    if is_heuristic(spec) and not cfg.get("automation", {}).get("best_guess_forms", False):
        # No real steps for this site. Guessing could type the person's details
        # into the wrong form (a newsletter box, a search bar), so a person does it.
        from .interpreter.executor import ExecResult
        found = None
        try:
            from .privacy_finder import best
            found = best(db, broker)
        except Exception:
            pass
        if found is not None:
            where = (f"OpenOptOut found {broker.name}'s privacy page at {found.url}. Open it"
                     if found.kind != "policy" else
                     f"{broker.name}'s privacy policy is at {found.url}; it should say how to opt out. Follow it")
            return ExecResult(ok=False, needs_manual=True, detail="no opt-out steps for this broker yet",
                              human_instruction=(f"{where}, ask for {member.full_name}'s data to be deleted "
                                                 f"and not sold, then press \"I've done this\"."))
        return ExecResult(ok=False, needs_manual=True, detail="no opt-out steps for this broker yet",
                          human_instruction=(
                              f"OpenOptOut doesn't have the steps for {broker.name}'s opt-out form yet. "
                              + (f"Open {broker.opt_out_url}, " if broker.opt_out_url else f"Find {broker.name}'s opt-out page, ")
                              + f"fill it in for {member.full_name}, then press \"I've done this\"."))

    # Resolve member fields (names, address parts, derived formats).
    from .interpreter.member_fields import resolve as resolve_fields
    member_fields = resolve_fields(member, combo)

    # Brokers whose form needs the member's own listing address.
    if any(s.field == "listing_url" and not s.optional for s in (spec.steps or [])):
        if not request.listing_url:
            from .interpreter.executor import ExecResult
            return ExecResult(
                ok=False, needs_manual=True, detail="listing address needed",
                human_instruction=(f"{broker.name} needs the web address of {member.full_name}'s own "
                                   f"listing. Open Discovery → Find your listings, search {broker.name}, "
                                   f"and paste the address of the page that shows the listing."))
    member_fields["listing_url"] = request.listing_url or ""

    # The address the broker should write back to for THIS submission.
    # Issued only when the spec asks for it, so no unused addresses pile up.
    from .interpreter.compiler import uses_field
    if uses_field(spec, "contact_email"):
        from . import mailboxes as mbx
        mailbox = mbx.resolve_mailbox(db, member)
        if mailbox is None:
            from .interpreter.executor import ExecResult
            return ExecResult(ok=False, needs_manual=True,
                              human_instruction=mbx.missing_mailbox_instruction(member),
                              detail="no inbox for this member")
        contact, reason = mbx.issue_contact_address(
            db, mailbox, member, broker=broker, request_key=request.request_key or "",
            combo_label=combo.masked_label() if combo else "",
            one_optout_per_email=bool(getattr(spec, "one_optout_per_email", False)),
            allow_plus=_plus_ok(spec, broker))
        if contact is None:
            from .interpreter.executor import ExecResult
            return ExecResult(ok=False, needs_manual=True, human_instruction=reason,
                              detail="no unused email address for this broker")
        member_fields["contact_email"] = contact.address
        db.commit()

    from .interpreter.compiler import CompileError
    try:
        job = compile_job(spec, member_fields, member_id=str(member.id), lang=_member_lang(member))
    except CompileError as e:
        from .interpreter.executor import ExecResult
        missing = _missing_field(str(e))
        if missing:
            return ExecResult(ok=False, needs_manual=True, detail=f"missing {missing}",
                              human_instruction=(f"{broker.name}'s form needs {member.full_name}'s "
                                                 f"{FIELD_LABELS.get(missing, missing.replace('_', ' '))}. "
                                                 f"Add it in the Identity vault and OpenOptOut will try again."))
        raise

    # Wire the plugin manager's dispatchers into the executor so the CAPTCHA
    # solver + fill_form takeover hooks fire.
    captcha_solver = None
    form_handler = None
    try:
        from ..plugins import get_manager
        mgr = get_manager()
        if mgr:
            preferred_captcha = getattr(broker, "captcha_plugin_id", None)
            from .captcha_services import plugin_meta
            captcha_solver = lambda ch: mgr.dispatch_solve_captcha(ch, preferred_plugin_id=preferred_captcha,
                                                                   meta_for=plugin_meta)
            def form_handler(job_, page_context):
                if isinstance(page_context, dict):
                    page_html = page_context.get("html", "")
                    meta = {
                        "method": str(broker.method),
                        "difficulty": str(broker.difficulty),
                        "current_url": str(page_context.get("url", "")),
                        "page_title": str(page_context.get("title", "")),
                        "has_iframes": str(bool(page_context.get("has_iframes", False))),
                        "stage_index": str(page_context.get("stage_index", 0)),
                    }
                else:
                    page_html = str(page_context or "")
                    meta = {"method": str(broker.method), "difficulty": str(broker.difficulty)}

                return mgr.dispatch_fill_form(
                    {"id": broker.id, "name": broker.name,
                     "opt_out_url": broker.opt_out_url or "",
                     "meta": meta},
                    page_html,
                    fields_provider=lambda: dict(member_fields),
                )
    except Exception as e:
        log.debug("plugin dispatchers unavailable: %s", e)

    should_close = False
    if hasattr(page_or_context, "goto"):
        page = page_or_context
    elif hasattr(page_or_context, "new_page"):
        page = await page_or_context.new_page()
        should_close = True
    else:
        page = None

    try:
        from .captcha_privacy import member_secrets
        if captcha_solver_override is not None:
            captcha_solver = captcha_solver_override
        from .listing_finder import _profile as match_profile
        from .match_policy import for_member as unclear_policy
        executor = PlaywrightExecutor(
            page=page, captcha_solver=captcha_solver, plugin_form_handler=form_handler,
            secrets=member_secrets(member), match_profile=match_profile(member),
            unclear_policy=unclear_policy(db, member, cfg), preset_listing_url=preset_listing_url,
            listing_pattern=getattr(spec, "listing_pattern", "") or "")
        res = await executor.run(job)
        if res.email_rejected and "+" in (job.contact_email or ""):
            res = await _retry_without_plus(db, request, broker, member, spec, combo, member_fields,
                                            page, captcha_solver, form_handler, res)
        if res.ok and is_heuristic(spec) and not res.verified:
            # A best guess only counts when the site says it worked.
            try:
                body = await page.locator("body").inner_text(timeout=3000)
            except Exception:
                body = ""
            if GENERIC_SUCCESS.search(body or ""):
                res.verified = True
            else:
                from .interpreter.executor import ExecResult
                return ExecResult(ok=False, needs_manual=True, trace=res.trace,
                                  detail="best-guess fill: no sign it worked",
                                  human_instruction=(
                                      f"OpenOptOut tried {broker.name}'s form but couldn't tell whether it "
                                      f"went through. Open {broker.opt_out_url or broker.name}, check or "
                                      f"finish the opt-out for {member.full_name}, then press \"I've done this\"."))
        res.contact_email = job.contact_email
        return res
    finally:
        if should_close and page:
            await page.close()


GENERIC_SUCCESS = re.compile(
    r"(request|submission|opt[- ]?out|removal)[^.\n]{0,40}(received|submitted|processed|complete|successful)|"
    r"(has|have) been (received|submitted|removed|processed)|thank you for your (request|submission)",
    re.I)


def _member_lang(member) -> str:
    """The language the person handling this member's opt-outs reads."""
    from ..plugins.plugin_i18n import member_language
    return member_language(member)


def _manual_instruction(request, broker, member, cfg, db) -> str:
    """Plain-language steps for an opt-out only a person can do."""
    from .interpreter.script_bridge import get_or_build_broker_spec, is_heuristic
    from .interpreter.member_fields import resolve as resolve_fields
    from .interpreter.compiler import _render
    spec = None
    try:
        script = db.query(BrokerScript).filter(BrokerScript.broker_id == broker.id).first()
        spec = get_or_build_broker_spec(broker, script=script, db=db)
    except Exception as e:
        log.debug("no spec for manual broker %s: %s", broker.name, e)
    if spec is not None and not is_heuristic(spec):
        from ..plugins.plugin_i18n import localize_spec
        spec = localize_spec(spec, _member_lang(member))
    text = (getattr(spec, "instructions", "") or "") if spec is not None and not is_heuristic(spec) else ""
    if not text:
        try:
            from .privacy_finder import best
            found = best(db, broker)
        except Exception:
            found = None
        where = (f"at {found.url}" if found is not None else
                 f"at {broker.opt_out_url}" if broker.opt_out_url else f"on {broker.name}'s website")
        how = "by phone" if broker.method == OptOutMethod.phone else where
        return (f"Opt {member.full_name} out of {broker.name} {how}, then press \"I've done this\"."
                + (f"\n{broker.notes.strip()}" if (broker.notes or "").strip() else ""))
    fields = {k: v for k, v in resolve_fields(member).items() if v}
    key = getattr(spec, "lookup_by", "") or ""
    if key in ("phone", "email") and not fields.get(key):
        return _missing_key_instruction(broker, member, key)
    if request.listing_url:
        fields["listing_url"] = request.listing_url
    if "{contact_email}" in text:
        from . import mailboxes as mbx
        mailbox = mbx.resolve_mailbox(db, member)
        if mailbox is not None:
            contact, _ = mbx.issue_contact_address(
                db, mailbox, member, broker=broker, request_key=request.request_key or "",
                one_optout_per_email=bool(getattr(spec, "one_optout_per_email", False)),
                allow_plus=_plus_ok(spec, broker))
            if contact is not None:
                fields["contact_email"] = contact.address
                db.commit()
        fields.setdefault("contact_email", "your email address")
    if "{listing_url}" in text and "listing_url" not in fields:
        fields["listing_url"] = "the address of your listing (find it under Discovery → Find your listings)"
    return _render(text, fields)


def _missing_key_instruction(broker, member, key: str) -> str:
    what, many = ("phone number", "phone numbers") if key == "phone" else ("email address", "email addresses")
    return (f"{broker.name} lists people by {what}. Add {member.full_name}'s {many} "
            f"on the Your details page, then send this again.")


def _lookup_by(db, broker) -> str:
    """'phone' or 'email' when this broker files people by that detail, else ''."""
    try:
        from .interpreter.script_bridge import get_or_build_broker_spec
        script = db.query(BrokerScript).filter(BrokerScript.broker_id == broker.id).first() if db else None
        spec = get_or_build_broker_spec(broker, script=script, db=db)
        return getattr(spec, "lookup_by", "") or ""
    except Exception:
        return ""


def _plus_ok(spec, broker) -> bool:
    """May this broker's forms be given a +address?"""
    return bool(getattr(spec, "accepts_plus_addresses", True)) and \
        not bool(getattr(broker, "rejects_plus_addresses", False))


async def _retry_without_plus(db, request, broker, member, spec, combo, member_fields,
                              page, captcha_solver, form_handler, first_result):
    """
    The form refused a +address. Remember that for this broker, then try once
    more with the inbox's plain address (replies to it are matched by sender).
    """
    from .interpreter import compile_job, PlaywrightExecutor
    from .interpreter.executor import ExecResult
    from . import mailboxes as mbx
    broker.rejects_plus_addresses = True
    db.commit()
    log.info("%s refused a +address; retrying with the plain address", broker.name)
    mailbox = mbx.resolve_mailbox(db, member)
    contact, reason = (None, mbx.missing_mailbox_instruction(member)) if mailbox is None else \
        mbx.issue_contact_address(
            db, mailbox, member, broker=broker, request_key=request.request_key or "",
            combo_label=combo.masked_label() if combo else "",
            one_optout_per_email=bool(getattr(spec, "one_optout_per_email", False)),
            allow_plus=False)
    plain_ok = contact is not None and "+" not in contact.address
    if not plain_ok:
        return ExecResult(ok=False, needs_manual=True, detail="form refused the +address",
                          trace=first_result.trace,
                          human_instruction=reason or (
                              f"{broker.name}'s form won't accept email addresses with a \"+\" in them. "
                              f"Finish this opt-out at {broker.opt_out_url or broker.name} using a plain email address."))
    db.commit()
    fields = dict(member_fields, contact_email=contact.address)
    job = compile_job(spec, fields, member_id=str(member.id), lang=_member_lang(member))
    from .captcha_privacy import member_secrets
    res = await PlaywrightExecutor(page=page, captcha_solver=captcha_solver,
                                   plugin_form_handler=form_handler, secrets=member_secrets(member)).run(job)
    if res.email_rejected:
        return ExecResult(ok=False, needs_manual=True, detail="form refused the email address",
                          trace=res.trace,
                          human_instruction=(f"{broker.name}'s form didn't accept {contact.address}. "
                                             f"Finish this opt-out at {broker.opt_out_url or broker.name} "
                                             f"with another email address."))
    return res


async def execute_optout(
    request: RemovalRequest,
    context: BrowserContext,
    cfg: dict,
    db,
) -> bool:
    """
    Fire opt-out for ONE RemovalRequest using the unified engine:
    - email brokers: one exhaustive email covering all variants
    - form brokers:  declarative interpreter submission for every identity combo
    - manual:        queue and mark sent
    Returns True if at least one submission succeeded.
    """
    start  = time.monotonic()
    member = request.member
    broker = request.broker
    script = db.query(BrokerScript).filter(BrokerScript.broker_id == broker.id).first()
    key    = request.request_key or str(uuid.uuid4())
    request.request_key = key   # set now: contact addresses issued below record it

    successes = 0
    failures  = 0
    last_error = ""   # captured for broker-health failure classification
    needs_human = ""  # plain-language instruction when a person must finish this
    skipped_note = ""  # set when this was left alone on purpose (unclear matches, by setting)
    not_listed_runs = runs = 0

    from . import mailboxes as _mbx
    try:
        if broker.method in (OptOutMethod.email, OptOutMethod.form) \
                and _mbx.resolve_mailbox(db, member) is None:
            # Opt-outs are sent from, and answered at, the member's own inbox.
            # Without one there is nowhere for confirmations to go.
            needs_human = _mbx.missing_mailbox_instruction(member)
            db.add(AutomationLog(
                request_id=request.id, member_id=member.id, broker_id=broker.id,
                action="mailbox_check", status="needs_manual",
                detail="No connected email inbox for this member", duration_ms=0,
            ))

        elif broker.method == OptOutMethod.email and not resolve_optout_address(broker, db):
            # No recorded address to send to. This is missing data, not a broken
            # broker, so it goes on the checklist instead of counting as a failure.
            needs_human = (f"We don't have a confirmed opt-out email address for {broker.name}. "
                           f"Find it on their privacy page"
                           + (f" ({broker.opt_out_url})" if broker.opt_out_url else "")
                           + " and add it to this broker, or send the request yourself.")
            db.add(AutomationLog(
                request_id=request.id, member_id=member.id, broker_id=broker.id,
                action="email_send", status="needs_manual",
                detail="No verified opt-out email address on record",
                duration_ms=0,
            ))

        elif broker.method == OptOutMethod.email:
            # Single exhaustive email covering all variants
            ok = send_opt_out_email(member, broker, key, script, cfg, db)
            if ok:
                successes += 1
                from .variant_report import record as _record_variants, identities_in_email
                _record_variants(db, request.id, identities_in_email(member))
            else:
                failures  += 1

            db.add(AutomationLog(
                request_id=request.id, member_id=member.id, broker_id=broker.id,
                action="email_send", status="success" if ok else "failure",
                detail=f"Exhaustive email: all {len(_get_values(member,'name',4))} name variants, "
                       f"{len(_get_values(member,'address',10))} addresses",
                duration_ms=int((time.monotonic() - start) * 1000),
            ))

        elif broker.method == OptOutMethod.form:
            key = _lookup_by(db, broker)
            if key in ("phone", "email"):
                from .combinations import build_keyed_optout_combos
                combos = build_keyed_optout_combos(member, key)
                if not combos:
                    needs_human = _missing_key_instruction(broker, member, key)
                log.info(f"{key} opt-out {broker.name} (member_id={member.id}): {len(combos)} {key}s")
            elif broker.is_property_broker:
                combos = build_property_optout_combos(member)
                log.info(f"Property form opt-out {broker.name} (member_id={member.id}): {len(combos)} combos")
            else:
                combos = build_optout_combos(member)
            log.info(f"Form opt-out {broker.name} (member_id={member.id}): {len(combos)} combos (unified declarative interpreter)")

            # Run through unified declarative interpreter engine. Each item is a
            # combination and, for sites where a listing is picked from search
            # results, the listing to go straight to (None = look it up).
            import json as _json
            picked = []
            if request.picked_enc:
                try:
                    picked = [u for u in _json.loads(request.picked_enc) if isinstance(u, str)]
                except Exception:
                    picked = []
            work = [(combos[0] if combos else None, u) for u in picked] if picked and combos else \
                [(c, None) for c in combos]
            if picked:
                request.picked_enc = None
                request.candidates_enc = None
            done_urls, not_listed_runs, runs = set(u for _, u in work if u), 0, 0
            while work:
                combo, preset_url = work.pop(0)
                runs += 1
                page = await context.new_page()
                try:
                    interp_res = await _run_form_via_interpreter(request, page, cfg, db, combo=combo,
                                                                 preset_listing_url=preset_url)
                    ok = interp_res.ok
                    # Listing picked from the site's search results (core/match_policy.py)
                    for u in getattr(interp_res, "extra_picks", None) or []:
                        if u not in done_urls:
                            done_urls.add(u)
                            work.append((combo, u))
                    if getattr(interp_res, "not_listed", False):
                        not_listed_runs += 1
                        continue
                    if getattr(interp_res, "skipped", False):
                        skipped_note = interp_res.detail or "skipped"
                        break
                    if getattr(interp_res, "candidates", None) and interp_res.needs_manual:
                        request.candidates_enc = _json.dumps(interp_res.candidates)
                        needs_human = interp_res.human_instruction
                        break
                    detail = interp_res.detail or ("ok" if ok else "form flow failed")
                    if ok and interp_res.verified:
                        detail += " (the broker's page confirmed it)"
                    if ok:
                        successes += 1
                        from .variant_report import record as _record_variants, identities_for_combo
                        _record_variants(db, request.id, identities_for_combo(member, combo))
                    else:
                        failures  += 1

                    screenshot_path = None
                    if interp_res.needs_captcha:
                        last_error = "captcha challenge encountered"
                        ch = interp_res.challenge or {}
                        if ch.get("screenshot"):
                            try:
                                os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
                                ts = int(time.time())
                                bname = broker.name.replace(".", "_").replace(" ", "_")
                                screenshot_path = f"{SCREENSHOTS_DIR}/captcha_{bname}_{ts}.png"
                                with open(screenshot_path, "wb") as sf:
                                    sf.write(ch["screenshot"])
                            except Exception as _se:
                                log.warning("Could not write captcha screenshot: %s", _se)

                        from ..models.database import CaptchaChallenge
                        existing_ch = db.query(CaptchaChallenge).filter(
                            CaptchaChallenge.request_id == request.id,
                            CaptchaChallenge.status == "pending"
                        ).first()
                        if not existing_ch:
                            c_entry = CaptchaChallenge(
                                request_id=request.id,
                                broker_id=broker.id,
                                member_id=member.id,
                                challenge_type=ch.get("type", "other") or "other",
                                site_key=ch.get("site_key") or None,
                                page_url=ch.get("page_url") or broker.opt_out_url or None,
                                screenshot=screenshot_path,
                                status="pending",
                                # which combination was being sent, so a person can
                                # pick it up live from the same point (encrypted)
                                combo_enc=__import__("json").dumps(combo.as_dict()),
                            )
                            db.add(c_entry)
                            db.commit()
                            db.refresh(c_entry)
                            try:
                                from ..plugins.hooks import fire_event
                                # No names or page addresses go to plugins.
                                fire_event("captcha_challenge_detected", entity_id=str(c_entry.id), data={
                                    "broker": broker.name, "member_id": member.id,
                                    "challenge_type": c_entry.challenge_type,
                                })
                            except Exception:
                                pass

                        request.notes = ("Stopped at a CAPTCHA (the site asked to prove a person is there). "
                                         "Open it from the CAPTCHAs page and finish the opt-out there")
                        if getattr(interp_res, "contact_email", ""):
                            request.notes += (f". If you finish it on the site yourself, give "
                                              f"{interp_res.contact_email} as the email address, so "
                                              f"OpenOptOut can match the reply and click any confirmation link.")

                    # A spec's pause_for_human step: the flow reached a point
                    # only a person can do (pick their listing, answer a phone
                    # call). Not a failure — it becomes a checklist item.
                    human_pause = (interp_res.needs_manual and not ok
                                   and not interp_res.needs_captcha)
                    if human_pause:
                        failures -= 1
                        needs_human = interp_res.human_instruction or (
                            f"Finish the opt-out for {broker.name} yourself"
                            + (f" at {broker.opt_out_url}" if broker.opt_out_url else "") + ".")

                    db.add(AutomationLog(
                        request_id=request.id, member_id=member.id, broker_id=broker.id,
                        action=("captcha_blocked" if interp_res.needs_captcha
                                else "human_step" if human_pause else "form_fill"),
                        status=("captcha" if interp_res.needs_captcha
                                else "needs_manual" if human_pause
                                else ("success" if ok else "failure")),
                        detail=f"[interpreter] {combo.masked_label()}: {detail}",
                        screenshot=screenshot_path,
                        duration_ms=int((time.monotonic() - start) * 1000),
                    ))
                    db.commit()

                    if interp_res.needs_captcha:
                        log.warning(f"CAPTCHA on {broker.name} — pausing execution for human")
                        break
                    if human_pause:
                        log.info("%s needs a person to finish — added to checklist", broker.name)
                        break

                    delay = cfg.get("automation", {}).get("inter_submission_delay_seconds", 1.5)
                    await asyncio.sleep(delay)
                finally:
                    await page.close()

        elif broker.method in (OptOutMethod.manual, OptOutMethod.phone):
            # Nothing was sent: a person has to do this one. It goes on the
            # checklist with the steps, instead of being counted as sent.
            needs_human = _manual_instruction(request, broker, member, cfg, db)
            db.add(AutomationLog(
                request_id=request.id, member_id=member.id, broker_id=broker.id,
                action="manual_queue", status="needs_manual",
                detail=f"Needs a person ({broker.method})",
                duration_ms=0,
            ))

    except Exception as e:
        log.error(f"execute_optout error {broker.name}: {e}")
        last_error = str(e)
        failures += 1

    # Update request status
    if successes > 0:
        request.status    = RequestStatus.sent
        request.sent_at   = datetime.utcnow()
        recheck_days      = cfg.get("scheduler", {}).get("recheck_interval_days", 90)
        request.recheck_after = datetime.utcnow() + timedelta(days=recheck_days)
        # A form stays "sent" even when the broker's page said "received":
        # that's an accepted request, not a removal. It becomes confirmed when
        # the broker writes back, its confirmation link is clicked, or a person
        # checks the listing is gone.
    elif "captcha" in (last_error or "").lower():
        # Keep in pending status with paused note so operator can resolve challenge
        request.status = RequestStatus.pending
    elif skipped_note:
        request.status = RequestStatus.skipped
        request.notes = skipped_note
    elif runs and not_listed_runs == runs:
        # The site's search shows nobody who could be this person.
        request.status = RequestStatus.skipped
        request.last_verdict = "not_found"
        request.notes = f"{broker.name}'s search didn't show anyone who could be {member.full_name}."
    elif needs_human:
        request.status = RequestStatus.needs_manual
        request.notes = needs_human
    else:
        request.status = RequestStatus.failed

    request.request_key = key
    request.updated_at  = datetime.utcnow()
    db.commit()

    # Record broker health (never let this break the pipeline). A run of
    # consecutive failures here is what auto-disables a broken broker.
    try:
        from .broker_health import record_success, record_failure
        if successes > 0:
            record_success(db, broker.id)
        elif (needs_human or skipped_note or (runs and not_listed_runs == runs)) and failures <= 0:
            pass  # waiting on a person, skipped on purpose, or not listed: not a broker malfunction
        else:
            record_failure(db, broker.id, detail=last_error or "opt-out failed")
    except Exception as e:
        log.error("broker health tracking failed for %s: %s", broker.name, e)

    # Notify plugins of the outcome (fire-and-forget, never blocks the pipeline)
    try:
        from ..plugins.hooks import fire_event
        fire_event(
            "optout_sent" if successes > 0 else "optout_failed",
            entity_id=str(request.id),
            data={"broker": broker.name, "broker_id": str(broker.id),
                  "member_id": str(member.id), "successes": str(successes),
                  "failures": str(failures)},
        )
    except Exception:
        pass

    log.info(f"Opt-out {broker.name} (member_id={member.id}): {successes} ok, {failures} failed")
    return successes > 0


async def run_optout_batch(request_ids: list[int]) -> dict:
    db  = SessionLocal()
    cfg = load_settings()
    sent = failed = skipped = 0
    errors = []

    try:
        async with async_playwright() as p:
            browser, _ = await _launch_browser(p)
            try:
                for req_id in request_ids:
                    req = db.query(RemovalRequest).filter(RemovalRequest.id == req_id).first()
                    if not req or req.status != RequestStatus.pending:
                        skipped += 1; continue
                    # Skip brokers that are disabled (by an admin or auto-disabled
                    # by the health monitor) — a broken broker never crashes or
                    # slows a run; it's quietly passed over until reviewed.
                    from .broker_gate import request_allowed
                    if req.broker and not request_allowed(req, db):
                        skipped += 1
                        log.info("Skipping disabled broker %s (request %s)",
                                 req.broker.name, req_id)
                        continue
                    # Fresh context (new UA) per request/broker
                    context = await _fresh_context(browser)
                    try:
                        ok = await execute_optout(req, context, cfg, db)
                        if ok: sent   += 1
                        else:  failed += 1
                    except Exception as e:
                        errors.append(f"Request {req_id}: {e}")
                        failed += 1
                    finally:
                        await context.close()
                    await asyncio.sleep(2)
            finally:
                await browser.close()
    except Exception as e:
        errors.append(str(e))
    finally:
        db.close()

    return {"sent": sent, "failed": failed, "skipped": skipped, "errors": errors}
