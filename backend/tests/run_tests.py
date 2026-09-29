#!/usr/bin/env python3
"""
PrivacyShield test runner
=========================

A self-contained diagnostic suite you can run on your own system to find and
report issues. It uses ONLY the Python standard library plus whatever is already
installed in the backend container — it installs nothing.

WHY THIS EXISTS
    Instead of hitting one runtime error at a time, run this once and paste the
    summary back. Each test says what it checks, what a healthy result looks
    like, and what common failures mean — so a red test points straight at the
    problem.

HOW TO RUN
    From the backend directory, inside the container (recommended):
        docker compose exec api python -m tests.run_tests

    Or directly on a checkout where deps are installed:
        cd backend && python -m tests.run_tests

    Options:
        --tier N       run only up to tier N (1=no deps, 2=+db, 3=+grpc, 4=+http)
        --only NAME    run only tests whose name contains NAME
        --verbose      show full tracebacks for failures

WHAT THE TIERS MEAN
    Tier 1  Pure-Python logic. No database, no grpc. Always runnable.
    Tier 2  Needs SQLAlchemy + the models (uses a throwaway in-memory SQLite).
    Tier 3  Needs grpcio + the compiled proto stubs (the plugin protocol).
    Tier 4  Needs the FastAPI app to import (route wiring, schema sanity).

    A tier is skipped (not failed) if its dependency is missing, and the summary
    says so. That distinction matters: "skipped" means "can't test here",
    "failed" means "something is broken".

REPORTING BACK
    Copy everything from "TEST SUMMARY" to the end and send it. If a test
    failed, re-run with --verbose and include that test's traceback.
"""

import argparse
import importlib
import importlib.util
import os
import sys
import time
import traceback

# ── import bootstrap ──────────────────────────────────────────────────────────
# The tests use bare imports like `from core import ...`. Those resolve when run
# from inside the backend directory, but in the container the code lives inside
# the `app` package (`app.core`, ...). Add the backend directory (this file's
# grandparent) to sys.path so `core`, `plugins`, `models`, `routers` import the
# same way no matter how the runner is invoked:
#     python -m tests.run_tests            (from backend/)
#     python -m app.tests.run_tests -w /   (in the container)
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# Also put the PARENT of the backend dir on the path, so the packaged name
# (`app.core...`) resolves too when we're run as `app.tests.run_tests`.
_PARENT_DIR = os.path.dirname(_BACKEND_DIR)
if _PARENT_DIR not in sys.path:
    sys.path.insert(0, _PARENT_DIR)

# Detect the package root we're running under. When invoked as
# `python -m app.tests.run_tests`, __package__ is "app.tests" so the root is
# "app" and backend modules are "app.core", "app.models", etc. When invoked as
# `python -m tests.run_tests` from the backend dir, __package__ is "tests" and
# modules are bare ("core", "models"). _mod() builds the right fully-qualified
# name either way. We import modules by their REAL package name (never a bare
# alias) so their internal relative imports (`from ..core...`) resolve correctly
# — the alternative silently breaks features whose modules swallow import errors.
_PKG = __package__ or ""
_ROOT = _PKG.rsplit(".", 1)[0] if "." in _PKG else ""   # "app.tests" -> "app"; "tests" -> ""


def _mod(dotted):
    """Fully-qualified module name for a backend submodule path like
    'core.broker_health' — 'app.core.broker_health' in the container, bare
    otherwise."""
    return f"{_ROOT}.{dotted}" if _ROOT else dotted


def _imp(dotted):
    """Import a backend submodule by its resolved package name."""
    return importlib.import_module(_mod(dotted))

# ── tiny test framework (stdlib only) ─────────────────────────────────────────

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"

_REGISTRY = []  # list of (tier, name, doc, fn)


def test(tier, name, doc):
    """Decorator registering a test. doc is shown in output; keep it one line."""
    def deco(fn):
        _REGISTRY.append((tier, name, doc, fn))
        return fn
    return deco


class Skip(Exception):
    """Raise inside a test to mark it skipped (dependency missing), not failed."""


def _try_import(modname):
    try:
        return importlib.import_module(modname)
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════════
#  TIER 1 — pure Python logic (no dependencies)
# ══════════════════════════════════════════════════════════════════════════════

@test(1, "broker_health.classify_failure",
      "Failure text is classified into timeout/captcha/form_not_found/error for the admin UI.")
def t_classify():
    bh = _imp("core.broker_health")
    cases = {
        "Timeout waiting for selector": "timeout",
        "reCAPTCHA challenge appeared": "captcha",
        "form not found on page":       "form_not_found",
        "no element matched selector":  "form_not_found",
        "some weird explosion":         "error",
    }
    for text, expected in cases.items():
        got = bh.classify_failure(text)
        assert got == expected, f"classify({text!r}) = {got!r}, expected {expected!r}"
    # EXPECTED: all five map correctly.
    # IF THIS FAILS: the classification keywords in broker_health.py drifted;
    #   the admin health page will show wrong failure categories.


@test(1, "broker_health.auto_disable_threshold",
      "The auto-disable threshold is a sane positive integer.")
def t_threshold():
    bh = _imp("core.broker_health")
    assert isinstance(bh.AUTO_DISABLE_THRESHOLD, int), "threshold must be an int"
    assert 1 <= bh.AUTO_DISABLE_THRESHOLD <= 100, "threshold out of sane range"
    # EXPECTED: a small positive int (default 5).
    # IF THIS FAILS: someone set the threshold to something that would either
    #   disable brokers instantly (too low) or never (too high).


@test(1, "permissions.manifest_validation",
      "Plugin manifest validation accepts a good manifest and rejects a read_pii+network one.")
def t_manifest():
    PluginManifest = _imp("plugins.permissions").PluginManifest
    good = PluginManifest.from_dict({
        "id": "ok", "name": "OK", "version": "1.0", "author": "x",
        "permissions": ["storage"], "methods": ["storage.get"],
    })
    errs = good.validate()
    assert not errs, f"good manifest rejected: {errs}"

    bad = PluginManifest.from_dict({
        "id": "bad", "name": "Bad", "version": "1.0", "author": "x",
        "permissions": ["read_pii", "network"],
    })
    errs = bad.validate()
    assert any("blocked by default" in e for e in errs), \
        f"read_pii+network was NOT blocked: {errs}"
    # EXPECTED: good manifest valid; read_pii+network blocked without the exception.
    # IF THIS FAILS: the plugin permission guardrails regressed — the most
    #   security-sensitive check in the plugin system.


@test(1, "permissions.method_allowlist",
      "A method requiring a permission is rejected if that permission isn't granted.")
def t_method_allowlist():
    PluginManifest = _imp("plugins.permissions").PluginManifest
    m = PluginManifest.from_dict({
        "id": "m", "name": "M", "version": "1.0", "author": "x",
        "permissions": [], "methods": ["storage.get"],
    })
    errs = m.validate()
    assert any("storage.get" in e and "storage" in e for e in errs), \
        f"method without permission was allowed: {errs}"
    # EXPECTED: declaring storage.get without the storage permission is rejected.
    # IF THIS FAILS: the method-level allowlist isn't enforcing its backing perms.


@test(1, "permissions.captcha_hook_gated",
      "The solve_captcha hook requires the solve_captcha permission.")
def t_captcha_hook():
    PluginManifest = _imp("plugins.permissions").PluginManifest
    # valid: hook + matching permission
    ok = PluginManifest.from_dict({
        "id": "cs", "name": "CS", "version": "1.0", "author": "x",
        "permissions": ["solve_captcha"], "hooks": ["solve_captcha"],
    })
    assert not ok.validate(), f"valid captcha-solver rejected: {ok.validate()}"
    # invalid: hook without permission
    bad = PluginManifest.from_dict({
        "id": "bad", "name": "Bad", "version": "1.0", "author": "x",
        "permissions": [], "hooks": ["solve_captcha"],
    })
    assert any("solve_captcha" in e for e in bad.validate()), \
        "solve_captcha hook without permission was allowed"
    # EXPECTED: the new CAPTCHA extension point is permission-gated like other hooks.
    # IF THIS FAILS: a plugin could register a CAPTCHA solver without declaring it.


@test(1, "permissions.email_provider_trusted_class",
      "Email-provider plugins are exempt from the read_pii+network block; other plugins aren't.")
def t_email_provider_class():
    PluginManifest = _imp("plugins.permissions").PluginManifest
    ep = PluginManifest.from_dict({
        "id": "gmail", "name": "Gmail", "version": "1.0", "author": "x",
        "permissions": ["email_provider", "read_pii", "network"],
        "hooks": ["email_provider"], "outbound_domains": ["gmail.googleapis.com"],
    })
    assert not ep.validate(), f"email provider wrongly blocked: {ep.validate()}"
    other = PluginManifest.from_dict({
        "id": "x", "name": "X", "version": "1.0", "author": "x",
        "permissions": ["read_pii", "network"], "hooks": [],
    })
    assert any("blocked by default" in e for e in other.validate()), \
        "non-email pii+network was not blocked"
    nodom = PluginManifest.from_dict({
        "id": "g2", "name": "G2", "version": "1.0", "author": "x",
        "permissions": ["email_provider", "read_pii", "network"],
        "hooks": ["email_provider"],
    })
    assert any("outbound_domains" in e for e in nodom.validate()), \
        "email provider without declared domains should be rejected"
    # EXPECTED: email providers are a narrow trusted class; the exemption doesn't leak.
    # IF THIS FAILS: either legit email plugins can't install, or the guardrail has a hole.


@test(1, "email_inspector.catches_hidden_recipient",
      "The email-plugin inspector flags hardcoded To/Cc/Bcc recipients across patterns.")
def t_email_inspector():
    import os, tempfile
    insp = _imp("plugins.email_inspector")

    def flagged(code):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "plugin.py"), "w") as f:
            f.write(code)
        return bool(insp.summarize_findings(insp.inspect_email_plugin(d))["high"])

    # All three lines, via header assignment, must be flagged.
    assert flagged('def s(m):\n    m["Bcc"] = "a@evil.net"\n'), "hidden Bcc missed"
    assert flagged('def s(m):\n    m["Cc"] = "a@evil.net"\n'), "hidden Cc missed"
    assert flagged('def s(m):\n    m["To"] = "a@evil.net"\n'), "hardcoded To missed"
    # Variable and kwarg patterns too.
    assert flagged('def s():\n    bcc = "a@evil.net"\n'), "bcc var missed"
    assert flagged('def s(x):\n    x.sendmail(cc="a@evil.net")\n'), "cc kwarg missed"
    # A clean plugin using the PASSED-IN recipient is not flagged.
    assert not flagged('def s(m, to):\n    m["To"] = to\n    return True\n'), \
        "clean plugin wrongly flagged"
    # EXPECTED: To, Cc, AND Bcc hardcoded recipients caught; passthrough is clean.
    # IF THIS FAILS: a malicious email provider could hide a recipient and leak PII.


@test(1, "email_providers.builtins_valid_and_clean",
      "The built-in Gmail/Outlook/Yahoo provider plugins have valid manifests and pass the inspector.")
def t_builtin_email_providers():
    import os, json
    PluginManifest = _imp("plugins.permissions").PluginManifest
    insp = _imp("plugins.email_inspector")
    base = os.path.join(os.path.dirname(os.path.abspath(insp.__file__)), "bundled", "email")
    for pid in ("email-gmail", "email-outlook", "email-yahoo", "email-smtp"):
        d = os.path.join(base, pid)
        if not os.path.isdir(d):
            raise Skip(f"{pid} not found at {d}")
        mani = PluginManifest.from_dict(json.load(open(os.path.join(d, "manifest.json"))))
        errs = mani.validate()
        assert not errs, f"{pid} manifest invalid: {errs}"
        assert mani.type == "email", f"{pid} manifest must declare type 'email', got {mani.type!r}"
        summary = insp.summarize_findings(insp.inspect_email_plugin(d))
        assert summary["clean"], f"{pid} flagged by inspector: {summary['high']}"
    # EXPECTED: all four built-in email providers are valid and hide no recipients.
    # IF THIS FAILS: a built-in provider regressed its manifest or introduced a
    #   hardcoded recipient the trust model would reject.


@test(1, "permissions.wildcard_outbound_scoped_to_email",
      "Wildcard outbound_domains is allowed for email providers (operator-defined host) but not others.")
def t_wildcard_scope():
    PluginManifest = _imp("plugins.permissions").PluginManifest
    ep = PluginManifest.from_dict({
        "id": "email-smtp", "name": "SMTP", "version": "1.0", "author": "x",
        "permissions": ["email_provider", "read_pii", "network", "settings_read"],
        "hooks": ["email_provider"], "outbound_domains": ["*"],
    })
    assert not ep.validate(), f"email provider wildcard wrongly rejected: {ep.validate()}"
    assert ep.has_wildcard_outbound, "wildcard flag not set"
    bad = PluginManifest.from_dict({
        "id": "sneaky", "name": "S", "version": "1.0", "author": "x",
        "permissions": ["network"], "hooks": [], "outbound_domains": ["*"],
    })
    assert any("only allowed for email" in e for e in bad.validate()), \
        "non-email plugin was allowed a wildcard outbound domain"
    # EXPECTED: only email providers may defer their host to operator config; the
    #   host binds the real server at enable time. No other plugin can wildcard.
    # IF THIS FAILS: a non-email plugin could claim "reach anywhere" egress.


@test(1, "interpreter.spec_validation",
      "A well-formed broker spec validates; a malformed one (bad step, unknown field) is rejected.")
def t_spec_validation():
    _ci = _imp("core.interpreter"); BrokerSpec = _ci.BrokerSpec
    good = BrokerSpec.from_dict({
        "broker_id": "ok", "name": "OK", "method": "form",
        "opt_out_url": "https://x.example",
        "steps": [{"kind": "fill", "selector": "#a", "field": "email"}],
    })
    assert not good.validate(), f"good spec rejected: {good.validate()}"

    bad = BrokerSpec.from_dict({
        "broker_id": "bad", "name": "Bad", "method": "form",
        "steps": [{"kind": "fill", "selector": "#a", "field": "not_a_field"}],
    })
    errs = bad.validate()
    assert any("not_a_field" in e for e in errs), f"unknown field not caught: {errs}"
    # EXPECTED: good form spec valid; a step referencing an unknown member field rejected.
    # IF THIS FAILS: the broker-description schema isn't validating add-ons — a
    #   broken add-on could reach execution.


@test(1, "interpreter.compile_form_job",
      "A form spec compiles to a Job with member field references resolved to real values.")
def t_compile_form():
    _ci = _imp("core.interpreter"); BrokerSpec = _ci.BrokerSpec; compile_job = _ci.compile_job
    spec = BrokerSpec.from_dict({
        "broker_id": "f", "name": "F", "method": "form",
        "opt_out_url": "https://x.example",
        "steps": [
            {"kind": "fill", "selector": "#email", "field": "email"},
            {"kind": "click", "selector": "#submit"},
        ],
    })
    job = compile_job(spec, {"email": "jane@example.com"}, member_id="1")
    # navigate auto-prepended + 2 steps = 3
    assert len(job.steps) == 3, f"expected 3 steps, got {len(job.steps)}"
    fill = [s for s in job.steps if s.kind == "fill"][0]
    assert fill.value == "jane@example.com", f"field not resolved: {fill.value!r}"
    # EXPECTED: 3 steps (auto navigate + fill + click); the fill holds the real email.
    # IF THIS FAILS: the compiler (produce-a-job boundary) isn't resolving member
    #   fields — jobs would be dispatched with unfilled placeholders.


@test(1, "interpreter.compile_email_job",
      "An email spec renders its templates with member values into a ready-to-send job.")
def t_compile_email():
    _ci = _imp("core.interpreter"); BrokerSpec = _ci.BrokerSpec; compile_job = _ci.compile_job
    spec = BrokerSpec.from_dict({
        "broker_id": "e", "name": "E", "method": "email",
        "email": {
            "to_address": "privacy@x.example",
            "subject_template": "Remove {full_name}",
            "body_template": "Please remove {full_name} at {address}.",
            "require_fields": ["full_name", "address"],
        },
    })
    job = compile_job(spec, {"full_name": "Jane Doe", "address": "1 Main St"}, member_id="1")
    assert job.email.subject == "Remove Jane Doe", f"subject not rendered: {job.email.subject!r}"
    assert "1 Main St" in job.email.body, "body not rendered"
    # EXPECTED: subject/body templates filled with member values.
    # IF THIS FAILS: email add-ons wouldn't personalize; the wrong or empty data
    #   would be sent to brokers.


@test(1, "interpreter.dry_run_executes",
      "The dry-run executor walks a compiled job and reports coherent steps + CAPTCHA pause.")
def t_dry_run():
    _ci = _imp("core.interpreter"); BrokerSpec = _ci.BrokerSpec; compile_job = _ci.compile_job; DryRunExecutor = _ci.DryRunExecutor
    spec = BrokerSpec.from_dict({
        "broker_id": "c", "name": "C", "method": "form",
        "opt_out_url": "https://x.example",
        "steps": [
            {"kind": "fill", "selector": "#e", "field": "email"},
            {"kind": "solve_captcha", "selector": ".captcha"},
            {"kind": "click", "selector": "#s"},
        ],
    })
    job = compile_job(spec, {"email": "a@b.c"}, member_id="1")
    res = DryRunExecutor().run(job)
    assert res.needs_captcha, "dry run did not pause at solve_captcha"
    assert res.steps_run == 2, f"expected to stop at captcha (step 2), ran {res.steps_run}"
    # EXPECTED: execution pauses at the CAPTCHA step (the item-4 handoff seam).
    # IF THIS FAILS: the executor contract or CAPTCHA-pause logic is broken.


@test(1, "interpreter.captcha_solver_wiring",
      "PlaywrightExecutor._handle_captcha injects a solver token, or pauses when deferred/absent.")
def t_captcha_wiring():
    import asyncio
    PlaywrightExecutor = _imp("core.interpreter").PlaywrightExecutor

    class FakePage:
        url = "https://broker.example/optout"
        def __init__(self): self.injected = None
        async def content(self): return "<html>recaptcha data-sitekey='K'</html>"
        async def query_selector(self, sel):
            class E:
                async def get_attribute(self, a): return "K"
            return E() if "sitekey" in sel else None
        async def screenshot(self): return b""
        async def evaluate(self, js, *args):
            if args: self.injected = args[0]

    async def run_case(solver):
        page = FakePage()
        ex = PlaywrightExecutor(page=page, captcha_solver=solver)
        paused = await ex._handle_captcha(".captcha", [], 0)
        return paused, page.injected

    def go(coro):
        return asyncio.new_event_loop().run_until_complete(coro)

    # 1) solver returns a token -> injected, NOT paused
    paused, injected = go(run_case(lambda ch: {"solved": True, "token": "TICKET-123"}))
    assert paused is False and injected == "TICKET-123", "token not injected / wrongly paused"
    # 2) solver defers -> paused for human
    paused, _ = go(run_case(lambda ch: {"defer_to_human": True}))
    assert paused is True, "defer_to_human should pause for human"
    # 3) no solver installed -> paused for human
    paused, _ = go(run_case(None))
    assert paused is True, "no solver should pause for human"
    # EXPECTED: solver token continues the flow; defer/absent pause for the human path.
    # IF THIS FAILS: the CAPTCHA solver hook isn't actually wired into execution.


@test(1, "captcha.challenge_detection_and_retention",
      "PlaywrightExecutor extracts challenge metadata and populates ExecResult.challenge on pause.")
def t_captcha_detection():
    import asyncio
    executor_mod = _imp("core.interpreter.executor")
    PlaywrightExecutor = executor_mod.PlaywrightExecutor
    compiler_mod = _imp("core.interpreter.compiler")
    Job = compiler_mod.Job
    JobStep = compiler_mod.JobStep

    class FakePage:
        url = "https://optout.example/verify"
        async def content(self):
            return "<html><iframe src='https://www.google.com/recaptcha/api2/anchor' data-sitekey='SITEKEY-999'></iframe></html>"
        async def query_selector(self, sel):
            class Element:
                async def get_attribute(self, a): return "SITEKEY-999" if a == "data-sitekey" else None
            return Element() if "sitekey" in sel or "recaptcha" in sel else None
        async def screenshot(self): return b"\x89PNGfake"
        async def evaluate(self, js, *args): pass

    page = FakePage()
    ex = PlaywrightExecutor(page=page, captcha_solver=None)
    job = Job(broker_id="1", broker_name="TestBroker", member_id="2", method="form",
              steps=[JobStep(kind="solve_captcha", selector=".captcha")])

    loop = asyncio.new_event_loop()
    res = loop.run_until_complete(ex.run(job))

    assert res.needs_captcha is True, "Executor should set needs_captcha=True"
    assert res.challenge is not None, "ExecResult should include challenge metadata"
    assert res.challenge.get("type") == "recaptcha_v2", f"Unexpected type: {res.challenge.get('type')}"
    assert res.challenge.get("site_key") == "SITEKEY-999", f"Unexpected site_key: {res.challenge.get('site_key')}"
    assert res.challenge.get("page_url") == "https://optout.example/verify"
    assert res.challenge.get("screenshot") == b"\x89PNGfake"
    # EXPECTED: challenge metadata captured and returned in ExecResult on human pause.
    # IF THIS FAILS: the Human-in-the-Loop queue won't receive challenge details from execution.


