#!/usr/bin/env python3
"""
Live opt-out test harness — run ONE broker spec against a real browser.

This is the first test that actually drives Playwright: it compiles a broker
spec into a Job and runs it through the real PlaywrightExecutor against a live
page, screenshotting every step so you can SEE what happened.

⚠ SAFETY — READ BEFORE USING AGAINST A REAL BROKER ⚠
    Submitting an opt-out to a real data broker sends a real removal request
    with real PII from your IP. Do NOT point this at a live broker for a first
    run. By default this targets a SAFE, self-contained test form served from a
    data: URL — it proves the mechanics (navigate, fill, submit, confirm) end to
    end without contacting anyone. Only after that works should you consider a
    real broker, deliberately and with test data.

Run inside the backend container (Playwright is installed there):
    docker compose exec api python -m app.core.interpreter.live_test          # safe built-in form
    docker compose exec api python -m app.core.interpreter.live_test SPEC.json # your own spec

Screenshots are written to /data/screenshots/livetest-*.png so you can inspect
each step. The script prints a step-by-step trace and a final PASS/FAIL.
"""

import asyncio
import json
import os
import sys
import time

# Resolve imports whether run as app.core.interpreter.live_test or standalone.
try:
    from .broker_spec import BrokerSpec
    from .compiler import compile_job
    from .executor import PlaywrightExecutor
except ImportError:
    from broker_spec import BrokerSpec
    from compiler import compile_job
    from executor import PlaywrightExecutor


SHOTS = "/data/screenshots"

# A completely self-contained test form (served via data: URL). It has the same
# shape as a real opt-out form — text inputs, a select, a checkbox, a submit —
# and shows a success message on submit. No network, no third party.
_SAFE_FORM_HTML = """<!DOCTYPE html><html><body>
<h1>Test Opt-Out Form</h1>
<form id="optout-form" onsubmit="document.getElementById('done').style.display='block';return false;">
  <input name="firstName" placeholder="First"/>
  <input name="lastName"  placeholder="Last"/>
  <input name="email"     placeholder="Email"/>
  <select name="state"><option value="">--</option><option value="TX">TX</option><option value="CA">CA</option></select>
  <input type="checkbox" name="confirm"/>
  <button type="submit">Submit</button>
</form>
<div id="done" style="display:none">Your request has been received</div>
</body></html>"""

# The spec that drives that safe form — mirrors a real form-method broker.
_SAFE_SPEC = {
    "broker_id": "livetest-safe",
    "name": "Live Test (safe built-in form)",
    "method": "form",
    "spec_version": "1.0",
    # A placeholder URL so the spec validates as a well-formed form spec. The
    # safe run ignores it — it loads the built-in form from a data: URL instead
    # and strips navigate steps (see run()). No request is ever made to this host.
    "opt_out_url": "https://example.com/livetest-placeholder",
    "steps": [
        {"kind": "wait_for", "selector": "#optout-form", "timeout_ms": 8000},
        {"kind": "fill",   "selector": "input[name=firstName]", "field": "first_name"},
        {"kind": "fill",   "selector": "input[name=lastName]",  "field": "last_name"},
        {"kind": "fill",   "selector": "input[name=email]",     "field": "email"},
        {"kind": "select", "selector": "select[name=state]",    "field": "state"},
        {"kind": "check",  "selector": "input[name=confirm]"},
        {"kind": "submit", "selector": "button[type=submit]"},
        {"kind": "expect_success", "text": "Your request has been received"},
    ],
    "success_text": "Your request has been received",
}

# Fake member data for the test — never real PII for the safe run.
_TEST_MEMBER = {
    "first_name": "Test", "last_name": "User", "full_name": "Test User",
    "email": "test@example.com", "state": "TX", "address": "1 Test St",
    "city": "Austin", "zip": "78701", "phone": "555-0100",
}


async def run(spec_dict, member, use_safe_form):
    os.makedirs(SHOTS, exist_ok=True)
    from playwright.async_api import async_playwright

    spec = BrokerSpec.from_dict(spec_dict)
    errs = spec.validate()
    if errs:
        print(f"SPEC INVALID: {errs}")
        return 1

    try:
        job = compile_job(spec, member, member_id="livetest")
    except Exception as e:
        print(f"COMPILE FAILED: {e}")
        return 1

    print(f"\nRunning '{spec.name}' — {len(job.steps)} steps\n" + "-" * 50)

    async with async_playwright() as pw:
        browser = await pw.firefox.launch(headless=True)
        page = await browser.new_page()

        # For the safe run, load the built-in form via data: URL and neutralize
        # the job's navigate step (there's nothing external to go to).
        if use_safe_form:
            import base64
            data_url = "data:text/html;base64," + base64.b64encode(
                _SAFE_FORM_HTML.encode()).decode()
            await page.goto(data_url)
            job.steps = [s for s in job.steps if s.kind != "navigate"]

        executor = PlaywrightExecutor(page=page)

        # Run step by step so we can screenshot each one.
        stamp = int(time.time())
        trace = []
        ok = True
        detail = ""
        for idx, step in enumerate(job.steps):
            try:
                paused = await executor._run_step(step, trace, idx)
                shot = f"{SHOTS}/livetest-{stamp}-{idx:02d}-{step.kind}.png"
                await page.screenshot(path=shot)
                print(f"  [{idx}] {step.kind:14} OK    -> {os.path.basename(shot)}")
                if paused:
                    ok = False; detail = "paused for CAPTCHA"
                    print("       ↳ paused (CAPTCHA). Stopping.")
                    break
            except Exception as e:
                shot = f"{SHOTS}/livetest-{stamp}-{idx:02d}-{step.kind}-FAIL.png"
                try: await page.screenshot(path=shot)
                except Exception: pass
                ok = False
                detail = f"step {idx} ({step.kind}) failed: {e}"
                print(f"  [{idx}] {step.kind:14} FAIL  -> {e}")
                print(f"       screenshot: {os.path.basename(shot)}")
                break

        await browser.close()

    print("-" * 50)
    if ok:
        print("RESULT: PASS — all steps ran, success confirmed.")
        print(f"Screenshots in {SHOTS}/livetest-{stamp}-*.png")
        return 0
    print(f"RESULT: FAIL — {detail}")
    print(f"Screenshots in {SHOTS}/livetest-{stamp}-*.png  (inspect the FAIL shot)")
    return 1


def main():
    if len(sys.argv) > 1:
        # Running a user-provided spec against a REAL target.
        path = sys.argv[1]
        print("=" * 50)
        print("⚠  Running a CUSTOM spec. If it navigates to a real broker, this")
        print("   sends a real request from your IP. Use test data. Ctrl+C to abort.")
        print("=" * 50)
        with open(path) as f:
            spec_dict = json.load(f)
        rc = asyncio.run(run(spec_dict, _TEST_MEMBER, use_safe_form=False))
    else:
        print("Running the SAFE built-in test form (no network, no third party).")
        rc = asyncio.run(run(_SAFE_SPEC, _TEST_MEMBER, use_safe_form=True))
    sys.exit(rc)


if __name__ == "__main__":
    main()
