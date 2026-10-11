"""
Job executors.

A Job (from the compiler) is executed by a JobExecutor. This module defines the
interface and two implementations:

  - DryRunExecutor: performs no real I/O. It "runs" the job by recording what it
    WOULD do at each step and returns a structured result. This is what makes the
    interpretation layer fully testable without a browser or network — it proves
    the compiled job is coherent and the executor contract holds.

  - PlaywrightExecutor: the real one, which drives a headless browser for form
    jobs and hands email jobs to the existing send path. It is on the live
    opt-out path (core/optout_engine.py), with the plugin manager's
    solve_captcha and fill_form dispatchers wired in.

Result shape is uniform across executors so the engine treats them identically:
    ExecResult(ok, steps_run, steps_total, detail, needs_captcha, needs_manual)
"""

from dataclasses import dataclass, field
from typing import Optional

import re

from .compiler import Job, JobStep

# A form saying the email address it was given isn't acceptable.
EMAIL_REJECTED = re.compile(
    r"(not a valid|invalid|enter a valid|incorrect|unsupported|not supported|not allowed|isn't valid|is not valid)"
    r"[^.\n]{0,30}\be-?mail\b|"
    r"\be-?mail\b[^.\n]{0,40}(is invalid|is not valid|isn't valid|not allowed|not supported|"
    r"can(no|')t contain|must not contain|special characters)",
    re.I)

# Visible CAPTCHA widgets. Invisible reCAPTCHA (v3 / size=invisible) is left
# alone: it never asks a person anything.
CAPTCHA_SELECTORS = (
    "iframe[src*='recaptcha'][src*='anchor']:not([src*='size=invisible'])",
    "iframe[src*='hcaptcha'][src*='checkbox']",
    ".h-captcha:not([data-size='invisible'])",
    "#captcha",
)
TURNSTILE = "iframe[src*='challenges.cloudflare.com']"


@dataclass
class ExecResult:
    ok: bool
    steps_run: int = 0
    steps_total: int = 0
    detail: str = ""
    needs_captcha: bool = False     # execution paused for a CAPTCHA (item 4)
    needs_manual: bool = False      # broker requires human action
    trace: list[str] = field(default_factory=list)   # human-readable per-step log
    challenge: Optional[dict] = None  # challenge metadata for human/solver path (type, site_key, page_url, etc.)
    human_instruction: str = ""     # what the person must do, when a pause_for_human step stopped the flow
    verified: bool = False          # the page showed the spec's success signal
    email_rejected: bool = False    # the form refused the contact address (e.g. a "+" address)

    def to_dict(self) -> dict:
        d = {
            "ok": self.ok,
            "steps_run": self.steps_run,
            "steps_total": self.steps_total,
            "detail": self.detail,
            "needs_captcha": self.needs_captcha,
            "needs_manual": self.needs_manual,
            "trace": list(self.trace),
        }
        if self.challenge is not None:
            d["challenge"] = dict(self.challenge)
        if self.human_instruction:
            d["human_instruction"] = self.human_instruction
        if self.verified:
            d["verified"] = True
        if self.email_rejected:
            d["email_rejected"] = True
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ExecResult":
        return cls(
            ok=bool(d.get("ok", False)),
            steps_run=int(d.get("steps_run", 0)),
            steps_total=int(d.get("steps_total", 0)),
            detail=str(d.get("detail", "")),
            needs_captcha=bool(d.get("needs_captcha", False)),
            needs_manual=bool(d.get("needs_manual", False)),
            trace=list(d.get("trace", [])),
            challenge=dict(d["challenge"]) if d.get("challenge") is not None else None,
            human_instruction=str(d.get("human_instruction", "")),
            verified=bool(d.get("verified", False)),
            email_rejected=bool(d.get("email_rejected", False)),
        )


class NeedsPerson(Exception):
    """A step decided a person should take over (e.g. autofill wasn't sure)."""


class JobExecutor:
    """Interface. Subclasses implement run(job) -> ExecResult."""

    def run(self, job: Job) -> ExecResult:
        raise NotImplementedError