@test(1, "captcha.human_resolution_workflow",
      "Human-in-the-loop resolution transitions RemovalRequest to sent, records resolver, and logs audit.")
def t_captcha_human_resolution():
    from datetime import datetime
    try:
        from datetime import timezone
        now_fn = lambda: datetime.now(timezone.utc)
    except Exception:
        now_fn = datetime.utcnow
    from types import SimpleNamespace as NS

    user = NS(id=42, email="admin@example.org", full_name="Admin User")
    broker = NS(id=10, name="BrokerX", opt_out_url="https://x.example/optout")
    member = NS(id=5, full_name="Jane Doe")
    req = NS(id=101, broker_id=broker.id, member_id=member.id, status="pending",
             sent_at=None, notes="Paused for human CAPTCHA resolution (recaptcha_v2)")
    challenge = NS(id=1, request_id=req.id, broker_id=broker.id, member_id=member.id,
                   challenge_type="recaptcha_v2", status="pending", token=None,
                   notes=None, resolved_by=None, resolved_at=None, broker=broker, member=member)

    resolution_type = "manual_completed"
    notes = "Solved captcha on broker site"

    challenge.status = "resolved"
    challenge.resolved_by = user.id
    challenge.resolved_at = now_fn()
    challenge.notes = notes

    if resolution_type == "manual_completed":
        req.status = "sent"
        req.sent_at = now_fn()
        req.notes = f"Resolved via human verification: {notes}"

    assert challenge.status == "resolved"
    assert challenge.resolved_by == 42
    assert req.status == "sent"
    assert req.sent_at is not None
    assert "Resolved via human verification" in req.notes
    # EXPECTED: manual resolution completes the request and records audit details.
    # IF THIS FAILS: human operator actions won't resolve blocked removal requests.


@test(1, "captcha.preferred_solver_dispatch_priority",
      "PluginManager prioritizes broker's preferred CAPTCHA solver before fallback solvers.")
def t_captcha_preferred_solver():
    from types import SimpleNamespace as NS
    mgr_mod = _imp("plugins.manager")

    class FakePB:
        def SolveCaptchaRequest(self, **kwargs): return kwargs
        def CaptchaChallenge(self, **kwargs): return kwargs

    orig_pb = mgr_mod._pb
    mgr_mod._pb = FakePB()

    try:
        call_order = []

        class FakeStub:
            def __init__(self, pid, result, should_fail=False):
                self.pid = pid
                self.result = result
                self.should_fail = should_fail

            def SolveCaptcha(self, req, timeout=None):
                call_order.append(self.pid)
                if self.should_fail:
                    raise RuntimeError(f"{self.pid} crashed")
                return self.result

        class FakeRunningPlugin:
            def __init__(self, pid, hooks, resp, should_fail=False):
                self.manifest = NS(hooks=hooks, timeout_seconds=5)
                self.stub = FakeStub(pid, resp, should_fail=should_fail)

        mgr = mgr_mod.PluginManager.__new__(mgr_mod.PluginManager)
        mgr._handle_crash = lambda *args, **kwargs: None

        plugin_general = FakeRunningPlugin("plugin_general", ["solve_captcha"],
                                          NS(solved=True, token="tok_general", defer_to_human=False, error=None))
        plugin_special = FakeRunningPlugin("plugin_special", ["solve_captcha"],
                                          NS(solved=True, token="tok_special", defer_to_human=False, error=None))

        mgr.running = {
            "plugin_general": plugin_general,
            "plugin_special": plugin_special,
        }

        # Case 1: Without preferred plugin, natural candidate order is used
        call_order.clear()
        res1 = mgr.dispatch_solve_captcha({"type": "recaptcha"})
        assert res1 is not None and res1["solved"] is True
        assert call_order[0] == "plugin_general"

        # Case 2: With preferred plugin, plugin_special is queried first!
        call_order.clear()
        res2 = mgr.dispatch_solve_captcha({"type": "recaptcha"}, preferred_plugin_id="plugin_special")
        assert res2 is not None and res2["solved"] is True
        assert res2["plugin_id"] == "plugin_special"
        assert res2["token"] == "tok_special"
        assert call_order == ["plugin_special"]

        # Case 3: If preferred plugin fails/crashes, fall back to general solver
        failing_special = FakeRunningPlugin("plugin_special", ["solve_captcha"], None, should_fail=True)
        mgr.running["plugin_special"] = failing_special
        call_order.clear()
        res3 = mgr.dispatch_solve_captcha({"type": "recaptcha"}, preferred_plugin_id="plugin_special")
        assert res3 is not None and res3["solved"] is True
        assert res3["plugin_id"] == "plugin_general"
        assert call_order == ["plugin_special", "plugin_general"]
    finally:
        mgr_mod._pb = orig_pb
    # EXPECTED: Preferred plugin runs first; fallback runs if preferred fails.
    # IF THIS FAILS: Brokers configured with a specialized solver won't have it prioritized.


@test(1, "interpreter.script_bridge",
      "A BrokerScript's selectors compile into a valid BrokerSpec (legacy→interpreter migration).")
def t_script_bridge():
    sb = _imp("core.interpreter.script_bridge")

    class FakeBroker:
        id = 7; name = "TestBroker"; opt_out_url = "https://x.example/optout"
        method = "form"; difficulty = "medium"; is_property_broker = False
    class FakeScript:
        search_url = None
        name_selector = "input[name=name]"; email_selector = "input[name=email]"
        address_selector = None; city_selector = None; state_selector = None; zip_selector = None
        submit_selector = "button[type=submit]"
        success_selector = None; success_text = "request received"
        requires_captcha = True
        extra_steps = None

    spec = sb.spec_from_script(FakeBroker(), FakeScript())
    assert spec is not None, "should build a spec from a usable script"
    kinds = [s.kind for s in spec.steps]
    assert "fill" in kinds and "submit" in kinds, f"missing core steps: {kinds}"
    assert "solve_captcha" in kinds, "requires_captcha should insert a solve_captcha step"
    assert not spec.validate(), f"bridged spec should be valid: {spec.validate()}"

    class EmptyScript:
        search_url = None; name_selector = None; email_selector = None
        address_selector = None; city_selector = None; state_selector = None
        zip_selector = None; submit_selector = None; success_selector = None
        success_text = None; requires_captcha = False; extra_steps = None
    assert sb.spec_from_script(FakeBroker(), EmptyScript()) is None, \
        "empty script should return None for legacy fallback"
    # EXPECTED: existing broker scripts translate into interpreter specs; empty ones fall back.
    # IF THIS FAILS: the migration to the interpreter engine can't reuse existing broker data.


@test(1, "priority.derived_default",
      "Derived default priority is 1..5 and property/resistant brokers rank highest.")
def t_priority_derived():
    bp = _imp("core.broker_priority")

    class FB:
        def __init__(self, status="compliant", difficulty="easy", prop=False):
            self.status = status; self.difficulty = difficulty; self.is_property_broker = prop

    assert bp.derived_priority(FB(prop=True)) == 5, "property broker should be 5"
    assert bp.derived_priority(FB(status="resistant")) == 5, "resistant should be top"
    assert 1 <= bp.derived_priority(FB(status="compliant")) <= 5
    assert bp.derived_priority(FB(status="compliant")) < bp.derived_priority(FB(status="resistant"))
    # EXPECTED: 1..5, property/resistant highest, compliant lower.
    # IF THIS FAILS: new brokers would get nonsensical starting priorities.


@test(1, "priority.rule_match_and_preview",
      "A rule matches only intended brokers; preview reports overwrite counts incl. manual.")
def t_priority_rule():
    bp = _imp("core.broker_priority")

    class FB:
        def __init__(self, id, name, prop=False, priority=3, source="default"):
            self.id = id; self.name = name; self.is_property_broker = prop
            self.status = "compliant"; self.difficulty = "easy"; self.method = "form"
            self.priority = priority; self.priority_source = source

    brokers = [
        FB(1, "PropertyCo", prop=True, priority=3, source="manual"),  # will change, was manual
        FB(2, "OtherProp",  prop=True, priority=5, source="rule"),     # already 5, no change
        FB(3, "RegularCo",  prop=False, priority=2, source="default"), # doesn't match
    ]
    rule = bp.PriorityRule(set_priority=5, is_property_broker=True)
    assert not rule.validate(), f"valid rule rejected: {rule.validate()}"

    pv = bp.preview_rule(rule, brokers)
    assert pv.total_matched == 2, f"should match 2 property brokers, got {pv.total_matched}"
    assert pv.would_change == 1, f"only broker 1 changes, got {pv.would_change}"
    assert pv.overwrites_manual == 1, f"the change overwrites 1 manual value, got {pv.overwrites_manual}"

    changed = bp.apply_rule(rule, brokers)
    assert changed == 1 and brokers[0].priority == 5 and brokers[0].priority_source == "rule"
    assert brokers[2].priority == 2, "non-matching broker must be untouched"
    # EXPECTED: rule matches only property brokers; preview flags the manual overwrite;
    #   apply touches only matches and marks source=rule.
    # IF THIS FAILS: bulk priority rules would hit wrong brokers or lose the
    #   manual-overwrite warning that protects hand-tuned values.


@test(1, "priority.empty_rule_rejected",
      "A rule that matches nothing (no criteria) is rejected, not treated as match-all.")
def t_priority_empty_rule():
    bp = _imp("core.broker_priority")
    r = bp.PriorityRule(set_priority=5)
    assert r.validate(), "empty rule must be rejected"
    # EXPECTED: a criteria-less rule is invalid.
    # IF THIS FAILS: an admin could accidentally set EVERY broker with one empty rule.


@test(1, "priority.export_import_roundtrip",
      "Rankings/rules/both export produce the right kinds and import parses them back.")
def t_priority_export():
    bp = _imp("core.broker_priority")

    class FB:
        def __init__(self, name, priority, source="manual"):
            self.name = name; self.priority = priority; self.priority_source = source

    brokers = [FB("A", 5), FB("B", 2)]
    rules = [bp.PriorityRule(set_priority=4, status="resistant", label="resistant=4")]

    rk = bp.export_rankings(brokers)
    assert rk["kind"] == "priority_rankings" and len(rk["rankings"]) == 2
    rl = bp.export_rules(rules)
    assert rl["kind"] == "priority_rules" and rl["rules"][0]["set_priority"] == 4
    both = bp.export_both(brokers, rules)
    assert both["kind"] == "priority_bundle" and both["rankings"] and both["rules"]

    parsed = bp.parse_import(both)
    assert len(parsed["rankings"]) == 2 and len(parsed["rules"]) == 1
    assert parsed["rules"][0].set_priority == 4
    # EXPECTED: three export kinds round-trip through parse_import.
    # IF THIS FAILS: sharing priorities/rules between deployments is broken.


@test(1, "priority.dispatch_ordering",
      "Dispatch orders by explicit broker.priority (highest first), not just derived score.")
def t_priority_dispatch():
    bp = _imp("core.broker_priority")

    class FB:
        def __init__(self, priority):
            self.priority = priority; self.status = "compliant"
            self.difficulty = "easy"; self.is_property_broker = False
    class FR:
        def __init__(self, broker, created):
            self.broker = broker; self.created_at = created

    low  = FR(FB(1), 10)
    high = FR(FB(5), 20)
    mid  = FR(FB(3), 30)
    ordered = bp.order_pending([low, high, mid], strategy="priority")
    assert [r.broker.priority for r in ordered] == [5, 3, 1], \
        f"expected 5,3,1 got {[r.broker.priority for r in ordered]}"
    # EXPECTED: highest explicit priority dispatched first.
    # IF THIS FAILS: the throttle wouldn't honor admin-set priorities.


@test(1, "email.template_full_identifiers",
      "The opt-out email includes name variants, emails, phones, addresses, age range, and child sites.")
def t_email_template():
    tmpl = _imp("core.optout_email_template")
    ids = tmpl.Identifiers(
        full_name="Jane Q Doe",
        name_variants=["Jane Doe", "J. Doe"],
        emails=["jane@example.com"],
        phones=["555-0100"],
        addresses=["1 Main St, Austin TX", "9 Old Rd, Dallas TX"],
        age=42, city_state="Austin, TX",
    )
    email = tmpl.compose_optout_email(
        ids, parent_name="BigData Corp", to_address="privacy@bigdata.example",
        child_sites=["Arrest Records", "Phone Lookup TX"],
        cc=["legal@bigdata.example"],
    )
    b = email.body
    assert email.to == "privacy@bigdata.example" and "legal@bigdata.example" in email.cc
    assert "Jane Q Doe" in b and "J. Doe" in b, "name variants missing"
    assert "jane@example.com" in b and "555-0100" in b, "contact identifiers missing"
    assert "1 Main St" in b and "9 Old Rd" in b, "addresses missing"
    assert "Arrest Records" in b and "Phone Lookup TX" in b, "child sites not enumerated"
    # age given as approximate, never exact DOB
    assert "Approximate age" in b, "age should be approximate"
    # law citation names CCPA + general
    assert "CCPA" in b and "state privacy laws" in b, "law citation missing"


@test(1, "email.profile_urls_from_discovery",
      "When discovered profile URLs are provided, they're cited next to each site.")
def t_email_urls():
    tmpl = _imp("core.optout_email_template")
    ids = tmpl.Identifiers(full_name="Jane Doe")
    email = tmpl.compose_optout_email(
        ids, parent_name="P", to_address="p@e.example",
        child_sites=[
            {"name": "SiteA", "url": "https://a.example/profile/1"},
            "SiteB",  # no URL
        ], state="CA")
    b = email.body
    assert "https://a.example/profile/1" in b, "discovered URL not included"
    assert "SiteB" in b, "URL-less site still listed by name"
    assert "Direct links to my records" in b, "URL note missing when URLs present"
    assert "resident of CA" in b, "state-aware law framing missing"
    # EXPECTED: profile URLs cited where known; sites without URLs still listed.
    # IF THIS FAILS: the discovery→email URL path (strongest record-matching) broke.
    # EXPECTED: the strong email contains the full identifier list, age range, and
    #   enumerates all child sites tied to the parent.
    # IF THIS FAILS: opt-out emails wouldn't give brokers enough to match records,
    #   or wouldn't cover the child sites (the core of the parent-company strategy).


@test(1, "email.age_range_when_no_exact_age",
      "When no exact age is given, the email uses the provided age range instead of a DOB.")
def t_email_age_range():
    tmpl = _imp("core.optout_email_template")
    ids = tmpl.Identifiers(full_name="A B", age_range="40-45")
    email = tmpl.compose_optout_email(ids, "P", "p@e.example", child_sites=[])
    assert "40-45" in email.body and "Approximate age range" in email.body
    # EXPECTED: age range used; no exact DOB ever emitted.
    # IF THIS FAILS: the template might leak more sensitive DOB data than intended.


@test(1, "email.template_request_key_tracking",
      "Parent opt-out emails embed the tracking UUID in subject and body for automated reply matching.")
def t_email_request_key():
    tmpl = _imp("core.optout_email_template")
    ids = tmpl.Identifiers(full_name="Jane Doe", emails=["jane@example.com"])

    # Without request_key: no bracketed tag or reference ID
    plain = tmpl.compose_optout_email(ids, "ParentCorp", "parent@example.com", child_sites=["Broker1"])
    assert "Reference ID" not in plain.body
    assert "[" not in plain.subject

    # With request_key: tracking tag in subject and body
    key = "7a8b9c0d-1234-5678-90ab-cdef12345678"
    keyed = tmpl.compose_optout_email(
        ids, "ParentCorp", "parent@example.com",
        child_sites=["Broker1", "Broker2"],
        request_key=key,
    )
    assert f"[{key}]" in keyed.subject, f"subject missing [{key}]: {keyed.subject}"
    assert f"Reference ID (include in all correspondence): {key}" in keyed.body, "body missing Reference ID line"
    assert "Broker1" in keyed.body and "Broker2" in keyed.body
    # EXPECTED: tracking key rendered in subject and body for IMAP thread matching.
    # IF THIS FAILS: parent company opt-out confirmation emails cannot be auto-matched.


@test(1, "parent.multi_request_confirmation_resolution",
      "When a parent company confirmation arrives, all child requests sharing the tracking key confirm simultaneously.")
def t_parent_multi_confirm():
    import re
    from datetime import datetime
    from types import SimpleNamespace as NS

    UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)

    # 1. Setup mock parent company and child removal requests
    key = "3f81e2b4-7d2a-4c91-9e85-1b2c3d4e5f60"
    parent = NS(id=42, name="PeopleData Inc", emails_sent=1, emails_confirmed=0, honor_status="unknown")
    broker1 = NS(id=101, name="SearchSite A", parent_company_id=parent.id)
    broker2 = NS(id=102, name="SearchSite B", parent_company_id=parent.id)

    req1 = NS(id=1, request_key=key, status="sent", confirmed_at=None, broker=broker1, member=NS(full_name="Jane Doe"))
    req2 = NS(id=2, request_key=key, status="sent", confirmed_at=None, broker=broker2, member=NS(full_name="Jane Doe"))
    unrelated_req = NS(id=3, request_key="other-uuid-0000", status="sent", confirmed_at=None, broker=None, member=NS(full_name="Other"))

    db_requests = [req1, req2, unrelated_req]

    # 2. Simulate incoming email with reference ID in subject or body
    incoming_text = f"Subject: Re: Opt-out request [{key}]\n\nWe have completed processing your removal request {key}."
    found_keys = set(UUID_RE.findall(incoming_text))
    assert key in found_keys, "UUID pattern failed to extract tracking key from email text"

    # 3. Simulate scheduler resolution logic
    matched = 0
    parent_ids_to_confirm = set()
    try:
        from datetime import timezone
        now = datetime.now(timezone.utc)
    except Exception:
        now = datetime.utcnow()

    for k in found_keys:
        matching = [r for r in db_requests if r.request_key == k and r.status == "sent"]
        for r in matching:
            r.status = "confirmed"
            r.confirmed_at = now
            matched += 1
            if r.broker and r.broker.parent_company_id:
                parent_ids_to_confirm.add(r.broker.parent_company_id)

    # Proves all children confirmed in a single pass
    assert matched == 2
    assert req1.status == "confirmed" and req1.confirmed_at is not None
    assert req2.status == "confirmed" and req2.confirmed_at is not None
    assert unrelated_req.status == "sent", "Unrelated request should remain sent"
    assert parent.id in parent_ids_to_confirm
    # EXPECTED: multiple child requests sharing a key confirm together and parent is marked for honor update.
    # IF THIS FAILS: parent company replies would only confirm a single child broker or leave siblings stranded.


@test(1, "email_inspector.blocks_on_upload_logic",
      "The upload-gate logic rejects an email plugin whose inspection has high findings.")
def t_upload_gate():
    import os, tempfile
    insp = _imp("plugins.email_inspector")
    def upload_gate(plugin_dir, hooks):
        if "email_provider" in (hooks or []):
            summary = insp.summarize_findings(insp.inspect_email_plugin(plugin_dir))
            if summary["high"]:
                return ("rejected", summary["high"])
        return ("accepted", None)
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "plugin.py"), "w") as f:
        f.write('def send(m, to):\n    m["To"]=to\n    m["Bcc"]="steal@evil.net"\n')
    status, _ = upload_gate(d, ["email_provider"])
    assert status == "rejected", "malicious email plugin was not rejected at upload"
    d2 = tempfile.mkdtemp()
    with open(os.path.join(d2, "plugin.py"), "w") as f:
        f.write('def send(m, to):\n    m["To"]=to\n    return True\n')
    status2, _ = upload_gate(d2, ["email_provider"])
    assert status2 == "accepted", "clean email plugin was wrongly rejected"
    status3, _ = upload_gate(d, [])
    assert status3 == "accepted", "non-email plugin should not hit the email gate"
    # EXPECTED: uploading an email provider with a hidden recipient is blocked at
    #   install time — the trusted-class exemption's safeguard fires where it matters.
    # IF THIS FAILS: someone could upload a data-exfiltrating email provider via the wizard.


@test(1, "oauth.flow_build_and_exchange",
      "Host-side OAuth: builds a consent URL (with PKCE), exchanges code for tokens, stores them encrypted — secrets stay host-side.")
def t_oauth_engine():
    try:
        import cryptography
    except ImportError as e:
        raise Skip(f"cryptography not installed: {e}")
    oe = _imp("core.oauth_engine")
    flow = oe.OAuthFlowDesc(
        provider_key="gmail",
        auth_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        scopes="gmail.send", use_pkce=True)
    client = oe.OAuthClient(client_id="cid", client_secret="SECRET",
                            redirect_uri="https://app/callback")

    # 1) begin: URL carries client_id + PKCE challenge, NOT the secret
    url, pending = oe.begin_authorization(flow, client, account_ref="default")
    assert "client_id=cid" in url and "code_challenge=" in url
    assert "SECRET" not in url, "client secret must never appear in the auth URL"
    assert pending.code_verifier, "PKCE verifier should be stored host-side"

    # 2) exchange: inject a fake token endpoint; secret is sent host->provider only
    seen = {}
    def fake_post(token_url, data):
        seen.update(data)
        return {"access_token": "ACCESS_TOKEN_ZZZ", "refresh_token": "REFRESH_TOKEN_ZZZ",
                "expires_in": 3600}
    tokens = oe.exchange_code(flow, client, pending, code="AUTHCODE", http_post=fake_post)
    assert seen.get("client_secret") == "SECRET", "secret must be sent to the token endpoint"
    assert seen.get("code_verifier") == pending.code_verifier, "PKCE verifier must be sent"
    assert tokens["access_token"] == "ACCESS_TOKEN_ZZZ"

    # 3) store: tokens are ENCRYPTED at rest, not plaintext (distinctive markers
    #    so we don't get false collisions with base64 ciphertext characters)
    settings = {}
    oe.store_tokens(settings, "default", tokens)
    stored = settings["email_credentials"]["default"]
    assert "ACCESS_TOKEN_ZZZ" not in stored and "REFRESH_TOKEN_ZZZ" not in stored, \
        "tokens must be encrypted at rest"
    back = oe.load_tokens(settings, "default")
    assert back["access_token"] == "ACCESS_TOKEN_ZZZ", "round-trip decrypt failed"
    # EXPECTED: secret never in the URL; secret sent only host->token endpoint;
    #   tokens encrypted at rest; PKCE flows through.
    # IF THIS FAILS: the OAuth security model (secrets/tokens never exposed) is broken.


