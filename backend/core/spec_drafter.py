"""
Drafting and repairing broker opt-out steps automatically.

Two jobs:

  new brokers   For a broker nobody wrote steps for, look at its public
                opt-out page (found by core/privacy_finder.py) and ask an AI
                helper (core/ai_helpers.py) to draft steps.
  repairs       When a broker's steps stop finding things on its page
                (broker_health classifies the failure as form_not_found),
                rehearse the current steps to see where they now break, move
                the step to the matching field or button by its label (the
                built-in rules), and only if that isn't enough, ask an AI helper.

Every draft is rehearsed before anyone relies on it (rehearse()):

  * the steps run in a fresh headless browser with MADE-UP details
    (FAKE_PERSON, an @example.invalid address), never a family member's;
  * the run stops before the final click that would send the request, and
    before any CAPTCHA; that last button is only checked to be on the page;
  * the result is a screenshot of the form filled with the made-up details,
    and a step-by-step trace.

Then (decide()):

  * a new broker's draft always waits for an admin ("ready");
  * a repair that passed its rehearsal and changes nothing but where steps
    find things on the page (selectors, timeouts) applies itself ("applied")
    when the admin allows it (ai_helpers auto_apply_repairs), and the admin
    is told on Broker updates; anything else waits for approval.

An applied or approved draft is used instead of the plugin's own steps
(interpreter/script_bridge.get_or_build_broker_spec), until an admin reverts
it or the plugin is updated.

What an AI helper sees is the public page and the steps, checked for every
saved personal detail before it is sent (blocked_values, ai_helpers.check_outgoing).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlparse

log = logging.getLogger(__name__)

SCREENSHOTS_DIR = os.path.join(os.getenv("DATA_DIR", "/data"), "screenshots", "rehearsals")
MAX_RULE_PASSES = 5
REPAIR_COOLDOWN = timedelta(hours=24)
REHEARSAL_DOMAIN_SUFFIX = "example.invalid"

# Made-up details for rehearsals. Nothing here belongs to anyone.
FAKE_PERSON = {
    "first_name": "Jordan", "last_name": "Example", "full_name": "Jordan Example",
    "formal_name": "Jordan A Example", "email": "jordan.example@example.invalid",
    "contact_email": "rehearsal@example.invalid", "phone": "(555) 010-0199",
    "phone_digits": "5550100199", "phone_e164": "+15550100199", "phone_dashed": "555-010-0199",
    "address": "100 Example Street, Springfield, IL 62701", "street": "100 Example Street",
    "city": "Springfield", "state": "IL", "state_name": "Illinois", "zip": "62701",
    "age": "40", "age_range": "40-49", "birth_year": "1986", "dob": "01/15/1986",
    "dob_iso": "1986-01-15", "birth_month": "01", "birth_day": "15", "relatives": "",
    "listing_url": "https://example.invalid/listing/0", "all_phones": "(555) 010-0199",
    "all_emails": "jordan.example@example.invalid",
}
SUBMITTING = {"submit", "click", "click_matching", "press"}
FILLING = {"fill", "type", "select", "check", "autofill"}
SUBMIT_WORDS = re.compile(r"submit|send|remove|opt[\s_-]*out|delete|request|continue|next|confirm", re.I)
AGREE_WORDS = re.compile(r"agree|certif|confirm|attest|accept|acknowledg|i am", re.I)
SENSITIVE_FIELDS = {"dob", "dob_iso", "birth_month", "birth_day"}
# Things an admin should check in a draft (translated on the page, like REHEARSAL_TEXTS).
WARNING_TEXTS = {
    "low": "The helper wasn't confident about these steps.",
    "dob": "These steps give the broker a date of birth. Check the form really requires it.",
    "no_instructions": "A guided opt-out without instructions for the person.",
}
# How a rehearsal ended, shown on the Automatic broker steps page (and
# translated there: scripts/extract_page_texts.py reads this).
REHEARSAL_TEXTS = {
    "captcha": "Reached the CAPTCHA, which a rehearsal doesn't solve.",
    "person": "Reached the point where a person takes over.",
    "confirmation": "Reached the confirmation check.",
    "stopped": "Stopped before the final click, which is on the page.",
    "all": "All steps ran.",
    "guided": "A guided opt-out: nothing to rehearse.",
}


# ── Personal details that must never leave ───────────────────────────────────

def blocked_values(db) -> list:
    """Every saved name, email, phone number and address, to keep out of
    anything sent to an AI helper."""
    from ..models.database import Identity, FamilyMember
    out = set()
    try:
        for (v,) in db.query(Identity.value).all():
            if v:
                out.add(str(v))
        for m in db.query(FamilyMember).all():
            for v in (getattr(m, "full_name", None), getattr(m, "formal_name", None)):
                if v:
                    out.add(str(v))
    except Exception as e:
        log.warning("couldn't list saved details for the AI check: %s", e)
        raise
    return sorted(out)


# ── Looking at a page ─────────────────────────────────────────────────────────

_MAP_JS = r"""(probe) => {
  const txt = (n) => (n ? (n.innerText || n.textContent || '') : '').replace(/\s+/g, ' ').trim();
  const vis = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length)
                      && getComputedStyle(el).visibility !== 'hidden';
  const sel = (el) => {
    const q = (v) => v.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
    if (el.id && /^[A-Za-z][\w-]*$/.test(el.id)) return '#' + el.id;
    const tag = el.tagName.toLowerCase();
    if (el.name) return tag + '[name="' + q(el.name) + '"]';
    if (el.getAttribute('aria-label')) return tag + '[aria-label="' + q(el.getAttribute('aria-label')) + '"]';
    const parts = [];
    let n = el;
    for (let depth = 0; n && n.nodeType === 1 && depth < 5; depth++) {
      if (n.id && /^[A-Za-z][\w-]*$/.test(n.id)) { parts.unshift('#' + n.id); break; }
      const t = n.tagName.toLowerCase();
      const sib = n.parentElement ? Array.from(n.parentElement.children).filter(c => c.tagName === n.tagName) : [n];
      parts.unshift(sib.length > 1 ? t + ':nth-of-type(' + (sib.indexOf(n) + 1) + ')' : t);
      n = n.parentElement;
    }
    return parts.join(' > ');
  };
  const label = (el) => {
    let l = '';
    if (el.id) { const f = document.querySelector('label[for="' + CSS.escape(el.id) + '"]'); if (f) l = txt(f); }
    if (!l) { const c = el.closest('label'); if (c) l = txt(c); }
    if (!l && el.getAttribute('aria-labelledby')) l = el.getAttribute('aria-labelledby').split(/\s+/).map(i => txt(document.getElementById(i))).join(' ');
    return l.slice(0, 160);
  };
  const fields = Array.from(document.querySelectorAll('input, select, textarea'))
    .filter(el => !['hidden', 'password', 'file'].includes((el.type || '').toLowerCase()) && vis(el))
    .slice(0, 80).map(el => ({
      selector: sel(el), tag: el.tagName.toLowerCase(), type: (el.type || '').toLowerCase(),
      name: el.name || '', id: el.id || '', label: label(el), aria: el.getAttribute('aria-label') || '',
      placeholder: el.getAttribute('placeholder') || '', autocomplete: el.getAttribute('autocomplete') || '',
      required: !!(el.required || el.getAttribute('aria-required') === 'true'),
      options: el.tagName === 'SELECT' ? Array.from(el.options).slice(0, 60).map(o => txt(o).slice(0, 60)) : []
    }));
  const buttons = Array.from(document.querySelectorAll('button, input[type=submit], input[type=button], [role=button]'))
    .filter(vis).slice(0, 40).map(el => ({selector: sel(el), text: (txt(el) || el.value || '').slice(0, 80),
                                          type: (el.type || '').toLowerCase()}));
  const links = Array.from(document.querySelectorAll('a[href]')).filter(vis)
    .map(a => ({text: txt(a).slice(0, 80), href: a.href}))
    .filter(l => /privacy|opt|remov|delet|suppress|do not sell|request|choices/i.test(l.text + ' ' + l.href)).slice(0, 30);
  const frames = Array.from(document.querySelectorAll('iframe')).map(f => f.src).filter(Boolean).slice(0, 10);
  const found = {};
  for (const s of (probe || [])) { try { found[s] = !!document.querySelector(s); } catch (e) { found[s] = false; } }
  return {url: location.href, title: document.title.slice(0, 200), fields, buttons, links, frames, found,
          text: txt(document.body).slice(0, 3000)};
}"""


def describe_page(pmap: dict) -> str:
    """The page map as compact text for an AI helper."""
    if not pmap:
        return "(no page)"
    lines = [f"Address: {pmap.get('url', '')}", f"Title: {pmap.get('title', '')}", "Form fields:"]
    for f in pmap.get("fields", []):
        bits = [f"{f['tag']}{'/' + f['type'] if f.get('type') else ''}", f"selector={f['selector']}"]
        for k in ("label", "placeholder", "aria", "autocomplete"):
            if f.get(k):
                bits.append(f"{k}={f[k]!r}")
        if f.get("required"):
            bits.append("required")
        if f.get("options"):
            bits.append("options=" + ", ".join(f["options"][:15]))
        lines.append("  - " + "; ".join(bits))
    lines.append("Buttons:")
    lines += [f"  - selector={b['selector']}; text={b['text']!r}" for b in pmap.get("buttons", [])]
    if pmap.get("links"):
        lines.append("Links about privacy:")
        lines += [f"  - {l['text']!r} -> {l['href']}" for l in pmap["links"]]
    if pmap.get("frames"):
        lines.append("Embedded frames: " + ", ".join(pmap["frames"]))
    lines.append("Page text (start): " + (pmap.get("text") or "")[:3000])
    return "\n".join(lines)


# ── Rehearsal ────────────────────────────────────────────────────────────────

def final_submit_index(steps) -> int:
    """Index of the click that sends the request: the last click/submit/press
    with no filling or navigating after it. -1 if there isn't one."""
    last = -1
    for i, s in enumerate(steps):
        if s.kind in SUBMITTING:
            last = i
        elif s.kind in FILLING or s.kind in ("navigate", "pick_listing"):
            last = -1
    return last