class DryRunExecutor(JobExecutor):
    """
    Executes a job without any real I/O — records intended actions. Used by the
    test suite and by a "validate this add-on" admin action: it proves a compiled
    job is internally coherent (every step is a known primitive with the data it
    needs) without contacting the broker.
    """

    def run(self, job: Job) -> ExecResult:
        if job.method == "manual":
            return ExecResult(ok=True, needs_manual=True,
                              detail="manual broker — queued for human action",
                              trace=["manual: queued for human"])

        if job.method == "email":
            if not job.email:
                return ExecResult(ok=False, detail="email job missing email payload")
            trace = [
                f"email -> {job.email.to_address} (locale={job.email.locale})",
                f"subject: {job.email.subject[:60]}",
                f"body: {len(job.email.body)} chars",
            ]
            return ExecResult(ok=True, steps_run=1, steps_total=1,
                              detail="email composed", trace=trace)

        # form method: walk the steps, "performing" each.
        trace = []
        total = len(job.steps)
        for i, s in enumerate(job.steps):
            if s.kind == "solve_captcha":
                trace.append(f"[{i}] solve_captcha -> would hand off to CAPTCHA layer")
                return ExecResult(ok=False, steps_run=i, steps_total=total,
                                  needs_captcha=True,
                                  detail="paused for CAPTCHA (handoff not yet wired)",
                                  trace=trace)
            if s.kind == "pause_for_human" and not s.selector:
                trace.append(f"[{i}] pause_for_human -> {s.text}")
                return ExecResult(ok=False, steps_run=i, steps_total=total,
                                  needs_manual=True, human_instruction=s.text,
                                  detail="paused for a person to finish", trace=trace)
            trace.append(self._describe(i, s))
        return ExecResult(ok=True, steps_run=total, steps_total=total,
                          detail="dry run complete — all steps coherent", trace=trace)

    @staticmethod
    def _describe(i: int, s: JobStep) -> str:
        if s.kind == "navigate":
            return f"[{i}] navigate -> {s.url}"
        if s.kind in ("fill", "type"):
            shown = (s.value[:20] + "…") if len(s.value) > 20 else s.value
            return f"[{i}] {s.kind} {s.selector} = {shown!r}"
        if s.kind in ("select", "check", "click"):
            return f"[{i}] {s.kind} {s.selector}" + (f" = {s.value!r}" if s.value else "")
        if s.kind in ("wait_for",):
            return f"[{i}] wait_for {s.selector} (<= {s.timeout_ms}ms)"
        if s.kind == "wait":
            return f"[{i}] wait {s.timeout_ms}ms"
        if s.kind == "submit":
            return f"[{i}] submit {s.selector}".rstrip()
        if s.kind == "click_matching":
            return f"[{i}] click_matching {s.selector or '*'} matching {s.text or s.value!r}"
        if s.kind == "press":
            return f"[{i}] press {s.value!r} on {s.selector or 'body'}"
        if s.kind == "frame":
            return f"[{i}] frame context -> {s.selector or 'main'}"
        if s.kind == "scroll":
            return f"[{i}] scroll {s.selector or 'window'}"
        if s.kind == "expect_success":
            return f"[{i}] expect_success {s.selector or s.text!r}"
        if s.kind == "pause_for_human":
            return f"[{i}] pause_for_human if {s.selector} present -> {s.text}"
        if s.kind == "autofill":
            import json as _json
            try:
                keys = sorted(_json.loads(s.value or "{}"))
            except ValueError:
                keys = []
            return f"[{i}] autofill form by its labels ({', '.join(keys)})"
        return f"[{i}] {s.kind}"