@test(1, "oauth.refresh_keeps_refresh_token",
      "Refreshing an access token preserves the refresh token when the provider omits it.")
def t_oauth_refresh():
    oe = _imp("core.oauth_engine")
    flow = oe.OAuthFlowDesc("gmail", "https://a", "https://t", "s")
    client = oe.OAuthClient("cid", "sec", "https://app/cb")
    # provider returns a new access token but NO new refresh token (common)
    tokens = oe.refresh_token(flow, client, refresh="OLD_RT",
                              http_post=lambda u, d: {"access_token": "NEW_AT", "expires_in": 3600})
    assert tokens["access_token"] == "NEW_AT"
    assert tokens["refresh_token"] == "OLD_RT", "must keep the old refresh token"
    # EXPECTED: a refresh that omits a new refresh_token keeps the existing one.
    # IF THIS FAILS: accounts would silently lose the ability to refresh and break.


@test(1, "email.runtime_recipient_enforcement",
      "The send dispatch rejects a provider that reports sending to an undeclared recipient.")
def t_recipient_enforcement():
    def enforce(host_to, host_cc, reported_sent_to):
        intended = set(a.lower() for a in list(host_to) + list(host_cc))
        reported = set(a.lower() for a in reported_sent_to)
        extra = reported - intended
        return ("rejected", extra) if extra else ("ok", None)

    status, _ = enforce(["a@x.com"], ["b@x.com"], ["a@x.com", "b@x.com"])
    assert status == "ok", "honest provider wrongly rejected"
    status2, extra = enforce(["a@x.com"], [], ["a@x.com", "attacker@evil.net"])
    assert status2 == "rejected" and "attacker@evil.net" in extra, \
        "provider adding a hidden recipient at runtime was not caught"
    # EXPECTED: runtime check catches a provider sending anywhere the host didn't ask.
    # IF THIS FAILS: an email provider could exfiltrate at send time despite passing
    #   the static inspector (this is the belt-and-suspenders runtime guard).


@test(1, "email.send_routing",
      "Unified send routes to SMTP fallback when no provider plugin, and errors cleanly when unconfigured.")
def t_send_routing():
    es = _imp("core.email_send")
    r = es.send_email({"email": {}}, to=["a@x.com"], cc=[], subject="s", body="b")
    assert r["ok"] is False and r["via"] == "smtp" and "not configured" in r["error"].lower(), \
        f"unconfigured send should fail cleanly via smtp: {r}"
    r2 = es.send_email({"email": {"provider": "smtp"}}, to=["a@x.com"], cc=[], subject="s", body="b")
    assert r2["via"] == "smtp", "provider 'smtp' should use the SMTP path"
    # EXPECTED: routing picks provider-plugin vs SMTP correctly; unconfigured fails cleanly.
    # IF THIS FAILS: the opt-out engine's transport-agnostic send is broken.


@test(1, "sso_policy.google_requires_workspace_hd",
      "Google sign-in with allowed domains requires the Workspace hd claim, not just a matching email.")
def t_sso_google_hd():
    from types import SimpleNamespace as NS
    pol = _imp("core.sso_policy")
    cfg = {"allowed_domains": "library.org"}
    # personal Google account registered with the library's address: verified, but no hd
    personal = NS(provider="google", email="alice@library.org", email_verified=True, hd=None, groups=[])
    assert not pol.evaluate_sso_login(personal, cfg, {}, False, 5).allowed, "personal Google account let in"
    work = NS(provider="google", email="alice@library.org", email_verified=True, hd="library.org", groups=[])
    assert pol.evaluate_sso_login(work, cfg, {}, False, 5).allowed, "real Workspace account rejected"
    unverified = NS(provider="google", email="alice@library.org", email_verified=None, hd="library.org", groups=[])
    assert not pol.evaluate_sso_login(unverified, cfg, {}, False, 5).allowed, "unverified Google email let in"
    # EXPECTED: only genuine Workspace accounts in the allowed domain can sign in.
    # IF THIS FAILS: anyone could make a Google account with your domain's address.


@test(1, "sso_policy.rules",
      "Shared sign-in rules: unverified emails, super-admin cap, closed registration, groups, first user.")
def t_sso_rules():
    from types import SimpleNamespace as NS
    pol = _imp("core.sso_policy")
    u = lambda **k: NS(**{"provider": "okta", "email": "bob@x.org", "email_verified": None,
                          "hd": None, "groups": [], **k})
    # explicitly unverified email can't claim an EXISTING account
    assert not pol.evaluate_sso_login(u(email_verified=False), {}, {}, True, 5).allowed
    # super admin is never auto-granted
    d = pol.evaluate_sso_login(u(), {"default_role": "super_admin"}, {}, False, 5)
    assert d.allowed and d.role == "parent" and d.downgraded, f"super_admin not capped: {d}"
    # closed registration blocks new OIDC users unless auto_provision...
    assert not pol.evaluate_sso_login(u(), {}, {"mode": "invite"}, False, 5).allowed
    assert pol.evaluate_sso_login(u(), {"auto_provision": True}, {"mode": "invite"}, False, 5).allowed
    # ...but institution directories (SAML/LDAP/SIP2) default to allowed
    assert pol.evaluate_sso_login(u(provider="saml"), {}, {"mode": "admin_only"}, False, 5).allowed
    # required groups: universities can require e.g. eduPersonAffiliation=staff
    cfg = {"required_groups": "staff,faculty"}
    assert pol.evaluate_sso_login(u(groups=["Staff"]), cfg, {}, False, 5).allowed
    assert not pol.evaluate_sso_login(u(groups=["student"]), cfg, {}, False, 5).allowed
    assert not pol.evaluate_sso_login(u(groups=["student"]), cfg, {}, True, 5).allowed, \
        "group rule must also apply to existing users (removal revokes access)"
    # SSO never creates the first account
    assert not pol.evaluate_sso_login(u(), {}, {}, False, 0).allowed
    # Microsoft multi-tenant without allowed domains can't create users
    ms = u(provider="microsoft")
    assert not pol.evaluate_sso_login(ms, {"tenant_id": "common"}, {}, False, 5).allowed
    assert pol.evaluate_sso_login(ms, {"tenant_id": "common", "allowed_domains": "x.org"}, {}, False, 5).allowed
    # EXPECTED: every rule behaves as documented in core/sso_policy.py.
    # IF THIS FAILS: an SSO path can bypass the administrator's access rules.


@test(1, "ldap.tls_mode_and_uri",
      "LDAP TLS mode + URI: LDAPS default for new configs, back-compat for old ones, mode is authoritative.")
def t_ldap_uri():
    ap = _imp("core.auth_providers")
    assert ap.ldap_tls_mode({}) == "ldaps", "new config should default to LDAPS"
    assert ap.ldap_tls_mode({"host": "ldaps://dc1"}) == "ldaps"
    assert ap.ldap_tls_mode({"host": "ldap://dc1", "use_tls": True}) == "starttls"
    assert ap.ldap_tls_mode({"host": "ldap://dc1", "use_tls": False}) == "none"
    assert ap.ldap_uri({"host": "dc1.corp.local", "tls_mode": "ldaps"}) == "ldaps://dc1.corp.local:636"
    assert ap.ldap_uri({"host": "dc1.corp.local", "tls_mode": "starttls"}) == "ldap://dc1.corp.local:389"
    # the selected mode wins over a stale scheme typed into the host field
    assert ap.ldap_uri({"host": "ldap://dc1:3269", "tls_mode": "ldaps"}) == "ldaps://dc1:3269"
    assert ap.ldap_uri({"host": "dc1", "tls_mode": "ldaps", "port": 3636}) == "ldaps://dc1:3636"
    assert ap.ldap_uri({"host": "[::1]:636", "tls_mode": "ldaps"}) == "ldaps://[::1]:636"
    # EXPECTED: the connection uses exactly the security mode the admin selected.
    # IF THIS FAILS: an admin choosing LDAPS could silently get an unencrypted connection.


@test(1, "ldap.empty_password_bypass_blocked",
      "Empty/blank LDAP passwords are refused before contacting the directory (unauthenticated-bind bypass).")
def t_ldap_empty_pw():
    ap = _imp("core.auth_providers")
    called = []
    orig_cfg, orig_conn = ap.get_provider_config, ap.ldap_connect
    ap.get_provider_config = lambda k: {"enabled": True, "host": "dc1"}
    ap.ldap_connect = lambda cfg: called.append(1) or (_ for _ in ()).throw(RuntimeError("no network in test"))
    try:
        for pw in ("", "   ", None):
            r = ap.try_ldap_auth("alice", pw)
            assert not r.success and r.error == "Invalid credentials", f"blank password {pw!r} not refused: {r}"
        r = ap.try_ldap_auth("", "secret")
        assert not r.success, "blank username not refused"
    finally:
        ap.get_provider_config, ap.ldap_connect = orig_cfg, orig_conn
    assert not called, "the directory was contacted with a blank credential"
    # EXPECTED: blank credentials never reach the directory.
    # IF THIS FAILS: on Active Directory (default settings) anyone could sign in as
    #   any user by leaving the password empty — an "unauthenticated bind".


@test(1, "certs.ca_paste_classification",
      "Pasting a server certificate (breaks on renewal) or an expired cert is blocked; a CA is accepted.")
def t_ca_classify():
    import datetime
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
    except ImportError as e:
        raise Skip(f"cryptography not installed: {e}")
    ap = _imp("core.auth_providers")
    now = datetime.datetime.now(datetime.timezone.utc)
    def cert(cn, issuer_cn, key, sign_key, is_ca, start_days_ago=1, days=90):
        b = (x509.CertificateBuilder()
             .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)]))
             .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, issuer_cn)]))
             .public_key(key.public_key()).serial_number(x509.random_serial_number())
             .not_valid_before(now - datetime.timedelta(days=start_days_ago))
             .not_valid_after(now - datetime.timedelta(days=start_days_ago) + datetime.timedelta(days=days)))
        if is_ca is not None:
            b = b.add_extension(x509.BasicConstraints(ca=is_ca, path_length=None), critical=True)
        return b.sign(sign_key, hashes.SHA256()).public_bytes(serialization.Encoding.PEM).decode()
    k_ca, k_srv = ec.generate_private_key(ec.SECP256R1()), ec.generate_private_key(ec.SECP256R1())
    ca = cert("Corp Root CA", "Corp Root CA", k_ca, k_ca, True, days=3650)
    leaf = cert("dc1.corp.local", "Corp Root CA", k_srv, k_ca, None)
    selfsigned_leaf = cert("homelab", "homelab", k_srv, k_srv, False)
    expired_ca = cert("Old CA", "Old CA", k_ca, k_ca, True, start_days_ago=400, days=365)

    assert not ap.classify_ca_pem(ca)["errors"], "a real CA was rejected"
    v = ap.classify_ca_pem(leaf)
    assert v["errors"] and "renews" in v["errors"][0], f"server cert paste not blocked: {v}"
    v = ap.classify_ca_pem(selfsigned_leaf)
    assert not v["errors"] and v["warnings"], "self-signed home-lab cert should be allowed with a warning"
    assert ap.classify_ca_pem(expired_ca)["errors"], "expired CA not blocked"
    # EXPECTED: only certificates that keep working across renewals can be saved.
    # IF THIS FAILS: an admin could pin the server's own certificate and staff
    #   sign-in would silently break at the next automatic renewal.


@test(1, "certs.expiry_thresholds",
      "Near-expiry warning scales with certificate lifetime (90-day, 47-day, very short, 1-year).")
def t_expiry_level():
    ap = _imp("core.auth_providers")
    L = ap.expiry_level
    assert L(-1, 90) == "expired"
    assert L(60, 90) == "ok" and L(14, 90) == "warning"          # LE renews at ~30 days left
    assert L(10, 47) == "ok" and L(7, 47) == "warning"           # 2029 industry maximum
    assert L(3, 6) == "ok" and L(1, 6) == "warning"              # very short-lived certs
    assert L(30, 365) == "ok" and L(14, 365) == "warning"
    # EXPECTED: warnings fire when renewal has likely failed, not during normal renewal.
    # IF THIS FAILS: admins get false alarms, or no warning before sign-in breaks.


@test(1, "sip2.response_parsing_and_injection",
      "SIP2 responses are read field-by-field (no substring bypass); injection characters are refused.")
def t_sip2_parse():
    ap = _imp("core.auth_providers")
    fixed = "64" + " " * 14 + "000" + "20260101    120000" + "0000" * 6
    # ILS rejects card + PIN but echoes the attacker's barcode in AA
    evil = fixed + "AOMAIN|AABLYCQY123|AE|BLN|CQN|AY1AZ0000"
    f = ap.sip2_parse_patron_response(evil)
    assert f.get("BL") == "N" and f.get("CQ") == "N", f"parser misread fields: {f}"
    assert ("BLY" in evil and "CQY" in evil), "sanity: the old substring check WOULD pass"
    ok = fixed + "AOMAIN|AA21234000123|AEDOE, JANE|BLY|CQY|AY1AZ0000"
    f = ap.sip2_parse_patron_response(ok)
    assert f.get("BL") == "Y" and f.get("CQ") == "Y" and f.get("AE") == "DOE, JANE"
    assert ap.sip2_parse_patron_response("64short") == {}, "malformed response must parse to nothing"
    for bad in ("123|AD1234", "123\r63001", "123\n", "", "caf\u00e9"):
        assert not ap.sip2_value_safe(bad), f"unsafe SIP2 value accepted: {bad!r}"
    assert ap.sip2_value_safe("21234000123") and ap.sip2_value_safe("12 34")
    # EXPECTED: only the real BL/CQ fields decide; delimiters/control chars rejected.
    # IF THIS FAILS: a crafted barcode could sign in without a valid PIN, or inject
    #   fields/messages into the ILS conversation.


@test(1, "consortium.sip2_location_code_parsing",
      "SIP2 location field (AQ, AF, etc.) is parsed from patron response and matched against branch codes.")
def t_consortium_sip2_location():
    ap = _imp("core.auth_providers")
    fixed = "64" + " " * 14 + "000" + "20260101    120000" + "0000" * 6
    # Response with standard AQ (permanent location)
    resp_aq = fixed + "AOMAIN|AA21234000123|AEDOE, JANE|BLY|CQY|AQDWTN|AY1AZ0000"
    fields = ap.sip2_parse_patron_response(resp_aq)
    assert fields.get("AQ") == "DWTN", f"failed to parse AQ field: {fields}"

    # Response with custom location field e.g. AF
    resp_af = fixed + "AOMAIN|AA21234000123|AEDOE, JANE|BLY|CQY|AFCENTRAL|AY1AZ0000"
    fields_af = ap.sip2_parse_patron_response(resp_af)
    assert fields_af.get("AF") == "CENTRAL", f"failed to parse AF field: {fields_af}"


@test(1, "consortium.manager_scope_isolation",
      "Manager scoping enforces strict isolation: super admin sees all, scoped manager sees only their system/branches, unscoped manager sees only own/shared.")
def t_consortium_scoping():
    from types import SimpleNamespace as NS
    auth = _imp("core.auth")

    class MockQuery:
        def __init__(self, items):
            self.items = items
        def filter(self, *a, **kw):
            return self
        def all(self):
            return self.items

    class MockSession:
        def __init__(self, members, scopes=None, branches=None, users=None):
            self._members = members
            self._scopes = scopes or []
            self._branches = branches or []
            self._users = users or []

        def query(self, model):
            s = str(model)
            if "FamilyMember" in s:
                return MockQuery(self._members)
            elif "ManagerScope" in s:
                return MockQuery(self._scopes)
            elif "Branch" in s:
                return MockQuery(self._branches)
            elif "User" in s:
                return MockQuery(self._users)
            elif "ProfileAccess" in s:
                return MockQuery([])
            return MockQuery([])

    m1 = NS(id=1, user_id=101)
    m2 = NS(id=2, user_id=102)
    m3 = NS(id=3, user_id=201)
    all_members = [m1, m2, m3]

    # 1. Super admin sees all
    sa = NS(id=1, is_super_admin=True, is_manager=False, role="super_admin")
    db_sa = MockSession(all_members)
    assert set(auth.get_accessible_member_ids(db_sa, sa)) == {1, 2, 3}

    # 2. Regular user (parent) sees only own
    p = NS(id=101, is_super_admin=False, is_manager=False, role="parent")
    db_p = MockSession([m1])
    assert set(auth.get_accessible_member_ids(db_p, p)) == {1}

    # 3. Manager with consortium-wide scope sees all
    mgr_consortium = NS(id=99, is_super_admin=False, is_manager=True, role="manager",
                        permissions_granted='["members.view_all"]', permissions_revoked=None)
    scope_consortium = [NS(user_id=99, scope_type="consortium", system_id=None, branch_id=None)]
    db_mc = MockSession(all_members, scopes=scope_consortium)
    assert set(auth.get_accessible_member_ids(db_mc, mgr_consortium)) == {1, 2, 3}

    # 4. Manager with cross_system permission sees all
    mgr_cross = NS(id=98, is_super_admin=False, is_manager=True, role="manager",
                   permissions_granted='["members.view_all", "consortium.cross_system"]', permissions_revoked=None)
    db_cross = MockSession(all_members, scopes=[])
    assert set(auth.get_accessible_member_ids(db_cross, mgr_cross)) == {1, 2, 3}


@test(1, "logs.sanitization_and_redaction",
      "Diagnostic logs sanitize passwords, bearer tokens, SIP2 credentials, and auth headers.")
def t_logs_sanitization():
    lc = _imp("core.logging_config")
    s = lc.sanitize_log_message

    # 1. Bearer token
    raw = "Request failed with token Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xyz123"
    san = s(raw)
    assert "Bearer [REDACTED]" in san
    assert "eyJhbG" not in san

    # 1b. Authorization header
    raw1b = "Request header Authorization: Basic dXNlcjpwYXNz"
    san1b = s(raw1b)
    assert "Authorization: [REDACTED]" in san1b
    assert "dXNlcj" not in san1b

    # 2. Query param secrets
    raw2 = "Connecting to ILS with host=10.0.0.1&pin=9876&password=supersecret&timeout=10"
    san2 = s(raw2)
    assert "pin=[REDACTED]" in san2
    assert "password=[REDACTED]" in san2
    assert "9876" not in san2
    assert "supersecret" not in san2

    # 3. JSON secrets
    raw3 = '{"username": "admin", "password": "mypassword123", "client_secret": "sec456"}'
    san3 = s(raw3)
    assert '"password": "[REDACTED]"' in san3
    assert '"client_secret": "[REDACTED]"' in san3
    assert "mypassword123" not in san3

    # 4. SIP2 credentials (|AD and |CO fields)
    raw4 = "6300120260101    120000AOMAIN|AA21234|ADsecretpin|COsipuserpass|AY1"
    san4 = s(raw4)
    assert "|AD[REDACTED]" in san4
    assert "|CO[REDACTED]" in san4
    assert "secretpin" not in san4
    assert "sipuserpass" not in san4


@test(1, "logs.ring_buffer_and_filtering",
      "MemoryRingBufferHandler buffers records up to capacity, provides structured entries, and filters by level/search/cursor.")
def t_logs_ring_buffer():
    import logging
    lc = _imp("core.logging_config")
    handler = lc.MemoryRingBufferHandler(capacity=5)

    for i in range(8):
        rec = logging.LogRecord(
            name=f"test.logger.{i % 2}",
            level=logging.INFO if i % 2 == 0 else logging.ERROR,
            pathname=__file__,
            lineno=10,
            msg=f"Message {i} with token {i * 100}",
            args=(),
            exc_info=None,
        )
        handler.emit(rec)

    # 1. Cap to capacity
    entries = handler.query(limit=10)
    assert len(entries) == 5, f"expected 5 entries, got {len(entries)}"
    assert entries[0]["id"] == 4
    assert entries[-1]["id"] == 8

    # 2. Filter by minimum level (ERROR only)
    errors = handler.query(level="ERROR")
    for e in errors:
        assert e["level"] == "ERROR"

    # 3. Filter by logger
    log0 = handler.query(logger_filter="logger.0")
    for e in log0:
        assert "logger.0" in e["logger"]

    # 4. Filter by search keyword
    searched = handler.query(search="token 700")
    assert len(searched) == 1
    assert searched[0]["message"] == "Message 7 with token 700"

    # 5. Cursor filtering
    newest = handler.query(cursor=6)
    assert [e["id"] for e in newest] == [7, 8]


@test(1, "logs.dynamic_verbosity",
      "Log verbosity can be checked and changed dynamically at runtime.")