def _launch():
    """An async context manager for a browser; replaced in tests if needed."""
    from playwright.async_api import async_playwright
    return async_playwright()


async def _rehearse_async(spec, screenshot_path: str = "", timeout_ms: int = 15000) -> dict:
    from .interpreter.compiler import compile_job
    from .interpreter.executor import PlaywrightExecutor, NeedsPerson
    job = compile_job(spec, dict(FAKE_PERSON), member_id="rehearsal")
    stop = final_submit_index(job.steps)
    out = {"ok": False, "reached": 0, "total": len(job.steps), "stop": stop, "failed": None,
           "detail": "", "trace": [], "page_map": None, "screenshot": ""}
    async with _launch() as pw:
        browser = await pw.firefox.launch(headless=True)
        try:
            page = await browser.new_page()
            page.set_default_timeout(timeout_ms)
            ex = PlaywrightExecutor(page=page, secrets=[], unclear_policy="skip")
            for i, s in enumerate(job.steps):
                out["reached"] = i
                if s.kind in ("solve_captcha",):
                    out.update(ok=True, detail=REHEARSAL_TEXTS["captcha"])
                    break
                if s.kind in ("pause_for_human", "pick_listing"):
                    out.update(ok=True, detail=REHEARSAL_TEXTS["person"])
                    break
                if s.kind in ("expect_success",):
                    out.update(ok=True, detail=REHEARSAL_TEXTS["confirmation"])
                    break
                if i == stop:
                    found = await _probe_step(ex, s)
                    out.update(ok=found, failed=None if found else i,
                               detail=(REHEARSAL_TEXTS["stopped"] if found
                                       else f"the final button ({s.selector or s.text}) isn't on the page"))
                    break
                try:
                    paused = await ex._run_step(s, out["trace"], i)
                    if paused:
                        out.update(ok=True, detail=REHEARSAL_TEXTS["captcha"])
                        break
                except NeedsPerson as e:
                    out.update(failed=i, detail=f"step {i + 1} ({s.kind}) needs a person: {e}")
                    break
                except Exception as e:
                    if s.optional:
                        out["trace"].append(f"[{i}] {s.kind} optional, skipped: {str(e)[:120]}")
                        continue
                    out.update(failed=i, detail=f"step {i + 1} ({s.kind}) failed: {str(e).splitlines()[0][:200]}")
                    break
            else:
                out.update(ok=True, reached=len(job.steps), detail=REHEARSAL_TEXTS["all"])
            probe = [x.selector for x in job.steps if x.selector and x.kind != "frame"]
            try:
                out["page_map"] = await page.evaluate(_MAP_JS, probe)
            except Exception as e:
                out["trace"].append(f"page description failed: {e}")
            if screenshot_path:
                try:
                    os.makedirs(os.path.dirname(screenshot_path), exist_ok=True)
                    await page.screenshot(path=screenshot_path)
                    out["screenshot"] = screenshot_path
                except Exception as e:
                    out["trace"].append(f"screenshot failed: {e}")
        finally:
            await browser.close()
    out["trace"] = [str(t)[:300] for t in out["trace"]][-60:]
    return out


