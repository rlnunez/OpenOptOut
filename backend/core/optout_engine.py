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

    if script and script.email_subject_tpl:
        subject = script.email_subject_tpl.format(
            name=primary_name, request_key=request_key, broker=broker.name
        )
    else:
        subject = f"Personal Data Removal Request — {primary_name} [Ref: {request_key}]"

    if script and script.email_body_tpl:
        body = script.email_body_tpl.format(
            name=primary_name, request_key=request_key, broker=broker.name
        )
    else:
        name_block    = "\n".join(f"  - {n}" for n in names)
        address_block = "\n".join(f"  - {a}" for a in addresses)
        phone_block   = "\n".join(f"  - {p}" for p in phones) if phones else "  (none provided)"
        email_block   = "\n".join(f"  - {e}" for e in emails) if emails else "  (none provided)"

        prop_note = ""
        if broker.is_property_broker and member.formal_name:
            deed_addrs = [i.value for i in member.identities if i.kind == "address" and i.is_deed]
            mtg_addrs  = [i.value for i in member.identities if i.kind == "address" and i.is_mortgage]
            prop_note  = f"""
NOTE — PROPERTY RECORDS REQUEST:
The legal name recorded on county documents is: {member.formal_name}
{"Deed address(es): " + ", ".join(deed_addrs) if deed_addrs else ""}
{"Mortgage address(es): " + ", ".join(mtg_addrs) if mtg_addrs else ""}
Please remove all property records, deed records, and mortgage records \
associated with the above name and addresses.
"""

        body = f"""To Whom It May Concern,

I am writing to request the complete removal of ALL personal information \
associated with any of the following identifiers from your databases, \
website, and any affiliated or downstream services.
{prop_note}
Please search for and remove records matching ANY of the following:

NAME VARIANTS:
{name_block}

ADDRESSES (current and historical):
{address_block}

PHONE NUMBERS:
{phone_block}

EMAIL ADDRESSES:
{email_block}

This is a comprehensive removal request covering ALL records associated \
with the above identifiers, not just the most recent or primary record. \
Please do not selectively remove only one listing while retaining others.

If you are subject to the California Consumer Privacy Act (CCPA, Cal. Civ. \
Code § 1798.105), I am exercising my right to deletion. Please confirm \
complete removal within 45 days as required by law.

If you are subject to GDPR, I am invoking my right to erasure under \
Article 17. Please confirm within 30 days.

Reference ID (include in all correspondence): {request_key}

Thank you,
{primary_name}
"""

    return subject, body


def _extract_email_from_notes(notes: Optional[str]) -> Optional[str]:
    if not notes: return None
    m = re.search(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', notes)
    return m.group(0) if m else None


def send_opt_out_email(
    member: FamilyMember,
    broker: Broker,
    request_key: str,
    script: Optional[BrokerScript],
    cfg: dict,
    db,
) -> bool:
    ec         = cfg.get("email", {})
    smtp_host  = ec.get("smtp_host")
    smtp_port  = ec.get("smtp_port", 587)
    smtp_user  = ec.get("smtp_user")
    smtp_pw    = decrypt_password(ec.get("smtp_password_enc", ""))
    from_name  = ec.get("from_name", "PrivacyShield Removals")
    from_email = ec.get("from_email") or smtp_user
    to_email   = _extract_email_from_notes(broker.notes) or \
        f"privacy@{broker.name.lower().replace(' ','').rstrip('.com')}.com"

    if not smtp_host or not smtp_pw:
        log.error("SMTP not configured")
        return False

    subject, body = _build_exhaustive_email(member, broker, request_key, script)

    msg             = MIMEMultipart("alternative")
    msg["Subject"]  = subject
    msg["From"]     = f"{from_name} <{from_email}>"
    msg["To"]       = to_email
    msg["Reply-To"] = from_email
    msg.attach(MIMEText(body, "plain"))

    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP(smtp_host, smtp_port) as s:
            if ec.get("smtp_tls", True):
                s.starttls(context=ctx)
            s.login(smtp_user, smtp_pw)
            s.sendmail(from_email, [to_email], msg.as_string())

        db.add(EmailLog(
            request_id=None, direction="sent",
            subject=subject, body_snippet=body[:500],
            matched_key=request_key,
        ))
        db.commit()
        log.info(f"Email opt-out sent: {broker.name} / {member.full_name} → {to_email}")
        return True

    except Exception as e:
        log.error(f"SMTP send failed for {broker.name}: {e}")
        return False


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
    subject_prefix: e.g. "[PrivacyShield TEST] " for test sends.
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
        locale=parent.locale or "en", state="",
        request_key=request_key,
    )
    subject = (subject_prefix or "") + composed.subject
    detail.update({"cc": list(composed.cc), "subject": subject,
                   "child_sites": len(child_sites)})

    # Transport-agnostic send (provider plugin w/ auto-refresh, or SMTP fallback).
    from ..routers.email_oauth import active_account_ref
    result = send_email(
        cfg, to=[composed.to], cc=list(composed.cc),
        subject=subject, body=composed.body,
        account_ref=active_account_ref(cfg),
        from_address=ec.get("from_address", ""),
    )
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
        log.info("Parent opt-out sent via %s: %s / %s -> %s (%d child sites, key=%s)",
                 detail["via"], parent.name, member.full_name, to_email, len(child_sites), matched_key)
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

        for req in pending_requests:
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
        # Skip disabled or test brokers
        if not req.broker.enabled or getattr(req.broker, "is_test", False):
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