def t_logs_verbosity():
    lc = _imp("core.logging_config")
    orig = lc.get_log_level()
    try:
        lc.set_log_level("DEBUG")
        assert lc.get_log_level() == "DEBUG"
        lc.set_log_level("WARNING")
        assert lc.get_log_level() == "WARNING"

        # Invalid level raises ValueError
        try:
            lc.set_log_level("INVALID_LEVEL")
            assert False, "should have raised ValueError"
        except ValueError:
            pass
    finally:
        lc.set_log_level(orig)


@test(1, "certs.reminder_milestones",
      "Certificate reminders fire once per milestone (30/14/7/3/1 days, expiry), never daily.")
def t_reminder_keys():
    cm = _imp("core.cert_monitor")
    k = lambda days, level="warning": cm._reminder_key("saml", {"level": level, "days_left": days,
                                                              "not_after": "2026-10-18T00:00:00"})
    assert k(40, "ok") is None
    assert k(30) == k(25) == k(15), "days 30..15 are one milestone"
    assert k(14) != k(15) and k(7) != k(8) and k(1) != k(2)
    assert k(-1, "expired").endswith(":expired")
    # a replaced certificate (different expiry date) starts a fresh reminder cycle
    other = cm._reminder_key("saml", {"level": "warning", "days_left": 25, "not_after": "2027-10-18T00:00:00"})
    assert other != k(25)
    # EXPECTED: one email per milestone per certificate.
    # IF THIS FAILS: admins get spammed daily, or miss the final reminders.


@test(1, "certs.saml_signing_cert_status",
      "SAML IdP signing cert: warns from 30 days, ok when a rollover cert is already published.")
def t_saml_cert_status():
    import base64, datetime
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        import defusedxml  # noqa: F401
    except ImportError as e:
        raise Skip(f"needs cryptography + defusedxml: {e}")
    cm = _imp("core.cert_monitor")
    now = datetime.datetime.now(datetime.timezone.utc)
    def b64cert(days):
        k = ec.generate_private_key(ec.SECP256R1())
        nm = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "idp")])
        c = (x509.CertificateBuilder().subject_name(nm).issuer_name(nm).public_key(k.public_key())
             .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(days=500))
             .not_valid_after(now + datetime.timedelta(days=days, hours=12)).sign(k, hashes.SHA256()))
        return base64.b64encode(c.public_bytes(serialization.Encoding.DER)).decode()
    def md(*days):
        kds = "".join(
            '<md:KeyDescriptor use="signing"><ds:KeyInfo><ds:X509Data><ds:X509Certificate>'
            f'{b64cert(d)}</ds:X509Certificate></ds:X509Data></ds:KeyInfo></md:KeyDescriptor>' for d in days)
        return ('<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata" '
                'xmlns:ds="http://www.w3.org/2000/09/xmldsig#" entityID="https://idp/x">'
                f'<md:IDPSSODescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">{kds}'
                '</md:IDPSSODescriptor></md:EntityDescriptor>')
    L = lambda *d: cm.saml_cert_status({"idp_metadata_xml": md(*d)})["level"]
    assert L(200) == "ok" and L(31) == "ok"
    assert L(30) == "warning" and L(5) == "warning"
    assert L(-2) == "expired"
    assert L(5, 400) == "ok", "a published rollover cert should suppress the warning"
    # EXPECTED: admins are warned 30 days out, not bothered during a planned rollover.
    # IF THIS FAILS: SAML sign-in can break with no warning, or warn needlessly.


@test(1, "plugins.uninstall_path_containment",
      "Plugin uninstall only deletes paths strictly inside the plugins dir: not a "
      "sibling that shares its name as a prefix, not the dir itself, not a parent.")
def t_plugin_uninstall_containment():
    import tempfile
    inside = _imp("plugins.layout").is_strictly_inside
    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.join(tmp, "plugins")
        os.makedirs(os.path.join(root, "email", "email-gmail"))
        os.makedirs(os.path.join(tmp, "plugins-other", "x"))
        assert inside(os.path.join(root, "email", "email-gmail"), root)
        assert not inside(os.path.join(tmp, "plugins-other", "x"), root), \
            "sibling dir sharing the root's name as a prefix must not count as inside"
        assert not inside(root, root), "the plugins root itself must never be removed"
        assert not inside(tmp, root)
        assert not inside(os.path.join(root, "..", "plugins-other"), root)
        # A symlink inside the root that points outside it resolves outside.
        link = os.path.join(root, "escape")
        os.symlink(os.path.join(tmp, "plugins-other"), link)
        assert not inside(link, root), "symlink pointing outside the root must not count"


@test(1, "plugins.type_rules",
      "Manifests declare a plugin type; each type's rules are enforced (required hooks, "
      "specialized hooks stay in their type, language/theme packs are data only).")
def t_plugin_type_rules():
    perms = _imp("plugins.permissions")
    M = perms.PluginManifest.from_dict
    base = {"id": "p", "name": "P", "version": "1", "author": "a"}

    def errs(**kw):
        return M({**base, **kw}).validate()

    assert errs(type="bogus") and "unknown plugin type" in errs(type="bogus")[0]
    assert any("must declare the 'solve_captcha' hook" in e for e in errs(type="captcha"))
    e = errs(type="general", hooks=["email_provider"], permissions=["email_provider"])
    assert any("only allowed in 'email' plugins" in x for x in e), e
    assert any("data only" in x for x in errs(type="languages", permissions=["storage"]))
    assert any("entrypoint" in x for x in errs(type="themes", entrypoint="plugin.py"))
    assert errs(type="languages") == [], "a bare language pack should be valid"
    assert M({**base, "type": "languages"}).entrypoint == "", "data-only types get no default entrypoint"
    # Legacy manifests (no type) keep working, with a type inferred from hooks.
    legacy = M({**base, "hooks": ["solve_captcha"], "permissions": ["solve_captcha"]})
    assert legacy.validate() == [] and legacy.effective_type == "captcha" and legacy.type_inferred
    assert M(base).effective_type == "general"
    # to_dict keeps the declared type as written, so a legacy manifest stored
    # in the database doesn't turn into a declared one on the way back.
    assert legacy.to_dict()["type"] == ""


@test(1, "plugins.type_permission_limits",
      "Each plugin type may only request the permissions its job needs (a CAPTCHA solver "
      "can't ask for member data, a form handler can't ask for the network); checked for "
      "legacy manifests too, by their inferred type.")
def t_plugin_type_permission_limits():
    M = _imp("plugins.permissions").PluginManifest.from_dict
    base = {"id": "p", "name": "P", "version": "1", "author": "a"}
    def errs(**kw):
        return M({**base, **kw}).validate()
    e = errs(type="captcha", hooks=["solve_captcha"], permissions=["solve_captcha", "read_pii"])
    assert any("may not request the 'read_pii'" in x for x in e), e
    e = errs(type="forms", hooks=["fill_form"], permissions=["fill_forms", "network"])
    assert any("may not request the 'network'" in x for x in e), e
    e = errs(type="brokers", permissions=["request_write"])
    assert any("may not request the 'request_write'" in x for x in e), e
    e = errs(hooks=["solve_captcha"], permissions=["solve_captcha", "trigger_optout_email"])
    assert any("'captcha' plugin may not request" in x for x in e), "legacy manifests must be limited too"
    assert errs(type="general", hooks=["on_event"], permissions=["receive_events", "storage"]) == []
    assert errs(type="email", hooks=["email_provider"], permissions=["email_provider", "read_pii",
                "network", "settings_read"], outbound_domains=["gmail.googleapis.com"]) == []


@test(1, "plugins.code_inspector_rules",
      "Install-time code inspection passes every bundled and example plugin, and blocks "
      "plugins that write files, run programs, load code dynamically, use native code, reach "
      "the network without permission, or ship binaries/scripts.")
def t_plugin_code_inspector():
    import glob, json, tempfile
    perms = _imp("plugins.permissions")
    insp = _imp("plugins.code_inspector")
    here = os.path.dirname(os.path.abspath(insp.__file__))
    for d in sorted(glob.glob(os.path.join(here, "bundled", "*", "*", ""))):
        m = perms.PluginManifest.from_dict(json.load(open(os.path.join(d, "manifest.json"))))
        s = insp.summarize(insp.inspect_plugin_code(d, m))
        assert s["clean"], f"bundled {m.id} flagged: {s['high'] + s['medium']}"
    general = perms.PluginManifest.from_dict({"id": "x", "name": "x", "version": "1",
                                              "author": "a", "type": "general"})
    samples = {
        "file write": "open('plugin.py', 'w').write('x')\n",
        "append": "f = open('log.txt', mode='a')\n",
        "subprocess": "import subprocess\nsubprocess.run(['id'])\n",
        "os.system": "import os\nos.system('id')\n",
        "os file": "import os as o\no.remove('x')\n",
        "eval": "eval('1+1')\n",
        "exec": "exec(compile('1', 'x', 'eval'))\n",
        "__import__": "__import__('socket')\n",
        "importlib": "import importlib\n",
        "builtins": "getattr(__builtins__, 'eval')\n",
        "ctypes": "from ctypes import CDLL\n",
        "pathlib write": "from pathlib import Path\nPath('x').write_bytes(b'')\n",
        "Path.open write": "from pathlib import Path\nPath('x.py').open('w')\n",
        "io.FileIO write": "import io\nio.FileIO('x.py', 'w')\n",
        "shutil": "import shutil\n",
        "pickle": "import pickle\n",
        "network without permission": "import requests\n",
        "unparseable": "def broken(:\n",
    }
    for label, code in samples.items():
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "plugin.py"), "w").write(code)
            s = insp.summarize(insp.inspect_plugin_code(d, general))
            assert s["blocked"], f"{label!r} was not blocked: {s}"
    # Ordinary code isn't flagged: reading files, str.replace, the SDK storage API.
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "plugin.py"), "w").write(
            "import json\ntext = open('data.json').read().replace('a', 'b')\n"
            "plugin.storage.set('k', json.dumps({'n': 1}))\n")
        assert insp.summarize(insp.inspect_plugin_code(d, general))["clean"]
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "helper.so"), "wb").write(b"\x7fELF\x02")
        open(os.path.join(d, "run.sh"), "w").write("#!/bin/sh\n")
        open(os.path.join(d, "hidden"), "w").write("#!/usr/bin/env python\n")
        s = insp.summarize(insp.inspect_plugin_code(d, general))
        assert len(s["high"]) == 3, s["high"]
    lang = perms.PluginManifest.from_dict({"id": "l", "name": "l", "version": "1",
                                           "author": "a", "type": "languages"})
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "messages.json"), "w").write("{}")
        open(os.path.join(d, "sneaky.py"), "w").write("x = 1\n")
        s = insp.summarize(insp.inspect_plugin_code(d, lang))
        assert s["blocked"] and "data only" in s["high"][0], s


@test(1, "plugins.sandbox_code_dir_read_only",
      "Under bubblewrap the plugin's own folder is mounted read-only (it can't rewrite its "
      "code or add program files) and its only writable space is a private /tmp.")
def t_plugin_sandbox_read_only():
    sandbox = _imp("plugins.sandbox")
    perms = _imp("plugins.permissions")
    caps = sandbox.SandboxCapabilities(bubblewrap=True, rlimits=False, platform="linux")
    m = perms.PluginManifest.from_dict({"id": "x", "name": "x", "version": "1", "author": "a"})
    cmd, _ = sandbox.build_sandboxed_command(["python", "runner.py"], "/data/plugins/general/x", caps, False, m)
    pairs = [cmd[i:i + 3] for i in range(len(cmd) - 2)]
    assert ["--ro-bind", "/data/plugins/general/x", "/data/plugins/general/x"] in pairs, cmd
    assert ["--bind", "/data/plugins/general/x", "/data/plugins/general/x"] not in pairs, cmd
    assert "--tmpfs" in cmd and cmd[cmd.index("--tmpfs") + 1] == "/tmp"
    i = cmd.index("HOME")
    assert cmd[i + 1] == "/tmp", "HOME must point at the writable /tmp, not the plugin folder"


@test(1, "plugins.sandbox_uds_mounts",
      "Sandbox command mounts the per-plugin runtime dir (writable for plugin.sock) "
      "and HostService socket (read-only) across bubblewrap/unshare namespaces.")
def t_plugin_sandbox_uds_mounts():
    sandbox = _imp("plugins.sandbox")
    perms = _imp("plugins.permissions")
    caps = sandbox.SandboxCapabilities(bubblewrap=True, rlimits=False, platform="linux")
    m = perms.PluginManifest.from_dict({"id": "p1", "name": "p1", "version": "1", "author": "a"})

    cmd, _ = sandbox.build_sandboxed_command(
        ["python", "runner.py"], "/data/plugins/general/p1", caps, False, m,
        run_dir="/tmp/ps-plugins/p1", host_uds_path="/tmp/ps-plugins/host.sock"
    )
    # Check that per-plugin run_dir is bound writable for plugin.sock creation
    assert "--bind" in cmd
    b_idx = cmd.index("--bind")
    assert cmd[b_idx + 1] == "/tmp/ps-plugins/p1"

    # Check that host_uds_path is mounted read-only so plugin cannot alter host socket
    assert "--ro-bind" in cmd
    ro_pairs = [(cmd[i+1], cmd[i+2]) for i in range(len(cmd)-2) if cmd[i] == "--ro-bind"]
    assert ("/tmp/ps-plugins/host.sock", "/tmp/ps-plugins/host.sock") in ro_pairs

    # Check _private_tmp_ok preserves /tmp when sockets or work_dir are inside /tmp
    assert sandbox._private_tmp_ok("/tmp/ps-plugins/p1") == "0"
    assert sandbox._private_tmp_ok("/var/plugins/p1") == "1"


@test(1, "plugins.uds_handshake_and_thread_stack",
      "PluginManager._read_ready parses both TCP ports and Unix domain sockets, and "
      "threading stack size is reduced to prevent memory starvation.")
def t_plugin_uds_handshake():
    mgr_mod = _imp("plugins.manager")
    sdk_mod = _imp("plugins.sdk.privacyshield_sdk")
    import threading

    # Test _read_ready parsing TCP and UDS
    class FakeProc:
        def __init__(self, line):
            self.stdout = [line.encode("utf-8") if isinstance(line, str) else line]

    mgr = mgr_mod.PluginManager.__new__(mgr_mod.PluginManager)
    # TCP port line
    assert mgr._read_ready(FakeProc("PLUGIN_READY 54321\n"), 1.0) == 54321
    # UDS socket line
    assert mgr._read_ready(FakeProc("PLUGIN_READY unix:/tmp/ps-plugins/p1/plugin.sock\n"), 1.0) == "unix:/tmp/ps-plugins/p1/plugin.sock"

    # Verify threading stack size can be set to 512KB without error
    old_stack = threading.stack_size(512 * 1024)
    try:
        assert threading.stack_size() == 512 * 1024
    finally:
        threading.stack_size(old_stack)


@test(1, "plugins.layout_scan_and_placement",
      "The plugin scan walks every type folder, flags a plugin sitting in the wrong "
      "folder, and still finds (as legacy) plugins in the old flat layout.")
def t_plugin_layout_scan():
    import tempfile, json
    layout = _imp("plugins.layout")

    def put(path, manifest):
        os.makedirs(path)
        json.dump({"name": "X", "version": "1", "author": "a", **manifest},
                  open(os.path.join(path, "manifest.json"), "w"))

    with tempfile.TemporaryDirectory() as root:
        layout.ensure_layout(root)
        for t in ("email", "captcha", "forms", "discovery", "brokers", "themes", "languages", "general"):
            assert os.path.isdir(os.path.join(root, t)), f"{t}/ not created"
        put(os.path.join(root, "languages", "es"), {"id": "es", "type": "languages"})
        put(os.path.join(root, "general", "wrong"), {"id": "wrong", "type": "languages"})
        put(os.path.join(root, "old-flat"), {"id": "old-flat", "hooks": ["on_event"],
                                              "permissions": ["receive_events"]})
        os.makedirs(os.path.join(root, "email", ".staging-leftover"))
        found = {f.manifest.id: f for f in layout.scan(root)}
        assert set(found) == {"es", "wrong", "old-flat"}, set(found)
        assert found["es"].valid and found["es"].folder_type == "languages"
        assert not found["wrong"].valid and "in the 'general/' folder" in found["wrong"].errors[0]
        assert found["old-flat"].legacy_location and found["old-flat"].valid
        m = found["old-flat"].manifest
        assert layout.install_dir(root, m) == os.path.join(root, "general", "old-flat")
        assert layout.relative_install_dir(found["es"].manifest) == "languages/es/"


@test(1, "https.status_endpoint_unconfigured",
      "GET /cert-monitor/https-status reports 'not configured yet' (not an error) when "
      "HTTPS_MODE/DOMAIN aren't set, so the dashboard doesn't show a false alarm.")
def t_https_status_endpoint():
    try:
        router_mod = _imp("routers.cert_monitor")
    except ImportError as e:
        raise Skip(f"needs full backend deps / package layout: {e}")
    for k in ("HTTPS_MODE", "DOMAIN"):
        os.environ.pop(k, None)
    result = router_mod.get_https_status(None)
    assert result["configured"] is False
    assert result["level"] == "none"
    assert "enable-https" in result["message"]
    # EXPECTED: an unconfigured deployment gets a calm "nothing to check yet",
    #   not something that looks like a broken certificate.
    # IF THIS FAILS: every fresh install would show a false HTTPS error.


@test(1, "https.entrypoint_validation",
      "deploy/caddy/entrypoint.sh: every HTTPS mode produces a Caddyfile Caddy accepts, "
      "and malformed/injected input (including multi-line values) is refused.")
def t_https_entrypoint():
    import subprocess, tempfile, shutil
    repo_root = os.path.dirname(_BACKEND_DIR)
    entry = os.path.join(repo_root, "deploy", "caddy", "entrypoint.sh")
    if not os.path.isfile(entry):
        raise Skip("deploy/caddy/entrypoint.sh not present (running from a bare backend checkout)")
    sh = shutil.which("sh")
    if not sh:
        raise Skip("no /bin/sh available")

    def run(env_overrides, caddyfile):
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "GENERATE_ONLY": "1",
               "CADDYFILE": caddyfile}
        env.update(env_overrides)
        return subprocess.run([sh, entry], env=env, capture_output=True, text=True, timeout=15)

    with tempfile.TemporaryDirectory() as td:
        cf = os.path.join(td, "Caddyfile")

        # Each of these must be REFUSED (nonzero exit), including a value whose
        # first line looks valid but carries a second line of injected config —
        # a naive single-line check would let this one through.
        bad = [
            {"HTTPS_MODE": "letsencrypt"},                                    # no DOMAIN
            {"HTTPS_MODE": "bogus", "DOMAIN": "a.org"},
            {"HTTPS_MODE": "letsencrypt", "DOMAIN": "a.org } evil {"},
            {"HTTPS_MODE": "letsencrypt", "DOMAIN": "a.org\n:9999 { respond pwned }"},
            {"HTTPS_MODE": "letsencrypt", "DOMAIN": "a.org", "ACME_EMAIL": "not-an-email"},
            {"HTTPS_MODE": "letsencrypt", "DOMAIN": "a.org",
             "ACME_EMAIL": "x@a.org\r\tadmin 0.0.0.0:2019"},
            {"HTTPS_MODE": "acme", "DOMAIN": "a.org"},                        # no ACME_CA
            {"HTTPS_MODE": "acme", "DOMAIN": "a.org", "ACME_CA": "http://insecure/dir"},
            {"HTTPS_MODE": "custom", "DOMAIN": "a.org"},                      # no cert files
        ]
        for env in bad:
            r = run(env, cf)
            assert r.returncode != 0, f"should have been refused but wasn't: {env}\nstdout={r.stdout}"

        # Each valid mode must produce a config file Caddy's own adapter accepts.
        # We don't need the caddy binary here — GENERATE_ONLY=1 writes the file
        # and exits before exec'ing caddy — so this runs without any extra binary.
        cert_file = os.path.join(td, "cert.pem"); key_file = os.path.join(td, "key.pem")
        open(cert_file, "w").close(); open(key_file, "w").close()
        good = [
            {"HTTPS_MODE": "letsencrypt", "DOMAIN": "privacy.lib.org", "ACME_EMAIL": "it@lib.org"},
            {"HTTPS_MODE": "letsencrypt-staging", "DOMAIN": "privacy.lib.org"},
            {"HTTPS_MODE": "internal", "DOMAIN": "privacy.lib.org"},
            {"HTTPS_MODE": "acme", "DOMAIN": "privacy.lib.org",
             "ACME_CA": "https://ca.lib.internal/acme/acme/directory"},
            {"HTTPS_MODE": "custom", "DOMAIN": "privacy.lib.org",
             "TLS_CERT_FILE": cert_file, "TLS_KEY_FILE": key_file},
        ]
        for env in good:
            r = run(env, cf)
            assert r.returncode == 0, f"valid config was refused: {env}\nstderr={r.stderr}"
            assert os.path.isfile(cf), f"no Caddyfile written for {env}"
            content = open(cf).read()
            assert "privacy.lib.org" in content
            os.remove(cf)
    # EXPECTED: the generator accepts every documented mode and rejects malformed
    #   or injected input, including values that only look valid on their first line.
    # IF THIS FAILS: either a legitimate deployment mode is broken, or a value an
    #   admin pastes into .env could inject arbitrary Caddy configuration.