async def _probe_step(ex, s) -> bool:
    try:
        tgt = ex._target()
        if s.kind == "click_matching" and s.text:
            loc = tgt.locator(s.selector or "button, a, input[type=submit], [role=button]").filter(has_text=s.text)
        elif s.kind == "press":
            return True
        else:
            loc = tgt.locator(s.selector)
        return await loc.count() > 0
    except Exception:
        return False


def rehearse(spec, screenshot_path: str = "") -> dict:
    """Run `spec` with made-up details up to (not including) the final click.

    Returns {ok, reached, total, stop, failed, detail, trace, page_map, screenshot}.
    `page_map` describes the page where the rehearsal ended (where it failed,
    for a broken step)."""
    try:
        return asyncio.run(_rehearse_async(spec, screenshot_path))
    except RuntimeError as e:
        if "running event loop" not in str(e):
            raise
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(1) as pool:
            return pool.submit(lambda: asyncio.run(_rehearse_async(spec, screenshot_path))).result()


def page_map(url: str) -> dict:
    """Describe a public page without typing anything into it."""
    from .interpreter.broker_spec import BrokerSpec, Step
    spec = BrokerSpec(broker_id="look", name="look", method="form", opt_out_url=url,
                      steps=[Step(kind="navigate", url=url, timeout_ms=30000), Step(kind="wait", timeout_ms=2500)])
    return rehearse(spec).get("page_map") or {}