# ── Form fill — one combo at a time ──────────────────────────────────────────

async def _fill_one_combo(
    page: Page,
    combo: IdentityCombo,
    broker: Broker,
    request_key: str,
    script: Optional[BrokerScript],
) -> tuple[bool, Optional[str]]:
    """Fill and submit the opt-out form for a single identity combo."""
    opt_url = broker.opt_out_url
    if not opt_url:
        return False, None

    screenshot = None
    try:
        await page.goto(opt_url, timeout=20_000)
        await page.wait_for_timeout(2000)

        async def try_fill(selector: Optional[str], value: Optional[str], field: str):
            if not selector or not value: return
            try:
                el = await page.query_selector(selector)
                if el: await el.fill(value)
            except Exception as e:
                log.debug(f"Fill {field}: {e}")

        if script:
            # Try to fill name as first+last if separate selectors exist
            first_sel = await page.query_selector("input[name='firstName'], input[id*='first' i]")
            last_sel  = await page.query_selector("input[name='lastName'],  input[id*='last' i]")
            parts = combo.name.split()
            if first_sel and last_sel and len(parts) >= 2:
                await first_sel.fill(parts[0])
                await last_sel.fill(" ".join(parts[1:]))
            else:
                await try_fill(script.name_selector, combo.name, "name")

            await try_fill(script.email_selector,   combo.email,   "email")
            await try_fill(script.address_selector, combo.address, "address")
            await try_fill(script.city_selector,    combo.city,    "city")
            await try_fill(script.zip_selector,     combo.zip,     "zip")

            if script.state_selector and combo.state:
                el = await page.query_selector(script.state_selector)
                if el:
                    try:    await el.select_option(value=combo.state)
                    except: await el.fill(combo.state)

            # Extra steps
            if script.extra_steps:
                try:
                    for step in json.loads(script.extra_steps):
                        a, sel, val = step.get("action"), step.get("selector"), step.get("value","")
                        el = await page.query_selector(sel) if sel else None
                        if a == "click"  and el: await el.click()
                        elif a == "fill" and el: await el.fill(val)
                        elif a == "wait":        await page.wait_for_timeout(int(val) if val else 1000)
                        elif a == "select" and el:
                            try:    await el.select_option(value=val)
                            except: await el.fill(val)
                except Exception as e:
                    log.warning(f"Extra steps error {broker.name}: {e}")

            if script.submit_selector:
                submit = await page.query_selector(script.submit_selector)
                if submit:
                    await submit.click()
                    await page.wait_for_timeout(3000)
        else:
            # Generic fallback
            parts = combo.name.split()
            first = await page.query_selector("input[name='firstName'], input[id*='first' i]")
            last  = await page.query_selector("input[name='lastName'],  input[id*='last' i]")
            full  = await page.query_selector("input[name='name'],      input[id*='fullname' i]")

            if first and last and len(parts) >= 2:
                await first.fill(parts[0])
                await last.fill(" ".join(parts[1:]))
            elif full:
                await full.fill(combo.name)

            if combo.email:
                el = await page.query_selector("input[type='email'], input[name='email']")
                if el: await el.fill(combo.email)

            submit = await page.query_selector(
                "button[type='submit'], input[type='submit'], "
                "button:has-text('Opt Out'), button:has-text('Remove'), "
                "button:has-text('Submit'), button:has-text('Request Removal')"
            )
            if submit:
                await submit.click()
                await page.wait_for_timeout(3000)

        # CAPTCHA check
        captcha = await page.query_selector(
            "iframe[src*='recaptcha'], iframe[src*='hcaptcha'], "
            ".g-recaptcha, .h-captcha, [data-sitekey]"
        )
        if captcha:
            screenshot = await _screenshot(page, f"captcha_{broker.name.replace('.','_')}")
            return False, screenshot

        # Success check
        content = await page.content()
        if script:
            if script.success_selector:
                el = await page.query_selector(script.success_selector)
                if el: return True, None
            if script.success_text and script.success_text.lower() in content.lower():
                return True, None

        success_phrases = [
            "successfully submitted", "opt-out request received",
            "removal request", "your request has been",
            "will be removed", "opt out complete", "request confirmed",
        ]
        if any(p in content.lower() for p in success_phrases):
            return True, None

        screenshot = await _screenshot(page, f"uncertain_{broker.name.replace('.','_')}")
        return True, screenshot   # optimistic — no clear error

    except PWTimeout:
        screenshot = await _screenshot(page, f"timeout_{broker.name.replace('.','_')}")
        return False, screenshot
    except Exception as e:
        screenshot = await _screenshot(page, f"error_{broker.name.replace('.','_')}")
        log.error(f"Form fill error {broker.name}: {e}")
        return False, screenshot