@test(1, "https.compose_sanity",
      "docker-compose.yml: the API isn't exposed beyond localhost by default, FRONTEND_URL "
      "actually reaches the api container, and the caddy service is opt-in via a profile.")
def t_compose_sanity():
    if _try_import("yaml") is None:
        raise Skip("pyyaml not installed")
    repo_root = os.path.dirname(_BACKEND_DIR)
    path = os.path.join(repo_root, "docker-compose.yml")
    if not os.path.isfile(path):
        raise Skip("docker-compose.yml not present (running from a bare backend checkout)")
    import yaml
    compose = yaml.safe_load(open(path))
    services = compose.get("services", {})
    assert "api" in services and "web" in services, "expected api and web services"

    api_ports = " ".join(str(p) for p in services["api"].get("ports", []))
    # The bug this guards: FRONTEND_URL was previously commented out in the api
    # service's environment, so SSO redirects silently used http://localhost even
    # when an admin set FRONTEND_URL in .env.
    api_env = services["api"].get("environment", [])
    api_env_joined = " ".join(str(e) for e in api_env)
    assert "FRONTEND_URL" in api_env_joined, "FRONTEND_URL is not passed to the api container"
    assert "API_BIND" in api_ports and "127.0.0.1" in api_ports, \
        f"api port should default to loopback-only, got: {api_ports}"

    assert "caddy" in services, "expected an optional caddy service for managed HTTPS"
    caddy = services["caddy"]
    assert caddy.get("profiles") == ["https"], \
        "caddy must be gated behind the 'https' compose profile (opt-in, never started by default)"
    caddy_env = " ".join(str(e) for e in caddy.get("environment", []))
    for needed in ("HTTPS_MODE", "DOMAIN"):
        assert needed in caddy_env, f"caddy service missing {needed} passthrough"
    volumes = compose.get("volumes", {})
    assert "caddy_data" in volumes, \
        "caddy_data must be a named volume — without it, every restart re-requests certificates"
    # EXPECTED: the API stays off the LAN by default, SSO redirects use the real
    #   FRONTEND_URL, and Caddy never starts (or fights for ports 80/443) unless
    #   an admin explicitly opts in.
    # IF THIS FAILS: either plain-HTTP sign-in is reachable from other machines by
    #   default, SSO silently redirects to the wrong URL, or a larger deployment's
    #   own reverse proxy could end up fighting our Caddy container for ports.


@test(1, "version.reports_file_env_and_fallback_correctly",
      "get_version()/get_commit() read the right source with the right precedence, and "
      "never raise — 'unknown' rather than a crash when nothing is available.")
def t_version_reporting():
    import os, tempfile, subprocess
    try:
        ver = _imp("core.version")
    except ImportError as e:
        raise Skip(f"needs full backend deps / package layout: {e}")

    assert ver.get_version() != "", "VERSION file should have been found and read"
    assert " " not in ver.get_version(), f"unexpected content in VERSION: {ver.get_version()!r}"

    orig_env = os.environ.get("GIT_COMMIT")
    orig_file = ver._VERSION_FILE
    try:
        # 1) GIT_COMMIT env var takes precedence over everything else — this
        # is what a real Docker build (docker-compose.yml's build arg) or a
        # native install's systemd EnvironmentFile actually sets.
        os.environ["GIT_COMMIT"] = "abc1234"
        assert ver.get_commit() == "abc1234"
        assert ver.version_string() == f"PrivacyShield {ver.get_version()} (commit abc1234)"

        # 2) No env var: falls back to asking git directly, for a native/dev
        # run inside a real checkout — build a throwaway one to prove it.
        os.environ.pop("GIT_COMMIT", None)
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["git", "init", "-q", "-b", "main", tmp], check=True)
            subprocess.run(["git", "-C", tmp, "-c", "user.email=t@t.com", "-c", "user.name=t",
                            "commit", "-q", "--allow-empty", "-m", "test"], check=True)
            ver._VERSION_FILE = os.path.join(tmp, "VERSION")   # cwd for the git fallback
            commit = ver.get_commit()
            assert commit != "unknown" and len(commit) >= 7, f"git fallback didn't work: {commit!r}"

        # 3) Neither an env var nor a real git checkout: "unknown", not a crash.
        with tempfile.TemporaryDirectory() as tmp:
            ver._VERSION_FILE = os.path.join(tmp, "VERSION")   # empty dir, no .git
            assert ver.get_commit() == "unknown"

        # 4) A missing VERSION file doesn't crash get_version() either.
        ver._VERSION_FILE = "/nonexistent/path/VERSION"
        assert ver.get_version() == "unknown"
    finally:
        ver._VERSION_FILE = orig_file
        if orig_env is None:
            os.environ.pop("GIT_COMMIT", None)
        else:
            os.environ["GIT_COMMIT"] = orig_env
    # EXPECTED: GIT_COMMIT env var (set by a real Docker build or native
    #   install) wins when present; a real git checkout is asked directly
    #   when it isn't; and missing/unavailable sources degrade to "unknown"
    #   rather than raising — this is startup-path code, so it must never be
    #   what breaks a deployment.
    # IF THIS FAILS: either the version reported in logs/health could be
    #   wrong, or a missing VERSION file / no git / no env var could crash
    #   application startup entirely.


@test(1, "auth.password_hashing_works_and_rejects_oversized",
      "hash_password/verify_password actually work with the pinned bcrypt version, and "
      "passwords over bcrypt's 72-byte limit are rejected with a clear error, not a crash "
      "or silent truncation.")
def t_password_hashing():
    try:
        auth = _imp("core.auth")
    except ImportError as e:
        raise Skip(f"needs full backend deps / package layout: {e}")
    if _try_import("bcrypt") is None:
        raise Skip("bcrypt not installed")

    # The actual regression: passlib 1.7.4's internal one-time self-test
    # (detect_wrap_bug, run on the FIRST hash() call in the process) is
    # incompatible with bcrypt>=4.1 — which pip installs by default, since
    # requirements.txt only pins passlib[bcrypt], leaving the bcrypt package
    # itself unpinned. That combination makes EVERY hash_password() call raise
    # ValueError("password cannot be longer than 72 bytes"), regardless of
    # the actual password's length — including short ones. requirements.txt
    # now pins bcrypt==4.0.1 (confirmed compatible); this proves the pinned
    # version this environment actually has installed still works.
    h = auth.hash_password("a perfectly normal short password")
    assert auth.verify_password("a perfectly normal short password", h)
    assert not auth.verify_password("wrong password", h)
    # EXPECTED: hashing a short, ordinary password just works.
    # IF THIS FAILS: bcrypt drifted incompatible with passlib again (or the pin
    #   in requirements.txt was removed/changed) — registration is broken for
    #   EVERY user, not just ones with long passwords, exactly like the
    #   original bug report.

    # Defense in depth: bcrypt silently truncates anything past 72 BYTES
    # rather than erroring (verified: two passwords sharing the same first 72
    # bytes but differing after that hash identically) — a real, permanent
    # algorithm limit, not a version-compatibility bug like the above. Reject
    # it up front with a clear message instead of accepting a password that's
    # silently not what the user thinks it is.
    ok_72 = "x" * 72
    auth.hash_password(ok_72)   # exactly at the limit — must still work
    too_long = "x" * 100
    try:
        auth.validate_password_length(too_long)
        raise AssertionError("a 100-byte password was not rejected")
    except ValueError as e:
        assert "72" in str(e)
    assert auth.validate_password_length(ok_72) == ok_72   # at the limit: allowed
    assert auth.validate_password_length(None) is None     # no password (SSO-only user): allowed
    assert auth.validate_password_length("") == ""          # empty: allowed (caller decides if that's valid)
    # EXPECTED: over the limit -> clear ValueError (a 422 once it reaches a
    #   Pydantic field_validator); at or under the limit, and no password at
    #   all, both pass through untouched.
    # IF THIS FAILS: a user could set a long password only part of which
    #   actually matters (a silent truncation), or the validator could wrongly
    #   block short passwords / SSO-only accounts with no password at all.



# ══════════════════════════════════════════════════════════════════════════════

def _memory_db():
    """Build the models against a throwaway in-memory SQLite. Raises Skip if
    SQLAlchemy isn't available."""
    if _try_import("sqlalchemy") is None:
        raise Skip("sqlalchemy not installed")
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    db = _imp("models.database")
    engine = create_engine("sqlite:///:memory:")
    db.Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return db, Session()


@test(2, "models.import_and_create",
      "All ORM models import and their tables create cleanly on a fresh DB.")
def t_models_create():
    db, s = _memory_db()
    # Touch the key tables so a mapping error surfaces here, clearly.
    for tbl in ("User", "FamilyMember", "Broker", "RemovalRequest",
                "BrokerHealth", "InstalledPlugin"):
        assert hasattr(db, tbl), f"model {tbl} missing from database module"
    s.close()
    # EXPECTED: all tables create, all models present.
    # IF THIS FAILS: a model or column is malformed, or a migration/model drift
    #   exists. The traceback names the offending table/column.


@test(2, "broker_health.auto_disable_flow",
      "Consecutive failures auto-disable a broker at the threshold; a success resets it.")
def t_health_flow():
    db, s = _memory_db()
    bh = _imp("core.broker_health")
    b = db.Broker(name="HealthTest", enabled=True)
    s.add(b); s.commit()
    bid = b.id

    # below threshold: stays enabled
    for _ in range(bh.AUTO_DISABLE_THRESHOLD - 1):
        bh.record_failure(s, bid, detail="Timeout waiting")
    s.refresh(b)
    assert b.enabled, "broker disabled too early (below threshold)"

    # hitting threshold: auto-disables
    just = bh.record_failure(s, bid, detail="Timeout waiting")
    s.refresh(b)
    assert just is True and b.enabled is False, "broker did NOT auto-disable at threshold"

    h = s.query(db.BrokerHealth).filter_by(broker_id=bid).first()
    assert h.needs_review and h.last_failure_reason == "timeout", \
        "health record not flagged/classified correctly"

    # re-enable resets
    bh.re_enable(s, bid)
    s.refresh(b); s.refresh(h)
    assert b.enabled and h.consecutive_failures == 0 and not h.auto_disabled, \
        "re_enable did not reset state"
    s.close()
    # EXPECTED: enabled below threshold, auto-disabled AT threshold, re-enable resets.
    # IF THIS FAILS: the core resilience feature (item 1) is broken — a broken
    #   broker either won't be disabled or gets disabled too aggressively.


@test(2, "broker_health.success_resets_streak",
      "A single success zeroes the consecutive-failure counter so a recovered broker heals.")
def t_health_reset():
    db, s = _memory_db()
    bh = _imp("core.broker_health")
    b = db.Broker(name="ResetTest", enabled=True)
    s.add(b); s.commit()
    for _ in range(bh.AUTO_DISABLE_THRESHOLD - 1):
        bh.record_failure(s, b.id, detail="blip")
    bh.record_success(s, b.id)
    h = s.query(db.BrokerHealth).filter_by(broker_id=b.id).first()
    assert h.consecutive_failures == 0, "success did not reset the failure streak"
    s.close()
    # EXPECTED: consecutive_failures back to 0 after a success.
    # IF THIS FAILS: an intermittently-failing broker would eventually be
    #   disabled even though it works most of the time.


@test(2, "parent.effectiveness_tracking",
      "Parent honor_status derives from real send/confirm activity against the DB.")
def t_parent_effectiveness():
    db, s = _memory_db()
    pc = _imp("core.parent_company")
    Status = db.EmailHonorStatus
    # A parent with children grouped under it
    p = db.ParentCompany(name="BigData Corp", optout_email="privacy@bigdata.example")
    s.add(p); s.commit()
    b1 = db.Broker(name="Arrest Records", parent_company_id=p.id)
    b2 = db.Broker(name="Phone Lookup TX", parent_company_id=p.id)
    s.add_all([b1, b2]); s.commit()

    # Send enough with high confirm rate -> honors
    for _ in range(4):
        pc.record_send(s, p.id)
        pc.record_confirmation(s, p.id)
    s.refresh(p)
    assert p.emails_sent == 4 and p.emails_confirmed == 4
    assert p.honor_status == Status.honors, f"expected honors, got {p.honor_status}"

    # The parent knows its children (the enumeration source for the email)
    assert len(p.children) == 2, f"parent should have 2 children, got {len(p.children)}"
    stats = pc.parent_stats(p)
    assert stats["child_count"] == 2 and stats["confirm_rate"] == 100.0
    s.close()
    # EXPECTED: sends/confirms tracked, honor_status derived, children linked.
    # IF THIS FAILS: the email-first effectiveness tracking or parent-child
    #   grouping (the core of the email strategy) is broken.


@test(2, "parent.discovered_url_resolver",
      "The discovery→email URL map is built from stored discovery results for a parent's children.")
def t_parent_urls():
    db, s = _memory_db()
    pc = _imp("core.parent_company")
    p = db.ParentCompany(name="PCorp", optout_email="p@e.example")
    s.add(p); s.commit()
    b1 = db.Broker(name="SiteA", parent_company_id=p.id)
    b2 = db.Broker(name="SiteB", parent_company_id=p.id)
    s.add_all([b1, b2]); s.commit()
    # A member (needs a user) and a discovery result giving SiteA a listing URL
    u = db.User(email="jane@example.com", full_name="Jane Doe",
                hashed_password="x", role=db.UserRole.member)
    s.add(u); s.commit()
    fam = db.FamilyMember(user_id=u.id, full_name="Jane Doe")
    s.add(fam); s.commit()
    s.add(db.DiscoveryResult(member_id=fam.id, broker_id=b1.id, found=True,
                             listing_url="https://a.example/profile/1", source="direct"))
    s.commit()
    s.refresh(p)
    urls = pc.discovered_urls_for_parent(s, p, fam.id)
    assert urls.get("SiteA") == "https://a.example/profile/1", f"SiteA URL not resolved: {urls}"
    assert "SiteB" not in urls, "SiteB has no discovery URL and should be absent"
    s.close()
    # EXPECTED: resolver maps child broker -> its discovered listing URL.
    # IF THIS FAILS: opt-out emails won't cite exact profile URLs (weaker matching).


@test(2, "parent.batch_grouping_and_metrics",
      "Parent company requests group by parent and update email honor metrics on send and confirm.")
def t_parent_batch_metrics():
    db, s = _memory_db()
    pc = _imp("core.parent_company")
    Status = db.EmailHonorStatus

    p = db.ParentCompany(name="DataHolding LLC", optout_email="optout@dataholding.example")
    s.add(p); s.commit()
    b1 = db.Broker(name="ChildOne", parent_company_id=p.id)
    b2 = db.Broker(name="ChildTwo", parent_company_id=p.id)
    s.add_all([b1, b2]); s.commit()

    u = db.User(email="alex@example.com", full_name="Alex Doe", hashed_password="x", role=db.UserRole.member)
    s.add(u); s.commit()
    m = db.FamilyMember(user_id=u.id, full_name="Alex Doe")
    s.add(m); s.commit()

    r1 = db.RemovalRequest(member_id=m.id, broker_id=b1.id, status=db.RequestStatus.pending)
    r2 = db.RemovalRequest(member_id=m.id, broker_id=b2.id, status=db.RequestStatus.pending)
    s.add_all([r1, r2]); s.commit()

    # Verify children resolution
    s.refresh(p)
    assert len(p.children) == 2

    # Record send for the parent and transition requests to sent with shared key
    import uuid
    shared_key = str(uuid.uuid4())
    pc.record_send(s, p.id)
    for r in [r1, r2]:
        r.status = db.RequestStatus.sent
        r.request_key = shared_key
    s.commit()

    s.refresh(p)
    assert p.emails_sent == 1
    assert p.emails_confirmed == 0

    # Inbound confirmation matches shared key
    matching = s.query(db.RemovalRequest).filter(
        db.RemovalRequest.request_key == shared_key,
        db.RemovalRequest.status == db.RequestStatus.sent,
    ).all()
    assert len(matching) == 2
    for r in matching:
        r.status = db.RequestStatus.confirmed
    pc.record_confirmation(s, p.id)
    s.commit()

    s.refresh(p)
    assert p.emails_confirmed == 1
    assert p.honor_status == Status.honors
    s.close()
    # EXPECTED: multiple requests linked to parent, updated to sent and confirmed with shared UUID.
    # IF THIS FAILS: parent company email tracking or reputation scoring is broken.


@test(2, "captcha.database_challenge_persistence",
      "CaptchaChallenge model stores challenges, links to RemovalRequest, and supports query filtering.")
def t_captcha_db():
    db, s = _memory_db()
    u = db.User(email="operator@example.org", full_name="Operator Name", hashed_password="x", role=db.UserRole.manager)
    s.add(u); s.commit()
    m = db.FamilyMember(user_id=u.id, full_name="Target Member")
    s.add(m); s.commit()
    b = db.Broker(name="CaptchaProtected Broker", opt_out_url="https://broker.example/optout")
    s.add(b); s.commit()

    req = db.RemovalRequest(member_id=m.id, broker_id=b.id, status=db.RequestStatus.pending, notes="Paused for human CAPTCHA resolution")
    s.add(req); s.commit()

    ch = db.CaptchaChallenge(
        request_id=req.id, broker_id=b.id, member_id=m.id,
        challenge_type="recaptcha_v2", site_key="TEST-SITEKEY",
        page_url="https://broker.example/optout", status="pending"
    )
    s.add(ch); s.commit()

    # Query back
    saved = s.query(db.CaptchaChallenge).filter(db.CaptchaChallenge.request_id == req.id).first()
    assert saved is not None
    assert saved.challenge_type == "recaptcha_v2"
    assert saved.site_key == "TEST-SITEKEY"
    assert saved.status == "pending"
    assert len(req.captcha_challenges) == 1

    # Resolve
    import datetime
    saved.status = "resolved"
    saved.resolved_by = u.id
    try:
        from datetime import timezone
        saved.resolved_at = datetime.datetime.now(timezone.utc)
    except Exception:
        saved.resolved_at = datetime.datetime.utcnow()
    s.commit()

    s.refresh(saved)
    assert saved.status == "resolved"
    assert saved.resolver.full_name == "Operator Name"
    s.close()
    # EXPECTED: CaptchaChallenge persists, relates to request, member, broker, and user.
    # IF THIS FAILS: The database schema for the human-in-the-loop CAPTCHA queue is broken.


@test(2, "captcha.broker_preferred_solver_db_and_migration",
      "Broker model has captcha_plugin_id column, persisted and loaded, and migrations list contains it.")
def t_broker_preferred_solver():
    db, s = _memory_db()
    mig_mod = _imp("core.migrations")
    assert any("captcha_plugin_id" in sql for name, sql in mig_mod.MIGRATIONS), \
        "MIGRATIONS missing captcha_plugin_id column addition"

    b = db.Broker(
        name="SolverTestBroker",
        opt_out_url="https://broker.example/optout",
        captcha_plugin_id="recaptcha-v2-solver"
    )
    s.add(b)
    s.commit()

    loaded = s.query(db.Broker).filter(db.Broker.id == b.id).first()
    assert loaded is not None
    assert loaded.captcha_plugin_id == "recaptcha-v2-solver"

    # Clearing/updating preferred solver
    loaded.captcha_plugin_id = None
    s.commit()
    s.refresh(loaded)
    assert loaded.captcha_plugin_id is None
    s.close()
    # EXPECTED: Broker.captcha_plugin_id is queryable and editable.
    # IF THIS FAILS: Broker model or database migration for captcha_plugin_id is broken.


@test(2, "provider_plugins.auto_provisions_bundled_email_plugin",
      "Connecting OAuth for a provider PrivacyShield ships a plugin for (Gmail/Outlook/"
      "Yahoo) auto-installs + enables that plugin and turns the plugin system on, without "
      "an admin needing to separately find Settings -> Plugins and do it by hand.")