# ── The built-in rules: find a moved field or button by its label ────────────

def _field_rx(field: str):
    from .interpreter.hosted_forms import _FIELDS
    want = "contact_email" if field in ("email", "contact_email") else field
    for name, rx, acs in _FIELDS:
        if name == want:
            return rx, acs
    return None, ()


def relocate(step, pmap: dict) -> Optional[str]:
    """A new selector for a step whose element moved, found by meaning on
    the page described by `pmap`, or None when there isn't exactly one match."""
    fields = pmap.get("fields", []) if pmap else []
    if step.kind in ("fill", "type", "select") and step.field:
        rx, acs = _field_rx(step.field)
        if rx is None:
            return None
        hits = [f for f in fields
                if f.get("autocomplete") in acs or any(rx.search(f.get(k) or "") for k in
                                                       ("label", "name", "id", "placeholder", "aria"))]
        if step.kind == "select":
            hits = [f for f in hits if f["tag"] == "select"]
        else:
            hits = [f for f in hits if f["tag"] in ("input", "textarea") and f["type"] not in ("checkbox", "radio")]
        return hits[0]["selector"] if len(hits) == 1 else None
    if step.kind == "check":
        hits = [f for f in fields if f["type"] == "checkbox" and AGREE_WORDS.search(f.get("label") or "")]
        return hits[0]["selector"] if len(hits) == 1 else None
    if step.kind in ("click", "submit", "click_matching"):
        buttons = pmap.get("buttons", []) if pmap else []
        if step.text:
            hits = [b for b in buttons if step.text.lower() in (b.get("text") or "").lower()]
        else:
            hits = [b for b in buttons if SUBMIT_WORDS.search(b.get("text") or "") or b.get("type") == "submit"]
        return hits[0]["selector"] if len(hits) == 1 else None
    return None


def rule_repair(spec, failed_index: int, pmap: dict):
    """A copy of `spec` with the failed step pointed at its new place, or None."""
    import copy
    if failed_index is None or failed_index >= len(spec.steps):
        return None
    step = spec.steps[failed_index]
    new_sel = relocate(step, pmap)
    if not new_sel or new_sel == step.selector:
        return None
    fixed = copy.deepcopy(spec)
    fixed.steps[failed_index].selector = new_sel
    if fixed.steps[failed_index].kind == "click_matching":
        fixed.steps[failed_index].text = ""
        fixed.steps[failed_index].kind = "click"
    return fixed


def selector_only_change(old, new) -> bool:
    """True when `new` differs from `old` only in where steps find things
    (selector, timeouts, optional waits) — never in what is typed, which
    details are used, where it goes, or what a person is told."""
    if old is None or new is None or len(old.steps) != len(new.steps):
        return False
    if (old.method, old.success_text, old.opt_out_url) != (new.method, new.success_text, new.opt_out_url):
        return False
    for a, b in zip(old.steps, new.steps):
        same_kind = a.kind == b.kind or {a.kind, b.kind} <= {"click", "click_matching"}
        if not same_kind or a.field != b.field or a.value != b.value or a.url != b.url:
            return False
        if a.kind == "pause_for_human" and a.text != b.text:
            return False
        if a.kind == "click_matching" and b.kind == "click_matching" and a.text != b.text and b.text:
            return False
    return True


# ── Checking a draft from an AI helper ───────────────────────────────────────