# ── Full opt-out for one request (all combos) ─────────────────────────────────

async def _run_form_via_interpreter(request, context, cfg, db) -> "tuple[bool, str] | None":
    """
    Run a form opt-out through the NEW interpreter engine: build a BrokerSpec from
    the broker's stored script, compile it for the member, and execute it through
    PlaywrightExecutor with the plugin manager's CAPTCHA-solver and fill_form
    dispatchers wired in. This is what makes the plugin hooks (items 3 & 4)
    actually fire during real runs.

    Returns (ok, detail) if the interpreter handled it, or None to signal the
    caller should fall back to the legacy combo engine (no usable spec).
    """
    from .interpreter import compile_job, PlaywrightExecutor
    from .interpreter.script_bridge import spec_from_script
    from .combinations import _get_values

    broker = request.broker
    member = request.member
    script = db.query(BrokerScript).filter(BrokerScript.broker_id == broker.id).first()

    spec = spec_from_script(broker, script)
    if spec is None:
        return None  # fall back to legacy engine

    # Resolve the member's field values for the compiler (first of each kind).
    def first(kind):
        vals = _get_values(member, kind, 1)
        return vals[0] if vals else ""
    member_fields = {
        "full_name": member.full_name or first("name"),
        "first_name": (member.full_name or "").split(" ")[0] if member.full_name else "",
        "last_name": (member.full_name or "").split(" ")[-1] if member.full_name else "",
        "email": first("email"), "phone": first("phone"),
        "address": first("address"), "city": "", "state": "", "zip": "",
    }

    try:
        job = compile_job(spec, member_fields, member_id=str(member.id))
    except Exception as e:
        log.info("interpreter compile failed for %s (%s) — legacy fallback", broker.name, e)
        return None

    # Wire the plugin manager's dispatchers into the executor so the CAPTCHA
    # solver + fill_form takeover hooks fire. If no manager/plugins, these are
    # None and the executor cleanly pauses/uses defaults.
    captcha_solver = None
    form_handler = None
    try:
        from ..plugins import get_manager
        mgr = get_manager()
        if mgr:
            captcha_solver = lambda ch: mgr.dispatch_solve_captcha(ch)
            def form_handler(job_, page_html):
                # Pass a provider, not the raw values: the manager materializes
                # real member fields ONLY for a plugin that holds read_pii;
                # unpermitted plugins get a redacted (keys-only) view and the
                # raw PII never reaches them. Defense-in-depth at the boundary.
                return mgr.dispatch_fill_form(
                    {"id": broker.id, "name": broker.name,
                     "opt_out_url": broker.opt_out_url or "",
                     "meta": {"method": str(broker.method), "difficulty": str(broker.difficulty)}},
                    page_html,
                    fields_provider=lambda: dict(member_fields),
                )
    except Exception as e:
        log.debug("plugin dispatchers unavailable: %s", e)

    page = await context.new_page()
    try:
        executor = PlaywrightExecutor(
            page=page, captcha_solver=captcha_solver, plugin_form_handler=form_handler)
        res = await executor.run(job)
        return (res.ok, res.detail or ("ok" if res.ok else "form flow failed"))
    finally:
        await page.close()