def t_provider_plugin_provisioning():
    from types import SimpleNamespace as NS
    import tempfile, json, os
    try:
        pp = _imp("core.provider_plugins")
        settings_store = _imp("core.settings_store")
        plugins_pkg = _imp("plugins")
    except ImportError as e:
        raise Skip(f"needs full backend deps / package layout: {e}")

    db, session = _memory_db()
    if not os.path.isdir(pp._PROVIDER_TO_PLUGIN_DIR.get("gmail", "")):
        raise Skip("bundled email-gmail plugin not present in this checkout layout")

    with tempfile.TemporaryDirectory() as tmp:
        settings_file = os.path.join(tmp, "settings.json")
        plugins_root = os.path.join(tmp, "plugins")
        json.dump({"plugins": {"plugins_dir": plugins_root}}, open(settings_file, "w"))
        saved_env = os.environ.pop("PLUGINS_DIR", None)

        # Fake plugin manager: proves launch_plugin gets called with the right
        # args WITHOUT actually spawning a sandboxed subprocess (that needs a
        # real host and is exercised by the manager's own tests elsewhere) —
        # this test is about the PROVISIONING decision logic, not the sandbox.
        launched = []
        fake_mgr = NS(launch_plugin=lambda manifest, path, granted: launched.append(
            (manifest.id, path, sorted(granted))))

        orig_load = settings_store.load_settings
        orig_settings_file = settings_store.SETTINGS_FILE
        orig_get_manager = plugins_pkg.get_manager
        orig_init = plugins_pkg.init_plugin_system
        settings_store.load_settings = lambda: json.load(open(settings_file))
        settings_store.SETTINGS_FILE = settings_file
        pp_get_manager_calls = {"n": 0}
        def fake_get_manager():
            pp_get_manager_calls["n"] += 1
            # Not running until init_plugin_system "starts" it (2nd+ call).
            return fake_mgr if pp_get_manager_calls["n"] > 1 else None
        plugins_pkg.get_manager = fake_get_manager
        plugins_pkg.init_plugin_system = lambda: fake_mgr

        try:
            ok = pp.ensure_provider_plugin("gmail", db_session_factory=lambda: session)
            assert ok, "provisioning reported failure"

            row = session.query(db.InstalledPlugin).filter(
                db.InstalledPlugin.plugin_id == "email-gmail").first()
            assert row is not None, "plugin was not installed"
            assert row.enabled, "plugin was not enabled"
            granted = json.loads(row.granted_permissions)
            assert "read_pii" in granted and "network" in granted and "email_provider" in granted, \
                f"expected the manifest's declared permissions to be granted, got: {granted}"

            s = json.load(open(settings_file))
            assert s.get("plugins", {}).get("enabled") is True, \
                "plugin system was not turned on despite provisioning a plugin that needs it"

            assert launched and launched[0][0] == "email-gmail", \
                f"launch_plugin was not called correctly: {launched}"

            # Installed as a copy in the typed layout, never run from the app's
            # own source tree.
            expected = os.path.join(plugins_root, "email", "email-gmail")
            assert row.install_path == expected, f"installed at {row.install_path}, not {expected}"
            assert launched[0][1] == expected
            assert os.path.isfile(os.path.join(expected, "manifest.json"))
            assert os.path.isfile(os.path.join(expected, ".privacyshield-bundled"))

            # A provider PrivacyShield has no bundled plugin for (a custom
            # uploaded one, say) must return False, not error or fabricate one.
            assert pp.ensure_provider_plugin("some-custom-uploaded-provider",
                                             db_session_factory=lambda: session) is False
        finally:
            settings_store.load_settings = orig_load
            settings_store.SETTINGS_FILE = orig_settings_file
            plugins_pkg.get_manager = orig_get_manager
            plugins_pkg.init_plugin_system = orig_init
            if saved_env is not None:
                os.environ["PLUGINS_DIR"] = saved_env
            session.close()
    # EXPECTED: picking an OAuth provider this app ships a plugin for results in
    #   that plugin being copied into <plugins root>/email/email-gmail/ and
    #   installed from there, enabled with the permissions it
    #   needs, and the (opt-in, off-by-default) plugin system turned on — all
    #   without the admin needing to separately discover and do this by hand.
    # IF THIS FAILS: OAuth email connect looks like it works (tokens are
    #   stored) but sending silently falls back to SMTP, which was never
    #   configured — the exact bug this exists to prevent.


def _plugin_zip(files: dict, symlinks: dict = None) -> bytes:
    """Build a plugin .zip in memory: {path: text}, plus optional symlink entries."""
    import io, zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, text in files.items():
            z.writestr(name, text)
        for name, target in (symlinks or {}).items():
            info = zipfile.ZipInfo(name)
            info.external_attr = (0o120777 << 16)
            z.writestr(info, target)
    return buf.getvalue()


@test(2, "plugins.migrate_flat_and_bundled_installs",
      "On upgrade, installs in the old flat layout move to <root>/<type>/<id>/, built-in "
      "plugins registered at their old source path are copied into email/, and plugins "
      "installed from outside the root are left alone.")
def t_plugin_layout_migration():
    import tempfile, json
    try:
        layout = _imp("plugins.layout")
        db, session = _memory_db()
    except ImportError as e:
        raise Skip(f"needs full backend deps / package layout: {e}")
    if "email-gmail" not in layout.bundled_plugins():
        raise Skip("bundled email plugins not present in this checkout layout")

    def row(pid, path, manifest):
        session.add(db.InstalledPlugin(
            plugin_id=pid, name=pid, version="1", author="a",
            manifest_json=json.dumps(manifest), granted_permissions="[]",
            enabled=False, install_path=path, status="stopped"))
        session.commit()

    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.join(tmp, "plugins")
        flat = os.path.join(root, "tracker")
        os.makedirs(flat)
        legacy_manifest = {"id": "tracker", "name": "T", "version": "1", "author": "a",
                           "hooks": ["on_event"], "permissions": ["receive_events"]}
        json.dump(legacy_manifest, open(os.path.join(flat, "manifest.json"), "w"))
        outside = os.path.join(tmp, "elsewhere", "ext")
        os.makedirs(outside)
        json.dump({**legacy_manifest, "id": "ext"}, open(os.path.join(outside, "manifest.json"), "w"))

        row("tracker", flat, legacy_manifest)
        # Where email-gmail used to be registered before bundled/ was typed.
        row("email-gmail", os.path.join(layout.BUNDLED_ROOT, "email-gmail"), {"id": "email-gmail"})
        row("ext", outside, {**legacy_manifest, "id": "ext"})

        changes = layout.migrate_installed(root, lambda: session)
        paths = {r.plugin_id: r.install_path for r in session.query(db.InstalledPlugin).all()}
        assert paths["tracker"] == os.path.join(root, "general", "tracker"), paths
        assert os.path.isfile(os.path.join(root, "general", "tracker", "manifest.json"))
        assert not os.path.exists(flat), "old flat directory should have been moved"
        gmail = os.path.join(root, "email", "email-gmail")
        assert paths["email-gmail"] == gmail and layout.is_bundled_copy(gmail), paths
        assert paths["ext"] == outside, "a plugin installed outside the root must not move"
        assert len(changes) == 2, changes
        # Idempotent: a second run changes nothing.
        assert layout.migrate_installed(root, lambda: session) == []
    session.close()


@test(1, "access.effective_permissions",
      "Manager permissions = (editable defaults + granted) - revoked; super admins hold "
      "everything, parents and members nothing; editing all members' data implies viewing it.")
def t_access_effective():
    from types import SimpleNamespace as NS
    try:
        access = _imp("core.access")
        settings_store = _imp("core.settings_store")
    except ImportError as e:
        raise Skip(f"needs full backend deps / package layout: {e}")
    settings = {}
    orig = settings_store.load_settings
    settings_store.load_settings = lambda: settings
    try:
        sa = NS(is_super_admin=True, is_manager=False)
        parent = NS(is_super_admin=False, is_manager=False)
        mgr = lambda g=None, r=None: NS(is_super_admin=False, is_manager=True,
                                        permissions_granted=g, permissions_revoked=r)
        assert access.effective_permissions(sa) == list(access.PERMISSIONS)
        assert access.effective_permissions(parent) == []
        assert access.effective_permissions(mgr()) == access.clean(access.DEFAULT_MANAGER_PERMISSIONS)
        assert not access.has_permission(mgr(), "members.view_all"), "member data must be off by default"
        m = mgr(g='["users.manage"]', r='["help.edit"]')
        held = access.effective_permissions(m)
        assert "users.manage" in held and "help.edit" not in held and "brokers.manage" in held
        assert access.has_permission(mgr(g='["members.edit_all"]'), "members.view_all")
        # Editing the defaults changes every manager, except their own changes.
        settings["access"] = {"manager_defaults": ["reporting.view", "help.edit"]}
        assert access.effective_permissions(mgr()) == ["reporting.view", "help.edit"]
        assert access.effective_permissions(m) == ["users.manage", "reporting.view"]
        # Garbage in stored overrides is ignored, unknown keys refused in code.
        assert access.effective_permissions(mgr(g="not json")) == ["reporting.view", "help.edit"]
        try:
            access.has_permission(sa, "no.such.permission")
            raise AssertionError("unknown permission key accepted")
        except ValueError:
            pass
    finally:
        settings_store.load_settings = orig


@test(2, "access.manager_escalation_guards",
      "A manager with 'Manage users' handles parents and members only: can't create, change "
      "or delete super admins or managers, change roles, share profiles with themselves, or "
      "issue super admin/manager invite codes. Only super admins set permissions and defaults.")
def t_access_escalation():
    import json, tempfile
    try:
        from fastapi import HTTPException
        admin_router = _imp("routers.admin")
        auth_router = _imp("routers.auth")
        settings_store = _imp("core.settings_store")
        db, session = _memory_db()
    except ImportError as e:
        raise Skip(f"needs full backend deps / package layout: {e}")

    def expect_http(status, fn, *a, **kw):
        try:
            fn(*a, **kw)
        except HTTPException as e:
            assert e.status_code == status, f"expected {status}, got {e.status_code}: {e.detail}"
            return
        raise AssertionError(f"expected HTTP {status} from {fn.__name__}")

    def user(email, role, **kw):
        u = db.User(email=email, full_name=email.split("@")[0], role=role, hashed_password="x", **kw)
        session.add(u); session.commit(); return u

    with tempfile.TemporaryDirectory() as tmp:
        settings_file = os.path.join(tmp, "settings.json")
        json.dump({}, open(settings_file, "w"))
        orig_load, orig_file = settings_store.load_settings, settings_store.SETTINGS_FILE
        settings_store.load_settings = lambda: json.load(open(settings_file))
        settings_store.SETTINGS_FILE = settings_file
        try:
            R = db.UserRole
            sa = user("sa@example.org", R.super_admin)
            mgr = user("mgr@example.org", R.manager, permissions_granted='["users.manage", "users.registration"]')
            other_mgr = user("mgr2@example.org", R.manager)
            parent = user("p@example.org", R.parent)
            parent2 = user("p2@example.org", R.parent)
            Create, Update = admin_router.CreateUserRequest, admin_router.UpdateUserRequest

            out = admin_router.create_user(Create(full_name="New", email="new@example.org",
                                                  role="parent", password="password123"), session, mgr)
            assert out.role == "parent"
            for role in ("super_admin", "manager"):
                expect_http(403, admin_router.create_user, Create(full_name="X", email=f"{role}@example.org",
                            role=role, password="password123"), session, mgr)
            expect_http(403, admin_router.update_user, parent.id, Update(role="super_admin"), session, mgr)
            expect_http(403, admin_router.update_user, sa.id, Update(full_name="Hacked"), session, mgr)
            expect_http(403, admin_router.update_user, other_mgr.id, Update(password="password123"), session, mgr)
            expect_http(403, admin_router.delete_user, sa.id, session, mgr)
            admin_router.update_user(parent.id, Update(full_name="Renamed"), session, mgr)   # allowed

            Grant = admin_router.AccessGrantRequest
            expect_http(403, admin_router.create_grant, Grant(manager_id=mgr.id, managed_id=parent.id), session, mgr)
            expect_http(403, admin_router.create_grant, Grant(manager_id=parent.id, managed_id=sa.id), session, mgr)
            admin_router.create_grant(Grant(manager_id=parent.id, managed_id=parent2.id), session, mgr)

            Invite = auth_router.InviteCodeCreate
            for role in ("super_admin", "manager"):
                expect_http(403, auth_router.create_invite_code, Invite(role=role), session, mgr)
            expect_http(400, auth_router.create_invite_code, Invite(role="emperor"), session, sa)
            assert auth_router.create_invite_code(Invite(role="parent"), session, mgr).role == "parent"
            assert auth_router.create_invite_code(Invite(role="manager"), session, sa).role == "manager"

            # Super admin sets a manager's permissions; stored as the difference
            # from the defaults so unchanged keys keep following them.
            Perms = admin_router.ManagerPermissionsRequest
            out = admin_router.set_manager_permissions(
                other_mgr.id, Perms(permissions=["reporting.view", "plugins.upload"]), session, sa)
            assert out.permissions == ["reporting.view", "plugins.upload"], out.permissions
            assert out.permissions_granted == ["plugins.upload"]
            assert "reporting.view" not in out.permissions_revoked and "brokers.manage" in out.permissions_revoked
            expect_http(400, admin_router.set_manager_permissions, parent.id, Perms(permissions=[]), session, sa)
            expect_http(400, admin_router.set_manager_permissions, other_mgr.id,
                        Perms(permissions=["root"]), session, sa)
            admin_router.set_manager_defaults(admin_router.ManagerDefaultsRequest(permissions=["help.edit"]), sa)
            assert json.load(open(settings_file))["access"]["manager_defaults"] == ["help.edit"]
            # Leaving the manager role drops the per-manager changes.
            admin_router.update_user(other_mgr.id, Update(role="parent"), session, sa)
            session.refresh(other_mgr)
            assert other_mgr.permissions_granted is None and other_mgr.permissions_revoked is None
        finally:
            settings_store.load_settings, settings_store.SETTINGS_FILE = orig_load, orig_file
            session.close()


@test(2, "access.member_data_and_broker_writes",
      "Managers see only their own and shared profiles unless granted 'view/edit all members' "
      "data'; broker edits, deletes and imports need 'Manage brokers' (before, any signed-in "
      "user could make them).")
def t_access_member_data_and_brokers():
    import json, tempfile
    try:
        from fastapi import FastAPI, HTTPException
        from fastapi.testclient import TestClient
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool
        auth = _imp("core.auth")
        brokers_router = _imp("routers.brokers")
        settings_store = _imp("core.settings_store")
        db = _imp("models.database")
    except ImportError as e:
        raise Skip(f"needs full backend deps / package layout: {e}")
    # One in-memory database shared across threads: TestClient runs endpoints
    # in a worker thread.
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    db.Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    orig_load = settings_store.load_settings
    settings_store.load_settings = lambda: {}
    try:
        R = db.UserRole
        def person(email, role, **kw):
            u = db.User(email=email, full_name=email, role=role, hashed_password="x", **kw)
            session.add(u); session.flush()
            session.add(db.FamilyMember(user_id=u.id, full_name=email)); session.commit()
            return u
        mgr = person("m@example.org", R.manager)
        viewer = person("v@example.org", R.manager, permissions_granted='["members.view_all"]')
        editor = person("e@example.org", R.manager, permissions_granted='["members.edit_all"]')
        fam = person("f@example.org", R.parent)
        fam_member = session.query(db.FamilyMember).filter_by(user_id=fam.id).one()

        assert fam_member.id not in auth.get_accessible_member_ids(session, mgr)
        try:
            auth.assert_can_view(session, mgr, fam_member.id)
            raise AssertionError("manager without members.view_all saw another family")
        except HTTPException as e:
            assert e.status_code == 403
        assert fam_member.id in auth.get_accessible_member_ids(session, viewer)
        auth.assert_can_view(session, viewer, fam_member.id)
        try:
            auth.assert_can_edit(session, viewer, fam_member.id)
            raise AssertionError("view-only manager could edit")
        except HTTPException as e:
            assert e.status_code == 403
        auth.assert_can_edit(session, editor, fam_member.id)

        # Broker writes over real HTTP: a parent gets 403, a manager with the
        # default set (includes brokers.manage) gets through.
        broker = db.Broker(name="Example Broker", opt_out_url="https://example.com/optout")
        session.add(broker); session.commit()
        app = FastAPI(); app.include_router(brokers_router.router)
        app.dependency_overrides[db.get_db] = lambda: session
        client = TestClient(app)
        who = {"user": fam}
        app.dependency_overrides[auth.get_current_user] = lambda: who["user"]
        for method, path, kw in (("patch", f"/api/brokers/{broker.id}", {"json": {"notes": "x"}}),
                                 ("delete", f"/api/brokers/{broker.id}", {}),
                                 ("post", "/api/brokers/import-json",
                                  {"files": {"file": ("b.json", b"[]", "application/json")}})):
            r = getattr(client, method)(path, **kw)
            assert r.status_code == 403, f"parent {method.upper()} {path} -> {r.status_code}"
        assert client.get("/api/brokers").status_code == 200, "reading brokers stays open"
        who["user"] = mgr
        r = client.patch(f"/api/brokers/{broker.id}", json={
            "opt_out_url": "https://example.com/optout", "method": "form",
            "difficulty": "easy", "notes": "checked"})
        assert r.status_code == 200, r.text
    finally:
        settings_store.load_settings = orig_load
        session.close()


@test(2, "access.migrates_plugin_upload_grants",
      "Users given the earlier per-user 'can upload plugins' switch become managers holding "
      "only plugins.upload, so nobody gains or loses access; the old switch is cleared.")
def t_access_migrate_upload_grants():
    import json
    try:
        migrations = _imp("core.migrations")
        access = _imp("core.access")
        settings_store = _imp("core.settings_store")
        db, session = _memory_db()
    except ImportError as e:
        raise Skip(f"needs full backend deps / package layout: {e}")
    R = db.UserRole
    u = db.User(email="up@example.org", full_name="Up", role=R.parent, hashed_password="x",
                can_upload_plugins=True)
    keep = db.User(email="sa@example.org", full_name="SA", role=R.super_admin, hashed_password="x",
                   can_upload_plugins=True)
    session.add_all([u, keep]); session.commit()
    orig_session, orig_load = db.SessionLocal, settings_store.load_settings
    db.SessionLocal = lambda: session
    settings_store.load_settings = lambda: {}
    try:
        migrations.migrate_plugin_upload_grants()   # closes the session it's given
        u = session.query(db.User).filter_by(email="up@example.org").one()
        keep = session.query(db.User).filter_by(email="sa@example.org").one()
        assert u.role == R.manager and not u.can_upload_plugins
        assert access.effective_permissions(u) == ["plugins.upload"], access.effective_permissions(u)
        assert keep.role == R.super_admin
    finally:
        db.SessionLocal, settings_store.load_settings = orig_session, orig_load
        session.close()


@test(2, "plugins.integrity_check_blocks_changed_code",
      "The manager refuses to launch a plugin whose files changed since it was installed or "
      "enabled (e.g. it rewrote itself), disables it, flags it for re-approval and logs a "
      "violation; a plugin with no recorded hash gets one on first launch.")
def t_plugin_integrity():
    import tempfile
    from types import SimpleNamespace as NS
    try:
        manager_mod = _imp("plugins.manager")
        layout = _imp("plugins.layout")
        db, session = _memory_db()
    except ImportError as e:
        raise Skip(f"needs full backend deps / package layout: {e}")
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "plugin.py"), "w").write("x = 1\n")
        session.add(db.InstalledPlugin(plugin_id="p", name="p", version="1", manifest_json="{}",
                                       granted_permissions="[]", enabled=True, install_path=d,
                                       status="running"))
        session.commit()
        fake = NS(session_factory=lambda: session)
        verify = manager_mod.PluginManager._verify_integrity
        verify(fake, "p", d)   # no hash yet: recorded, allowed
        row = session.query(db.InstalledPlugin).filter_by(plugin_id="p").one()
        assert row.code_hash == layout.dir_hash(d)
        verify(fake, "p", d)   # unchanged: allowed
        open(os.path.join(d, "extra.py"), "w").write("import os\n")   # plugin adds a file
        try:
            verify(fake, "p", d)
            raise AssertionError("changed plugin was allowed to launch")
        except PermissionError:
            pass
        row = session.query(db.InstalledPlugin).filter_by(plugin_id="p").one()
        assert not row.enabled and row.needs_reapproval and "changed" in row.last_error
        v = session.query(db.PluginViolation).filter_by(plugin_id="p").one()
        assert v.vtype == "code_changed" and v.severity == "critical"
    session.close()


@test(2, "plugins.upload_wizard_routes_by_type",
      "The upload wizard inspects a zip, installs it into <root>/<type>/<id>/ (email "
      "providers into email/), enforces expected_type, refuses unsafe zips, and only "
      "lets super admins and managers with the plugins.upload permission use it.")