def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def build_spec(draft: dict, broker, allowed_hosts: set):
    """BrokerSpec from an AI draft, plus warnings for the admin.
    Raises ValueError for a draft that may not be used at all."""
    from .interpreter.broker_spec import BrokerSpec
    from .privacy_finder import hosted_kind
    from .listing_finder import registrable_domain
    steps = []
    for st in draft.get("steps") or []:
        d = {k: st.get(k) for k in ("kind", "selector", "field", "value", "url", "text", "optional")
             if st.get(k) not in (None, "")}
        steps.append(d)
    slug = re.sub(r"[^a-zA-Z0-9_-]", "_", str(getattr(broker, "plugin_id", "") or broker.name).lower()).strip("_")
    spec = BrokerSpec.from_dict({
        "broker_id": slug or "broker", "name": broker.name, "method": draft.get("method") or "manual",
        "opt_out_url": draft.get("opt_out_url") or "", "steps": steps,
        "success_text": draft.get("success_text") or "", "success_selector": draft.get("success_selector") or "",
        "instructions": draft.get("instructions") or "", "requires": draft.get("requires") or [],
        "lookup_by": draft.get("lookup_by") or "",
        "notes": "Drafted automatically. " + (draft.get("notes") or "")[:1500],
        "source": "Drafted from the broker's public opt-out page by OpenOptOut's spec drafter.",
    })
    errs = spec.validate()
    if errs:
        raise ValueError("; ".join(errs[:5]))
    roots = {registrable_domain(h) for h in allowed_hosts if h}
    for url in [spec.opt_out_url] + [s.url for s in spec.steps if s.kind == "navigate"]:
        if not url:
            continue
        h = _host(url)
        if not url.startswith("https://") or not (registrable_domain(h) in roots or hosted_kind(url)):
            raise ValueError(f"goes to {h or url}, which isn't the broker's site or a privacy-request platform")
    warnings = []
    if draft.get("confidence") == "low":
        warnings.append(WARNING_TEXTS["low"])
    used = {s.field for s in spec.steps if s.field}
    if used & SENSITIVE_FIELDS:
        warnings.append(WARNING_TEXTS["dob"])
    for s in spec.steps:
        if s.value and (re.search(r"@|\d{5,}", s.value)) and s.kind in ("fill", "type", "select"):
            raise ValueError("a step types a fixed email address or number; steps may only use the person's own fields")
    if spec.method == "manual" and not spec.instructions:
        warnings.append(WARNING_TEXTS["no_instructions"])
    return spec, warnings


# ── Drafting ─────────────────────────────────────────────────────────────────

def _screenshot_path(draft_id: int) -> str:
    return os.path.join(SCREENSHOTS_DIR, f"draft-{draft_id}.png")


def current_spec(db, broker):
    """The steps the broker uses now, ignoring drafts that applied themselves."""
    from .interpreter.script_bridge import get_or_build_broker_spec
    return get_or_build_broker_spec(broker, db=db, use_drafts=False)


def _plugin_version(db, broker) -> str:
    from ..models.database import InstalledPlugin
    pid = getattr(broker, "plugin_id", None)
    if not pid:
        return ""
    row = db.query(InstalledPlugin).filter(InstalledPlugin.plugin_id == pid).first()
    return (row.version or "") if row else ""


def _ai_prompt(broker, pmap: dict, spec=None, failure: str = "", kind: str = "new", url: str = "") -> str:
    from .listing_finder import broker_domain
    head = [f"Broker: {broker.name}", f"Website: {broker_domain(broker) or ''}"]
    if kind == "new":
        head.append(f"Its opt-out page appears to be {url}. Draft the opt-out steps for it.")
    else:
        head.append("These steps used to work and now fail. Return the full corrected set of steps. "
                    "Keep every step that still matches the page; change only what is needed.")
        head.append("Current steps (JSON): " + json.dumps(spec.to_dict())[:12000])
        head.append(f"What went wrong (a rehearsal with made-up details): {failure[:400]}")
    head.append("The page as it is now:\n" + describe_page(pmap))
    return "\n".join(head)


def _ask_ai(db, cfg, broker, prompt: str, provider: str = "", page_url: str = ""):
    """(draft dict, provider id, model) from the first helper that answers."""
    from . import ai_helpers as ai
    providers = [provider] if provider else ai.available(cfg)
    if not providers:
        raise ai.AIError("No AI helper is turned on. Add a key on the Automatic broker steps page.")
    blocked = blocked_values(db)
    last = None
    for pid in providers:
        try:
            return ai.draft(cfg, pid, prompt, blocked, page_url=page_url), pid, ai._model(cfg, pid)
        except ai.AIError as e:
            last = e
            log.info("AI helper %s couldn't draft for %s: %s", pid, broker.name, e)
    raise last


def _save_rehearsal(row, result: dict) -> None:
    keep = {k: result.get(k) for k in ("ok", "reached", "total", "stop", "failed", "detail", "trace")}
    row.rehearsal_json = json.dumps(keep)
    row.screenshot_path = result.get("screenshot") or None


