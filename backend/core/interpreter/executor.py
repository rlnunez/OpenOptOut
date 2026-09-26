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

from .compiler import Job, JobStep


@dataclass
class ExecResult:
    ok: bool
    steps_run: int = 0
    steps_total: int = 0
    detail: str = ""
    needs_captcha: bool = False     # execution paused for a CAPTCHA (item 4)
    needs_manual: bool = False      # broker requires human action
    trace: list[str] = field(default_factory=list)   # human-readable per-step log


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
            trace.append(self._describe(i, s))
        return ExecResult(ok=True, steps_run=total, steps_total=total,
                          detail="dry run complete — all steps coherent", trace=trace)

    @staticmethod
    def _describe(i: int, s: JobStep) -> str:
        if s.kind == "navigate":
            return f"[{i}] navigate -> {s.url}"
        if s.kind == "fill":
            shown = (s.value[:20] + "…") if len(s.value) > 20 else s.value
            return f"[{i}] fill {s.selector} = {shown!r}"
        if s.kind in ("select", "check", "click"):
            return f"[{i}] {s.kind} {s.selector}" + (f" = {s.value!r}" if s.value else "")
        if s.kind in ("wait_for",):
            return f"[{i}] wait_for {s.selector} (<= {s.timeout_ms}ms)"
        if s.kind == "wait":
            return f"[{i}] wait {s.timeout_ms}ms"
        if s.kind == "submit":
            return f"[{i}] submit {s.selector}".rstrip()
        if s.kind == "expect_success":
            return f"[{i}] expect_success {s.selector or s.text!r}"
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

        # Extension point: a fill_form plugin may take over this broker entirely.
        # If one handles it, we execute the plugin's returned actions instead of
        # the compiled spec steps (this is how multi-form / broker-specific logic
        # lives in an add-on rather than the core). If none handles it, fall
        # through to the default spec-driven execution below.
        if self.plugin_form_handler:
            try:
                nav = next((st for st in job.steps if st.kind == "navigate"), None)
                if nav and nav.url:
                    await self.page.goto(nav.url, timeout=20000)
                    await self.page.wait_for_timeout(1500)
                page_html = await self.page.content()
                handled = await self._maybe_await(self.plugin_form_handler(job, page_html))
                if handled and handled.get("handled"):
                    actions = handled.get("actions", [])
                    trace.append(f"[plugin:{handled.get('plugin_id','?')}] took over — {len(actions)} actions")
                    res = await self._run_plugin_actions(actions, trace)
                    if res is not None:
                        return res
            except Exception as e:
                trace.append(f"fill_form plugin takeover failed ({e}); using default steps")

        total = len(job.steps)
        for i, s in enumerate(job.steps):
            try:
                paused = await self._run_step(s, trace, i)
                if paused:
                    return ExecResult(ok=False, steps_run=i, steps_total=total,
                                      needs_captcha=True, detail="paused for CAPTCHA",
                                      trace=trace)
            except Exception as e:
                if s.optional:
                    trace.append(f"[{i}] {s.kind} optional-failed: {e}")
                    continue
                return ExecResult(ok=False, steps_run=i, steps_total=total,
                                  detail=f"step {i} ({s.kind}) failed: {e}", trace=trace)
        return ExecResult(ok=True, steps_run=total, steps_total=total,
                          detail="form flow complete", trace=trace)

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
                                      trace=trace)
            except Exception as e:
                if step.optional:
                    continue
                return ExecResult(ok=False, steps_run=i, steps_total=total,
                                  detail=f"plugin action {i} ({step.kind}) failed: {e}", trace=trace)
        return ExecResult(ok=True, steps_run=total, steps_total=total,
                          detail="plugin form flow complete", trace=trace)

    async def _run_step(self, s: JobStep, trace: list, i: int) -> bool:
        """
        Perform one step against self.page. Returns True if execution should
        pause for a CAPTCHA. Mirrors the Playwright usage already proven in
        core/optout_engine.py (goto/fill/click/select/wait, with timeouts).
        Raises on failure; the caller decides whether the step was optional.
        """
        if s.kind == "solve_captcha":
            return await self._handle_captcha(s.selector, trace, i)

        if s.kind == "navigate":
            await self.page.goto(s.url, timeout=s.timeout_ms or 20000)
            await self.page.wait_for_timeout(1500)   # let the page settle

        elif s.kind == "fill":
            await self.page.fill(s.selector, s.value, timeout=s.timeout_ms or 8000)

        elif s.kind == "select":
            await self.page.select_option(s.selector, s.value, timeout=s.timeout_ms or 8000)

        elif s.kind == "check":
            await self.page.check(s.selector, timeout=s.timeout_ms or 8000)

        elif s.kind == "click":
            await self.page.click(s.selector, timeout=s.timeout_ms or 8000)
            await self.page.wait_for_timeout(500)

        elif s.kind == "wait_for":
            await self.page.wait_for_selector(s.selector, timeout=s.timeout_ms or 8000)

        elif s.kind == "wait":
            await self.page.wait_for_timeout(s.timeout_ms or 1000)

        elif s.kind == "submit":
            # Prefer clicking a given submit selector; otherwise submit the
            # enclosing form via JS as a fallback.
            if s.selector:
                await self.page.click(s.selector, timeout=s.timeout_ms or 8000)
            else:
                await self.page.evaluate(
                    "() => { const f = document.querySelector('form'); if (f) f.submit(); }")
            await self.page.wait_for_timeout(2000)

        elif s.kind == "expect_success":
            # Confirm the opt-out landed: either a success selector appears, or
            # success text is present in the page body. Raises if neither.
            if s.selector:
                await self.page.wait_for_selector(s.selector, timeout=s.timeout_ms or 8000)
            elif s.text:
                content = await self.page.content()
                if s.text not in content:
                    raise RuntimeError(f"success text not found: {s.text!r}")

        # Best-effort CAPTCHA detection AFTER the action: if a known CAPTCHA
        # widget appeared, try to solve it (via the solver hook) or pause for
        # the human path.
        try:
            for sel in ("iframe[src*='recaptcha']", ".g-recaptcha",
                        "iframe[src*='hcaptcha']", ".h-captcha", "#captcha"):
                if await self.page.query_selector(sel):
                    return await self._handle_captcha(sel, trace, i)
        except Exception:
            pass

        trace.append(f"[{i}] {s.kind} {s.selector or s.url}".rstrip())
        return False

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
        if not self.captcha_solver:
            trace.append(f"[{i}] CAPTCHA detected — no solver installed, pausing for human")
            return True
        challenge = await self._detect_challenge(selector)
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