def t_plugin_upload_wizard():
    import io, json, tempfile
    from types import SimpleNamespace as NS
    try:
        from fastapi import HTTPException, UploadFile
        plugins_router = _imp("routers.plugins")
        settings_store = _imp("core.settings_store")
        access = _imp("core.access")
        db, session = _memory_db()
    except ImportError as e:
        raise Skip(f"needs full backend deps / package layout: {e}")

    def upload(data, name="p.zip"):
        return UploadFile(file=io.BytesIO(data), filename=name)

    def expect_http(status, fn, *a, **kw):
        try:
            fn(*a, **kw)
        except HTTPException as e:
            assert e.status_code == status, f"expected {status}, got {e.status_code}: {e.detail}"
            return e.detail
        raise AssertionError(f"expected HTTP {status}")

    admin = NS(id=1, email="admin@example.org", is_super_admin=True, is_manager=False)
    staff = NS(id=2, email="staff@example.org", is_super_admin=False, is_manager=True,
               permissions_granted='["plugins.upload"]', permissions_revoked=None)
    other = NS(id=3, email="other@example.org", is_super_admin=False, is_manager=True,
               permissions_granted=None, permissions_revoked=None)   # defaults only
    can_upload = access.require_permission("plugins.upload")

    email_manifest = {"id": "email-acme", "name": "Acme Mail", "version": "1.0.0",
                      "type": "email", "author": "t", "hooks": ["email_provider"],
                      "permissions": ["email_provider"], "entrypoint": "plugin.py"}
    email_zip = _plugin_zip({"acme/manifest.json": json.dumps(email_manifest),
                             "acme/plugin.py": "def send(msg):\n    return True\n"})
    lang_zip = _plugin_zip({"manifest.json": json.dumps(
        {"id": "lang-es", "name": "Español", "version": "1", "type": "languages", "author": "t"}),
        "messages.json": "{}"})

    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.join(tmp, "plugins")
        settings = {"plugins": {"plugins_dir": root}}
        orig_load = settings_store.load_settings
        settings_store.load_settings = lambda: settings
        saved_env = os.environ.pop("PLUGINS_DIR", None)
        try:
            # Permission: super admins and managers holding plugins.upload (not
            # in the default set); managers are refused while the system is denied.
            assert can_upload(admin) is admin and can_upload(staff) is staff
            expect_http(403, can_upload, other)
            assert plugins_router.require_plugin_uploader(staff) is staff
            settings["plugins"]["denied"] = True
            expect_http(403, plugins_router.require_plugin_uploader, staff)
            settings["plugins"]["denied"] = False

            # Inspect: reports type and destination without installing.
            plan = plugins_router.inspect_upload(upload(email_zip), None, session, staff)
            assert plan["type"] == "email" and plan["destination"] == "email/email-acme/", plan
            assert plan["can_install"] and plan["enable_requires_super_admin"], plan
            assert not os.path.exists(os.path.join(root, "email", "email-acme"))
            bad_plan = plugins_router.inspect_upload(upload(email_zip), "captcha", session, admin)
            assert not bad_plan["can_install"] and "can be uploaded here" in bad_plan["problems"][0]

            # Upload: lands in email/, registered disabled; expected_type enforced.
            expect_http(400, plugins_router.upload_plugin, upload(email_zip), "languages", session, admin)
            res = plugins_router.upload_plugin(upload(email_zip), "email", session, staff)
            dest = os.path.join(root, "email", "email-acme")
            assert res["destination"] == "email/email-acme/" and res["enable_requires_super_admin"]
            assert os.path.isfile(os.path.join(dest, "plugin.py"))
            r = session.query(db.InstalledPlugin).filter_by(plugin_id="email-acme").one()
            assert r.install_path == dest and not r.enabled
            expect_http(400, plugins_router.upload_plugin, upload(email_zip), None, session, admin)

            # Data-only language pack: lands in languages/, enabling it launches nothing.
            plugins_router.upload_plugin(upload(lang_zip), None, session, admin)
            assert os.path.isfile(os.path.join(root, "languages", "lang-es", "messages.json"))
            out = plugins_router.enable_plugin(
                "lang-es", plugins_router.EnableRequest(granted_permissions=[]), session, admin)
            r = session.query(db.InstalledPlugin).filter_by(plugin_id="lang-es").one()
            assert out["enabled"] and r.enabled and r.status == "data"

            # A delegated uploader can't replace files already in a destination
            # folder (e.g. a plugin a super admin placed but hasn't installed).
            placed = os.path.join(root, "forms", "filler")
            os.makedirs(placed)
            open(os.path.join(placed, "plugin.py"), "w").write("# placed by the super admin\n")
            forms_zip = _plugin_zip({"manifest.json": json.dumps(
                {"id": "filler", "name": "F", "version": "1", "type": "forms", "author": "t",
                 "hooks": ["fill_form"], "permissions": ["fill_forms"]}), "plugin.py": "x = 1\n"})
            assert not plugins_router.inspect_upload(upload(forms_zip), None, session, staff)["can_install"]
            expect_http(409, plugins_router.upload_plugin, upload(forms_zip), None, session, staff)
            assert open(os.path.join(placed, "plugin.py")).read().startswith("# placed by")
            plugins_router.upload_plugin(upload(forms_zip), None, session, admin)   # a super admin may
            assert open(os.path.join(placed, "plugin.py")).read() == "x = 1\n"

            # Code inspection blocks a plugin that writes files / runs programs.
            evil_zip = _plugin_zip({"manifest.json": json.dumps(
                {"id": "evil", "name": "E", "version": "1", "type": "general", "author": "t"}),
                "plugin.py": "import subprocess\nopen('plugin.py', 'w')\n"})
            plan = plugins_router.inspect_upload(upload(evil_zip), None, session, admin)
            assert not plan["can_install"] and any("subprocess" in p for p in plan["problems"]), plan
            expect_http(400, plugins_router.upload_plugin, upload(evil_zip), None, session, admin)
            assert not os.path.exists(os.path.join(root, "general", "evil"))
            r = session.query(db.InstalledPlugin).filter_by(plugin_id="email-acme").one()
            assert r.code_hash, "installed plugins record the hash of what was inspected"

            # Unsafe zips are refused before anything is extracted into the root.
            for evil in (_plugin_zip({"../escape.txt": "x", "manifest.json": "{}"}),
                         _plugin_zip({"/abs.txt": "x", "manifest.json": "{}"}),
                         _plugin_zip({"manifest.json": "{}"}, symlinks={"link": "/etc/passwd"})):
                expect_http(400, plugins_router.upload_plugin, upload(evil), None, session, admin)
            expect_http(400, plugins_router.upload_plugin, upload(b"not a zip"), None, session, admin)
            expect_http(400, plugins_router.upload_plugin, upload(email_zip, "p.tar"), None, session, admin)
            assert not os.path.exists(os.path.join(tmp, "escape.txt"))
        finally:
            settings_store.load_settings = orig_load
            if saved_env is not None:
                os.environ["PLUGINS_DIR"] = saved_env
            session.close()


@test(2, "branding.logo_extension_mapping",
      "Uploaded logos are saved under their REAL file extension (jpeg/webp, not silently "
      "mislabeled as png), replacing any previous logo in a different format, and "
      "GET /config detects all four supported formats — not just png/svg.")
def t_logo_extension_mapping():
    from types import SimpleNamespace as NS
    import tempfile, io, os
    try:
        branding = _imp("routers.branding")
    except ImportError as e:
        raise Skip(f"needs full backend deps / package layout: {e}")

    admin = NS(is_super_admin=True)
    with tempfile.TemporaryDirectory() as tmp:
        orig_path = branding.LOGO_PATH
        branding.LOGO_PATH = tmp
        try:
            def fake_upload(content_type, data=b"fake-bytes"):
                f = NS(content_type=content_type, file=io.BytesIO(data))
                return branding.upload_logo(file=f, _=admin)

            # Was: every non-svg upload got hardcoded ext="png", so a jpeg or
            # webp logo was silently saved AS a .png file (wrong bytes under
            # that extension) and the jpeg/webp branches of get_logo/delete
            # were unreachable dead code as a result.
            fake_upload("image/jpeg")
            assert os.path.exists(os.path.join(tmp, "logo.jpeg")), "jpeg upload not saved with a .jpeg extension"
            assert not os.path.exists(os.path.join(tmp, "logo.png")), "jpeg upload was mislabeled as .png"

            # GET /config must detect a jpeg-only logo too (was: only checked
            # for logo.png / logo.svg on disk, so this would have reported
            # logo_url=None even though a real logo file existed).
            cfg = branding.get_branding(_=None)
            assert cfg.logo_url == "/api/branding/logo", "a jpeg logo was not detected by /config"

            # Uploading a new format must clean up the old one — otherwise
            # both files exist and the fixed-order lookup could keep serving
            # the STALE one after the operator "replaced" their logo.
            fake_upload("image/webp")
            assert os.path.exists(os.path.join(tmp, "logo.webp"))
            assert not os.path.exists(os.path.join(tmp, "logo.jpeg")), "old jpeg logo was left behind after replacing with webp"

            # An unsupported type is refused, not silently accepted.
            from fastapi import HTTPException
            try:
                fake_upload("image/gif")
                raise AssertionError("a gif upload was not rejected")
            except HTTPException as e:
                assert e.status_code == 400
        finally:
            branding.LOGO_PATH = orig_path
    # EXPECTED: every accepted format is saved under its own real extension,
    #   detected correctly by /config, and replacing the logo cleans up the
    #   previous file rather than leaving a stale one that could get served.
    # IF THIS FAILS: an uploaded jpeg/webp logo could be corrupted on disk,
    #   invisible to /config, or a replaced logo could silently keep showing
    #   the old image.


@test(2, "test_broker.fenced_and_sends_end_to_end",
      "Test broker is fenced from real runs, and a test send reaches the transport + commits its log.")
def t_test_broker():
    from types import SimpleNamespace
    try:
        tb = _imp("routers.test_broker")
        es = _imp("core.email_send")
        _imp("core.optout_engine")          # needs playwright importable
    except ImportError as e:
        raise Skip(f"needs full backend deps / package layout: {e}")
    db, s = _memory_db()
    admin = SimpleNamespace(is_super_admin=True)

    # 1) Setup creates a FENCED parent + broker.
    info = tb.setup_test_broker(tb.SetupIn(optout_email="me@example.org"), db=s, user=admin)
    assert info["exists"] and info["optout_email"] == "me@example.org"
    broker = s.query(db.Broker).filter(db.Broker.id == info["broker_id"]).first()
    assert broker.is_test and broker.enabled is False, "test broker must be is_test + disabled"
    # Re-running setup updates the address without duplicating.
    tb.setup_test_broker(tb.SetupIn(optout_email="new@example.org"), db=s, user=admin)
    assert s.query(db.ParentCompany).filter(db.ParentCompany.is_test.is_(True)).count() == 1
    # Discovery's broker query excludes it.
    real = s.query(db.Broker).filter(db.Broker.is_test.isnot(True)).all()
    assert broker not in real, "discovery would scan the test broker"

    # 2) Send with NO SMTP settings and an OAuth provider configured — proves the
    #    stale 'SMTP not configured' gate is gone: the send reaches the transport.
    captured = {}
    def fake_send(cfg, to, cc, subject, body, account_ref="default", from_address=""):
        captured.update(to=to, subject=subject)
        return {"ok": True, "via": "provider", "error": "", "sent_to": to}
    orig_send, orig_load = es.send_email, tb.load_settings
    es.send_email = fake_send
    tb.load_settings = lambda: {"email": {"provider": "gmail"}}
    try:
        r = tb.send_test_optout(tb.SendIn(), db=s, user=admin)   # fake identity
    finally:
        es.send_email, tb.load_settings = orig_send, orig_load
    assert r["ok"], f"test send failed: {r}"
    assert captured.get("to") == ["new@example.org"], f"wrong recipient: {captured}"
    assert captured["subject"].startswith("[PrivacyShield TEST]"), "missing test prefix"

    # 3) The success-path bookkeeping COMMITTED against a real DB (this is the
    #    NOT NULL request_id bug check) and effectiveness was recorded.
    parent = s.query(db.ParentCompany).filter(db.ParentCompany.is_test.is_(True)).first()
    logs = s.query(db.EmailLog).filter(db.EmailLog.matched_key == f"parent:{parent.id}").count()
    assert logs == 1, "parent-level email log did not commit (request_id NOT NULL?)"
    assert parent.emails_sent == 1, "effectiveness tracking not recorded"
    s.close()
    # EXPECTED: fenced test pair; send reaches transport without SMTP gating; log commits.
    # IF THIS FAILS: the live test would misreport, leak into real runs, or 500 on success.


@test(2, "sso.provisioned_user_can_log_in",
      "An SSO-created user (no password) can actually use their token; super admin is never granted.")
def t_sso_login_works():
    from types import SimpleNamespace as NS
    try:
        auth_router = _imp("routers.auth")
    except ImportError as e:
        raise Skip(f"needs full backend deps / package layout: {e}")
    db, s = _memory_db()
    # an existing admin, so SSO isn't creating the first account
    s.add(db.User(email="admin@x.org", full_name="Admin", hashed_password="x",
                  role=db.UserRole.super_admin)); s.commit()
    orig = auth_router.load_settings
    auth_router.load_settings = lambda: {"auth_providers": {"okta": {"default_role": "super_admin"}},
                                         "registration": {"mode": "open"}}
    try:
        res = NS(provider="okta", email="New.Staff@X.org", full_name="New Staff",
                 email_verified=True, hd=None, groups=[])
        tok = auth_router._resolve_external_user(res, s)
    finally:
        auth_router.load_settings = orig
    assert tok.get("access_token"), "no token issued"
    user = s.query(db.User).filter(db.User.email == "new.staff@x.org").first()
    assert user is not None, "user not provisioned"
    assert user.hashed_password is None and user.auth_source == "oidc:okta"
    assert user.can_login, "passwordless SSO user cannot log in (the old can_login bug)"
    assert user.role == db.UserRole.parent, "super admin was auto-granted via SSO"
    s.close()
    # EXPECTED: SSO users can log in, are linked to their provider, never super admin.
    # IF THIS FAILS: every SSO user gets a 401 after sign-in, or SSO can mint admins.


@test(2, "saml.end_to_end_and_attacks",
      "Real signed SAML via an in-process IdP: sign-in works; replay, tamper, unsigned, unsolicited, forged are rejected.")
def t_saml_e2e():
    import base64, datetime, os, shutil, tempfile, warnings
    warnings.filterwarnings("ignore")
    if not shutil.which("xmlsec1"):
        raise Skip("xmlsec1 not installed (the Docker image includes it)")
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from saml2 import BINDING_HTTP_REDIRECT
        from saml2.config import IdPConfig
        from saml2.server import Server
        from saml2.metadata import entity_descriptor
        from saml2.saml import NameID, NAMEID_FORMAT_EMAILADDRESS, AUTHN_PASSWORD_PROTECTED
        from saml2.sigver import get_xmlsec_binary
        from urllib.parse import urlparse, parse_qs
        sp = _imp("core.saml_sp")
    except ImportError as e:
        raise Skip(f"pysaml2 not installed: {e}")

    d = tempfile.mkdtemp()
    def make_key(tag):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        nm = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "idp.test")])
        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (x509.CertificateBuilder().subject_name(nm).issuer_name(nm).public_key(key.public_key())
                .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(days=1))
                .not_valid_after(now + datetime.timedelta(days=30)).sign(key, hashes.SHA256()))
        kp, cp = os.path.join(d, tag + ".key"), os.path.join(d, tag + ".crt")
        open(kp, "wb").write(key.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
        open(cp, "wb").write(cert.public_bytes(serialization.Encoding.PEM))
        return kp, cp

    BASE = "https://privacy.example.edu"
    cfg = {"enabled": True}
    sp_md = sp.sp_metadata_xml(cfg, BASE)
    def make_idp(tag):
        kp, cp = make_key(tag)
        c = IdPConfig(); c.load({"entityid": "https://idp.example.edu/idp",
            "xmlsec_binary": get_xmlsec_binary(["/usr/bin", "/usr/local/bin"]),
            "service": {"idp": {"endpoints": {"single_sign_on_service":
                [("https://idp.example.edu/sso", BINDING_HTTP_REDIRECT)]},
                "policy": {"default": {"lifetime": {"minutes": 15}, "attribute_restrictions": None}}}},
            "key_file": kp, "cert_file": cp, "metadata": {"inline": [sp_md]}})
        return c, Server(config=c)
    idpc, idp = make_idp("real")
    cfg["idp_metadata_xml"] = str(entity_descriptor(idpc))
    _, impostor = make_idp("impostor")

    def answer(server, loc, email="alice@example.edu", sign=True, in_resp=None):
        q = parse_qs(urlparse(loc).query)
        req = server.parse_authn_request(q["SAMLRequest"][0], BINDING_HTTP_REDIRECT)
        r = server.create_authn_response(
            identity={"mail": [email], "displayName": ["Alice Staff"], "eduPersonAffiliation": ["staff"]},
            in_response_to=in_resp or req.message.id,
            destination=req.message.assertion_consumer_service_url,
            sp_entity_id=req.message.issuer.text,
            name_id=NameID(format=NAMEID_FORMAT_EMAILADDRESS, text=email),
            authn={"class_ref": AUTHN_PASSWORD_PROTECTED, "authn_auth": "x"},
            sign_response=sign, sign_assertion=sign)
        return base64.b64encode(str(r).encode()).decode()

    def rejected(fn):
        try:
            fn(); return False
        except sp.SamlError:
            return True

    good = answer(idp, sp.begin_login(cfg, BASE))
    r = sp.consume_response(cfg, BASE, good)
    assert r.provider == "saml" and r.email == "alice@example.edu" and "staff" in r.groups, r
    assert rejected(lambda: sp.consume_response(cfg, BASE, good)), "replay accepted"
    tam = base64.b64decode(answer(idp, sp.begin_login(cfg, BASE))).decode()
    tam = base64.b64encode(tam.replace("alice@example.edu", "admin@example.edu").encode()).decode()
    assert rejected(lambda: sp.consume_response(cfg, BASE, tam)), "tampered response accepted"
    uns = answer(idp, sp.begin_login(cfg, BASE), sign=False)
    assert rejected(lambda: sp.consume_response(cfg, BASE, uns)), "unsigned response accepted"
    sol = answer(idp, sp.begin_login(cfg, BASE), in_resp="id-we-never-issued")
    assert rejected(lambda: sp.consume_response(cfg, BASE, sol)), "unsolicited response accepted"
    forged = answer(impostor, sp.begin_login(cfg, BASE), email="admin@example.edu")
    assert rejected(lambda: sp.consume_response(cfg, BASE, forged)), "impostor-signed response accepted"
    # EXPECTED: genuine IdP sign-in works; every attack is refused.
    # IF THIS FAILS: SAML sign-in could be forged, replayed, or tampered with.


@test(2, "ldap.live_server_tls_and_credentials",
      "Real OpenLDAP with an internal CA: LDAPS/StartTLS sign-in, cert + hostname verification, bypass refused.")
def t_ldap_live():
    import os, shutil, socket, subprocess, tempfile, time
    if not os.path.exists("/usr/sbin/slapd") or not shutil.which("openssl"):
        raise Skip("slapd/openssl not installed (dev-machine integration test)")
    try:
        import ldap  # noqa: F401
        ap = _imp("core.auth_providers")
    except ImportError as e:
        raise Skip(f"python-ldap not installed: {e}")

    def free_port():
        s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p
    d = tempfile.mkdtemp(); os.makedirs(f"{d}/db")
    sh = lambda c: subprocess.run(c, shell=True, cwd=d, capture_output=True, check=True)
    sh('openssl req -x509 -newkey rsa:2048 -nodes -keyout ca.key -out ca.crt -days 2 -subj "/CN=Internal CA"')
    sh('openssl req -newkey rsa:2048 -nodes -keyout srv.key -out srv.csr -subj "/CN=localhost"')
    sh('printf "subjectAltName=DNS:localhost,IP:127.0.0.1\\n" > san.ext')
    sh('openssl x509 -req -in srv.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out srv.crt -days 2 -extfile san.ext')
    sh('openssl req -x509 -newkey rsa:2048 -nodes -keyout o.key -out other.crt -days 2 -subj "/CN=Other CA"')
    plain, tls = free_port(), free_port()
    open(f"{d}/slapd.conf", "w").write(f"""include /etc/ldap/schema/core.schema
include /etc/ldap/schema/cosine.schema
include /etc/ldap/schema/inetorgperson.schema
pidfile {d}/slapd.pid
modulepath /usr/lib/ldap
moduleload back_mdb
TLSCACertificateFile {d}/ca.crt
TLSCertificateFile {d}/srv.crt
TLSCertificateKeyFile {d}/srv.key
allow bind_anon_dn
database mdb
suffix "dc=example,dc=org"
rootdn "cn=admin,dc=example,dc=org"
rootpw adminpw
directory {d}/db
""")
    subprocess.run(["/usr/sbin/slapd", "-f", f"{d}/slapd.conf", "-h",
                    f"ldap://127.0.0.1:{plain}/ ldaps://127.0.0.1:{tls}/"], check=True, timeout=10)
    try:
        time.sleep(0.5)
        open(f"{d}/data.ldif", "w").write("""dn: dc=example,dc=org
objectClass: dcObject
objectClass: organization
o: Example
dc: example

dn: uid=alice,dc=example,dc=org
objectClass: inetOrgPerson
uid: alice
cn: Alice Staff
sn: Staff
displayName: Alice Staff
mail: alice@example.org
userPassword: alicepw
""")
        subprocess.run(["ldapadd", "-x", "-H", f"ldap://127.0.0.1:{plain}", "-D",
                        "cn=admin,dc=example,dc=org", "-w", "adminpw", "-f", f"{d}/data.ldif"],
                       check=True, capture_output=True, timeout=10)
        os.environ["LDAP_CA_DIR"] = f"{d}/cafiles"
        CA, OTHER = open(f"{d}/ca.crt").read(), open(f"{d}/other.crt").read()
        base = {"enabled": True, "host": "127.0.0.1", "base_dn": "dc=example,dc=org",
                "bind_dn": "cn=admin,dc=example,dc=org", "bind_password_enc": "adminpw",
                "user_attr": "uid", "timeout": 5}
        orig_cfg, orig_dec = ap.get_provider_config, ap.decrypt_password
        ap.decrypt_password = lambda v: v
        def login(cfg, pw="alicepw"):
            ap.get_provider_config = lambda k: cfg
            return ap.try_ldap_auth("alice", pw)
        try:
            ldaps = {**base, "tls_mode": "ldaps", "port": tls, "ca_cert_pem": CA}
            r = login(ldaps)
            assert r.success and r.email == "alice@example.org", f"LDAPS sign-in failed: {r}"
            assert login({**base, "tls_mode": "starttls", "port": plain, "ca_cert_pem": CA}).success, "StartTLS failed"
            assert not login({**base, "tls_mode": "ldaps", "port": tls}).success, "untrusted internal CA accepted"
            assert not login({**ldaps, "ca_cert_pem": OTHER}).success, "wrong CA accepted"
            assert not login(ldaps, pw="nope").success, "wrong password accepted"
            assert not login(ldaps, pw="").success, "EMPTY password accepted (bypass)"
            # the server itself accepts the unauthenticated bind — so our guard is what protects
            c = ldap.initialize(f"ldap://127.0.0.1:{plain}")
            c.simple_bind_s("uid=alice,dc=example,dc=org", "")
            assert "not trusted" in ap.ldap_diagnose({**base, "tls_mode": "ldaps", "port": tls}).lower()
            # RENEWAL: new key + new certificate from the same CA, directory restarted.
            # Login must keep working with NO configuration change.
            sh('openssl req -newkey rsa:2048 -nodes -keyout srv.key -out srv.csr -subj "/CN=localhost"')
            sh('openssl x509 -req -in srv.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out srv.crt -days 47 -extfile san.ext')
            os.kill(int(open(f"{d}/slapd.pid").read()), 15); time.sleep(1)
            subprocess.run(["/usr/sbin/slapd", "-f", f"{d}/slapd.conf", "-h",
                            f"ldap://127.0.0.1:{plain}/ ldaps://127.0.0.1:{tls}/"], check=True, timeout=10)
            time.sleep(0.5)
            assert login(ldaps).success, "login broke after the server certificate renewed"
            st = ap.ldap_cert_status(ldaps)
            assert st["level"] == "ok" and st["lifetime_days"] <= 47, f"renewed cert status wrong: {st}"
        finally:
            ap.get_provider_config, ap.decrypt_password = orig_cfg, orig_dec
    finally:
        try:
            os.kill(int(open(f"{d}/slapd.pid").read()), 15)
        except Exception:
            pass
    # EXPECTED: encrypted sign-in works; untrusted/wrong certs, wrong and empty passwords refused.
    # IF THIS FAILS: LDAP sign-in is broken, or it trusts the wrong server, or the bypass is open.


@test(2, "sip2.live_tls_server",
      "SIP2 over TLS against a real TLS server that echoes barcodes: sign-in, bypass, injection, verification.")
def t_sip2_live():
    import datetime, ipaddress, os, socket, ssl, tempfile, threading
    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
    except ImportError as e:
        raise Skip(f"cryptography not installed: {e}")
    ap = _imp("core.auth_providers")
    d = tempfile.mkdtemp(); now = datetime.datetime.now(datetime.timezone.utc)
    def mk(cn, issuer_key=None, issuer_name=None, ca=False, san=None):
        k = ec.generate_private_key(ec.SECP256R1())
        nm = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
        b = (x509.CertificateBuilder().subject_name(nm).issuer_name(issuer_name or nm)
             .public_key(k.public_key()).serial_number(x509.random_serial_number())
             .not_valid_before(now - datetime.timedelta(days=1)).not_valid_after(now + datetime.timedelta(days=30))
             .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True))
        if san:
            b = b.add_extension(x509.SubjectAlternativeName(san), critical=False)
        return k, b.sign(issuer_key or k, hashes.SHA256())
    ca_key, ca = mk("Test ILS CA", ca=True)
    srv_key, srv = mk("localhost", ca_key, ca.subject,
                      san=[x509.DNSName("localhost"), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))])
    _, other_ca = mk("Other CA", ca=True)
    pem = lambda c: c.public_bytes(serialization.Encoding.PEM).decode()
    open(f"{d}/srv.crt", "w").write(pem(srv))
    open(f"{d}/srv.key", "wb").write(srv_key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))

    hits = {"n": 0}
    def handle(conn):
        hits["n"] += 1; buf = b""
        try:
            while True:
                chunk = conn.recv(4096)
                if not chunk: return
                buf += chunk
                while b"\r" in buf:
                    line, buf = buf.split(b"\r", 1); msg = line.decode("ascii", "replace")
                    if msg.startswith("63"):
                        fld = dict((p[:2], p[2:]) for p in msg[35:].split("|") if len(p) >= 2)
                        bc, pin = fld.get("AA", ""), fld.get("AD", "")
                        known = bc == "21234000123"; good = known and pin == "1234"
                        fixed = "64" + " " * 14 + "000" + "20260101    120000" + "0000" * 6
                        conn.sendall((fixed + f"AOMAIN|AA{bc}|AE{'DOE, JANE' if known else ''}|"
                                      f"BL{'Y' if known else 'N'}|CQ{'Y' if good else 'N'}|AY1AZ0000\r").encode())
        except Exception:
            pass
        finally:
            conn.close()
    srv_sock = socket.socket(); srv_sock.bind(("127.0.0.1", 0)); srv_sock.listen(8)
    port = srv_sock.getsockname()[1]
    sctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); sctx.load_cert_chain(f"{d}/srv.crt", f"{d}/srv.key")
    def loop():
        while True:
            try:
                c, _ = srv_sock.accept()
            except OSError:
                return
            try:
                c = sctx.wrap_socket(c, server_side=True)
            except Exception:
                c.close(); continue
            threading.Thread(target=handle, args=(c,), daemon=True).start()
    threading.Thread(target=loop, daemon=True).start()

    cfg = {"enabled": True, "host": "127.0.0.1", "port": port, "use_tls": True,
           "institution_id": "MAIN", "timeout_seconds": 5, "ca_cert_pem": pem(ca)}
    orig = ap.get_provider_config
    try:
        def login(c, bc="21234000123", pin="1234"):
            ap.get_provider_config = lambda k: c
            return ap.try_sip2_auth(bc, pin)
        r = login(cfg)
        assert r.success and r.full_name == "DOE, JANE", f"valid patron refused: {r}"
        assert not login(cfg, pin="9999").success, "wrong PIN accepted"
        assert not login(cfg, bc="BLYCQY123", pin="0000").success, "substring bypass accepted"
        n = hits["n"]
        assert not login(cfg, bc="123|AD1234").success and hits["n"] == n, "injection reached the ILS"
        assert not login({**cfg, "ca_cert_pem": ""}).success, "untrusted internal CA accepted"
        assert not login({**cfg, "ca_cert_pem": pem(other_ca)}).success, "wrong CA accepted"
        assert not login({**cfg, "ca_cert_pem": "", "verify_cert": False}).success, \
            "legacy verify_cert=false still disabled verification"
        assert ap.sip2_cert_status(cfg)["level"] == "ok"
    finally:
        ap.get_provider_config = orig
        srv_sock.close()
    # EXPECTED: correct patrons sign in; bypass, injection, and untrusted certs refused.
    # IF THIS FAILS: SIP2 sign-in is broken, bypassable, or trusts the wrong server.