def draft_new(db, broker, provider: str = "", cfg=None):
    """Draft steps for a broker with none. Returns the SpecDraft row."""
    from ..models.database import SpecDraft
    from .settings_store import load_settings
    from . import ai_helpers as ai
    from .privacy_finder import best
    from .listing_finder import broker_domain
    cfg = cfg if cfg is not None else load_settings()
    row = SpecDraft(broker_id=broker.id, kind="new", status="drafting", created_at=datetime.utcnow())
    db.add(row)
    db.commit()
    try:
        page = best(db, broker, ("hosted_onetrust", "hosted_trustarc", "hosted_other", "request_form", "optout_page"))
        url = page.url if page is not None else (broker.opt_out_url or "")
        if not url.startswith("https://"):
            raise ai.AIError("There's no opt-out page for this broker yet. "
                             "The privacy-page finder looks daily, or add its opt-out address.")
        pmap = page_map(url)
        if not pmap.get("fields") and not pmap.get("buttons"):
            raise ai.AIError("The opt-out page didn't load or has nothing to fill in.")
        hosts = {_host(url), broker_domain(broker) or ""}
        prompt = _ai_prompt(broker, pmap, kind="new", url=url)
        data, pid, model = _ask_ai(db, cfg, broker, prompt, provider, page_url=url)
        spec, warnings = build_spec(data, broker, hosts)
        row.source, row.model, row.confidence = pid, model, data.get("confidence")
        row.notes = (data.get("notes") or "")[:3000]
        result = rehearse(spec, _screenshot_path(row.id)) if spec.method == "form" else \
            {"ok": True, "detail": REHEARSAL_TEXTS["guided"], "trace": []}
        if not result["ok"] and result.get("page_map") and spec.method == "form":
            # One more try, with what went wrong.
            retry = _ai_prompt(broker, result["page_map"], spec, result["detail"], kind="repair")
            try:
                data2, pid, model = _ask_ai(db, cfg, broker, retry, pid, page_url=url)
                spec2, warnings2 = build_spec(data2, broker, hosts)
                result2 = rehearse(spec2, _screenshot_path(row.id))
                if result2["ok"]:
                    spec, warnings, result = spec2, warnings2, result2
                    row.notes = (data2.get("notes") or "")[:3000]
            except (ai.AIError, ValueError) as e:
                log.info("second draft for %s failed: %s", broker.name, e)
        row.spec_json = json.dumps(spec.to_dict())
        row.warnings_json = json.dumps(warnings)
        _save_rehearsal(row, result)
        row.status = "ready" if result["ok"] else "rehearsal_failed"
        db.commit()
        _notify(db, row, broker)
    except (ai.AIError, ValueError) as e:
        row.status, row.reason = "failed", str(e)[:1000]
        db.commit()
    except Exception as e:
        log.exception("drafting steps for %s failed", broker.name)
        row.status, row.reason = "failed", f"Something went wrong ({type(e).__name__})."
        db.commit()
    return row


def request_repair(db, broker_id: int, detail: str = "") -> Optional[int]:
    """Queue a repair after a failure that looks like a page change. At most
    one per broker per day. Never raises into the caller."""
    from ..models.database import SpecDraft
    try:
        since = datetime.utcnow() - REPAIR_COOLDOWN
        recent = (db.query(SpecDraft).filter(SpecDraft.broker_id == broker_id, SpecDraft.kind == "repair",
                                             SpecDraft.created_at >= since).first())
        if recent is not None:
            return None
        row = SpecDraft(broker_id=broker_id, kind="repair", status="queued", reason=(detail or "")[:1000],
                        created_at=datetime.utcnow())
        db.add(row)
        db.flush()
        return row.id
    except Exception as e:
        log.warning("couldn't queue a repair for broker %s: %s", broker_id, e)
        return None