class PlaywrightExecutor(JobExecutor):
    """
    Real executor — drives a headless browser for form jobs and the existing
    email path for email jobs.

    CAPTCHA and multi-form handling are extension points: a captcha_solver
    callback (wired from the plugin manager's solve_captcha dispatch) is invoked
    when a CAPTCHA is hit — it returns a token to inject, or signals the human
    path. Without a solver, the executor pauses (needs_captcha) for the human.
    """

    def __init__(self, page=None, email_sender=None, captcha_solver=None,
                 plugin_form_handler=None):
        # page: a Playwright Page (async). email_sender: callable(EmailJob)->ok.
        # captcha_solver: callable(challenge_dict) -> result_dict | None, where
        #   result is {"solved": bool, "token": str, "defer_to_human": bool}.
        #   None means no solver installed → pause for human.
        # plugin_form_handler: callable(job, page_html) -> handled_dict | None.
        #   Lets a fill_form plugin take over a broker (multi-form / custom logic).
        self.page = page
        self.email_sender = email_sender
        self.captcha_solver = captcha_solver
        self.plugin_form_handler = plugin_form_handler
        self._current_frame = None

    def _target(self):
        """Current interaction target: either an active iframe locator or the main page."""
        return self._current_frame if self._current_frame is not None else self.page

    def _loc(self, selector: str):
        """First element matching selector in the current page or iframe.
        (Locators work the same on a Page and a FrameLocator, which has no
        fill()/click() of its own.)"""
        return self._target().locator(selector).first

    _DESCRIBE_JS = """(els) => els.map((el, i) => {
        const visible = !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length)
                        && getComputedStyle(el).visibility !== 'hidden';
        const txt = (n) => (n ? (n.innerText || n.textContent || '') : '').replace(/\\s+/g, ' ').trim();
        let label = '';
        if (el.id) { const l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]'); if (l) label = txt(l); }
        if (!label) { const l = el.closest('label'); if (l) label = txt(l); }
        if (!label && el.getAttribute('aria-labelledby')) {
            label = el.getAttribute('aria-labelledby').split(/\\s+/).map(id => txt(document.getElementById(id))).join(' ');
        }
        const fs = el.closest('fieldset'); const legend = fs ? txt(fs.querySelector('legend')) : '';
        const grp = el.closest('[role=radiogroup], [role=group]');
        const groupLabel = legend || (grp ? (grp.getAttribute('aria-label') || txt(grp.querySelector('label, legend, h3, h4, p'))) : '');
        const opts = el.tagName === 'SELECT' ? Array.from(el.options).map(o => ({value: o.value, label: txt(o)})) : [];
        return {i, visible, tag: el.tagName.toLowerCase(), type: (el.type || '').toLowerCase(), name: el.name || '',
                id: el.id || '', label: label.slice(0, 200), aria: el.getAttribute('aria-label') || '',
                placeholder: el.getAttribute('placeholder') || '', autocomplete: el.getAttribute('autocomplete') || '',
                required: !!(el.required || el.getAttribute('aria-required') === 'true'),
                value: el.type === 'radio' || el.type === 'checkbox' ? (el.value || '') : '',
                group: el.type === 'radio' || el.type === 'checkbox' ? (el.name || '') : '',
                group_label: groupLabel.slice(0, 200), options: opts};
    })"""

    async def _autofill(self, s, trace, i):
        """Fill a privacy-request form by reading its labels (see hosted_forms)."""
        import json as _json
        from .hosted_forms import plan_autofill
        controls = self._target().locator("input, select, textarea")
        desc = await controls.evaluate_all(self._DESCRIBE_JS)
        desc = [d for d in desc if d.get("visible")]
        values = _json.loads(s.value or "{}")
        plan = plan_autofill(desc, values)
        if not plan["ok"]:
            raise NeedsPerson(plan["why"])
        for a in plan["actions"]:
            loc = controls.nth(a["i"])
            if a["op"] == "fill":
                await loc.fill(a["value"], timeout=8000)
            elif a["op"] == "select":
                await loc.select_option(a["value"], timeout=8000)
            elif a["op"] == "check":
                await loc.check(timeout=8000, force=True)
        trace.append(f"[{i}] autofill: {', '.join(plan['mapped'])}")

    async def _turnstile_passed(self, wait_ms: int = 15000) -> bool:
        """Cloudflare Turnstile usually passes by itself; give it a moment."""
        try:
            await self.page.wait_for_function(
                "() => { const i = document.querySelector('input[name=\"cf-turnstile-response\"]');"
                " return !!(i && i.value); }", timeout=wait_ms)
            return True
        except Exception:
            return False

    async def _get_page_context(self, stage_index: int = 0) -> dict:
        """Gather rich page state for fill_form plugins (roadmap item 3)."""
        current_url = getattr(self.page, "url", "") if hasattr(self.page, "url") else ""
        page_title = ""
        try:
            page_title = await self.page.title() if hasattr(self.page, "title") else ""
        except Exception:
            pass
        has_iframes = False
        try:
            frames = self.page.frames if hasattr(self.page, "frames") else []
            has_iframes = len(frames) > 1
        except Exception:
            pass
        page_html = ""
        try:
            page_html = await self.page.content() if hasattr(self.page, "content") else ""
        except Exception:
            pass
        return {
            "url": current_url,
            "title": page_title,
            "has_iframes": has_iframes,
            "html": page_html,
            "stage_index": stage_index,
        }

    async def run(self, job: Job) -> ExecResult:  # async: mirrors optout_engine
        if job.method == "manual":
            return ExecResult(ok=True, needs_manual=True, detail="queued for human")

        if job.method == "email":
            if not self.email_sender:
                return ExecResult(ok=False, detail="no email sender configured")
            ok = await self._maybe_await(self.email_sender(job.email))
            return ExecResult(ok=bool(ok), steps_run=1, steps_total=1,
                              detail="email sent" if ok else "email send failed")

        if not self.page:
            return ExecResult(ok=False, detail="no browser page provided for form job")

        trace = []
        self._current_frame = None
        self._verified = False

        # Extension point: a fill_form plugin may take over this broker entirely
        # (multi-form / complex wizard flow, roadmap item 3). Supports multi-stage
        # interactive takeover loops.
        if self.plugin_form_handler:
            try:
                nav = next((st for st in job.steps if st.kind == "navigate"), None)
                if nav and nav.url:
                    await self.page.goto(nav.url, timeout=20000)
                    await self.page.wait_for_timeout(1500)

                stage = 0
                max_stages = 5
                plugin_handled = False
                while stage < max_stages:
                    ctx = await self._get_page_context(stage_index=stage)
                    handled = await self._maybe_await(self.plugin_form_handler(job, ctx))
                    if not (handled and handled.get("handled")):
                        break  # not handled, fall back to spec steps

                    plugin_handled = True
                    actions = handled.get("actions", [])
                    trace.append(f"[plugin:{handled.get('plugin_id','?')}] stage {stage+1} — {len(actions)} actions")
                    res = await self._run_plugin_actions(actions, trace)
                    if res is not None and not res.ok:
                        return res

                    # Multi-stage chained flow: if plugin requests another turn, advance
                    if handled.get("next_stage"):
                        stage += 1
                        await self.page.wait_for_timeout(1500)
                        continue

                    # Success verification if declared by plugin
                    succ_sel = handled.get("success_selector")
                    if succ_sel:
                        try:
                            await self.page.wait_for_selector(succ_sel, timeout=10000)
                            trace.append(f"success selector verified: {succ_sel}")
                        except Exception:
                            return ExecResult(ok=False, detail=f"success selector not found: {succ_sel}", trace=trace)

                    return res or ExecResult(ok=True, steps_run=len(actions), steps_total=len(actions),
                                             detail="plugin form flow complete", trace=trace)
            except Exception as e:
                trace.append(f"fill_form plugin takeover failed ({e}); using default steps")

        total = len(job.steps)
        for i, s in enumerate(job.steps):
            if s.kind == "pause_for_human":
                if await self._should_pause_for_human(s):
                    trace.append(f"[{i}] pause_for_human -> {s.text}")
                    return ExecResult(ok=False, steps_run=i, steps_total=total,
                                      needs_manual=True, human_instruction=s.text,
                                      detail="paused for a person to finish", trace=trace)
                trace.append(f"[{i}] pause_for_human skipped ({s.selector} not on page)")
                continue
            try:
                paused = await self._run_step(s, trace, i)
                if paused:
                    return ExecResult(ok=False, steps_run=i, steps_total=total,
                                      needs_captcha=True, detail="paused for CAPTCHA",
                                      trace=trace, challenge=getattr(self, "last_challenge", None))
            except NeedsPerson as e:
                trace.append(f"[{i}] {s.kind}: needs a person ({e})")
                site = getattr(self.page, "url", "") if isinstance(getattr(self.page, "url", ""), str) else ""
                return ExecResult(ok=False, steps_run=i, steps_total=total, needs_manual=True, trace=trace,
                                  detail=f"form needs a person: {e}",
                                  human_instruction=(f"OpenOptOut found {job.broker_name}'s privacy request form"
                                                     + (f" at {site}" if site else "")
                                                     + f" but didn't fill it in, because {e}. Fill it in "
                                                     f"yourself, asking for your data to be deleted, then press "
                                                     f"\"I've done this\"."))
            except Exception as e:
                if s.optional:
                    trace.append(f"[{i}] {s.kind} optional-failed: {e}")
                    continue
                if await self._email_rejected(job):
                    return ExecResult(ok=False, steps_run=i, steps_total=total, email_rejected=True,
                                      detail="the form refused the email address", trace=trace)
                return ExecResult(ok=False, steps_run=i, steps_total=total,
                                  detail=f"step {i} ({s.kind}) failed: {e}", trace=trace)
        if await self._email_rejected(job):
            return ExecResult(ok=False, steps_run=total, steps_total=total, email_rejected=True,
                              detail="the form refused the email address", trace=trace)
        verified = self._verified
        if job.success_selector or job.success_text:
            try:
                if job.success_selector:
                    await self.page.locator(job.success_selector).first.wait_for(timeout=10000)
                if job.success_text and job.success_text not in (await self.page.content()):
                    raise RuntimeError("success text not on the page")
                verified = True
            except Exception as e:
                return ExecResult(ok=False, steps_run=total, steps_total=total,
                                  detail=f"the broker's page didn't confirm the request ({e})", trace=trace)
        return ExecResult(ok=True, steps_run=total, steps_total=total, verified=verified,
                          detail="form flow complete", trace=trace)

    async def _email_rejected(self, job) -> bool:
        """Did the form complain about the email address we gave it?"""
        if not job.contact_email:
            return False
        texts = []
        for tgt in (self.page, self._current_frame):
            if tgt is None:
                continue
            try:
                texts.append(await tgt.locator("body").inner_text(timeout=2000))
            except Exception:
                pass
        return any(EMAIL_REJECTED.search(t or "") for t in texts)

    async def _run_plugin_actions(self, actions: list, trace: list):
        """Execute the BrowserActions a fill_form plugin returned. Reuses the
        same primitive handling as spec steps by adapting each action to a
        JobStep-like object. Returns an ExecResult, or None to fall through."""
        from .compiler import JobStep
        total = len(actions)
        for i, a in enumerate(actions):
            step = JobStep(
                kind=a.get("action", ""), selector=a.get("selector", ""),
                value=a.get("value", ""), timeout_ms=a.get("timeout_ms", 8000) or 8000,
                optional=a.get("optional", False),
            )
            try:
                paused = await self._run_step(step, trace, i)
                if paused:
                    return ExecResult(ok=False, steps_run=i, steps_total=total,
                                      needs_captcha=True, detail="paused for CAPTCHA (plugin flow)",
                                      trace=trace, challenge=getattr(self, "last_challenge", None))
            except Exception as e:
                if step.optional:
                    continue
                return ExecResult(ok=False, steps_run=i, steps_total=total,
                                  detail=f"plugin action {i} ({step.kind}) failed: {e}", trace=trace)
        return ExecResult(ok=True, steps_run=total, steps_total=total,
                          detail="plugin form flow complete", trace=trace)

    async def _run_step(self, s: JobStep, trace: list, i: int) -> bool:
        """
        Perform one step against self.page (or active frame context).
        Returns True if execution should pause for a CAPTCHA.
        """
        if s.kind == "solve_captcha":
            return await self._handle_captcha(s.selector, trace, i)

        if s.kind == "frame":
            # Switch target context into an iframe, or reset to main page
            if not s.selector or s.selector.lower() in ("main", "top", ":root", "parent"):
                self._current_frame = None
                trace.append(f"[{i}] frame context reset to main page")
            else:
                self._current_frame = self.page.frame_locator(s.selector)
                trace.append(f"[{i}] frame context switched to {s.selector}")
            return False

        if s.kind == "navigate":
            self._current_frame = None  # Navigation resets frame context
            await self.page.goto(s.url, timeout=s.timeout_ms or 20000)
            await self.page.wait_for_timeout(1500)   # let the page settle

        elif s.kind == "fill":
            await self._loc(s.selector).fill(s.value, timeout=s.timeout_ms or 8000)

        elif s.kind == "autofill":
            await self._autofill(s, trace, i)

        elif s.kind == "type":
            # Key by key: React/MUI inputs ignore a programmatic fill.
            loc = self._loc(s.selector)
            await loc.click(timeout=s.timeout_ms or 8000)
            await loc.fill("", timeout=s.timeout_ms or 8000)
            await loc.press_sequentially(s.value, delay=35, timeout=max(s.timeout_ms or 8000, 60 * len(s.value)))

        elif s.kind == "select":
            loc = self._loc(s.selector)
            try:
                await loc.select_option(s.value, timeout=s.timeout_ms or 8000)
            except Exception:
                await loc.select_option(label=s.value, timeout=s.timeout_ms or 8000)

        elif s.kind == "check":
            await self._loc(s.selector).check(timeout=s.timeout_ms or 8000)

        elif s.kind == "click":
            await self._loc(s.selector).click(timeout=s.timeout_ms or 8000)
            await self.page.wait_for_timeout(500)

        elif s.kind == "click_matching":
            target = self._target()
            matching_text = s.text or s.value
            exact = re.compile(r"^\s*" + re.escape(matching_text) + r"\s*$", re.I)
            if s.selector:
                # Whole-text match first, so "Kansas" never picks "Arkansas".
                locator = target.locator(s.selector).filter(has_text=exact)
                if not await locator.count():
                    locator = target.locator(s.selector).filter(has_text=matching_text)
                locator = locator.first
            else:
                locator = target.get_by_text(matching_text, exact=True).first
            await locator.click(timeout=s.timeout_ms or 8000)
            await self.page.wait_for_timeout(1000)

        elif s.kind == "press":
            if s.selector:
                await self._loc(s.selector).press(s.value or "Enter", timeout=s.timeout_ms or 8000)
            else:
                await self.page.keyboard.press(s.value or "Enter")
            await self.page.wait_for_timeout(500)

        elif s.kind == "scroll":
            if s.selector:
                await self._loc(s.selector).scroll_into_view_if_needed(timeout=s.timeout_ms or 8000)
            else:
                await self.page.evaluate("window.scrollBy(0, 500)")

        elif s.kind == "wait_for":
            await self._loc(s.selector).wait_for(state="visible", timeout=s.timeout_ms or 8000)

        elif s.kind == "wait":
            await self.page.wait_for_timeout(s.timeout_ms or 1000)

        elif s.kind == "submit":
            if s.selector:
                await self._loc(s.selector).click(timeout=s.timeout_ms or 8000)
            else:
                await self.page.evaluate(
                    "() => { const f = document.querySelector('form'); if (f) f.submit(); }")
            await self.page.wait_for_timeout(2000)

        elif s.kind == "expect_success":
            if s.selector:
                await self._loc(s.selector).wait_for(timeout=s.timeout_ms or 8000)
            elif s.text:
                body = await self._target().locator("body").inner_text(timeout=s.timeout_ms or 8000)
                if s.text.lower() not in (body or "").lower():
                    raise RuntimeError(f"success text not found: {s.text!r}")
            self._verified = True

        # Best-effort CAPTCHA detection AFTER the action: if a known CAPTCHA
        # widget appeared, try to solve it (via the solver hook) or pause for
        # the human path.
        try:
            if s.kind not in ("wait", "expect_success"):
                for sel in CAPTCHA_SELECTORS:
                    el = await self.page.query_selector(sel)
                    if el and await el.is_visible():
                        return await self._handle_captcha(sel, trace, i)
                if await self.page.query_selector(TURNSTILE) and not await self._turnstile_passed():
                    return await self._handle_captcha(TURNSTILE, trace, i)
        except Exception:
            pass

        trace.append(f"[{i}] {s.kind} {s.selector or s.url}".rstrip())
        return False

    async def _should_pause_for_human(self, s: JobStep) -> bool:
        """A pause_for_human step always pauses, unless it names a selector,
        in which case it pauses only when that element is on the page."""
        if not s.selector:
            return True
        try:
            target = self._target()
            el = await target.query_selector(s.selector) if hasattr(target, "query_selector") \
                else await target.locator(s.selector).count()
            return bool(el)
        except Exception:
            return True   # can't tell — safer to hand it to a person

    async def _detect_challenge(self, selector: str) -> dict:
        """Gather what we can about the CAPTCHA for the solver hook."""
        ctype, site_key = "other", ""
        try:
            content = await self.page.content()
            low = content.lower()
            if "hcaptcha" in low:
                ctype = "hcaptcha"
            elif "recaptcha" in low:
                ctype = "recaptcha_v2"
            # Try to read a site-key attribute from a common widget.
            try:
                el = await self.page.query_selector("[data-sitekey]")
                if el:
                    site_key = await el.get_attribute("data-sitekey") or ""
            except Exception:
                pass
        except Exception:
            pass
        screenshot = b""
        try:
            screenshot = await self.page.screenshot()
        except Exception:
            pass
        return {
            "type": ctype, "site_key": site_key,
            "page_url": getattr(self.page, "url", "") if isinstance(getattr(self.page, "url", ""), str) else "",
            "screenshot": screenshot, "meta": {"selector": selector},
        }

    async def _handle_captcha(self, selector: str, trace: list, i: int) -> bool:
        """
        Invoke the CAPTCHA solver hook. If it returns a token, inject it and
        continue (return False). If it defers, or there's no solver, pause for
        the human path (return True).
        """
        challenge = await self._detect_challenge(selector)
        self.last_challenge = challenge
        if not self.captcha_solver:
            trace.append(f"[{i}] CAPTCHA detected — no solver installed, pausing for human")
            return True
        try:
            result = await self._maybe_await(self.captcha_solver(challenge))
        except Exception as e:
            trace.append(f"[{i}] CAPTCHA solver errored ({e}) — pausing for human")
            return True
        if not result or result.get("defer_to_human") or not result.get("solved"):
            trace.append(f"[{i}] CAPTCHA solver deferred — pausing for human")
            return True
        token = result.get("token", "")
        if not token:
            trace.append(f"[{i}] CAPTCHA solver returned no token — pausing for human")
            return True
        # Inject the token into the standard reCAPTCHA/hCaptcha response field so
        # the page's form picks it up on submit.
        try:
            await self.page.evaluate(
                """(tok) => {
                    for (const name of ['g-recaptcha-response','h-captcha-response']) {
                        let el = document.getElementsByName(name)[0];
                        if (!el) {
                            el = document.createElement('textarea');
                            el.name = name; el.style.display='none';
                            document.body.appendChild(el);
                        }
                        el.value = tok;
                    }
                }""", token)
            trace.append(f"[{i}] CAPTCHA solved by plugin — token injected, continuing")
            return False
        except Exception as e:
            trace.append(f"[{i}] token injection failed ({e}) — pausing for human")
            return True

    @staticmethod
    async def _maybe_await(v):
        import inspect
        return await v if inspect.isawaitable(v) else v