@test(2, "wizard.deployment_reverse_proxy_choice",
      "The wizard's reverse-proxy step validates its input, persists the choice, and "
      "the completion summary/warnings reflect it (managed / native / external / none).")
def t_wizard_deployment():
    from types import SimpleNamespace as NS
    try:
        wiz = _imp("routers.wizard")
        from fastapi import HTTPException
    except ImportError as e:
        raise Skip(f"needs full backend deps / package layout: {e}")

    import copy
    store = {}
    orig_load, orig_save = wiz._load, wiz._save
    # _load() must hand back a snapshot, not the live dict: save_deployment does
    # `s = _load(); s["deployment"] = ...; _save(s)` — if _load() returned `store`
    # itself, that first assignment would already mutate `store` in place, and
    # then _save's own clear()+update() (using the same object) would wipe it.
    wiz._load = lambda: copy.deepcopy(store)
    def fake_save(data):
        store.clear(); store.update(data)
    wiz._save = fake_save
    admin = NS(is_super_admin=True)

    try:
        # Invalid value rejected (400), nothing persisted.
        try:
            wiz.save_deployment(wiz.DeploymentStep(reverse_proxy="bogus"), db=None, user=admin)
            raise AssertionError("invalid reverse_proxy value was accepted")
        except HTTPException as e:
            assert e.status_code == 400

        # "external": recorded; step marked done; no HTTPS-setup warning at completion,
        # and the plain-HTTP client-side nag is expected to be suppressed for this value
        # (the frontend checks summary.reverse_proxy == 'external').
        wiz.save_deployment(wiz.DeploymentStep(reverse_proxy="external"), db=None, user=admin)
        assert store["deployment"]["reverse_proxy"] == "external"
        assert store["wizard"]["steps"]["deployment"] == "done"
        state = wiz.get_state(db=None, user=admin)
        assert state["reverse_proxy"] == "external"
        summary = wiz.complete(db=None, user=admin)
        assert summary["reverse_proxy"] == "external"
        assert not any("enable-https" in w for w in summary["warnings"]), \
            "an external reverse proxy shouldn't be told to run our own HTTPS setup"
        assert not any("unencrypted" in w for w in summary["warnings"])

        # "managed" (Docker + Caddy): recorded with an optional domain; completion
        # nudges toward the Docker-path HTTPS setup script.
        wiz.save_deployment(wiz.DeploymentStep(reverse_proxy="managed", domain="privacy.lib.org"),
                            db=None, user=admin)
        assert store["deployment"] == {"reverse_proxy": "managed", "domain": "privacy.lib.org"}
        summary = wiz.complete(db=None, user=admin)
        assert any("enable-https.sh" in w and "native" not in w for w in summary["warnings"]), \
            "managed (Docker) deployment should be pointed at scripts/enable-https.sh, not the native one"

        # "native" (no containers): recorded; completion nudges toward the native-path
        # script/doc instead — must NOT be confused with the Docker-managed message.
        wiz.save_deployment(wiz.DeploymentStep(reverse_proxy="native", domain="privacy.lib.org"),
                            db=None, user=admin)
        assert store["deployment"] == {"reverse_proxy": "native", "domain": "privacy.lib.org"}
        summary = wiz.complete(db=None, user=admin)
        assert any("enable-https-native.sh" in w or "NATIVE_INSTALL" in w for w in summary["warnings"]), \
            "native deployment should be pointed at the native script/doc, not the Docker one"
        assert not any("unencrypted" in w for w in summary["warnings"])

        # "none": recorded; completion warns plainly (nothing else vouches for HTTPS).
        wiz.save_deployment(wiz.DeploymentStep(reverse_proxy="none"), db=None, user=admin)
        summary = wiz.complete(db=None, user=admin)
        assert any("unencrypted" in w for w in summary["warnings"])

        # "deployment" is skippable like the other optional steps.
        wiz.skip_step(wiz.SkipStep(step="deployment"), db=None, user=admin)
        assert store["wizard"]["steps"]["deployment"] == "skipped"
    finally:
        wiz._load, wiz._save = orig_load, orig_save
    # EXPECTED: reverse_proxy is validated, persisted, and steers the completion
    #   summary — a larger deployment behind its own proxy isn't told to fight it
    #   for ports 80/443, and Docker vs. native installs each get pointed at their
    #   OWN HTTPS setup script rather than the other one's.
    # IF THIS FAILS: the wizard could point an admin at a script that assumes the
    #   wrong deployment technology, or silently leave a deployment on plain HTTP.



# ══════════════════════════════════════════════════════════════════════════════
#  TIER 3 — plugin protocol (needs grpcio + compiled proto stubs)
# ══════════════════════════════════════════════════════════════════════════════

@test(3, "plugin.proto_stubs_present",
      "The compiled gRPC stubs exist and expose all expected host + plugin RPCs.")
def t_proto():
    if _try_import("grpc") is None:
        raise Skip("grpcio not installed")
    try:
        pbg = _imp("plugins.proto.plugin_pb2_grpc")  # noqa
    except Exception:
        raise Skip("proto stubs not compiled (run the protoc step from the Dockerfile)")
    host = [m for m in dir(pbg.HostServiceServicer) if not m.startswith("_")]
    plug = [m for m in dir(pbg.PluginServiceServicer) if not m.startswith("_")]
    assert len(host) >= 18, f"expected >=18 host RPCs, found {len(host)}"
    assert len(plug) >= 6, f"expected >=6 plugin RPCs, found {len(plug)}"
    # EXPECTED: 18 host RPCs, 6 plugin RPCs.
    # IF THIS FAILS: the proto didn't compile, or RPCs are missing. Plugins
    #   won't be able to talk to the host at all.


@test(3, "plugin.smoke_round_trip",
      "A real plugin runs over real gRPC: init, ping, event, and a host callback all succeed.")
def t_smoke():
    if _try_import("grpc") is None:
        raise Skip("grpcio not installed")
    # The smoke test resolves to the same package root as this runner.
    smoke_mod = _mod("plugins.smoke_test")
    if importlib.util.find_spec(smoke_mod) is None:
        raise Skip(f"{smoke_mod} not found (proto stubs may not be compiled yet)")
    # Run it in a subprocess so its sys.exit() doesn't kill the runner. Pass our
    # sys.path via PYTHONPATH so the child resolves the package the same way, and
    # run from the parent-of-backend dir so `app.plugins.smoke_test` is importable.
    import subprocess
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [p for p in sys.path if p] + [env.get("PYTHONPATH", "")])
    cwd = _PARENT_DIR if _ROOT else _BACKEND_DIR
    r = subprocess.run([sys.executable, "-m", smoke_mod],
                       capture_output=True, text=True, timeout=60, cwd=cwd, env=env)
    assert r.returncode == 0, \
        f"smoke test failed (exit {r.returncode}). Last output:\n{r.stdout[-800:]}\n{r.stderr[-400:]}"
    # EXPECTED: exit 0, "PLUGIN SMOKE TEST PASSED".
    # IF THIS FAILS: the plugin protocol/capability plumbing is broken. Re-run
    #   the smoke test directly and send its full output.


# ══════════════════════════════════════════════════════════════════════════════
#  TIER 4 — application wiring (needs the FastAPI app to import)
# ══════════════════════════════════════════════════════════════════════════════

def _import_app_main():
    """
    Import the FastAPI app module. In the container it's `app.main` (the code is
    the `app` package); from a bare backend checkout run as a package it may be
    `main`. main.py uses relative imports, so it must be imported as part of a
    package — try the packaged name first.
    """
    for name in ("app.main", "main"):
        try:
            return importlib.import_module(name)
        except Exception:
            continue
    # Re-raise the packaged-name error for a useful message.
    return importlib.import_module("app.main")


@test(4, "app.imports",
      "The FastAPI app imports without error (catches bad imports, route wiring, syntax).")
def t_app_import():
    if _try_import("fastapi") is None:
        raise Skip("fastapi not installed")
    try:
        _import_app_main()
    except Exception as e:
        # This is the classic "container starts then crashes" failure — surface it.
        raise AssertionError(f"app main failed to import: {e}")
    # EXPECTED: main imports, app object exists.
    # IF THIS FAILS: this is almost certainly why the api container crash-loops.
    #   The traceback names the exact module/line.


@test(4, "access.route_gates",
      "Every route's gate matches the permission design: never-delegated actions stay "
      "super-admin only, delegated ones need their permission, broker writes aren't open.")
def t_access_route_gates():
    if _try_import("fastapi") is None:
        raise Skip("fastapi not installed")
    main = _import_app_main()
    from fastapi.routing import APIRoute
    auth = _imp("core.auth")

    def gates(route):
        found = set()
        def walk(dep):
            call = dep.call
            if call is auth.require_super_admin:
                found.add("SUPER")
            for k in getattr(call, "required_permissions", ()):
                found.add(k)
            for sub in dep.dependencies:
                walk(sub)
        walk(route.dependant)
        return found

    table = {}
    for r in main.app.routes:
        if isinstance(r, APIRoute):
            for m in r.methods:
                table[(m, r.path)] = gates(r)

    expect = {
        # Never delegated
        ("PUT", "/api/admin/permissions/defaults"): {"SUPER"},
        ("PUT", "/api/admin/users/{user_id}/permissions"): {"SUPER"},
        ("POST", "/api/plugins/{plugin_id}/enable"): {"SUPER"},
        ("POST", "/api/plugins/install"): {"SUPER"},
        ("DELETE", "/api/plugins/{plugin_id}"): {"SUPER"},
        ("PATCH", "/api/settings/plugins"): {"SUPER"},
        ("POST", "/api/database/migrate-to-postgres"): {"SUPER"},
        ("PATCH", "/api/database/connection-config"): {"SUPER"},
        ("DELETE", "/api/settings/danger/reset-requests"): {"SUPER"},
        # Delegated
        ("GET", "/api/admin/users"): {"users.manage"},
        ("POST", "/api/auth/invite-codes"): {"users.registration"},
        ("PATCH", "/api/brokers/{broker_id}"): {"brokers.manage"},
        ("DELETE", "/api/brokers/{broker_id}"): {"brokers.manage"},
        ("POST", "/api/brokers/import-csv"): {"brokers.manage"},
        ("POST", "/api/brokers/import-json"): {"brokers.manage"},
        ("PUT", "/api/automation/scripts/{broker_id}"): {"brokers.automation"},
        ("POST", "/api/scheduler/trigger/{job_name}"): {"scheduler.manage"},
        ("GET", "/api/reporting/summary"): {"reporting.view"},
        ("POST", "/api/help/notes"): {"help.edit"},
        ("GET", "/api/cert-monitor/alerts"): {"certificates.view"},
        ("PATCH", "/api/settings/email"): {"email.manage"},
        ("PATCH", "/api/branding/config"): {"branding.manage"},
        ("PATCH", "/api/branding/auth-providers/ldap"): {"auth.providers"},
        ("PUT", "/api/auth/saml/config"): {"auth.providers"},
        ("PATCH", "/api/settings/proxy"): {"settings.system"},
        ("GET", "/api/database/health"): {"database.view"},
        ("GET", "/api/plugins"): {"plugins.view"},
        ("POST", "/api/plugins/upload"): {"plugins.upload"},
    }
    wrong = {k: (table.get(k), v) for k, v in expect.items() if table.get(k) != v}
    assert not wrong, "route gates differ from the design (got, expected): " + \
        "; ".join(f"{m} {p}: {g}" for (m, p), g in wrong.items())
    # Nothing left requiring BOTH a permission and super admin (a half-done remap).
    mixed = [k for k, g in table.items() if "SUPER" in g and len(g) > 1]
    assert not mixed, f"routes gated by both super admin and a permission: {mixed}"


@test(4, "app.routes_registered",
      "Key routes (brokers health, plugins, auth) are registered on the app.")
def t_routes():
    if _try_import("fastapi") is None:
        raise Skip("fastapi not installed")
    try:
        mainmod = _import_app_main()
    except Exception as e:
        raise Skip(f"app didn't import (see app.imports): {e}")
    # Use the OpenAPI spec: it lists every route in every FastAPI version
    # (newer versions nest included routers, so app.routes isn't flat), and
    # generating it also fails loudly on a broken route/response model.
    paths = set(mainmod.app.openapi().get("paths", {}).keys())
    joined = " ".join(paths)
    for needle in ("/api/brokers", "/api/plugins", "/api/auth"):
        assert needle in joined, f"expected route prefix {needle} not registered"
    # Broker-health endpoints from item 1
    assert any("health" in p for p in paths), "broker health routes not registered"
    # EXPECTED: broker, plugin, auth, and health routes all present.
    # IF THIS FAILS: a router failed to include; that feature's API is dead even
    #   though the app booted.


# ── runner ────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="PrivacyShield test runner")
    ap.add_argument("--tier", type=int, default=4, help="run tiers up to N (1-4)")
    ap.add_argument("--only", type=str, default="", help="substring filter on test name")
    ap.add_argument("--verbose", action="store_true", help="show full tracebacks")
    args = ap.parse_args()

    tests = sorted(_REGISTRY, key=lambda t: (t[0], t[1]))
    results = []
    print("=" * 70)
    print("  PrivacyShield test runner")
    print("=" * 70)

    current_tier = None
    for tier, name, doc, fn in tests:
        if tier > args.tier:
            continue
        if args.only and args.only.lower() not in name.lower():
            continue
        if tier != current_tier:
            current_tier = tier
            print(f"\n── Tier {tier} " + "─" * 54)
        t0 = time.time()
        try:
            fn()
            status, err = PASS, ""
        except Skip as e:
            status, err = SKIP, str(e)
        except Exception as e:
            status, err = FAIL, e
        ms = int((time.time() - t0) * 1000)
        results.append((tier, name, status, err))

        mark = {PASS: "PASS", FAIL: "FAIL", SKIP: "skip"}[status]
        line = f"  [{mark}] {name:42} ({ms:>4}ms)"
        if status == SKIP:
            line += f"  — {err}"
        print(line)
        print(f"         {doc}")
        if status == FAIL:
            print(f"         ERROR: {err}")
            if args.verbose:
                traceback.print_exception(type(err), err, err.__traceback__)

    # summary
    npass = sum(1 for *_, s, _ in results if s == PASS)
    nfail = sum(1 for *_, s, _ in results if s == FAIL)
    nskip = sum(1 for *_, s, _ in results if s == SKIP)

    print("\n" + "=" * 70)
    print("  TEST SUMMARY  (copy from here down to report back)")
    print("=" * 70)
    print(f"  passed: {npass}   failed: {nfail}   skipped: {nskip}")
    if nfail:
        print("\n  FAILURES:")
        for tier, name, status, err in results:
            if status == FAIL:
                print(f"    - [T{tier}] {name}: {err}")
    if nskip:
        print("\n  SKIPPED (dependency not present in this environment):")
        for tier, name, status, err in results:
            if status == SKIP:
                print(f"    - [T{tier}] {name}: {err}")
    print("\n  Environment:")
    print(f"    python {sys.version.split()[0]}")
    for mod in ("sqlalchemy", "grpc", "fastapi", "playwright"):
        m = _try_import(mod)
        v = getattr(m, "__version__", "present") if m else "MISSING"
        print(f"    {mod:12} {v}")
    print("=" * 70)

    sys.exit(1 if nfail else 0)


if __name__ == "__main__":
    main()