def repair(db, row, provider: str = "", cfg=None):
    """Work on a queued repair. Returns the row."""
    from ..models.database import Broker
    from .settings_store import load_settings
    from . import ai_helpers as ai
    from .interpreter.script_bridge import is_heuristic
    from .listing_finder import broker_domain
    cfg = cfg if cfg is not None else load_settings()
    broker = db.query(Broker).filter(Broker.id == row.broker_id).first()
    row.status = "drafting"
    db.commit()
    try:
        spec = current_spec(db, broker)
        if spec is None or is_heuristic(spec) or spec.method != "form":
            raise ai.AIError("This broker has no automated steps to repair.")
        row.previous_spec_json = json.dumps(spec.to_dict())
        row.base_version = _plugin_version(db, broker)
        result = rehearse(spec, _screenshot_path(row.id))
        if result["ok"]:
            raise ai.AIError("The steps still get through the form with made-up details, so the page "
                             "hasn't changed in a way this can fix. Check the failure on Broker health.")
        candidate, source = spec, "rules"
        for _ in range(MAX_RULE_PASSES):
            fixed = rule_repair(candidate, result.get("failed"), result.get("page_map") or {})
            if fixed is None:
                break
            candidate = fixed
            result = rehearse(candidate, _screenshot_path(row.id))
            if result["ok"]:
                break
        if not result["ok"]:
            hosts = {_host(spec.opt_out_url), broker_domain(broker) or ""} | \
                    {_host(s.url) for s in spec.steps if s.kind == "navigate"}
            prompt = _ai_prompt(broker, result.get("page_map") or {}, candidate, result.get("detail", ""), kind="repair")
            data, pid, model = _ask_ai(db, cfg, broker, prompt, provider, page_url=spec.opt_out_url)
            candidate, warnings = build_spec(data, broker, hosts)
            for k in ("broker_id", "legal_basis", "statutory_response_days", "search_url", "listing_pattern",
                      "one_optout_per_email", "accepts_plus_addresses", "lookup_by", "jurisdiction",
                      "legal_language", "email_templates", "letter", "source"):
                setattr(candidate, k, getattr(spec, k))
            candidate.requires = candidate.requires or spec.requires
            source, row.model, row.confidence = pid, model, data.get("confidence")
            row.notes = (data.get("notes") or "")[:3000]
            row.warnings_json = json.dumps(warnings)
            result = rehearse(candidate, _screenshot_path(row.id))
        else:
            row.notes = "Found the moved field or button by its label."
        row.source = source
        row.spec_json = json.dumps(candidate.to_dict())
        _save_rehearsal(row, result)
        decide(db, row, broker, spec, candidate, result, cfg)
    except (ai.AIError, ValueError) as e:
        row.status, row.reason = "failed", ((row.reason or "") + "\n" + str(e))[-1000:]
        db.commit()
    except Exception as e:
        log.exception("repairing steps for broker %s failed", row.broker_id)
        row.status = "failed"
        row.reason = ((row.reason or "") + f"\nSomething went wrong ({type(e).__name__}).")[-1000:]
        db.commit()
    return row


def decide(db, row, broker, old, new, result: dict, cfg) -> None:
    """Apply a passing selector-only repair if allowed; otherwise wait for an admin."""
    from . import ai_helpers as ai
    if not result["ok"]:
        row.status = "rehearsal_failed"
    elif (row.kind == "repair" and ai.settings_of(cfg)["auto_apply_repairs"]
          and selector_only_change(old, new) and not json.loads(row.warnings_json or "[]")):
        row.status, row.decided_at, row.decided_by = "applied", datetime.utcnow(), "automatic"
        _supersede_others(db, row)
        _reenable(db, broker)
    else:
        row.status = "ready"
    db.commit()
    _notify(db, row, broker)


def _supersede_others(db, row) -> None:
    from ..models.database import SpecDraft
    for other in db.query(SpecDraft).filter(SpecDraft.broker_id == row.broker_id, SpecDraft.id != row.id,
                                            SpecDraft.status.in_(("applied", "approved"))).all():
        other.status = "superseded"


def _reenable(db, broker) -> None:
    from ..models.database import BrokerHealth
    h = db.query(BrokerHealth).filter(BrokerHealth.broker_id == broker.id).first()
    if h is not None and h.auto_disabled:
        from .broker_health import re_enable
        re_enable(db, broker.id, clear_review=False)


def _notify(db, row, broker) -> None:
    from .broker_updates import record
    titles = {
        "applied": f"{broker.name}'s opt-out steps were fixed automatically",
        "ready": (f"New opt-out steps for {broker.name} are ready to check" if row.kind == "new"
                  else f"A fix for {broker.name}'s opt-out steps is ready to check"),
        "rehearsal_failed": f"Drafted steps for {broker.name} didn't get through a rehearsal",
    }
    if row.status not in titles:
        return
    detail = {
        "applied": "Its page moved a field or button. The fix was rehearsed with made-up details "
                   "and only changes where the steps look. You can undo it on Automatic broker steps.",
        "ready": "Rehearsed with made-up details. Look it over and approve it on Automatic broker steps.",
        "rehearsal_failed": "Look at where it stopped on Automatic broker steps.",
    }[row.status]
    record(db, "steps_" + row.status, titles[row.status], detail, broker_id=broker.id)
    db.commit()


# ── Admin decisions ──────────────────────────────────────────────────────────

def approve(db, row, who: str) -> None:
    from ..models.database import Broker
    if row.status not in ("ready", "rehearsal_failed") or not row.spec_json:
        raise ValueError("Only a drafted set of steps can be approved.")
    row.status, row.decided_at, row.decided_by = "approved", datetime.utcnow(), who
    _supersede_others(db, row)
    broker = db.query(Broker).filter(Broker.id == row.broker_id).first()
    if broker is not None:
        _reenable(db, broker)
        if row.kind == "new":
            from .interpreter.broker_spec import BrokerSpec
            from ..models.database import OptOutMethod
            spec = BrokerSpec.from_dict(json.loads(row.spec_json))
            broker.method = OptOutMethod.form if spec.method == "form" else OptOutMethod.manual
            if spec.opt_out_url:
                broker.opt_out_url = spec.opt_out_url
    db.commit()