async def execute_optout(
    request: RemovalRequest,
    context: BrowserContext,
    cfg: dict,
    db,
) -> bool:
    """
    Fire opt-out for ONE RemovalRequest using the full combination matrix.
    - email brokers: one exhaustive email covering all variants
    - form brokers:  submit form for every name×address×phone×email combo
    - manual:        queue and mark sent
    Returns True if at least one submission succeeded.
    """
    start  = time.monotonic()
    member = request.member
    broker = request.broker
    script = db.query(BrokerScript).filter(BrokerScript.broker_id == broker.id).first()
    key    = request.request_key or str(uuid.uuid4())

    successes = 0
    failures  = 0
    last_error = ""   # captured for broker-health failure classification

    try:
        if broker.method == OptOutMethod.email:
            # Single exhaustive email covering all variants
            # For property brokers, _build_exhaustive_email will include formal name prominently
            ok = send_opt_out_email(member, broker, key, script, cfg, db)
            if ok: successes += 1
            else:  failures  += 1

            db.add(AutomationLog(
                request_id=request.id, member_id=member.id, broker_id=broker.id,
                action="email_send", status="success" if ok else "failure",
                detail=f"Exhaustive email: all {len(_get_values(member,'name',4))} name variants, "
                       f"{len(_get_values(member,'address',10))} addresses",
                duration_ms=int((time.monotonic() - start) * 1000),
            ))

        elif broker.method == OptOutMethod.form:
            # Try the NEW interpreter engine first (this is where the CAPTCHA
            # solver + fill_form plugin hooks fire). Falls back to the legacy
            # combination-matrix engine if the broker has no usable spec/script.
            interp = await _run_form_via_interpreter(request, context, cfg, db)
            if interp is not None:
                ok, detail = interp
                if ok: successes += 1
                else:  failures  += 1
                if not ok and "captcha" in (detail or "").lower():
                    last_error = "captcha challenge encountered"
                db.add(AutomationLog(
                    request_id=request.id, member_id=member.id, broker_id=broker.id,
                    action="form_fill", status="success" if ok else "failure",
                    detail=f"[interpreter] {detail}",
                    duration_ms=int((time.monotonic() - start) * 1000),
                ))
                db.commit()
            else:
                # Legacy combination-matrix engine (unchanged).
                if broker.is_property_broker:
                    combos = build_property_optout_combos(member)
                    log.info(f"Property form opt-out {broker.name} / {member.full_name}: {len(combos)} combos (formal name: {member.formal_name or 'not set'})")
                else:
                    combos = build_optout_combos(member)
                log.info(f"Form opt-out {broker.name} / {member.full_name}: {len(combos)} combos (legacy engine)")

                for combo in combos:
                    page = await context.new_page()
                    try:
                        ok, shot = await _fill_one_combo(page, combo, broker, key, script)
                        if ok: successes += 1
                        else:  failures  += 1

                        db.add(AutomationLog(
                            request_id=request.id, member_id=member.id, broker_id=broker.id,
                            action="form_fill",
                            status="success" if ok else ("captcha" if shot and "captcha" in (shot or "") else "failure"),
                            detail=combo.label(),
                            screenshot=shot,
                            duration_ms=int((time.monotonic() - start) * 1000),
                        ))
                        db.commit()

                        # Stop if CAPTCHA detected — no point continuing
                        if shot and "captcha" in (shot or ""):
                            log.warning(f"CAPTCHA on {broker.name} — stopping combo loop")
                            last_error = "captcha challenge encountered"
                            break

                        # Configurable inter-submission delay (bot-evasion)
                        delay = cfg.get("automation", {}).get("inter_submission_delay_seconds", 1.5)
                        await asyncio.sleep(delay)
                    finally:
                        await page.close()

        elif broker.method in (OptOutMethod.manual, OptOutMethod.phone):
            successes = 1
            db.add(AutomationLog(
                request_id=request.id, member_id=member.id, broker_id=broker.id,
                action="manual_queue", status="success",
                detail=f"Queued for manual action ({broker.method})",
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

    log.info(f"Opt-out {broker.name} / {member.full_name}: {successes} ok, {failures} failed")
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
                    if req.broker and (not req.broker.enabled or getattr(req.broker, "is_test", False)):
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