def reject(db, row, who: str) -> None:
    if row.status in ("applied", "approved"):
        raise ValueError("Undo it instead.")
    row.status, row.decided_at, row.decided_by = "rejected", datetime.utcnow(), who
    db.commit()


def revert(db, row, who: str) -> None:
    if row.status not in ("applied", "approved"):
        raise ValueError("Only steps in use can be undone.")
    row.status, row.decided_at, row.decided_by = "reverted", datetime.utcnow(), who
    db.commit()


def active_draft(db, broker, plugin_version: str = ""):
    """The applied or approved draft for this broker, or None. A repair made
    against an older version of the broker's plugin is set aside when the
    plugin is updated: the update is assumed to carry its own fix."""
    from ..models.database import SpecDraft
    row = (db.query(SpecDraft).filter(SpecDraft.broker_id == broker.id,
                                      SpecDraft.status.in_(("applied", "approved")))
             .order_by(SpecDraft.decided_at.desc()).first())
    if row is None:
        return None
    if row.kind == "repair" and row.base_version and plugin_version and plugin_version != row.base_version:
        row.status = "superseded"
        db.commit()
        return None
    return row


def export_plugin(row, broker, dest_zip: str) -> str:
    """The draft as an installable broker plugin zip (to share or contribute)."""
    import tempfile
    from ..plugins.broker_addon import package_broker_addon
    spec = json.loads(row.spec_json)
    pid = spec.get("broker_id") or "broker"
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, pid)
        os.makedirs(path)
        manifest = {"id": pid, "type": "brokers", "broker_id": pid, "name": broker.name, "version": "0.1.0",
                    "author": "OpenOptOut spec drafter",
                    "description": f"Opt-out steps for {broker.name}, drafted automatically and approved by an admin.",
                    "spec_file": "spec.json", "difficulty": "medium"}
        with open(os.path.join(path, "manifest.json"), "w") as f:
            json.dump(manifest, f, indent=2)
        with open(os.path.join(path, "spec.json"), "w") as f:
            json.dump(spec, f, indent=2)
        return package_broker_addon(path, dest_zip)


# ── Scheduled work ───────────────────────────────────────────────────────────

def run_queue(db, limit: int = 3, cfg=None) -> dict:
    """Hourly: work on queued repairs, then (if turned on) draft steps for a
    few brokers that have an opt-out page but no steps."""
    from ..models.database import SpecDraft, Broker
    from .settings_store import load_settings
    from . import ai_helpers as ai
    cfg = cfg if cfg is not None else load_settings()
    done = {"repaired": 0, "drafted": 0}
    for row in (db.query(SpecDraft).filter(SpecDraft.status == "queued")
                  .order_by(SpecDraft.created_at).limit(limit).all()):
        repair(db, row, cfg=cfg)
        done["repaired"] += 1
    if ai.settings_of(cfg)["draft_new_brokers"] and ai.available(cfg):
        for broker in needs_draft(db, limit=1):
            draft_new(db, broker, cfg=cfg)
            done["drafted"] += 1
    return done


def needs_draft(db, limit: int = 1) -> list:
    """Enabled brokers with a found opt-out page, no steps and no recent draft."""
    from ..models.database import Broker, SpecDraft, PrivacyPage, BrokerScript
    from .interpreter.script_bridge import get_or_build_broker_spec, is_heuristic
    from .interpreter.hosted_forms import is_found_form
    since = datetime.utcnow() - timedelta(days=30)
    recent = {b for (b,) in db.query(SpecDraft.broker_id).filter(SpecDraft.kind == "new",
                                                                 SpecDraft.created_at >= since).all()}
    with_page = {b for (b,) in db.query(PrivacyPage.broker_id).filter(
        PrivacyPage.kind.in_(("request_form", "optout_page", "hosted_other")),
        PrivacyPage.status.in_(("active", "approved"))).all()}
    out = []
    for broker in db.query(Broker).filter(Broker.id.in_(with_page - recent), Broker.enabled == True).all():  # noqa: E712
        if getattr(broker, "plugin_id", None):
            continue
        script = db.query(BrokerScript).filter(BrokerScript.broker_id == broker.id).first()
        spec = get_or_build_broker_spec(broker, script=script, db=db)
        if spec is None or is_heuristic(spec) or is_found_form(spec):
            out.append(broker)
        if len(out) >= limit:
            break
    return out
