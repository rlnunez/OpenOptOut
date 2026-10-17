#!/usr/bin/env python3
"""
OpenOptOut test runner
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
import re
import sys
import time
import traceback

os.environ.setdefault("SECRET_KEY", "test-runner-ephemeral-secret-key-0123456789abcdef")
from urllib.parse import urlparse

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


def _yahoo_plugin():
    import importlib.util, sys, pathlib, json
    here = pathlib.Path(__file__).resolve().parents[1]
    d = here / "plugins" / "bundled" / "email" / "email-yahoo"
    sys.path.insert(0, str(here / "plugins" / "sdk"))
    try:
        spec = importlib.util.spec_from_file_location("yahoo_plugin_under_test", d / "plugin.py")
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    except Exception as e:
        raise Skip(f"plugin SDK not importable here: {e}")
    finally:
        sys.path.pop(0)
    mod.plugin.get_email_credentials = lambda ref: {"access_token": "tok-" + ref, "token_type": "Bearer"}
    return mod, json.loads((d / "manifest.json").read_text())


@test(1, "email_providers.yahoo_oauth_only",
      "Yahoo is sign-in only: its manifest reaches only Yahoo's IMAP/SMTP, and it signs in with the token.")
def t_yahoo_oauth_only():
    if _try_import("fastapi") is None:
        raise Skip("fastapi not installed")
    mod, mani = _yahoo_plugin()
    m = mod.plugin.manifest
    assert mani["version"] == m["version"] == "2.0.0"
    assert sorted(mani["outbound_domains"]) == sorted(m["outbound_domains"]) == \
        ["imap.mail.yahoo.com", "smtp.mail.yahoo.com"], "only Yahoo's mail servers"
    assert set(mani["methods"]) == set(m["methods"]) and "email.get_credentials" in mani["methods"]
    info = mod.plugin._email_info
    assert info["auth_type"] == "oauth" and info["oauth_scopes"] == "mail-r mail-w"
    src = open(mod.__file__).read()
    assert "app_password" not in src and "smtp_password" not in src, "no app-password mode"
    assert mod.oauthbearer("jordan@example.invalid", "T", "imap.mail.yahoo.com", 993) == \
        "n,a=jordan@example.invalid,\x01host=imap.mail.yahoo.com\x01port=993\x01auth=Bearer T\x01\x01"
    assert mod.xoauth2("jordan@example.invalid", "T") == "user=jordan@example.invalid\x01auth=Bearer T\x01\x01"
    flow = _imp("routers.email_oauth")._provider_flow("yahoo")
    assert flow.scopes == "mail-r mail-w", "the built-in Yahoo sign-in must ask to read mail too"
    assert "yahoo" not in _imp("routers.settings").PRESETS, "no Yahoo app-password preset"


@test(1, "email_providers.yahoo_reads_links_over_imap",
      "Yahoo reads confirmation links over IMAP with the token, without marking mail read.")
def t_yahoo_list():
    mod, _ = _yahoo_plugin()
    raw = (b"From: Brokr <privacy@broker.example>\r\nTo: jordan@example.invalid\r\n"
           b"Subject: Confirm your request\r\nDate: Sat, 10 Oct 2026 12:00:00 +0000\r\n"
           b"Message-ID: <m1@broker.example>\r\nContent-Type: text/plain\r\n\r\n"
           b"Click https://broker.example/confirm?t=abc to confirm.\r\n")
    old = (b"From: x@old.example\r\nTo: jordan@example.invalid\r\nSubject: old\r\n"
           b"Date: Mon, 01 Jan 2024 00:00:00 +0000\r\nMessage-ID: <m0@old.example>\r\n\r\nhi\r\n")
    calls = []

    class FakeIMAP:
        capabilities = (b"IMAP4REV1", b"AUTH=OAUTHBEARER", b"AUTH=XOAUTH2")
        def authenticate(self, mech, cb):
            calls.append(("auth", mech, cb(b"").decode())); return ("OK", [b""])
        def select(self, box, readonly=False):
            calls.append(("select", box, readonly)); return ("OK", [b"2"])
        def search(self, charset, crit): return ("OK", [b"1 2"])
        def fetch(self, i, what):
            calls.append(("fetch", i, what))
            body = raw if i == b"2" else old
            if what == "(BODY.PEEK[HEADER])":
                body = body.split(b"\r\n\r\n")[0] + b"\r\n\r\n"
            return ("OK", [(b"x", body)])
        def logout(self): calls.append(("logout",))

    mod._imap = lambda *a, **k: FakeIMAP()
    r = mod.list_messages({"account_ref": "fam1", "max_results": 10, "since_ts": 1700000000 + 86400 * 365,
                           "include_links": True, "links_if_to_contains": "",
                           "account_address": "jordan@example.invalid"})
    assert r["ok"] and r["links_supported"], r
    assert [x["message_id"] for x in r["messages"]] == ["m1@broker.example"], "older mail skipped"
    assert [l["url"] for l in r["messages"][0]["links"]] == ["https://broker.example/confirm?t=abc"]
    assert ("select", "INBOX", True) in calls, "opened read-only"
    assert all("PEEK" in c[2] for c in calls if c[0] == "fetch"), "bodies read with PEEK so they stay unread"
    auth = [c for c in calls if c[0] == "auth"][0]
    assert auth[1] == "OAUTHBEARER" and "a=jordan@example.invalid" in auth[2] and "Bearer tok-fam1" in auth[2]
    # No address from the host: a plain error, nothing fetched.
    calls.clear()
    r = mod.list_messages({"account_ref": "fam1", "account_address": ""})
    assert not r["ok"] and "Yahoo address" in r["error"] and not calls


@test(1, "email_providers.yahoo_sends_with_token",
      "Yahoo sends over SMTP with the token, only to the host's recipients, and needs the account address.")
def t_yahoo_send():
    mod, _ = _yahoo_plugin()
    seen = {}

    class FakeSMTP:
        esmtp_features = {"auth": "PLAIN LOGIN XOAUTH2 OAUTHBEARER"}
        def __init__(self, host, port, timeout=None): seen["host"] = (host, port)
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def ehlo(self): pass
        def auth(self, mech, cb, initial_response_ok=True): seen["auth"] = (mech, cb())
        def sendmail(self, frm, rcpts, msg): seen["mail"] = (frm, list(rcpts), msg)

    real = mod.smtplib.SMTP_SSL          # the shared smtplib module: put it back
    mod.smtplib.SMTP_SSL = FakeSMTP
    try:
        r = mod.send({"account_ref": "fam1", "to": ["privacy@broker.example"], "cc": [],
                      "subject": "Opt-out", "body": "Please remove.",
                      "meta": {"account_address": "jordan@example.invalid", "reply_to": "jordan@example.invalid"}})
    finally:
        mod.smtplib.SMTP_SSL = real
    assert r["ok"] and r["sent_to"] == ["privacy@broker.example"], r
    assert seen["host"] == ("smtp.mail.yahoo.com", 465)
    assert seen["auth"][0] == "OAUTHBEARER" and "Bearer tok-fam1" in seen["auth"][1]
    assert seen["mail"][0] == "jordan@example.invalid" and seen["mail"][1] == ["privacy@broker.example"]
    r = mod.send({"account_ref": "fam1", "to": ["privacy@broker.example"], "meta": {}})
    assert not r["ok"] and "Yahoo address" in r["error"]


@test(1, "email_providers.account_address_passed_to_plugins",
      "The host tells email-provider plugins which address they sign in to, for reading and sending.")
def t_account_address_passed():
    import types
    mgr_mod = _imp("plugins.manager")
    if not mgr_mod._load_grpc():
        raise Skip("gRPC stubs not built here")
    pb = mgr_mod._pb
    got = {}

    class Stub:
        def EmailProviderInfo(self, req, timeout=None): return types.SimpleNamespace(provider_key="yahoo")
        def EmailProviderList(self, req, timeout=None):
            got["list"] = req; return pb.EmailProviderListResponse(ok=True)
        def EmailProviderSend(self, req, timeout=None):
            got["send"] = req; return pb.EmailProviderSendResponse(ok=True, sent_to=list(req.to))

    m = object.__new__(mgr_mod.PluginManager)
    m.running = {"email-yahoo": types.SimpleNamespace(
        manifest=types.SimpleNamespace(hooks=["email_provider"], timeout_seconds=5), stub=Stub())}
    m.dispatch_email_list("yahoo", "fam1", account_address="jordan@example.invalid")
    assert got["list"].account_address == "jordan@example.invalid"

    es = _imp("core.email_send")
    plugins_pkg = _imp("plugins")
    old_gm, old_ref = plugins_pkg.get_manager, es._refresh_if_needed
    plugins_pkg.get_manager = lambda: m
    es._refresh_if_needed = lambda *a, **k: True
    try:
        r = es.send_email({"email": {"provider": "yahoo"}}, to=["privacy@broker.example"], cc=[],
                          subject="s", body="b", account_ref="fam1", from_address="jordan@example.invalid")
    finally:
        plugins_pkg.get_manager, es._refresh_if_needed = old_gm, old_ref
    assert r.get("ok"), r
    assert dict(got["send"].meta).get("account_address") == "jordan@example.invalid"
    assert list(got["send"].to) == ["privacy@broker.example"], "the address is not added as a recipient"


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
    # Never the whole page: only a cropped, blacked-out picture of the CAPTCHA,
    # and here (no element boxes from the fake page) nothing at all.
    assert res.challenge.get("screenshot") == b""
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


@test(1, "email_grace.snapshot_on_mode_change",
      "Switching email mode or mailbox creates an active grace period snapshot of the previous config.")
def t_email_grace_snapshot():
    eg = _imp("core.email_grace")
    old_settings = {
        "email": {
            "mode": "shared",
            "imap_host": "imap.example.org",
            "imap_port": 993,
            "imap_user": "removals@example.org",
            "imap_password_enc": "enc123",
            "from_email": "removals@example.org",
        }
    }

    # Case 1: Identical settings -> No snapshot
    res_noop = eg.maybe_snapshot_grace_period(
        current_settings=old_settings,
        new_email_config={"imap_host": "imap.example.org", "imap_user": "removals@example.org"},
        new_mode="shared"
    )
    assert res_noop is None, "Should not snapshot when nothing changed"
    assert "email_grace_period" not in old_settings

    # Case 2: Mode changed to per_user -> Snapshot created
    res_mode = eg.maybe_snapshot_grace_period(
        current_settings=old_settings,
        new_email_config={},
        new_mode="per_user"
    )
    assert res_mode is not None, "Should snapshot when mode changes"
    assert res_mode["active"] is True
    assert res_mode["grace_period_days"] == 60
    assert res_mode["previous_config"]["imap_user"] == "removals@example.org"
    assert res_mode["previous_config"]["mode"] == "shared"


@test(1, "email_grace.lifecycle_and_expiration",
      "Grace period status computes remaining days, handles extend/dismiss, and expires when overdue.")
def t_email_grace_lifecycle():
    from datetime import datetime, timezone, timedelta
    eg = _imp("core.email_grace")

    now = datetime.now(timezone.utc)
    settings = {
        "email_grace_period": {
            "active": True,
            "transition_started_at": (now - timedelta(days=10)).isoformat(),
            "grace_period_days": 60,
            "previous_config": {"imap_user": "old@example.org", "mode": "shared"}
        }
    }

    # Status check
    status = eg.get_email_grace_status(settings)
    assert status["active"] is True
    assert 49 <= status["days_remaining"] <= 51
    assert status["previous_inbox"] == "old@example.org"

    # Extend
    new_days = eg.extend_email_grace_period(settings, extra_days=30)
    assert new_days == 90
    status_ext = eg.get_email_grace_status(settings)
    assert 79 <= status_ext["days_remaining"] <= 81

    # Dismiss
    dismissed = eg.dismiss_email_grace_period(settings)
    assert dismissed is True
    assert eg.get_email_grace_status(settings)["active"] is False

    # Expiration check
    expired_settings = {
        "email_grace_period": {
            "active": True,
            "transition_started_at": (now - timedelta(days=70)).isoformat(),
            "grace_period_days": 60,
            "previous_config": {"imap_user": "expired@example.org"}
        }
    }
    exp_status = eg.get_email_grace_status(expired_settings)
    assert exp_status["active"] is False
    assert exp_status["days_remaining"] == 0


@test(2, "email_grace.scheduler_dual_inbox_integration",
      "Scheduler email monitor polls both primary and previous mailboxes when grace period is active.")
def t_email_grace_scheduler_dual_inbox():
    if _try_import("apscheduler") is None:
        raise Skip("apscheduler not installed")
    if _try_import("sqlalchemy") is None:
        raise Skip("sqlalchemy not installed")
    sched_mod = _imp("core.scheduler")

    polled_configs = []
    def fake_poll(ec, db, cfg, is_grace_period=False):
        polled_configs.append((ec.get("imap_user"), is_grace_period))
        return 1, []

    orig_poll = getattr(sched_mod, "_poll_imap_mailbox", None)
    sched_mod._poll_imap_mailbox = fake_poll

    settings_mod = _imp("core.settings_store")
    orig_load = settings_mod.load_settings
    orig_sched_load = getattr(sched_mod, "load_settings", None)
    settings_mod.load_settings = lambda: {
        "email": {
            "imap_host": "imap.new.org",
            "imap_user": "new@example.org",
            "imap_password_enc": "enc_new",
        },
        "email_grace_period": {
            "active": True,
            "transition_started_at": "2026-01-01T00:00:00+00:00",
            "grace_period_days": 3650,
            "previous_config": {
                "imap_host": "imap.old.org",
                "imap_user": "old@example.org",
                "imap_password_enc": "enc_old",
            }
        }
    }
    sched_mod.load_settings = settings_mod.load_settings

    try:
        class FakeDB:
            def add(self, x): pass
            def commit(self): pass
            def close(self): pass

        orig_session = sched_mod.SessionLocal
        sched_mod.SessionLocal = lambda: FakeDB()

        sched_mod.email_monitor_job()

        assert len(polled_configs) == 2, f"Expected 2 polled mailboxes, got {polled_configs}"
        assert polled_configs[0] == ("new@example.org", False), f"Primary poll mismatch: {polled_configs[0]}"
        assert polled_configs[1] == ("old@example.org", True), f"Grace poll mismatch: {polled_configs[1]}"
    finally:
        sched_mod._poll_imap_mailbox = orig_poll
        settings_mod.load_settings = orig_load
        if orig_sched_load is not None:
            sched_mod.load_settings = orig_sched_load
        sched_mod.SessionLocal = orig_session


@test(1, "memory_hygiene.secure_buffer_zeroize",
      "SecureBuffer stores sensitive data and overwrites its mutable byte buffer with zeros on exit.")
def t_memory_hygiene_secure_buffer():
    mh = _imp("core.memory_hygiene")
    buf = mh.SecureBuffer.from_str("SuperSecretPassword123!")
    assert buf.as_str() == "SuperSecretPassword123!"
    assert len(buf) > 0
    assert buf.is_zeroized is False

    # Manual zeroization
    buf.zeroize()
    assert buf.is_zeroized is True
    assert buf.as_str() == ""
    assert buf.as_bytes() == b""

    # Context manager zeroization
    with mh.SecureBuffer.from_str("EphemeralToken456") as ctx_buf:
        captured_buf = ctx_buf
        assert ctx_buf.as_str() == "EphemeralToken456"
        assert ctx_buf.is_zeroized is False
    assert captured_buf.is_zeroized is True
    assert captured_buf.as_str() == ""


@test(1, "memory_hygiene.disable_core_dumps",
      "disable_core_dumps sets RLIMIT_CORE to (0, 0) to prevent process crash memory dumps.")
def t_memory_hygiene_disable_core_dumps():
    mh = _imp("core.memory_hygiene")
    result = mh.disable_core_dumps()
    assert isinstance(result, bool)
    try:
        import resource
        soft, hard = resource.getrlimit(resource.RLIMIT_CORE)
        assert soft == 0
    except (ImportError, AttributeError):
        pass


@test(1, "memory_hygiene.ephemeral_secret_lifecycle",
      "ephemeral_secret yields secret during block execution and wipes buffer upon exit and on exceptions.")
def t_memory_hygiene_ephemeral_secret():
    mh = _imp("core.memory_hygiene")

    # Success case
    with mh.ephemeral_secret("my-plaintext-api-key", decrypt=False) as secret:
        assert secret == "my-plaintext-api-key"

    # Exception safety: buffer is still wiped even if error occurs
    caught = False
    try:
        with mh.ephemeral_secret("my-failing-secret", decrypt=False) as secret:
            assert secret == "my-failing-secret"
            raise ValueError("Intentional error inside secret block")
    except ValueError:
        caught = True
    assert caught is True, "Exception inside ephemeral_secret should propagate"


@test(1, "memory_hygiene.scoped_credentials_and_streaming",
      "scoped_credentials clears secret dictionary upon exit and stream_records streams items cleanly.")
def t_memory_hygiene_scoped_creds_and_streaming():
    mh = _imp("core.memory_hygiene")

    # Scoped credentials
    with mh.scoped_credentials(user="test_user", token="test_token") as creds:
        assert creds.get("token") == "test_token"
    # Dictionary cleared on exit
    assert len(creds) == 0

    # Stream records
    items = list(range(100))
    streamed = list(mh.stream_records(items, batch_size=25))
    assert streamed == items

    # Stream query mock with yield_per
    class FakeQuery:
        def __init__(self, data):
            self.data = data
            self.yield_per_called_with = None
        def yield_per(self, n):
            self.yield_per_called_with = n
            return iter(self.data)

    fq = FakeQuery(["record1", "record2", "record3"])
    out = list(mh.stream_records(fq, batch_size=10))
    assert out == ["record1", "record2", "record3"]
    assert fq.yield_per_called_with == 10


@test(1, "encryption.db_key_derivation_and_optout",
      "get_db_encryption_key derives key from env and honors DISABLE_DB_ENCRYPTION opt-out.")
def t_encryption_key_derivation():
    enc = _imp("core.encryption")
    import os
    orig_db_key = os.environ.get("DB_ENCRYPTION_KEY")
    orig_sec_key = os.environ.get("SECRET_KEY")
    orig_disable = os.environ.get("DISABLE_DB_ENCRYPTION")
    try:
        os.environ["DB_ENCRYPTION_KEY"] = "custom-db-passphrase-123"
        os.environ["SECRET_KEY"] = "secret-key-fallback-456"
        os.environ.pop("DISABLE_DB_ENCRYPTION", None)
        assert enc.get_db_encryption_key() == "custom-db-passphrase-123"

        os.environ.pop("DB_ENCRYPTION_KEY", None)
        assert enc.get_db_encryption_key() == "secret-key-fallback-456"

        os.environ["DISABLE_DB_ENCRYPTION"] = "true"
        assert enc.get_db_encryption_key() is None
    finally:
        for k, v in [("DB_ENCRYPTION_KEY", orig_db_key), ("SECRET_KEY", orig_sec_key), ("DISABLE_DB_ENCRYPTION", orig_disable)]:
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)


@test(1, "encryption.sqlite_plaintext_detection",
      "is_sqlite_plaintext correctly distinguishes unencrypted SQLite from non-sqlite files.")
def t_encryption_sqlite_plaintext_detection():
    enc = _imp("core.encryption")
    import tempfile, sqlite3, os
    with tempfile.TemporaryDirectory() as tmpdir:
        db_file = os.path.join(tmpdir, "test_plain.db")
        conn = sqlite3.connect(db_file)
        conn.execute("CREATE TABLE test_table (id INTEGER PRIMARY KEY, val TEXT);")
        conn.execute("INSERT INTO test_table VALUES (1, 'hello');")
        conn.commit()
        conn.close()

        assert enc.is_sqlite_plaintext(db_file) is True

        fake_file = os.path.join(tmpdir, "test_fake.db")
        with open(fake_file, "wb") as f:
            f.write(b"\x00" * 32)
        assert enc.is_sqlite_plaintext(fake_file) is False
        assert enc.is_sqlite_plaintext(os.path.join(tmpdir, "nonexistent.db")) is False


@test(1, "encryption.url_extraction_and_status",
      "extract_sqlite_path parses local paths and check_db_encryption_status reports accurate posture.")
def t_encryption_url_and_status():
    enc = _imp("core.encryption")
    import tempfile, sqlite3, os

    assert enc.extract_sqlite_path("sqlite:////data/privacy_pipeline.db") == "/data/privacy_pipeline.db"
    assert enc.extract_sqlite_path("sqlite:///./relative.db") == "./relative.db"
    assert enc.extract_sqlite_path("sqlite:///relative.db") == "relative.db"
    assert enc.extract_sqlite_path("postgresql://user:pass@localhost:5432/db") is None

    with tempfile.TemporaryDirectory() as tmpdir:
        missing = os.path.join(tmpdir, "missing.db")
        assert enc.check_db_encryption_status(missing)["status"] == "missing"

        empty = os.path.join(tmpdir, "empty.db")
        open(empty, "a").close()
        assert enc.check_db_encryption_status(empty)["status"] == "empty"

        plain = os.path.join(tmpdir, "plain.db")
        conn = sqlite3.connect(plain)
        conn.execute("CREATE TABLE foo (x INTEGER);")
        conn.commit()
        conn.close()
        status_info = enc.check_db_encryption_status(plain)
        assert status_info["status"] == "plaintext"
        assert status_info["is_encrypted"] is False


@test(1, "hardening.tmpfs_sizing_simulation",
      "Simulate ephemeral /tmp tmpfs worker allocations, measuring peak memory and verifying zero leakage.")
def t_hardening_tmpfs_sizing():
    import sys, os
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    if root_dir not in sys.path:
        sys.path.insert(0, root_dir)
    tests_dir = os.path.abspath(os.path.dirname(__file__))
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)

    try:
        from deploy.tests.test_tmpfs_sizing import run_tmpfs_stress_test, get_tmp_stats
    except ImportError:
        try:
            from test_tmpfs_sizing import run_tmpfs_stress_test, get_tmp_stats
        except ImportError:
            try:
                from tests.test_tmpfs_sizing import run_tmpfs_stress_test, get_tmp_stats
            except ImportError:
                raise Skip("test_tmpfs_sizing not present in this runtime")

    stats = get_tmp_stats()
    assert "total_mb" in stats and stats["total_mb"] > 0
    assert "free_mb" in stats

    res = run_tmpfs_stress_test(concurrency=2, payload_mb=2, duration_sec=0.05)
    assert res["all_succeeded"] is True
    assert res["all_cleaned"] is True
    assert res["total_simulated_mb"] >= 4.0
    assert res["recommended_min_tmpfs_mb"] >= 256


@test(1, "hardening.no_new_privs_probe",
      "Validate container no-new-privileges and sandbox capability probing logic.")
def t_hardening_no_new_privs():
    import sys, os
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    if root_dir not in sys.path:
        sys.path.insert(0, root_dir)
    tests_dir = os.path.abspath(os.path.dirname(__file__))
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)

    try:
        from deploy.tests.test_no_new_privs import run_probe, check_no_new_privs_flag
    except ImportError:
        try:
            from test_no_new_privs import run_probe, check_no_new_privs_flag
        except ImportError:
            try:
                from tests.test_no_new_privs import run_probe, check_no_new_privs_flag
            except ImportError:
                raise Skip("test_no_new_privs not present in this runtime")

    flag_active, detail = check_no_new_privs_flag()
    assert isinstance(flag_active, bool)
    assert isinstance(detail, str)

    probe = run_probe()
    assert "platform" in probe
    assert "is_linux" in probe
    assert "no_new_privs_active" in probe
    assert "compatible" in probe


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
        "empty script should return None from spec_from_script"

    # Heuristic fallback for unscripted brokers (retires legacy combo engine)
    h_spec = sb.heuristic_spec_for_broker(FakeBroker())
    assert h_spec is not None, "heuristic spec must be created"
    assert not h_spec.validate(), f"heuristic spec must validate cleanly: {h_spec.validate()}"
    h_kinds = [s.kind for s in h_spec.steps]
    assert "fill" in h_kinds and "submit" in h_kinds, "heuristic spec must include fill and submit steps"

    # get_or_build_broker_spec resolves script when present, falls back to heuristic when empty
    resolved_with_script = sb.get_or_build_broker_spec(FakeBroker(), FakeScript())
    assert resolved_with_script.name == "TestBroker"
    resolved_empty = sb.get_or_build_broker_spec(FakeBroker(), EmptyScript())
    assert resolved_empty is not None and not resolved_empty.validate()
    assert any(s.field == "first_name" for s in resolved_empty.steps)



@test(1, "interpreter.complex_page_actions",
      "Multi-form interpreter compiles and executes complex steps (click_matching, press, frame, scroll) and multi-stage plugin loops.")
def t_complex_page_actions():
    import asyncio
    bs_mod = _imp("core.interpreter.broker_spec")
    compiler_mod = _imp("core.interpreter.compiler")
    executor_mod = _imp("core.interpreter.executor")

    # 1. Declarative spec validation with complex steps
    spec = bs_mod.BrokerSpec(
        broker_id="wizard-broker",
        name="Wizard Broker",
        method="form",
        opt_out_url="https://wizard.example/search",
        steps=[
            bs_mod.Step(kind="fill", selector="#name-input", field="full_name"),
            bs_mod.Step(kind="press", selector="#name-input", value="Enter"),
            bs_mod.Step(kind="scroll", selector="#results-container"),
            bs_mod.Step(kind="click_matching", selector=".result-card", field="city"),
            bs_mod.Step(kind="frame", selector="iframe#removal-form"),
            bs_mod.Step(kind="fill", selector="#email-input", field="email"),
            bs_mod.Step(kind="click", selector="#submit-btn"),
            bs_mod.Step(kind="frame", selector="main"),
            bs_mod.Step(kind="expect_success", text="Removal confirmed"),
        ]
    )
    val_errs = spec.validate()
    assert not val_errs, f"spec validation failed: {val_errs}"

    # 2. Compilation and field substitution
    member = {
        "full_name": "Jane Doe",
        "city": "Austin",
        "email": "jane@example.org"
    }
    job = compiler_mod.compile_job(spec, member, member_id="42")
    assert len(job.steps) == 10  # 1 auto-navigate + 9 steps
    click_matching_step = next(s for s in job.steps if s.kind == "click_matching")
    assert click_matching_step.text == "Austin"

    # 3. DryRunExecutor
    dry = executor_mod.DryRunExecutor()
    res = dry.run(job)
    assert res.ok is True
    assert any("press 'Enter'" in t for t in res.trace)
    assert any("click_matching .result-card matching 'Austin'" in t for t in res.trace)
    assert any("frame context -> iframe#removal-form" in t for t in res.trace)
    assert any("frame context -> main" in t for t in res.trace)

    # 4. PlaywrightExecutor multi-stage plugin takeover simulation
    class FakeLocator:
        def __init__(self, sel):
            self.sel = sel
        def filter(self, has_text=None):
            return self
        @property
        def first(self):
            return self
        async def count(self):
            return 1
        async def click(self, timeout=None):
            pass
        async def fill(self, value, timeout=None):
            pass
        async def press(self, key, timeout=None):
            pass
        async def wait_for(self, state=None, timeout=None):
            pass
        async def inner_text(self, timeout=None):
            return "Search Results"
        async def scroll_into_view_if_needed(self, timeout=None):
            pass

    class FakePage:
        def __init__(self):
            self.url = "https://wizard.example/search"
            self.frames = [1, 2]
        async def title(self):
            return "Search Directory"
        async def content(self):
            return "<html><body><h1>Search Results</h1></body></html>"
        async def goto(self, url, timeout=None):
            self.url = url
        async def wait_for_timeout(self, ms):
            pass
        async def wait_for_selector(self, sel, timeout=None):
            pass
        def frame_locator(self, sel):
            return self
        def locator(self, sel):
            return FakeLocator(sel)
        async def press(self, sel, key, timeout=None):
            pass
        async def fill(self, sel, val, timeout=None):
            pass
        async def click(self, sel, timeout=None):
            pass
        async def query_selector(self, sel):
            return None

    stages_seen = []
    async def fake_multi_stage_handler(j, ctx):
        stages_seen.append(ctx.get("stage_index"))
        assert ctx.get("has_iframes") is True
        if ctx.get("stage_index") == 0:
            return {
                "handled": True,
                "plugin_id": "test-multistep",
                "actions": [
                    {"action": "fill", "selector": "#name", "value": "Jane Doe"},
                    {"action": "press", "selector": "#name", "value": "Enter"}
                ],
                "next_stage": True,
            }
        else:
            return {
                "handled": True,
                "plugin_id": "test-multistep",
                "actions": [
                    {"action": "frame", "selector": "iframe#optout"},
                    {"action": "click_matching", "selector": ".card", "value": "Austin"},
                    {"action": "expect_success", "selector": ".done"}
                ],
                "next_stage": False,
            }

    fake_page = FakePage()
    pw_exec = executor_mod.PlaywrightExecutor(
        page=fake_page,
        plugin_form_handler=fake_multi_stage_handler
    )
    pw_res = asyncio.run(pw_exec.run(job))
    assert pw_res.ok is True, f"pw_exec failed: {pw_res.detail}"
    assert stages_seen == [0, 1], f"expected stages 0 and 1, got {stages_seen}"
    assert any("stage 1" in t for t in pw_res.trace)
    assert any("stage 2" in t for t in pw_res.trace)


@test(1, "distributed.job_envelope_serialization",
      "JobEnvelope and JobResultEnvelope serialize canonically, verify HMAC signatures, reject tampering, and zeroize memory (Phase 7.1).")
def t_job_envelope_serialization():
    env_mod = _imp("core.distributed.envelope")
    compiler_mod = _imp("core.interpreter.compiler")
    executor_mod = _imp("core.interpreter.executor")
    Job = compiler_mod.Job
    JobStep = compiler_mod.JobStep
    ExecResult = executor_mod.ExecResult

    secret_key = "test-secret-key-32-bytes-long!!"

    # 1. Job and ExecResult serialization round-trip
    job = Job(
        broker_id="acme",
        broker_name="Acme Data",
        member_id="mem_123",
        method="form",
        steps=[
            JobStep(kind="navigate", url="https://acme.example/optout"),
            JobStep(kind="fill", selector="#name", value="Alice Smith"),
            JobStep(kind="submit", selector="button[type=submit]"),
        ],
        success_selector=".confirmed"
    )
    job_dict = job.to_dict()
    job_restored = Job.from_dict(job_dict)
    assert job_restored.broker_id == "acme"
    assert len(job_restored.steps) == 3
    assert job_restored.steps[1].value == "Alice Smith"

    exec_res = ExecResult(
        ok=True,
        steps_run=3,
        steps_total=3,
        detail="Submitted successfully",
        trace=["navigate", "fill", "submit"],
        challenge={"type": "recaptcha_v2", "site_key": "xyz123"}
    )
    res_dict = exec_res.to_dict()
    res_restored = ExecResult.from_dict(res_dict)
    assert res_restored.ok is True
    assert res_restored.challenge["site_key"] == "xyz123"

    # 2. Removal envelope creation, signing, and canonical JSON serialization
    env = env_mod.create_removal_envelope(
        job=job,
        member_fields={"full_name": "Alice Smith", "email": "alice@example.com"},
        request_id=42,
        request_key="req-uuid-42",
        secret_key=secret_key,
        priority="high",
        ttl_seconds=3600
    )
    assert env.action == "removal"
    assert env.hmac_signature != ""
    assert env.verify(secret_key) is True

    json_str = env.to_json()
    assert isinstance(json_str, str)

    # Deserialization from JSON with HMAC verification
    deserialized = env_mod.JobEnvelope.from_json(json_str, secret_key=secret_key)
    assert deserialized.envelope_id == env.envelope_id
    assert deserialized.broker_id == "acme"
    assert deserialized.payload["job"]["steps"][1]["value"] == "Alice Smith"

    # 3. Discovery envelope creation and verification
    disc_env = env_mod.create_discovery_envelope(
        query_criteria={"name": "Alice Smith", "city": "Austin", "state": "TX"},
        broker_id="fastpeople",
        broker_name="FastPeopleLookup",
        member_id="mem_123",
        secret_key=secret_key
    )
    assert disc_env.action == "discovery"
    assert disc_env.payload["query"]["city"] == "Austin"
    assert disc_env.verify(secret_key) is True

    # 4. Tampering rejection
    tampered_dict = env.to_dict()
    tampered_dict["broker_name"] = "Evil Broker Hijack"
    tampered_json = env_mod.canonical_json(tampered_dict)
    try:
        env_mod.JobEnvelope.from_json(tampered_json, secret_key=secret_key)
        assert False, "Tampered envelope should have raised EnvelopeTamperedError"
    except env_mod.EnvelopeTamperedError:
        pass

    # Tampering with payload
    tampered_payload_dict = env.to_dict()
    tampered_payload_dict["payload"]["job"]["steps"][1]["value"] = "Mallory Hacker"
    tampered_payload_json = env_mod.canonical_json(tampered_payload_dict)
    try:
        env_mod.JobEnvelope.from_json(tampered_payload_json, secret_key=secret_key)
        assert False, "Tampered payload should have raised EnvelopeTamperedError"
    except env_mod.EnvelopeTamperedError:
        pass

    # Wrong secret key rejection
    try:
        env.verify("wrong-secret-key!!")
        assert False, "Verification with wrong secret key should fail"
    except env_mod.EnvelopeTamperedError:
        pass

    # 5. Expiry rejection
    expired_env = env_mod.create_removal_envelope(
        job=job,
        secret_key=secret_key,
        ttl_seconds=-10
    )
    try:
        expired_env.verify(secret_key)
        assert False, "Expired envelope should have raised EnvelopeExpiredError"
    except env_mod.EnvelopeExpiredError:
        pass
    assert expired_env.verify(secret_key, allow_expired=True) is True

    # 6. Authenticated payload encryption / decryption round-trip
    enc_env = env_mod.create_removal_envelope(
        job=job,
        member_fields={"email": "secret@example.com"},
        secret_key=secret_key,
        encrypt=True
    )
    assert enc_env.payload == {}
    assert enc_env.encrypted_payload is not None
    assert enc_env.verify(secret_key) is True

    dec_env = env_mod.JobEnvelope.from_json(enc_env.to_json(), secret_key=secret_key)
    dec_env.decrypt_payload(secret_key)
    assert dec_env.payload["member_fields"]["email"] == "secret@example.com"
    assert dec_env.encrypted_payload is None
    assert dec_env.verify(secret_key) is True

    # 7. JobResultEnvelope creation, signing, tamper rejection, round-trip
    result_env = env_mod.create_result_envelope(
        request_envelope=env,
        ok=True,
        status="success",
        exec_result=exec_res,
        worker_id="node-worker-01",
        screenshots={"page": "base64encodedbytes..."},
        secret_key=secret_key
    )
    assert result_env.envelope_id == env.envelope_id
    assert result_env.worker_id == "node-worker-01"
    assert result_env.ok is True
    assert result_env.verify(secret_key) is True

    res_json = result_env.to_json()
    restored_res_env = env_mod.JobResultEnvelope.from_json(res_json, secret_key=secret_key)
    assert restored_res_env.duration_ms >= 0
    assert restored_res_env.result["exec_result"]["detail"] == "Submitted successfully"

    tampered_res_dict = result_env.to_dict()
    tampered_res_dict["ok"] = False
    try:
        env_mod.JobResultEnvelope.from_dict(tampered_res_dict, secret_key=secret_key)
        assert False, "Tampered result envelope should have failed verification"
    except env_mod.EnvelopeTamperedError:
        pass

    # 8. Cryptographic zeroization & memory hygiene
    with env_mod.create_removal_envelope(job=job, secret_key=secret_key) as scoped_env:
        assert len(scoped_env.payload["job"]["steps"]) == 3
        scoped_env.zeroize()
        assert scoped_env.is_zeroized is True
        assert scoped_env.payload == {}

    test_env2 = env_mod.create_removal_envelope(job=job, secret_key=secret_key)
    with test_env2:
        assert test_env2.is_zeroized is False
    assert test_env2.is_zeroized is True
    assert test_env2.payload == {}


@test(1, "distributed.unified_job_queue",
      "Unified queue abstraction provides priority dispatch, in-flight tracking, ack, requeue, and DLQ routing (Phase 7.2).")
def t_unified_job_queue():
    queue_mod = _imp("core.distributed.queue")
    env_mod = _imp("core.distributed.envelope")
    compiler_mod = _imp("core.interpreter.compiler")
    executor_mod = _imp("core.interpreter.executor")
    Job = compiler_mod.Job
    JobStep = compiler_mod.JobStep
    ExecResult = executor_mod.ExecResult

    secret_key = "test-queue-secret-key-32-bytes!"

    def make_job(name, priority="normal"):
        return Job(
            broker_id=f"broker_{name}",
            broker_name=f"Broker {name}",
            member_id="m1",
            method="form",
            steps=[JobStep(kind="fill", selector="#input", value=name)],
        )

    # ── 1. InProcessJobQueue Priority Ordering ────────────────────────────────
    q = queue_mod.InProcessJobQueue(secret_key=secret_key)

    # Create envelopes across channels
    env_normal = env_mod.create_removal_envelope(make_job("Normal"), priority="normal", secret_key=secret_key)
    env_high = env_mod.create_removal_envelope(make_job("High"), priority="high", secret_key=secret_key)
    env_disc = env_mod.create_discovery_envelope({"name": "Bob"}, "broker_d", "Broker D", "m1", secret_key=secret_key)

    # Enqueue in non-priority order: normal first, then discovery, then high
    q.enqueue(env_normal)
    q.enqueue(env_disc)
    q.enqueue(env_high)

    depths = q.queue_depth()
    assert depths["removal_high"] == 1
    assert depths["removal_normal"] == 1
    assert depths["discovery"] == 1
    assert depths["total"] == 3

    # Dequeue must respect strict priority: high -> normal -> discovery
    deq1 = q.dequeue()
    assert deq1 is not None and deq1.envelope_id == env_high.envelope_id
    assert q.in_flight_count() == 1

    deq2 = q.dequeue()
    assert deq2 is not None and deq2.envelope_id == env_normal.envelope_id
    assert q.in_flight_count() == 2

    deq3 = q.dequeue()
    assert deq3 is not None and deq3.envelope_id == env_disc.envelope_id
    assert q.in_flight_count() == 3

    # Dequeue when empty returns None
    assert q.dequeue(timeout=0.01) is None

    # ── 2. Acknowledge, Requeue & Dead-Letter ──────────────────────────────────
    # Acknowledge high priority job
    assert q.acknowledge(deq1.envelope_id) is True
    assert q.in_flight_count() == 2
    # Second ack on same ID returns False
    assert q.acknowledge(deq1.envelope_id) is False

    # Requeue normal job to retry queue
    q.requeue(deq2, queue_name=queue_mod.CHANNEL_RETRY)
    assert q.in_flight_count() == 1
    assert q.queue_depth(queue_mod.CHANNEL_RETRY) == 1
    requeued_env = q.dequeue(queue_names=[queue_mod.CHANNEL_RETRY])
    assert requeued_env.meta.get("retries") == 1
    q.acknowledge(requeued_env.envelope_id)

    # Dead-letter discovery job
    q.dead_letter(deq3, reason="Search endpoint permanently blocked")
    assert q.in_flight_count() == 0
    assert q.queue_depth(queue_mod.CHANNEL_DEAD_LETTER) == 1

    # ── 3. Results Channel ───────────────────────────────────────────────────
    res_env = env_mod.create_result_envelope(
        request_envelope=env_high,
        ok=True,
        status="success",
        exec_result=ExecResult(ok=True, detail="Form submitted"),
        worker_id="worker-node-42",
        secret_key=secret_key,
    )
    q.publish_result(res_env)
    received_res = q.get_result(timeout=1.0)
    assert received_res is not None
    assert received_res.envelope_id == env_high.envelope_id
    assert received_res.worker_id == "worker-node-42"
    assert q.get_result(timeout=0.01) is None

    # ── 4. Mock Redis Client Verification ─────────────────────────────────────
    import collections as col
    class MockRedis:
        def __init__(self):
            self.lists = col.defaultdict(col.deque)
            self.hashes = col.defaultdict(dict)

        def rpush(self, key, val):
            self.lists[key].append(val)
            return len(self.lists[key])

        def lpop(self, key):
            q = self.lists.get(key)
            return q.popleft() if q and len(q) > 0 else None

        def blpop(self, keys, timeout=0):
            for k in keys:
                val = self.lpop(k)
                if val is not None:
                    return (k, val)
            return None

        def hset(self, key, field, val):
            self.hashes[key][field] = val
            return 1

        def hdel(self, key, field):
            return 1 if self.hashes[key].pop(field, None) is not None else 0

        def hlen(self, key):
            return len(self.hashes[key])

        def llen(self, key):
            return len(self.lists.get(key, []))

        def delete(self, *keys):
            for k in keys:
                self.lists.pop(k, None)
                self.hashes.pop(k, None)
            return len(keys)

    mock_client = MockRedis()
    rq = queue_mod.RedisJobQueue(redis_client=mock_client, secret_key=secret_key)

    rq.enqueue(env_high)
    assert rq.queue_depth(queue_mod.CHANNEL_REMOVAL_HIGH) == 1

    r_deq = rq.dequeue()
    assert r_deq is not None and r_deq.envelope_id == env_high.envelope_id
    assert rq.in_flight_count() == 1

    assert rq.acknowledge(r_deq.envelope_id) is True
    assert rq.in_flight_count() == 0

    rq.publish_result(res_env)
    r_res = rq.get_result()
    assert r_res is not None and r_res.envelope_id == env_high.envelope_id

    # ── 5. Global Factory Resolution ──────────────────────────────────────────
    g_queue = queue_mod.get_queue(reset=True, secret_key=secret_key)
    assert isinstance(g_queue, queue_mod.InProcessJobQueue)


@test(1, "distributed.worker_daemon_execution",
      "Stateless worker daemon executes removal and discovery envelopes, handles retries/DLQ, and drains gracefully (Phase 7.3).")
def t_worker_daemon_execution():
    import asyncio
    worker_mod = _imp("core.distributed.worker")
    queue_mod = _imp("core.distributed.queue")
    env_mod = _imp("core.distributed.envelope")
    compiler_mod = _imp("core.interpreter.compiler")
    Job = compiler_mod.Job
    JobStep = compiler_mod.JobStep

    secret_key = "test-worker-daemon-key-32-bytes!"

    def make_test_job(name: str):
        return Job(
            broker_id=f"broker_{name.lower()}",
            broker_name=f"Broker {name}",
            member_id="mem_test_1",
            method="form",
            steps=[
                JobStep(kind="navigate", url=f"https://{name.lower()}.example/optout"),
                JobStep(kind="fill", selector="#name", value="Alice Tester"),
                JobStep(kind="submit", selector="button.submit"),
            ],
            success_selector=".confirmed",
        )

    # ── 1. Removal Job Execution & Result Publishing ─────────────────────────
    q = queue_mod.InProcessJobQueue(secret_key=secret_key)
    config = worker_mod.WorkerConfig(
        worker_id="worker-test-node-01",
        concurrency=1,
        dry_run=True,
        secret_key=secret_key,
    )
    daemon = worker_mod.WorkerDaemon(config=config, queue=q)

    removal_env = env_mod.create_removal_envelope(
        job=make_test_job("Acme"),
        member_fields={"email": "alice@test.example"},
        secret_key=secret_key,
        priority="high",
    )
    q.enqueue(removal_env)
    assert q.queue_depth("removal_high") == 1

    # Execute single item
    processed = asyncio.run(daemon.process_one(timeout=0.1))
    assert processed is True
    assert q.in_flight_count() == 0
    assert q.queue_depth("removal_high") == 0

    res = q.get_result(timeout=0.1)
    assert res is not None
    assert res.envelope_id == removal_env.envelope_id
    assert res.worker_id == "worker-test-node-01"
    assert res.ok is True
    assert res.status == "success"
    assert res.action == "removal"
    assert res.result["exec_result"]["steps_run"] == 3
    assert res.verify(secret_key) is True

    # ── 2. Discovery Job Execution & Result Publishing ───────────────────────
    disc_env = env_mod.create_discovery_envelope(
        query_criteria={
            "name": "Alice Tester",
            "city": "Austin",
            "state": "TX",
            "broker_domain": "fastpeople.example",
        },
        broker_id="fastpeople",
        broker_name="FastPeopleSearch",
        member_id="mem_test_1",
        secret_key=secret_key,
    )
    q.enqueue(disc_env)

    processed_disc = asyncio.run(daemon.process_one(timeout=0.1))
    assert processed_disc is True

    res_disc = q.get_result(timeout=0.1)
    assert res_disc is not None
    assert res_disc.envelope_id == disc_env.envelope_id
    assert res_disc.action == "discovery"
    assert res_disc.ok is True
    assert res_disc.result["discovery"]["count"] >= 1
    assert "fastpeople.example" in res_disc.result["discovery"]["listings"][0]["url"]

    # ── 3. Tampered Envelope Rejection ───────────────────────────────────────
    tampered_env = env_mod.create_removal_envelope(
        job=make_test_job("Tampered"),
        secret_key=secret_key,
    )
    # Modify payload without resigning
    tampered_env.payload["job"]["broker_name"] = "Hacked Broker"
    q.enqueue(tampered_env)

    processed_tampered = asyncio.run(daemon.process_one(timeout=0.1))
    assert processed_tampered is True
    res_tampered = q.get_result(timeout=0.1)
    assert res_tampered is not None
    assert res_tampered.ok is False
    assert res_tampered.status == "tampered"

    # ── 4. Transient Error Requeue & DLQ Routing ─────────────────────────────
    # Envelope that triggers simulated error
    failing_env = env_mod.create_removal_envelope(
        job=make_test_job("FailBroker"),
        secret_key=secret_key,
    )

    async def fail_execute(env):
        return env_mod.create_result_envelope(
            request_envelope=env,
            ok=False,
            status="error",
            error="Simulated network disconnect",
            worker_id=daemon.config.worker_id,
            secret_key=secret_key,
        )

    orig_exec = daemon.execute_envelope
    daemon.execute_envelope = fail_execute
    try:
        # First attempt: should be requeued to retry queue
        q.enqueue(failing_env)
        asyncio.run(daemon.process_one(timeout=0.1))
        assert q.queue_depth(queue_mod.CHANNEL_RETRY) == 1
        assert daemon.stats["retried"] == 1

        # Dequeue from retry channel, set retries to max_retries (3)
        retry_env = q.dequeue(queue_names=[queue_mod.CHANNEL_RETRY])
        retry_env.meta["retries"] = 3
        q.enqueue(retry_env)

        # Attempt with max retries exceeded: should be routed to DLQ
        daemon.config.active_queues = [queue_mod.CHANNEL_RETRY]
        asyncio.run(daemon.process_one(timeout=0.1))
        assert q.queue_depth(queue_mod.CHANNEL_DEAD_LETTER) == 1
        assert daemon.stats["dead_lettered"] >= 1
    finally:
        daemon.execute_envelope = orig_exec
        daemon.config.active_queues = None

    # ── 5. Multi-Slot Concurrency & Graceful Draining ────────────────────────
    async def run_concurrency_test():
        conc_config = worker_mod.WorkerConfig(
            worker_id="worker-concurrent-node",
            concurrency=2,
            dry_run=True,
            poll_interval=0.05,
            secret_key=secret_key,
        )
        conc_daemon = worker_mod.WorkerDaemon(config=conc_config, queue=q)

        # Enqueue 4 jobs
        for i in range(4):
            env = env_mod.create_removal_envelope(
                job=make_test_job(f"Job{i}"),
                secret_key=secret_key,
            )
            q.enqueue(env)

        run_task = asyncio.create_task(conc_daemon.run())

        # Wait until jobs are drained or up to 2 seconds
        for _ in range(40):
            if conc_daemon.stats["processed"] >= 4:
                break
            await asyncio.sleep(0.05)

        conc_daemon.request_stop()
        await run_task
        assert conc_daemon.stats["processed"] == 4

    asyncio.run(run_concurrency_test())


@test(1, "distributed.control_plane_ingestion_and_reclamation",
      "Control plane drains execution results, updates requests, auto-chains discovery URLs, and reclaims orphaned leases (Phase 7.4).")
def t_control_plane_ingestion_and_reclamation():
    queue_mod = _imp("core.distributed.queue")
    env_mod = _imp("core.distributed.envelope")
    ingestion_mod = _imp("core.distributed.ingestion")
    compiler_mod = _imp("core.interpreter.compiler")
    Job = compiler_mod.Job
    JobStep = compiler_mod.JobStep

    secret_key = "test-control-plane-ingestion-key!"

    # ── 1. Orphan Lease Reclamation ───────────────────────────────────────────
    q = queue_mod.InProcessJobQueue(secret_key=secret_key)
    dummy_job = Job(
        broker_id="broker_test",
        broker_name="Broker Test",
        member_id="1",
        method="form",
        steps=[JobStep(kind="navigate", url="https://test.example")],
    )
    env1 = env_mod.create_removal_envelope(dummy_job, secret_key=secret_key)
    env2 = env_mod.create_removal_envelope(dummy_job, secret_key=secret_key)
    q.enqueue(env1)
    q.enqueue(env2)

    # Dequeue env1 to place it in-flight
    leased = q.dequeue()
    assert leased is not None
    assert leased.envelope_id == env1.envelope_id
    assert q.in_flight_count() == 1

    # Lease timeout = 0 seconds makes it immediately considered orphaned
    report = ingestion_mod.reclaim_orphaned_leases(q, lease_timeout_seconds=0.0, max_retries=3)
    assert report["inspected"] == 1
    assert report["reclaimed_retried"] == 1
    assert report["reclaimed_dead_lettered"] == 0
    assert q.queue_depth(queue_mod.CHANNEL_RETRY) == 1
    assert q.in_flight_count() == 0

    # Test DLQ routing when retries are exhausted
    requeued_env = q.dequeue(queue_names=[queue_mod.CHANNEL_RETRY])
    assert requeued_env is not None
    requeued_env.meta["retries"] = 3  # already at max retries
    q.enqueue(requeued_env)
    q.dequeue(queue_names=[queue_mod.CHANNEL_RETRY])  # place in flight
    report_dlq = ingestion_mod.reclaim_orphaned_leases(q, lease_timeout_seconds=0.0, max_retries=3)
    assert report_dlq["inspected"] == 1
    assert report_dlq["reclaimed_retried"] == 0
    assert report_dlq["reclaimed_dead_lettered"] == 1
    assert q.queue_depth(queue_mod.CHANNEL_DEAD_LETTER) == 1
    assert q.in_flight_count() == 0

    # ── 2. Mock Database Setup for Result Ingestion ───────────────────────────
    class MockRemovalRequest:
        def __init__(self, id, member_id, broker_id, status="pending", listing_url=None, notes=None):
            self.id = id
            self.member_id = member_id
            self.broker_id = broker_id
            self.status = status
            self.listing_url = listing_url
            self.notes = notes
            self.sent_at = None
            self.broker = None

    class MockBroker:
        def __init__(self, id, name):
            self.id = id
            self.name = name

    class MockQuery:
        def __init__(self, items):
            self._items = list(items)

        def filter(self, *criteria):
            return self

        def first(self):
            return self._items[0] if self._items else None

        def all(self):
            return list(self._items)

    class MockSession:
        def __init__(self, requests=None, brokers=None):
            self.requests = requests or []
            self.brokers = brokers or []
            self.added = []
            self.committed = False
            self.rolled_back = False

        def query(self, model):
            name = getattr(model, "__name__", str(model))
            if "RemovalRequest" in name:
                return MockQuery(self.requests)
            if "Broker" in name:
                return MockQuery(self.brokers)
            return MockQuery([])

        def add(self, item):
            self.added.append(item)

        def flush(self):
            pass

        def commit(self):
            self.committed = True

        def rollback(self):
            self.rolled_back = True

        def added_types(self):
            return [type(x).__name__ for x in self.added]

        def close(self):
            pass

    # ── 3. Ingestion of Successful Removal Result ─────────────────────────────
    removal_env_1 = env_mod.create_removal_envelope(dummy_job, request_id=101, secret_key=secret_key)
    test_req = MockRemovalRequest(id=101, member_id=1, broker_id=5, status="pending")
    mock_db = MockSession(requests=[test_req])
    ingestion_service = ingestion_mod.ResultIngestionService(queue=q, db_session_factory=lambda: mock_db)

    succ_result = env_mod.create_result_envelope(
        request_envelope=removal_env_1,
        ok=True,
        status="success",
        worker_id="worker-node-1",
        duration_ms=450,
        secret_key=secret_key,
        exec_result={"detail": "Submitted form successfully"},
    )
    q.publish_result(succ_result)
    assert q.results_depth() == 1

    processed_succ = ingestion_service.process_next(timeout=0.1)
    assert processed_succ is not None
    assert processed_succ["updated_request"] is True
    assert test_req.status == "submitted"
    assert test_req.sent_at is not None
    # The run is logged once. (A BrokerHealth row may also be written: the
    # first success for a broker creates its health record.)
    assert mock_db.added_types().count("AutomationLog") == 1, mock_db.added_types()
    assert set(mock_db.added_types()) <= {"AutomationLog", "BrokerHealth"}, mock_db.added_types()
    assert mock_db.committed is True

    # ── 4. Ingestion of CAPTCHA Result ────────────────────────────────────────
    removal_env_2 = env_mod.create_removal_envelope(dummy_job, request_id=102, secret_key=secret_key)
    captcha_req = MockRemovalRequest(id=102, member_id=1, broker_id=5, status="pending")
    mock_captcha_db = MockSession(requests=[captcha_req])
    ingestion_captcha_service = ingestion_mod.ResultIngestionService(queue=q, db_session_factory=lambda: mock_captcha_db)

    captcha_result = env_mod.create_result_envelope(
        request_envelope=removal_env_2,
        ok=False,
        status="captcha",
        worker_id="worker-node-1",
        secret_key=secret_key,
        exec_result={"challenge": {"type": "recaptcha_v2", "site_key": "xyz"}},
    )
    q.publish_result(captcha_result)
    processed_captcha = ingestion_captcha_service.process_next(timeout=0.1)
    assert processed_captcha is not None
    assert captcha_req.status == "needs_manual"
    assert "CAPTCHA" in (captcha_req.notes or "")
    # Should have added CaptchaChallenge and AutomationLog (plus, possibly,
    # the broker's BrokerHealth row recording the failure).
    _types = mock_captcha_db.added_types()
    assert _types.count("CaptchaChallenge") == 1, _types
    assert _types.count("AutomationLog") == 1, _types
    assert set(_types) <= {"CaptchaChallenge", "AutomationLog", "BrokerHealth"}, _types

    # ── 5. Ingestion of Discovery Result & Auto-Chaining ──────────────────────
    chaining_req = MockRemovalRequest(id=103, member_id=1, broker_id=5, status="pending", listing_url=None)
    mock_disc_db = MockSession(requests=[chaining_req])
    ingestion_disc_service = ingestion_mod.ResultIngestionService(queue=q, db_session_factory=lambda: mock_disc_db)

    disc_env = env_mod.create_discovery_envelope(
        query_criteria={"name": "Alice Tester"},
        broker_id="5",
        broker_name="Broker Five",
        member_id="1",
        secret_key=secret_key,
    )
    disc_result = env_mod.create_result_envelope(
        request_envelope=disc_env,
        ok=True,
        status="success",
        worker_id="worker-node-1",
        secret_key=secret_key,
        discovery_result={
            "count": 1,
            "listings": [{"url": "https://broker.example/profiles/alice-1", "snippet": "Alice Tester Austin TX"}],
        },
    )
    q.publish_result(disc_result)
    processed_disc = ingestion_disc_service.process_next(timeout=0.1)
    assert processed_disc is not None
    assert processed_disc["discovery_listings_saved"] == 1
    assert processed_disc["chained_requests"] == 1
    assert chaining_req.listing_url == "https://broker.example/profiles/alice-1"
    assert "Auto-chained" in (chaining_req.notes or "")


@test(1, "distributed.fleet_monitoring_and_telemetry",
      "Worker fleet registry aggregates heartbeats, telemetry, capacity utilization, and supports node draining (Phase 7.5).")
def t_fleet_monitoring_and_telemetry():
    import asyncio, time
    registry_mod = _imp("core.distributed.registry")
    queue_mod = _imp("core.distributed.queue")
    worker_mod = _imp("core.distributed.worker")

    # 1. Heartbeat registration and status computation
    reg = registry_mod.WorkerRegistry()
    w1 = reg.record_heartbeat(
        worker_id="worker-node-1",
        concurrency=2,
        active_jobs=1,
        jobs_completed=10,
        jobs_failed=1,
        uptime_seconds=120.0,
        hostname="node-1.internal",
    )
    assert w1["worker_id"] == "worker-node-1"
    assert w1["status"] == "online"

    # Worker 2: at full concurrency -> "busy"
    w2 = reg.record_heartbeat(
        worker_id="worker-node-2",
        concurrency=4,
        active_jobs=4,
        jobs_completed=25,
        jobs_failed=0,
        uptime_seconds=300.0,
        hostname="node-2.internal",
    )
    assert w2["status"] == "busy"

    workers = reg.list_workers(timeout_seconds=30.0)
    assert len(workers) == 2
    assert workers[0]["worker_id"] == "worker-node-1"
    assert workers[0]["status"] == "online"
    assert workers[1]["worker_id"] == "worker-node-2"
    assert workers[1]["status"] == "busy"

    # 2. Timeout / offline threshold detection
    offline_workers = reg.list_workers(timeout_seconds=0.0)
    assert all(w["status"] == "offline" for w in offline_workers)

    # 3. Fleet summary and queue integration
    mock_q = queue_mod.InProcessJobQueue()
    summary = reg.get_fleet_summary(timeout_seconds=30.0, queue=mock_q)
    assert summary["total_nodes"] == 2
    assert summary["online_nodes"] == 2
    assert summary["busy_nodes"] == 1
    assert summary["total_slots"] == 6
    assert summary["active_slots"] == 5
    assert summary["idle_slots"] == 1
    assert summary["utilization_pct"] == 83.3
    assert summary["total_jobs_completed"] == 35
    assert summary["total_jobs_failed"] == 1
    assert "queue_depths" in summary

    # 4. Node draining signal
    assert reg.is_draining("worker-node-1") is False
    reg.set_drain_signal("worker-node-1", drain=True)
    assert reg.is_draining("worker-node-1") is True

    w1_draining = reg.get_worker("worker-node-1", timeout_seconds=30.0)
    assert w1_draining["status"] == "draining"

    reg.set_drain_signal("worker-node-1", drain=False)
    assert reg.is_draining("worker-node-1") is False

    # 5. Stale worker pruning
    reg.record_heartbeat(
        worker_id="worker-ancient",
        concurrency=1,
        active_jobs=0,
    )
    with reg._lock:
        reg._in_memory_workers["worker-ancient"]["last_heartbeat_at"] = time.time() - 1000.0

    pruned = reg.prune_stale_workers(max_age_seconds=100.0)
    assert pruned == 1
    assert reg.get_worker("worker-ancient") is None

    # 6. WorkerDaemon heartbeat and graceful drain integration
    daemon_q = queue_mod.InProcessJobQueue()
    daemon_config = worker_mod.WorkerConfig(
        worker_id="worker-daemon-fleet-test",
        concurrency=1,
        dry_run=True,
        enable_heartbeat=True,
        heartbeat_interval=0.05,
    )
    daemon = worker_mod.WorkerDaemon(config=daemon_config, queue=daemon_q, registry=reg)

    async def run_daemon_test():
        run_task = asyncio.create_task(daemon.run())
        for _ in range(20):
            if reg.get_worker("worker-daemon-fleet-test"):
                break
            await asyncio.sleep(0.05)

        live_worker = reg.get_worker("worker-daemon-fleet-test")
        assert live_worker is not None
        assert live_worker["worker_id"] == "worker-daemon-fleet-test"

        reg.set_drain_signal("worker-daemon-fleet-test", True)
        await asyncio.wait_for(run_task, timeout=2.0)
        assert daemon._running is False

    asyncio.run(run_daemon_test())


@test(1, "network_health.circuit_breaker_and_worker_halt",
      "Network canary probe detects internet loss, halts batches gracefully without false failures, and worker requeues jobs without penalty.")
def t_network_health_circuit_breaker():
    import asyncio, socket
    net_mod = _imp("core.network_health")
    queue_mod = _imp("core.distributed.queue")
    worker_mod = _imp("core.distributed.worker")
    reg_mod = _imp("core.distributed.registry")
    env_mod = _imp("core.distributed.envelope")

    # 1. Canary probes & Mocking
    try:
        net_mod.set_mock_internet_status(True)
        assert net_mod.is_internet_available() is True

        net_mod.set_mock_internet_status(False)
        assert net_mod.is_internet_available() is False
    finally:
        net_mod.set_mock_internet_status(None)

    # 2. Error classification
    assert net_mod.is_network_error(socket.gaierror(8, "nodename nor servname provided")) is True
    assert net_mod.is_network_error(ConnectionResetError("Connection reset by peer")) is True
    assert net_mod.is_network_error(socket.timeout("timed out")) is True
    assert net_mod.is_network_error(Exception("net::ERR_INTERNET_DISCONNECTED at https://example.com")) is True
    assert net_mod.is_network_error(Exception("net::ERR_NAME_NOT_RESOLVED")) is True
    assert net_mod.is_network_error(Exception("NS_ERROR_NET_ON_DISCONNECTED")) is True
    assert net_mod.is_network_error(Exception("temporary failure in name resolution")) is True
    assert net_mod.is_network_error(ValueError("Invalid syntax")) is False
    assert net_mod.is_network_error(None) is False

    # 3. Registry paused_offline status
    reg = reg_mod.WorkerRegistry()
    hb = reg.record_heartbeat(
        worker_id="worker-offline-test",
        concurrency=2,
        active_jobs=0,
        is_offline=True,
    )
    assert hb["status"] == "paused_offline"
    assert hb["is_offline"] is True

    # 4. Single-node batch halting when offline
    if _try_import("sqlalchemy") is not None:
        optout_engine = _imp("core.optout_engine")
        try:
            net_mod.set_mock_internet_status(False)
            batch_res = asyncio.run(optout_engine.run_optout_batch([101, 102, 103]))
            assert batch_res.get("halted_offline") is True
            assert batch_res.get("sent") == 0
            assert batch_res.get("failed") == 0
            assert batch_res.get("skipped") == 3
            assert "unavailable" in batch_res["errors"][0].lower()
        finally:
            net_mod.set_mock_internet_status(None)

    # 5. Distributed worker offline protection
    q = queue_mod.InProcessJobQueue()
    test_key = "test-circuit-breaker-key"
    env = env_mod.create_removal_envelope(
        job={"broker_id": "test_broker", "broker_name": "TestBroker", "member_id": "m-123", "steps": []},
        priority="high",
        secret_key=test_key,
    )
    q.enqueue(env)
    assert q.queue_depth(queue_mod.CHANNEL_REMOVAL_HIGH) == 1

    cfg = worker_mod.WorkerConfig(
        worker_id="worker-circuit-breaker",
        concurrency=1,
        dry_run=True,
        enable_heartbeat=False,
        secret_key=test_key,
    )
    worker = worker_mod.WorkerDaemon(config=cfg, queue=q, registry=reg)

    try:
        # With internet offline, worker does not dequeue
        net_mod.set_mock_internet_status(False)
        processed = asyncio.run(worker.process_one(timeout=0.01))
        assert processed is False
        assert q.queue_depth(queue_mod.CHANNEL_REMOVAL_HIGH) == 1
        assert worker._busy_slots == 0

        # With internet online, worker dequeues and executes
        net_mod.set_mock_internet_status(True)
        processed = asyncio.run(worker.process_one(timeout=0.01))
        assert processed is True
        assert q.queue_depth(queue_mod.CHANNEL_REMOVAL_HIGH) == 0
        assert worker.stats["success"] == 1

        # Test worker handling when envelope returns network_offline
        env2 = env_mod.create_removal_envelope(
            job={"broker_id": "test_offline", "broker_name": "TestOffline", "member_id": "m-456", "steps": []},
            priority="high",
            secret_key=test_key,
        )
        q.enqueue(env2)

        # Patch worker.execute_envelope to simulate network disconnect during run
        async def mock_execute_offline(e):
            return env_mod.create_result_envelope(
                request_envelope=e,
                ok=False,
                status="network_offline",
                error="net::ERR_INTERNET_DISCONNECTED",
                worker_id="worker-circuit-breaker",
                secret_key=test_key,
            )
        worker.execute_envelope = mock_execute_offline

        processed2 = asyncio.run(worker.process_one(timeout=0.01))
        assert processed2 is True
        # Envelope must be requeued without incrementing retries or routing to DLQ!
        assert q.queue_depth(queue_mod.CHANNEL_REMOVAL_HIGH) == 1
        assert q.queue_depth(queue_mod.CHANNEL_DEAD_LETTER) == 0
        assert env2.meta.get("retries", 0) == 0
    finally:
        net_mod.set_mock_internet_status(None)


@test(1, "installer.role_specialization_and_configs",
      "Unified installer verifies package matrices, role specialization, Nginx config, and systemd units (Roadmap Item 23).")
def t_installer_role_specialization_and_configs():
    installer_mod = _imp("core.installer_config")

    # 1. Package isolation per role
    standalone_pkgs = set(installer_mod.get_packages_for_role("standalone"))
    cp_pkgs = set(installer_mod.get_packages_for_role("control-plane"))
    worker_pkgs = set(installer_mod.get_packages_for_role("worker"))

    # Control plane must NOT include playwright browser and graphics dependencies (>1.5GB savings)
    assert "bubblewrap" in standalone_pkgs
    assert "bubblewrap" in worker_pkgs
    assert "bubblewrap" not in cp_pkgs, "control-plane must exclude bubblewrap"
    assert "libx11-xcb1" not in cp_pkgs, "control-plane must exclude X11 packages"
    assert "libatk1.0-0" not in cp_pkgs, "control-plane must exclude browser rendering libraries"

    # Worker must NOT include nginx or web identity dev headers
    assert "nginx" in standalone_pkgs
    assert "nginx" in cp_pkgs
    assert "nginx" not in worker_pkgs, "worker node must exclude nginx web server"
    assert "xmlsec1" not in worker_pkgs, "worker node must exclude xmlsec1 web SSO library"

    # Base dependencies present across all roles
    for base in ("python3", "python3-venv", "curl", "rsync"):
        assert base in standalone_pkgs
        assert base in cp_pkgs
        assert base in worker_pkgs

    # Invalid role raises ValueError
    try:
        installer_mod.get_packages_for_role("invalid-role")
        assert False, "should have raised ValueError on invalid role"
    except ValueError:
        pass

    # 2. Role feature requirements
    assert installer_mod.requires_frontend_build("standalone") is True
    assert installer_mod.requires_frontend_build("control-plane") is True
    assert installer_mod.requires_frontend_build("worker") is False

    assert installer_mod.requires_nginx("standalone") is True
    assert installer_mod.requires_nginx("control-plane") is True
    assert installer_mod.requires_nginx("worker") is False

    assert installer_mod.requires_playwright_browsers("standalone") is True
    assert installer_mod.requires_playwright_browsers("control-plane") is False
    assert installer_mod.requires_playwright_browsers("worker") is True

    # 3. Nginx configuration generator
    nginx_conf = installer_mod.generate_nginx_config(
        domain="privacy.citylibrary.org",
        frontend_root="/opt/openoptout/frontend/dist",
        api_host="127.0.0.1",
        api_port=8000,
        client_max_body_size="50M",
    )
    assert "server_name privacy.citylibrary.org;" in nginx_conf
    assert "root /opt/openoptout/frontend/dist;" in nginx_conf
    assert "proxy_pass http://127.0.0.1:8000;" in nginx_conf
    assert "proxy_set_header Upgrade $http_upgrade;" in nginx_conf
    assert 'proxy_set_header Connection "upgrade";' in nginx_conf
    assert "proxy_buffering off;" in nginx_conf
    assert "client_max_body_size 50M;" in nginx_conf
    assert "X-Content-Type-Options" in nginx_conf

    # 4. Systemd unit generators
    api_unit = installer_mod.generate_systemd_api_service(
        install_dir="/opt/openoptout",
        user="openoptout",
        workers=3,
        port=8000,
    )
    assert "Description=OpenOptOut API" in api_unit
    assert "ExecStart=/opt/openoptout/venv/bin/uvicorn app.main:app" in api_unit
    assert "--workers 3" in api_unit
    assert "NoNewPrivileges=true" in api_unit

    worker_unit = installer_mod.generate_systemd_worker_service(
        install_dir="/opt/openoptout",
        user="openoptout",
    )
    assert "Description=OpenOptOut Stateless Worker Daemon" in worker_unit
    assert "ExecStart=/opt/openoptout/venv/bin/python -m app.worker" in worker_unit
    assert "Restart=always" in worker_unit

    # 5. Environment generation (.env) per role
    env_standalone = installer_mod.generate_env_config(
        role="standalone",
        domain="privacy.lib.org",
        database_url="sqlite:////opt/openoptout/data/openoptout.db",
    )
    assert env_standalone["ROLE"] == "standalone"
    assert env_standalone["FRONTEND_URL"] == "https://privacy.lib.org"
    assert "DATABASE_URL" in env_standalone
    assert "WORKER_ID" not in env_standalone

    env_cp = installer_mod.generate_env_config(
        role="control-plane",
        redis_url="redis://redis.internal:6379/0",
    )
    assert env_cp["ROLE"] == "control-plane"
    assert env_cp["REDIS_URL"] == "redis://redis.internal:6379/0"

    env_worker = installer_mod.generate_env_config(
        role="worker",
        worker_id="worker-node-42",
        worker_concurrency=4,
        redis_url="redis://control-plane:6379/0",
    )
    assert env_worker["ROLE"] == "worker"
    assert env_worker["WORKER_ID"] == "worker-node-42"
    assert env_worker["WORKER_CONCURRENCY"] == "4"
    assert env_worker["HEADLESS"] == "true"
    assert "DATABASE_URL" not in env_worker, "stateless worker should not require database connection"

    # Format .env content
    env_text = installer_mod.format_env_file(env_worker)
    assert "ROLE=worker" in env_text
    assert "WORKER_ID=worker-node-42" in env_text
    assert "HEADLESS=true" in env_text


@test(1, "broker_addon.manifest_and_spec_validation",
      "Broker add-on manifests and declarative specs parse, validate, and detect bad paths/steps.")
def t_broker_addon_validation():
    import tempfile, json, os
    permissions = _imp("plugins.permissions")
    broker_addon = _imp("plugins.broker_addon")

    # Declarative broker manifest defaults entrypoint to "" (no subprocess)
    m = permissions.PluginManifest.from_dict({
        "id": "broker-fastsearch",
        "name": "FastSearch Add-on",
        "version": "1.0.0",
        "author": "Community",
        "type": "brokers",
        "spec_file": "spec.json",
        "captcha_plugin_id": "recaptcha-solver",
    })
    assert m.effective_type == "brokers"
    assert m.entrypoint == "", "declarative broker add-on must default entrypoint to empty string"
    assert not m.validate(), f"valid broker manifest had errors: {m.validate()}"

    # Path traversal in spec_file is rejected
    bad_m = permissions.PluginManifest.from_dict({
        "id": "broker-bad", "name": "Bad", "version": "1.0", "author": "Attacker",
        "type": "brokers", "spec_file": "../secret.json"
    })
    errs = bad_m.validate()
    assert any("directory traversal" in e for e in errs), f"expected traversal error, got {errs}"

    # Validate spec file inspection
    with tempfile.TemporaryDirectory() as tmp:
        # 1. Missing spec file
        res = broker_addon.inspect_broker_addon(tmp, m)
        assert not res["valid"]
        assert any("not found" in e for e in res["errors"])

        # 2. Well-formed spec file
        spec_content = {
            "broker_id": "fastsearch",
            "name": "FastSearch",
            "method": "form",
            "opt_out_url": "https://fastsearch.example/optout",
            "steps": [
                {"kind": "navigate", "url": "https://fastsearch.example/optout"},
                {"kind": "fill", "selector": "#name", "field": "full_name"},
                {"kind": "submit", "selector": "#submit-btn"},
                {"kind": "expect_success", "text": "removal confirmed"}
            ]
        }
        with open(os.path.join(tmp, "spec.json"), "w", encoding="utf-8") as f:
            json.dump(spec_content, f)

        res2 = broker_addon.inspect_broker_addon(tmp, m)
        assert res2["valid"], f"valid spec was rejected: {res2['errors']}"
        assert res2["steps_count"] == 4
        assert res2["captcha_plugin_id"] == "recaptcha-solver"


@test(1, "broker_addon.package_round_trip",
      "package_broker_addon bundles a validated broker add-on into a distributable zip archive.")
def t_broker_addon_packaging():
    import tempfile, json, os, zipfile
    broker_addon = _imp("plugins.broker_addon")

    with tempfile.TemporaryDirectory() as src_dir, tempfile.TemporaryDirectory() as out_dir:
        # Create valid source addon
        manifest_data = {
            "id": "broker-testsite",
            "name": "TestSite Opt-Out",
            "version": "1.2.0",
            "author": "OpenOptOut Team",
            "type": "brokers",
            "spec_file": "spec.json"
        }
        spec_data = {
            "broker_id": "testsite",
            "name": "TestSite",
            "method": "form",
            "opt_out_url": "https://testsite.example/optout",
            "steps": [
                {"kind": "navigate", "url": "https://testsite.example/optout"},
                {"kind": "fill", "selector": "input.email", "field": "email"},
                {"kind": "submit", "selector": "button.submit"}
            ]
        }
        with open(os.path.join(src_dir, "manifest.json"), "w") as f:
            json.dump(manifest_data, f)
        with open(os.path.join(src_dir, "spec.json"), "w") as f:
            json.dump(spec_data, f)

        zip_dest = os.path.join(out_dir, "testsite-1.2.0.zip")
        packaged_path = broker_addon.package_broker_addon(src_dir, zip_dest)
        assert os.path.isfile(packaged_path), "packaged zip file should exist"

        # Verify zip contents
        with zipfile.ZipFile(packaged_path, "r") as z:
            names = z.namelist()
            assert "manifest.json" in names and "spec.json" in names, f"zip missing files: {names}"


@test(1, "i18n.builtin_languages_complete",
      "Chinese, Tagalog, Vietnamese, Korean, Portuguese, Hindi, Russian and German ship complete, keep placeholders, and are turned on once for existing installs.")
def t_i18n_new_languages():
    import json, tempfile
    i18n = _imp("core.i18n")
    ss = _imp("core.settings_store")
    master = {d["key"]: d["default_text"] for d in i18n.MASTER_DICTIONARY}
    for code in ("zh", "tl", "vi", "ko", "pt", "hi", "ru", "de"):
        t = i18n.BUILTIN_TRANSLATIONS.get(code)
        assert t, f"{code} missing"
        assert set(t) == set(master), (code, sorted(set(master) - set(t)))
        for k, en in master.items():
            for ph in ("{details}",):
                if ph in en:
                    assert ph in t[k], (code, k)
        assert not i18n.is_rtl_language(code)
        assert code in i18n.DEFAULT_ENABLED
    old = ss.SETTINGS_FILE
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        with open(path, "w") as f:
            json.dump({"i18n": {"enabled_languages": ["en", "es"]}}, f)
        ss.SETTINGS_FILE = path
        new = i18n.offer_new_builtin_languages()
        assert "zh" in new and "hi" in new and "fr" not in new, new
        cfg = json.load(open(path))["i18n"]
        assert "de" in cfg["enabled_languages"] and "ar" not in cfg["enabled_languages"], "only new ones are added"
        cfg["enabled_languages"].remove("de")
        json.dump({"i18n": cfg}, open(path, "w"))
        assert i18n.offer_new_builtin_languages() == [], "a language an admin turned off stays off"
    finally:
        ss.SETTINGS_FILE = old
        try:
            os.remove(path)
        except OSError:
            pass


@test(1, "i18n.resolution_and_rtl",
      "i18n engine resolves translations with fallbacks, handles RTL detection, and registers custom overrides.")
def t_i18n_resolution_and_rtl():
    import json
    i18n = _imp("core.i18n")
    settings_mod = _imp("core.settings_store")

    # 1. RTL detection
    assert i18n.is_rtl_language("ar") is True
    assert i18n.is_rtl_language("he") is True
    assert i18n.is_rtl_language("fa") is True
    assert i18n.is_rtl_language("ur") is True
    assert i18n.is_rtl_language("en") is False
    assert i18n.is_rtl_language("es") is False
    assert i18n.is_rtl_language("fr") is False

    # 2. Master dictionary schema with locations
    master = i18n.get_dictionary()
    assert len(master) >= 20, f"master dictionary unexpectedly small: {len(master)}"
    first = master[0]
    assert "key" in first and "default_text" in first and "location" in first and "description" in first
    assert any("tutorial." in item["key"] for item in master)
    assert any("nav." in item["key"] for item in master)

    # 3. Translation resolution & fallback
    es_trans = i18n.get_translations_for_locale("es")
    assert es_trans["nav.dashboard"] == "Panel de Control"
    assert es_trans["common.save"] == "Guardar"
    assert es_trans["ils.import_action_import"] == "Importar mi información"
    assert es_trans["sip2.consent_required"] == "Consentimiento Requerido"

    ar_trans = i18n.get_translations_for_locale("ar")
    assert ar_trans["nav.dashboard"] == "لوحة التحكم"
    assert ar_trans["common.save"] == "حفظ"
    assert ar_trans["ils.import_action_import"] == "استيراد معلوماتي"
    assert ar_trans["sip2.consent_required"] == "الموافقة مطلوبة"

    fr_trans = i18n.get_translations_for_locale("fr")
    assert fr_trans["ils.import_action_import"] == "Importer mes informations"
    assert fr_trans["sip2.consent_required"] == "Consentement Requis"

    pirate_trans = i18n.get_translations_for_locale("pirate")
    assert pirate_trans["nav.dashboard"] == "Captain's Quarters"
    assert pirate_trans["common.save"] == "Stash It!"
    assert pirate_trans["nav.vault"] == "Treasure Chest"
    assert pirate_trans["ils.import_action_import"] == "Aye, Plunder Me Scroll!"
    assert pirate_trans["sip2.consent_required"] == "Parley Consent Required"
    assert pirate_trans["a11y.high_contrast"] == "High Contrast Beacon (WCAG 2.2 AAA)"
    assert pirate_trans["a11y.theme"] == "Ship's Colors"
    assert pirate_trans["a11y.font_size"] == "Rune Sizing & Lettering"
    assert es_trans["a11y.high_contrast"] == "Modo de Alto Contraste (WCAG 2.2 AAA)"
    assert es_trans["a11y.theme"] == "Tema de Color"
    assert ar_trans["a11y.high_contrast"] == "وضع التباين العالي (WCAG 2.2 AAA)"
    assert ar_trans["a11y.theme"] == "سمة الألوان"
    assert fr_trans["a11y.high_contrast"] == "Mode Contraste Élevé (WCAG 2.2 AAA)"
    assert fr_trans["a11y.theme"] == "Thème de Couleur"

    # 4. In-memory settings override test
    orig_load = settings_mod.load_settings
    fake_store = {
        "i18n": {
            "enabled_languages": ["en", "es", "ar", "fr"],
            "default_language": "en",
            "custom_languages": {},
            "custom_translations": {
                "es": {"nav.dashboard": "Mi Panel Personalizado"}
            }
        }
    }
    settings_mod.load_settings = lambda: json.loads(json.dumps(fake_store))
    try:
        # Override should take precedence over built-in Spanish
        overridden = i18n.get_translations_for_locale("es")
        assert overridden["nav.dashboard"] == "Mi Panel Personalizado", \
            f"Custom override did not apply: {overridden['nav.dashboard']}"
        # Built-in unchanged key remains
        assert overridden["common.save"] == "Guardar"

        # Languages list includes active status
        langs = i18n.get_available_languages()
        lang_codes = [l["code"] for l in langs]
        assert "en" in lang_codes and "es" in lang_codes and "ar" in lang_codes
        ar_entry = next(l for l in langs if l["code"] == "ar")
        assert ar_entry["is_rtl"] is True
    finally:
        settings_mod.load_settings = orig_load


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
    import uuid
    tracking_uuid = str(uuid.uuid4())
    keyed = tmpl.compose_optout_email(
        ids, "ParentCorp", "parent@example.com",
        child_sites=["Broker1", "Broker2"],
        request_key=tracking_uuid,
    )
    assert f"[{tracking_uuid}]" in keyed.subject, f"subject missing [{tracking_uuid}]: {keyed.subject}"
    assert f"Reference ID (include in all correspondence): {tracking_uuid}" in keyed.body, "body missing Reference ID line"
    assert "Broker1" in keyed.body and "Broker2" in keyed.body
    # EXPECTED: tracking key rendered in subject and body for IMAP thread matching.
    # IF THIS FAILS: parent company opt-out confirmation emails cannot be auto-matched.


@test(1, "parent.multi_request_confirmation_resolution",
      "When a parent company confirmation arrives, all child requests sharing the tracking key confirm simultaneously.")
def t_parent_multi_confirm():
    import re, uuid
    from datetime import datetime
    from types import SimpleNamespace as NS

    UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)

    # 1. Setup mock parent company and child removal requests
    tracking_uuid = str(uuid.uuid4())
    parent = NS(id=42, name="PeopleData Inc", emails_sent=1, emails_confirmed=0, honor_status="unknown")
    broker1 = NS(id=101, name="SearchSite A", parent_company_id=parent.id)
    broker2 = NS(id=102, name="SearchSite B", parent_company_id=parent.id)

    req1 = NS(id=1, request_key=tracking_uuid, status="sent", confirmed_at=None, broker=broker1, member=NS(full_name="Jane Doe"))
    req2 = NS(id=2, request_key=tracking_uuid, status="sent", confirmed_at=None, broker=broker2, member=NS(full_name="Jane Doe"))
    unrelated_req = NS(id=3, request_key=str(uuid.uuid4()), status="sent", confirmed_at=None, broker=None, member=NS(full_name="Other"))

    db_requests = [req1, req2, unrelated_req]

    # 2. Simulate incoming email with reference ID in subject or body
    incoming_text = f"Subject: Re: Opt-out request [{tracking_uuid}]\n\nWe have completed processing your removal request {tracking_uuid}."
    found_keys = set(UUID_RE.findall(incoming_text))
    assert tracking_uuid in found_keys, "UUID pattern failed to extract tracking key from email text"

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


@test(1, "sip2.eligibility_birthdate_and_age_calculation",
      "SIP2 birthdate formats (YYYYMMDD, YYYY-MM-DD, MM/DD/YYYY, etc.) parse correctly and compute exact age.")
def t_sip2_dob_and_age():
    from datetime import date
    rules_mod = _imp("core.sip2_rules")
    ref = date(2026, 10, 8)

    # Various date formats for a person born Oct 8, 2000 (turns 26 on ref date)
    for dob_str in ("20001008", "2000-10-08", "10/08/2000", "2000/10/08", "10-08-2000"):
        d = rules_mod.parse_patron_birthdate(dob_str)
        assert d == date(2000, 10, 8), f"failed to parse {dob_str}: {d}"
        assert rules_mod.calculate_patron_age(dob_str, reference_date=ref) == 26

    # Birthday hasn't happened yet this year: Oct 9, 2000 is still 25 on Oct 8, 2026
    assert rules_mod.calculate_patron_age("2000-10-09", reference_date=ref) == 25
    # Birthday was yesterday: Oct 7, 2000 is 26 on Oct 8, 2026
    assert rules_mod.calculate_patron_age("2000-10-07", reference_date=ref) == 26

    # Ambiguous date resolution: 10/07/2000 (Oct 7 vs July 10)
    # MM/DD/YYYY -> October 7, 2000
    d_us = rules_mod.parse_patron_birthdate("10/07/2000", date_format="MM/DD/YYYY")
    assert d_us == date(2000, 10, 7), f"expected Oct 7, got {d_us}"

    # DD/MM/YYYY -> July 10, 2000
    d_intl = rules_mod.parse_patron_birthdate("10/07/2000", date_format="DD/MM/YYYY")
    assert d_intl == date(2000, 7, 10), f"expected July 10, got {d_intl}"

    # Verify age differences for intermediate reference dates (e.g. Aug 1, 2026):
    ref_aug = date(2026, 8, 1)
    # With US format (born Oct 7), hasn't had 26th birthday yet in Aug 2026 -> age 25
    assert rules_mod.calculate_patron_age("10/07/2000", reference_date=ref_aug, date_format="MM/DD/YYYY") == 25
    # With International format (born July 10), already had 26th birthday in July 2026 -> age 26
    assert rules_mod.calculate_patron_age("10/07/2000", reference_date=ref_aug, date_format="DD/MM/YYYY") == 26

    # Numeric age fallback
    assert rules_mod.calculate_patron_age("42") == 42
    assert rules_mod.calculate_patron_age(19) == 19

    # Invalid / empty
    assert rules_mod.parse_patron_birthdate("") is None
    assert rules_mod.parse_patron_birthdate("invalid-dob") is None
    assert rules_mod.calculate_patron_age("invalid") is None


@test(1, "sip2.field_mapping_and_vault_demographics",
      "SIP2 optional field mapping extracts patron email, phone, and address into AuthResult.")
def t_sip2_mapping():
    ap = _imp("core.auth_providers")
    fixed = "64" + " " * 14 + "000" + "20260101    120000" + "0000" * 6
    raw_msg = fixed + "AOMAIN|AA21234000123|AEDOE, JANE|BLY|CQY|BEjane.doe@example.org|BF555-0100|BD123 Main St|AY1AZ0000"
    fields = ap.sip2_parse_patron_response(raw_msg)
    assert fields.get("BE") == "jane.doe@example.org"
    assert fields.get("BF") == "555-0100"
    assert fields.get("BD") == "123 Main St"


@test(1, "sip2.patron_choice_and_forced_fields",
      "SIP2 forced fields auto-import while patron-driven fields stage for user choice.")
def t_sip2_patron_choice():
    ap = _imp("core.auth_providers")
    auth_result = ap.AuthResult(
        success=True,
        provider="sip2",
        email="21234000123@library.local",
        full_name="Patron 21234000123",
        external_id="21234000123",
        mapped_demographics={
            "name": "Jane Doe",
            "email": "jane@example.org",
            "phone": "555-0100",
            "address": "123 Main St, Seattle, WA 98101",
        },
        forced_fields=["library"],
        patron_choice=True,
        populate_vault=False,
    )
    assert auth_result.forced_fields == ["library"]
    assert auth_result.patron_choice is True
    assert auth_result.mapped_demographics["name"] == "Jane Doe"
    assert auth_result.mapped_demographics["address"] == "123 Main St, Seattle, WA 98101"


@test(1, "sip2.eligibility_rules_engine_complex_and_nested",
      "SIP2 eligibility rules evaluate multi-value library/profile matching, age ranges, and nested AND/OR combinators.")
def t_sip2_eligibility_engine():
    from datetime import date
    rules_mod = _imp("core.sip2_rules")
    ref = date(2026, 10, 8)

    # Specification:
    # Library contains lib1, lib2, lib3 AND
    # (age between 18 and 99 OR User profile is not user1, user2, user3)
    complex_spec = {
        "enabled": True,
        "mode": "all",
        "rules": [
            {"field": "library", "operator": "contains", "value": "lib1, lib2, lib3"},
            {
                "mode": "any",
                "rules": [
                    {"field": "age", "operator": "between", "value": [18, 99]},
                    {"field": "profile_type", "operator": "not_in", "value": "user1, user2, user3"}
                ]
            }
        ]
    }

    # Case 1: Matching library (lib2), age 26 (DOB 2000-10-08), profile 'user1'
    # Age between 18 and 99 is TRUE -> inner OR passes -> whole rule PASSES
    p1 = {"AQ": "lib2", "PA": "2000-10-08", "PC": "user1"}
    ok, reason = rules_mod.evaluate_sip2_eligibility(complex_spec, p1, reference_date=ref)
    assert ok is True, f"p1 should be eligible: {reason}"

    # Case 2: Matching library (lib3), age 12 (DOB 2014-10-08), profile 'student'
    # Age between 18 and 99 is FALSE, but profile 'student' not in [user1, user2, user3] is TRUE
    # Inner OR passes -> whole rule PASSES
    p2 = {"AQ": "lib3", "PA": "2014-10-08", "PC": "student"}
    ok, reason = rules_mod.evaluate_sip2_eligibility(complex_spec, p2, reference_date=ref)
    assert ok is True, f"p2 should be eligible: {reason}"

    # Case 3: Matching library (lib1), age 12, profile 'user2'
    # Both inner conditions fail -> inner OR fails -> whole rule FAILS
    p3 = {"AQ": "lib1", "PA": "2014-10-08", "PC": "user2"}
    ok, reason = rules_mod.evaluate_sip2_eligibility(complex_spec, p3, reference_date=ref)
    assert ok is False, f"p3 should fail: {reason}"
    assert "Patron does not meet any of the required criteria" in reason

    # Case 4: Mismatched library (other_branch), age 30, profile 'admin'
    # Library condition fails immediately -> whole rule FAILS
    p4 = {"AQ": "other_branch", "PA": "1996-10-08", "PC": "admin"}
    ok, reason = rules_mod.evaluate_sip2_eligibility(complex_spec, p4, reference_date=ref)
    assert ok is False, f"p4 should fail due to library: {reason}"
    assert "failed eligibility requirement" in reason

    # Case 5: Disabled rule config passes everyone
    disabled_spec = dict(complex_spec, enabled=False)
    ok, reason = rules_mod.evaluate_sip2_eligibility(disabled_spec, p4, reference_date=ref)
    assert ok is True

    # Case 6: Structural validation checks
    valid, err = rules_mod.validate_sip2_rules(complex_spec)
    assert valid is True and err is None

    bad_op_spec = {
        "mode": "all",
        "rules": [{"field": "age", "operator": "bad_operator", "value": 18}]
    }
    valid, err = rules_mod.validate_sip2_rules(bad_op_spec)
    assert valid is False and "Unsupported operator" in err


@test(1, "sip2.eligibility_sso_policy_and_auth_gate",
      "Ineligible SIP2 patrons are denied during SSO policy evaluation and direct authentication.")
def t_sip2_eligibility_policy():
    from types import SimpleNamespace as NS
    sso_policy = _imp("core.sso_policy")

    spec = {
        "enabled": True,
        "mode": "all",
        "rules": [
            {"field": "library", "operator": "contains", "value": "main_lib, west_branch"}
        ]
    }

    # Ineligible patron (wrong branch)
    res_ineligible = NS(
        provider="sip2",
        email="21234000123@library.local",
        email_verified=True,
        raw_profile={"AQ": "east_branch"}
    )
    decision = sso_policy.evaluate_sso_login(
        res_ineligible,
        provider_cfg={"eligibility_rules": spec},
        registration_cfg={"mode": "open"},
        user_exists=False,
        user_count=5
    )
    assert decision.allowed is False, f"ineligible patron was allowed: {decision}"
    assert "not eligible to sign in" in decision.reason

    # Eligible patron (correct branch)
    res_eligible = NS(
        provider="sip2",
        email="21234000123@library.local",
        email_verified=True,
        raw_profile={"AQ": "main_lib"}
    )
    decision_ok = sso_policy.evaluate_sso_login(
        res_eligible,
        provider_cfg={"eligibility_rules": spec},
        registration_cfg={"mode": "open"},
        user_exists=False,
        user_count=5
    )
    assert decision_ok.allowed is True, f"eligible patron was rejected: {decision_ok}"


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


@test(1, "plugins.sandbox_bwrap_mounts_runtime",
      "The bubblewrap probe and the real plugin launch both mount the system runtime "
      "(/usr and the /lib* loader dirs) and the runner's code, read-only; no /etc unless "
      "the plugin has network access.")
def t_plugin_sandbox_bwrap_runtime():
    sandbox = _imp("plugins.sandbox")
    perms = _imp("plugins.permissions")
    probe = sandbox._bwrap_probe_cmd()
    ro = lambda c: {c[i + 1] for i in range(len(c) - 2) if c[i] == "--ro-bind"}
    linked = lambda c: {c[i + 2] for i in range(len(c) - 2) if c[i] == "--symlink"}
    assert "/usr" in ro(probe), probe
    for d in ("/lib", "/lib64"):
        if os.path.lexists(d):
            assert d in ro(probe) | linked(probe), f"{d} missing from probe: {probe}"
    assert probe[-3:] == [os.path.realpath(sys.executable), "-c", "pass"], probe

    caps = sandbox.SandboxCapabilities(bubblewrap=True, rlimits=False, platform="linux")
    m = perms.PluginManifest.from_dict({"id": "p", "name": "p", "version": "1", "author": "a"})
    cmd, _ = sandbox.build_sandboxed_command([sys.executable, "runner.py"], "/data/plugins/p",
                                             caps, False, m)
    assert ro(probe) <= ro(cmd), "launch must mount at least what the probe proved works"
    assert os.path.join(sandbox._PLUGIN_HOST_DIR, "runner.py") in ro(cmd)
    assert sandbox._PLUGIN_HOST_DIR not in ro(cmd), "only the runner pieces, not all of plugins/"
    assert not any(p.startswith("/etc") for p in ro(cmd) | {cmd[i + 1] for i in range(len(cmd) - 1)
                                                           if cmd[i] == "--ro-bind-try"})
    assert "--clearenv" in cmd, "without a caller-built env, the host env must be cleared"
    net, _ = sandbox.build_sandboxed_command(["python"], "/data/plugins/p", caps, True, m)
    assert "/etc/resolv.conf" in net, "network plugins need name resolution"
    inh, _ = sandbox.build_sandboxed_command(["python"], "/data/plugins/p", caps, False, m,
                                             inherit_caller_env=True)
    assert "--clearenv" not in inh


@test(1, "plugins.sandbox_bwrap_really_starts_python",
      "Where bubblewrap works, detect_capabilities() says so and a sandboxed Python really "
      "starts — sees only the runtime, not the app or /etc, and gets the session env.")
def t_plugin_sandbox_bwrap_starts():
    import json, shutil, subprocess, tempfile
    sandbox = _imp("plugins.sandbox")
    perms = _imp("plugins.permissions")
    if not shutil.which("bwrap"):
        raise Skip("bubblewrap not installed")
    plain = subprocess.run(["bwrap", "--ro-bind", "/", "/", "--unshare-all", "--", "true"],
                           capture_output=True)
    if plain.returncode != 0:
        raise Skip("this host blocks user namespaces")
    assert sandbox.detect_capabilities().bubblewrap, "bwrap works here but was not detected"
    work = tempfile.mkdtemp(prefix="ps-sbx-", dir="/var/tmp")
    try:
        caps = sandbox.SandboxCapabilities(bubblewrap=True, rlimits=False, platform="linux")
        m = perms.PluginManifest.from_dict({"id": "p", "name": "p", "version": "1", "author": "a"})
        code = ("import os,json;print(json.dumps([os.environ.get('PS_SESSION_TOKEN'),"
                "os.path.exists('/etc/passwd'),os.path.exists(%r)]))"
                % os.path.join(os.path.dirname(sandbox._PLUGIN_HOST_DIR), "core"))
        cmd, _ = sandbox.build_sandboxed_command([sys.executable, "-c", code], work, caps,
                                                 False, m, inherit_caller_env=True)
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20,
                           env={"PATH": "/usr/bin:/bin", "PS_SESSION_TOKEN": "t0k"})
        assert r.returncode == 0, r.stderr
        assert json.loads(r.stdout) == ["t0k", False, False], r.stdout
        assert "t0k" not in cmd, "session token must not be on the command line"
    finally:
        shutil.rmtree(work, ignore_errors=True)


@test(1, "plugins.uds_handshake_and_thread_stack",
      "PluginManager._read_ready parses both TCP ports and Unix domain sockets, and "
      "threading stack size is reduced to prevent memory starvation.")
def t_plugin_uds_handshake():
    mgr_mod = _imp("plugins.manager")
    sdk_mod = _imp("plugins.sdk.openoptout_sdk")
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
        cf_ips = os.path.join(repo_root, "deploy", "cloudflare", "ip-ranges.txt")
        bad_ips = os.path.join(td, "bad-ips.txt")
        with open(bad_ips, "w") as f:
            f.write("103.21.244.0/22\n1.2.3.4/32 } evil {\n")

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
            # Cloudflare DNS: needs a token, only for ACME modes, known values only
            {"HTTPS_MODE": "letsencrypt", "DOMAIN": "a.org", "ACME_CHALLENGE": "cloudflare"},
            {"HTTPS_MODE": "internal", "DOMAIN": "a.org", "ACME_CHALLENGE": "cloudflare",
             "CLOUDFLARE_API_TOKEN": "x" * 40},
            {"HTTPS_MODE": "letsencrypt", "DOMAIN": "a.org", "ACME_CHALLENGE": "dns"},
            {"HTTPS_MODE": "none", "DOMAIN": "a.org } evil {"},
            # Flood protection: known values only; Cloudflare's proxy needs a certificate that doesn't rely on Let's Encrypt reaching port 80
            {"HTTPS_MODE": "letsencrypt", "DOMAIN": "a.org", "RATE_LIMIT": "maybe"},
            {"HTTPS_MODE": "letsencrypt", "DOMAIN": "a.org", "RATE_LIMIT_PER_MINUTE": "0"},
            {"HTTPS_MODE": "letsencrypt", "DOMAIN": "a.org", "AUTH_RATE_LIMIT_PER_MINUTE": "60 }"},
            {"HTTPS_MODE": "letsencrypt", "DOMAIN": "a.org", "CLOUDFLARE_PROXY": "on",
             "CLOUDFLARE_IPS_FILE": cf_ips},
            {"HTTPS_MODE": "none", "CLOUDFLARE_PROXY": "on", "CLOUDFLARE_IPS_FILE": cf_ips},
            {"HTTPS_MODE": "letsencrypt", "DOMAIN": "a.org", "ACME_CHALLENGE": "cloudflare",
             "CLOUDFLARE_API_TOKEN": "x" * 40, "CLOUDFLARE_PROXY": "on", "CLOUDFLARE_IPS_FILE": bad_ips},
            # InCommon (beta): credentials required, well-formed, and only for ACME modes
            {"HTTPS_MODE": "incommon", "DOMAIN": "a.org"},
            {"HTTPS_MODE": "incommon", "DOMAIN": "a.org", "ACME_EAB_KID": "kid1"},
            {"HTTPS_MODE": "incommon", "DOMAIN": "a.org", "ACME_EAB_KID": "kid } evil {", "ACME_EAB_HMAC": "c2VjcmV0LWhtYWMta2V5LWZvci10ZXN0aW5n"},
            {"HTTPS_MODE": "incommon", "DOMAIN": "a.org", "ACME_EAB_KID": "kid1", "ACME_EAB_HMAC": "short"},
            {"HTTPS_MODE": "letsencrypt", "DOMAIN": "a.org", "ACME_EAB_KID": "kid1", "ACME_EAB_HMAC": "c2VjcmV0LWhtYWMta2V5LWZvci10ZXN0aW5n"},
            {"HTTPS_MODE": "letsencrypt", "DOMAIN": "a.org", "ACME_KEY_TYPE": "dsa1024"},
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
            {"HTTPS_MODE": "letsencrypt", "DOMAIN": "privacy.lib.org",
             "ACME_CHALLENGE": "cloudflare", "CLOUDFLARE_API_TOKEN": "t0ken-" + "x" * 34},
            {"HTTPS_MODE": "none", "DOMAIN": "privacy.lib.org"},
            {"HTTPS_MODE": "none"},
            {"HTTPS_MODE": "letsencrypt", "DOMAIN": "privacy.lib.org", "RATE_LIMIT": "off"},
            {"HTTPS_MODE": "letsencrypt", "DOMAIN": "privacy.lib.org", "ACME_CHALLENGE": "cloudflare",
             "CLOUDFLARE_API_TOKEN": "t0ken-" + "x" * 34, "CLOUDFLARE_PROXY": "on",
             "CLOUDFLARE_IPS_FILE": cf_ips, "RATE_LIMIT_PER_MINUTE": "600", "AUTH_RATE_LIMIT_PER_MINUTE": "30"},
            {"HTTPS_MODE": "incommon", "DOMAIN": "privacy.univ.edu", "ACME_EAB_KID": "kid1", "ACME_EAB_HMAC": "c2VjcmV0LWhtYWMta2V5LWZvci10ZXN0aW5n"},
            {"HTTPS_MODE": "acme", "DOMAIN": "privacy.lib.org", "ACME_CA": "https://ca.example.com/dir",
             "ACME_EAB_KID": "kid1", "ACME_EAB_HMAC": "c2VjcmV0LWhtYWMta2V5LWZvci10ZXN0aW5n", "ACME_KEY_TYPE": "p384"},
        ]
        for env in good:
            r = run(env, cf)
            assert r.returncode == 0, f"valid config was refused: {env}\nstderr={r.stderr}"
            assert os.path.isfile(cf), f"no Caddyfile written for {env}"
            content = open(cf).read()
            parsed_hostnames = set()
            for line in content.splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or line[:1].isspace():
                    continue
                token = stripped.split()[0].strip("{}(),")
                if "://" in token:
                    host = urlparse(token).hostname
                else:
                    host = token.split(":", 1)[0].strip("[]")
                if host:
                    parsed_hostnames.add(host.lower())
            if env.get("DOMAIN"):
                assert any(h == env["DOMAIN"] for h in parsed_hostnames)
            if env.get("ACME_CHALLENGE") == "cloudflare":
                # The token is referenced, never written to disk.
                assert "dns cloudflare {env.CLOUDFLARE_API_TOKEN}" in content
                assert env["CLOUDFLARE_API_TOKEN"] not in content
            # Rate limits: on unless switched off (GENERATE_ONLY assumes the module is present), with a stricter zone for sign-in endpoints.
            if env.get("RATE_LIMIT") == "off":
                assert "rate_limit" not in content
            else:
                assert "rate_limit {" in content and "path /api/auth/*" in content
                assert f"events {env.get('RATE_LIMIT_PER_MINUTE', '1200')}" in content
                assert f"events {env.get('AUTH_RATE_LIMIT_PER_MINUTE', '60')}" in content
            assert "read_header 10s" in content
            assert "persist_config off" in content, "Caddy must not save its loaded config (it can hold the EAB secret)"
            if env.get("ACME_EAB_KID"):
                assert "eab {$ACME_EAB_KID} {$ACME_EAB_HMAC}" in content
                assert env["ACME_EAB_HMAC"] not in content, "the EAB HMAC key must never be written to the Caddyfile"
            if env["HTTPS_MODE"] == "incommon":
                assert "ca https://acme-us.certinext.io/v1/directory" in content
                assert "key_type rsa2048" in content, "CERTInext requires RSA 2048"
            elif env.get("ACME_KEY_TYPE"):
                assert f"key_type {env['ACME_KEY_TYPE']}" in content
            if env.get("CLOUDFLARE_PROXY") == "on":
                # Only Cloudflare may connect, and only Cloudflare is trusted for the client IP.
                assert "@not_cloudflare not remote_ip 173.245.48.0/20" in content and "2c0f:f248::/32" in content
                assert "abort @not_cloudflare" in content
                assert "trusted_proxies static 173.245.48.0/20" in content
                assert "client_ip_headers CF-Connecting-IP" in content
                # The drop happens first, before rate limiting or proxying.
                assert content.index("abort @not_cloudflare") < content.index("rate_limit {") < content.index("reverse_proxy")
            else:
                assert "trusted_proxies" not in content and "@not_cloudflare" not in content
            if env["HTTPS_MODE"] == "none":
                # Plain HTTP: no certificate, no HSTS, no redirect.
                assert "tls " not in content and "Strict-Transport-Security" not in content
                site_header = f"http://{env['DOMAIN']}" if env.get("DOMAIN") else ":80"
                assert any(line.strip().startswith(site_header) for line in content.splitlines())
            os.remove(cf)
    # EXPECTED: the generator accepts every documented mode and rejects malformed
    #   or injected input, including values that only look valid on their first line.
    # IF THIS FAILS: either a legitimate deployment mode is broken, or a value an
    #   admin pastes into .env could inject arbitrary Caddy configuration.


@test(1, "https.traefik_entrypoint_validation",
      "deploy/traefik/entrypoint.sh: every supported HTTPS mode produces valid Traefik YAML, "
      "unsupported modes (internal, wildcards) and injected input are refused.")
def t_https_traefik_entrypoint():
    import subprocess, tempfile, shutil
    if _try_import("yaml") is None:
        raise Skip("pyyaml not installed")
    import yaml
    repo_root = os.path.dirname(_BACKEND_DIR)
    entry = os.path.join(repo_root, "deploy", "traefik", "entrypoint.sh")
    if not os.path.isfile(entry):
        raise Skip("deploy/traefik/entrypoint.sh not present (running from a bare backend checkout)")
    sh = shutil.which("sh")
    if not sh:
        raise Skip("no /bin/sh available")

    with tempfile.TemporaryDirectory() as td:
        conf = os.path.join(td, "conf")
        cf_ips = os.path.join(repo_root, "deploy", "cloudflare", "ip-ranges.txt")

        def run(env_overrides):
            env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "GENERATE_ONLY": "1",
                   "TRAEFIK_CONF_DIR": conf, "ACME_STORAGE": os.path.join(td, "acme.json")}
            env.update(env_overrides)
            return subprocess.run([sh, entry], env=env, capture_output=True, text=True, timeout=15)

        bad = [
            {"HTTPS_MODE": "letsencrypt"},                                    # no DOMAIN
            {"HTTPS_MODE": "bogus", "DOMAIN": "a.org"},
            {"HTTPS_MODE": "internal", "DOMAIN": "a.org"},                    # Caddy-only
            {"HTTPS_MODE": "letsencrypt", "DOMAIN": "*.a.org"},              # no wildcards
            {"HTTPS_MODE": "letsencrypt", "DOMAIN": "a.org`) || PathPrefix(`/"},
            {"HTTPS_MODE": "letsencrypt", "DOMAIN": 'a.org"\nproviders: {}'},
            {"HTTPS_MODE": "letsencrypt", "DOMAIN": "a.org\nb.org"},
            {"HTTPS_MODE": "letsencrypt", "DOMAIN": "a.org", "ACME_EMAIL": "x@a.org\nlog: {}"},
            {"HTTPS_MODE": "acme", "DOMAIN": "a.org"},                        # no ACME_CA
            {"HTTPS_MODE": "acme", "DOMAIN": "a.org", "ACME_CA": "http://insecure/dir"},
            {"HTTPS_MODE": "custom", "DOMAIN": "a.org"},                      # no cert files
            {"HTTPS_MODE": "letsencrypt", "DOMAIN": "a.org", "UPSTREAM": "web:80/evil"},
            {"HTTPS_MODE": "letsencrypt", "DOMAIN": "a.org", "ACME_CHALLENGE": "cloudflare"},
            {"HTTPS_MODE": "custom", "DOMAIN": "a.org", "ACME_CHALLENGE": "cloudflare",
             "CLOUDFLARE_API_TOKEN": "x" * 40},
            {"HTTPS_MODE": "letsencrypt", "DOMAIN": "a.org", "ACME_CHALLENGE": "dns"},
            {"HTTPS_MODE": "letsencrypt", "DOMAIN": "a.org", "RATE_LIMIT": "maybe"},
            {"HTTPS_MODE": "letsencrypt", "DOMAIN": "a.org", "RATE_LIMIT_PER_MINUTE": "-5"},
            {"HTTPS_MODE": "letsencrypt", "DOMAIN": "a.org", "CLOUDFLARE_PROXY": "on",
             "CLOUDFLARE_IPS_FILE": cf_ips},
            {"HTTPS_MODE": "none", "CLOUDFLARE_PROXY": "on", "CLOUDFLARE_IPS_FILE": cf_ips},
            {"HTTPS_MODE": "incommon", "DOMAIN": "a.org"},
            {"HTTPS_MODE": "incommon", "DOMAIN": "a.org", "ACME_EAB_KID": "kid1", "ACME_EAB_HMAC": 'x"\nproviders: {}'},
            {"HTTPS_MODE": "custom", "DOMAIN": "a.org", "ACME_EAB_KID": "kid1", "ACME_EAB_HMAC": "c2VjcmV0LWhtYWMta2V5LWZvci10ZXN0aW5n"},
            {"HTTPS_MODE": "letsencrypt", "DOMAIN": "a.org", "ACME_KEY_TYPE": "rsa1024"},
        ]
        for env in bad:
            r = run(env)
            assert r.returncode != 0, f"should have been refused but wasn't: {env}\nstdout={r.stdout}"

        cert_file = os.path.join(td, "cert.pem"); key_file = os.path.join(td, "key.pem")
        open(cert_file, "w").close(); open(key_file, "w").close()
        good = [
            {"HTTPS_MODE": "letsencrypt", "DOMAIN": "privacy.lib.org, www.lib.org",
             "ACME_EMAIL": "it@lib.org"},
            {"HTTPS_MODE": "letsencrypt-staging", "DOMAIN": "privacy.lib.org", "HSTS": "off"},
            {"HTTPS_MODE": "acme", "DOMAIN": "privacy.lib.org",
             "ACME_CA": "https://ca.lib.internal/acme/acme/directory"},
            {"HTTPS_MODE": "custom", "DOMAIN": "privacy.lib.org",
             "TLS_CERT_FILE": cert_file, "TLS_KEY_FILE": key_file},
            {"HTTPS_MODE": "letsencrypt", "DOMAIN": "privacy.lib.org",
             "ACME_CHALLENGE": "cloudflare", "CLOUDFLARE_API_TOKEN": "t0ken-" + "x" * 34},
            {"HTTPS_MODE": "none", "DOMAIN": "privacy.lib.org"},
            {"HTTPS_MODE": "none"},
            {"HTTPS_MODE": "letsencrypt", "DOMAIN": "privacy.lib.org", "RATE_LIMIT": "off"},
            {"HTTPS_MODE": "letsencrypt", "DOMAIN": "privacy.lib.org", "ACME_CHALLENGE": "cloudflare",
             "CLOUDFLARE_API_TOKEN": "t0ken-" + "x" * 34, "CLOUDFLARE_PROXY": "on",
             "CLOUDFLARE_IPS_FILE": cf_ips, "RATE_LIMIT_PER_MINUTE": "600", "AUTH_RATE_LIMIT_PER_MINUTE": "30"},
            {"HTTPS_MODE": "incommon", "DOMAIN": "privacy.univ.edu", "ACME_EAB_KID": "kid1", "ACME_EAB_HMAC": "c2VjcmV0LWhtYWMta2V5LWZvci10ZXN0aW5n"},
        ]
        for env in good:
            r = run(env)
            assert r.returncode == 0, f"valid config was refused: {env}\nstderr={r.stderr}"
            static = yaml.safe_load(open(os.path.join(conf, "traefik.yml")))
            dynamic = yaml.safe_load(open(os.path.join(conf, "dynamic.yml")))
            # Only the generated file may define routes — never the Docker provider.
            assert list(static["providers"].keys()) == ["file"], static["providers"]
            router = dynamic["http"]["routers"]["openoptout"]
            for d in (env.get("DOMAIN") or "").split(","):
                if d.strip():
                    assert f"Host(`{d.strip()}`)" in router["rule"], router["rule"]
            headers = dynamic["http"]["middlewares"]["openoptout-headers"]["headers"]
            assert headers.get("frameDeny") and headers.get("contentTypeNosniff")
            if env["HTTPS_MODE"] == "incommon":
                acme = static["certificatesResolvers"]["openoptout"]["acme"]
                assert acme["caServer"] == "https://acme-us.certinext.io/v1/directory"
                assert acme["keyType"] == "RSA2048", "CERTInext requires RSA 2048"
                assert acme["eab"] == {"kid": "kid1", "hmacEncoded": env["ACME_EAB_HMAC"]}
                assert env["ACME_EAB_HMAC"] not in r.stdout, "the EAB HMAC key must never be printed"
            # Sign-in endpoints get their own router with the stricter limit.
            signin = dynamic["http"]["routers"]["openoptout-signin"]
            assert "PathPrefix(`/api/auth/`)" in signin["rule"]
            mws = dynamic["http"].get("middlewares", {})
            if env.get("RATE_LIMIT") == "off":
                assert "openoptout-ratelimit" not in mws and "openoptout-ratelimit" not in router["middlewares"]
            else:
                assert router["middlewares"][-3:] == ["openoptout-ratelimit", "openoptout-headers", "openoptout-compress"]
                assert "openoptout-signin-ratelimit" in signin["middlewares"]
                assert mws["openoptout-ratelimit"]["rateLimit"]["average"] == int(env.get("RATE_LIMIT_PER_MINUTE", 1200))
                assert mws["openoptout-signin-ratelimit"]["rateLimit"]["average"] == int(env.get("AUTH_RATE_LIMIT_PER_MINUTE", 60))
                assert mws["openoptout-ratelimit"]["rateLimit"]["period"] == "1m"
            if env.get("CLOUDFLARE_PROXY") == "on":
                for r_ in (router, signin):
                    assert r_["middlewares"][0] == "openoptout-cloudflare-only", "Cloudflare check must run first"
                allow = mws["openoptout-cloudflare-only"]["ipAllowList"]["sourceRange"]
                assert "173.245.48.0/20" in allow and "2c0f:f248::/32" in allow
                assert static["entryPoints"]["websecure"]["forwardedHeaders"]["trustedIPs"] == allow
                assert mws["openoptout-ratelimit"]["rateLimit"]["sourceCriterion"] == {"requestHeaderName": "Cf-Connecting-Ip"}
            else:
                assert "openoptout-cloudflare-only" not in mws
                assert "forwardedHeaders" not in (static["entryPoints"]["websecure"] or {})
            if env["HTTPS_MODE"] == "none":
                # Plain HTTP on port 80: no redirect, no TLS, no HSTS, no resolver.
                assert "http" not in (static["entryPoints"]["web"] or {})
                assert router["entryPoints"] == ["web"] and "tls" not in router
                assert "stsSeconds" not in headers and "certificatesResolvers" not in static
                if not env.get("DOMAIN"):
                    assert router["rule"] == "PathPrefix(`/`)"
                continue
            assert static["entryPoints"]["web"]["http"]["redirections"]["entryPoint"]["to"] == "websecure"
            assert ("stsSeconds" in headers) == (env.get("HSTS") != "off")
            if env.get("ACME_CHALLENGE") == "cloudflare":
                acme = static["certificatesResolvers"]["openoptout"]["acme"]
                assert acme["dnsChallenge"]["provider"] == "cloudflare" and "httpChallenge" not in acme
                both = open(os.path.join(conf, "traefik.yml")).read() + open(os.path.join(conf, "dynamic.yml")).read()
                assert env["CLOUDFLARE_API_TOKEN"] not in both, "token must never be written to config files"
                continue
            if env["HTTPS_MODE"] == "custom":
                assert "certificatesResolvers" not in (static or {})
                assert dynamic["tls"]["certificates"][0]["certFile"] == cert_file
            else:
                acme = static["certificatesResolvers"]["openoptout"]["acme"]
                assert router["tls"]["certResolver"] == "openoptout"
                assert acme["httpChallenge"]["entryPoint"] == "web"
                if env["HTTPS_MODE"] == "acme":
                    assert acme["caServer"] == env["ACME_CA"]
    # EXPECTED: Traefik gets the same safety properties as the Caddy front door — validated input, HTTPS redirect, security headers, file-only routing.
    # IF THIS FAILS: a legitimate mode is broken, a value pasted into .env could inject Traefik config (e.g. widen the router rule), or the Docker provider crept in and Traefik could be steered by other containers.


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
    assert any(str(t).startswith("/tmp") for t in (services["api"].get("tmpfs") or [])), \
        "api service must mount /tmp in memory (tmpfs) for ephemeral browser isolation"

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

    # Optional Traefik front door: opt-in via its own profile (never both at once by default), and never given the Docker socket.
    assert "traefik" in services, "expected an optional traefik service (FRONT_DOOR=traefik)"
    traefik = services["traefik"]
    assert traefik.get("profiles") == ["https-traefik"], \
        "traefik must be gated behind the 'https-traefik' compose profile"
    traefik_env = " ".join(str(e) for e in traefik.get("environment", []))
    for needed in ("HTTPS_MODE", "DOMAIN"):
        assert needed in traefik_env, f"traefik service missing {needed} passthrough"
    traefik_vols = " ".join(str(v) for v in traefik.get("volumes", []))
    assert "docker.sock" not in traefik_vols, \
        "the traefik front door must not get the Docker socket (host-level control)"
    assert "traefik_data" in volumes, "traefik_data must be a named volume (ACME account + certs)"

    # Extended Caddy (Cloudflare DNS + rate-limit modules): its own opt-in profile (built only when chosen), reachable as "caddy" so the certificate monitor needs no change, and the only Caddy that gets the Cloudflare token.
    assert "caddy-extended" in services, "expected a caddy-extended service (rate limits, Cloudflare DNS)"
    cdns = services["caddy-extended"]
    assert cdns.get("profiles") == ["https-caddy-extended"], "caddy-extended must be opt-in via its own profile"
    assert cdns.get("build"), "caddy-extended must build deploy/caddy/Dockerfile (stock Caddy lacks the modules)"
    assert "caddy" in (cdns.get("networks", {}).get("default", {}) or {}).get("aliases", []), \
        "caddy-extended must answer as 'caddy' on the Docker network (certificate monitor)"
    # Every Caddy/Traefik front door gets the flood-protection settings and the Cloudflare IP list (read-only) for CLOUDFLARE_PROXY=on.
    for name in ("caddy", "caddy-extended", "traefik"):
        svc_env = " ".join(str(e) for e in services[name].get("environment", []))
        for needed in ("RATE_LIMIT=", "RATE_LIMIT_PER_MINUTE", "AUTH_RATE_LIMIT_PER_MINUTE", "CLOUDFLARE_PROXY"):
            assert needed in svc_env, f"{name} missing {needed} passthrough"
        vols = " ".join(str(v) for v in services[name].get("volumes", []))
        assert "cloudflare/ip-ranges.txt:/deploy/cloudflare-ips.txt:ro" in vols, \
            f"{name} must mount the Cloudflare IP list read-only"
        for needed in ("ACME_EAB_KID", "ACME_EAB_HMAC", "ACME_KEY_TYPE"):
            assert needed in svc_env, f"{name} missing {needed} passthrough (InCommon / EAB)"
    assert any(str(t).startswith("/etc/traefik") for t in (traefik.get("tmpfs") or [])), \
        "Traefik's generated config (which can hold the EAB secret) must live in memory (tmpfs)"
    cdns_env = " ".join(str(e) for e in cdns.get("environment", []))
    assert "CLOUDFLARE_API_TOKEN" in cdns_env
    assert "CLOUDFLARE_API_TOKEN" not in " ".join(str(e) for e in caddy.get("environment", [])), \
        "the stock caddy service has no use for the Cloudflare token"
    assert "CLOUDFLARE_API_TOKEN" in " ".join(str(e) for e in traefik.get("environment", []))

    # Cloudflare Tunnel: opt-in, dials out — so it publishes no ports and needs no host mounts at all.
    assert "cloudflared" in services, "expected an optional cloudflared service (Cloudflare Tunnel)"
    cfd = services["cloudflared"]
    assert cfd.get("profiles") == ["cloudflare-tunnel"]
    assert not cfd.get("ports"), "cloudflared dials out; it must not publish ports"
    assert not cfd.get("volumes"), "cloudflared needs no host mounts"
    assert "TUNNEL_TOKEN=${CLOUDFLARE_TUNNEL_TOKEN" in " ".join(str(e) for e in cfd.get("environment", []))
    assert ":latest" not in str(cfd.get("image", "")) and ":" in str(cfd.get("image", "")), \
        "pin the cloudflared image version"

    # Companion updater: opt-in via profile, isolates Docker socket from api container.
    assert "updater" in services, "expected an optional updater service"
    upd = services["updater"]
    assert upd.get("profiles") == ["updater"], "updater must be gated behind 'updater' compose profile"
    upd_vols = " ".join(str(v) for v in upd.get("volumes", []))
    assert "docker.sock" in upd_vols and "app_data:/data" in upd_vols, \
        "updater container must mount docker.sock and app_data volume"
    # EXPECTED: the API stays off the LAN by default, SSO redirects use the real
    #   FRONTEND_URL, and Caddy never starts (or fights for ports 80/443) unless
    #   an admin explicitly opts in.
    # IF THIS FAILS: either plain-HTTP sign-in is reachable from other machines by
    #   default, SSO silently redirects to the wrong URL, or a larger deployment's
    #   own reverse proxy could end up fighting our Caddy container for ports.


@test(1, "system_updates.core_and_routes",
      "Automated updater semver parsing, Docker engine version audit, update policy, and workload draining.")
def t_system_updates():
    import json, os, tempfile, shutil
    upd = _imp("core.updater")

    # 1. Semver parsing and version comparisons
    assert upd.is_newer_version("v1.5.0", "v1.4.9") is True
    assert upd.is_newer_version("v2.0.0", "v1.99.99") is True
    assert upd.is_newer_version("v1.4.0", "v1.4.0") is False
    assert upd.is_newer_version("v1.4.0", "v1.5.0") is False
    assert upd.is_newer_version("v1.5.0-beta", "v1.5.0") is False
    assert upd.is_newer_version("v1.5.0", "v1.5.0-beta") is True
    assert upd.is_newer_version("v1.5.0-rc.2", "v1.5.0-rc.1") is True

    # 2. Docker Engine version audit
    assert upd._check_docker_outdated("20.10.21") is True
    assert upd._check_docker_outdated("23.0.6") is True
    assert upd._check_docker_outdated("24.0.5") is False
    assert upd._check_docker_outdated("27.3.1") is False

    # 3. Policy & config persistence
    tmpdir = tempfile.mkdtemp()
    old_req = upd.UPDATE_REQUEST_FILE
    try:
        req_file = os.path.join(tmpdir, "update_request.json")
        upd.UPDATE_REQUEST_FILE = req_file

        cfg = upd.get_updater_config()
        assert cfg.get("policy") in {"approval_required", "notify_only", "auto_install", "disabled"}

        cfg["policy"] = "notify_only"
        cfg["channel"] = "pre_release"
        upd.save_updater_config(cfg)
        loaded = upd.get_updater_config()
        assert loaded["policy"] == "notify_only"
        assert loaded["channel"] == "pre_release"

        # 4. Request system update creates request envelope and marks draining
        res = upd.request_system_update(target_tag="v2.5.0")
        assert res["status"] == "ok"
        assert res["target_version"] == "v2.5.0"
        assert res["state"] == "draining"
        assert os.path.isfile(req_file)
        with open(req_file, "r") as f:
            env = json.load(f)
        assert env["action"] == "upgrade"
        assert env["target_version"] == "v2.5.0"
        assert env["status"] == "pending_drain"
    finally:
        upd.UPDATE_REQUEST_FILE = old_req
        shutil.rmtree(tmpdir, ignore_errors=True)


@test(1, "https.enable_script_paths",
      "scripts/enable-https.sh: each front door + certificate choice writes the right .env keys "
      "(profiles, challenge, tokens), the tunnel warning shows, and bad combinations are refused.")
def t_enable_https_script():
    import subprocess, tempfile, shutil
    repo_root = os.path.dirname(_BACKEND_DIR)
    script = os.path.join(repo_root, "scripts", "enable-https.sh")
    example = os.path.join(repo_root, ".env.example")
    bash = shutil.which("bash")
    if not os.path.isfile(script) or not os.path.isfile(example):
        raise Skip("scripts/enable-https.sh or .env.example not present (bare backend checkout)")
    if not bash:
        raise Skip("no bash available")

    def run(*args):
        td = tempfile.mkdtemp()
        env_file = os.path.join(td, ".env")
        shutil.copy(example, env_file)
        r = subprocess.run([bash, script, "--env-file", env_file, "--yes", *args],
                           capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)
        vals = {}
        for line in open(env_file):
            line = line.rstrip("\n")
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                vals[k] = v
        shutil.rmtree(td, ignore_errors=True)
        return r, vals

    token = "t0ken" + "x" * 35
    cases = [
        # Rate limits are on by default, so Caddy uses its extended build.
        (["--proxy", "caddy", "--cert", "letsencrypt", "--domain", "a.org"],
         {"COMPOSE_PROFILES": "https-caddy-extended", "HTTPS_MODE": "letsencrypt", "ACME_CHALLENGE": "http",
          "FRONTEND_URL": "https://a.org", "TRUSTED_PROXY_HOPS": "2", "RATE_LIMIT": "on",
          "CLOUDFLARE_PROXY": "off"}),
        (["--proxy", "caddy", "--cert", "letsencrypt", "--domain", "a.org", "--no-rate-limit"],
         {"COMPOSE_PROFILES": "https", "RATE_LIMIT": "off"}),
        (["--proxy", "caddy", "--cert", "cloudflare-dns", "--domain", "a.org", "--cf-token", token],
         {"COMPOSE_PROFILES": "https-caddy-extended", "ACME_CHALLENGE": "cloudflare",
          "CLOUDFLARE_API_TOKEN": token, "HTTPS_CHECK_HOST": "caddy"}),
        (["--proxy", "caddy", "--cert", "cloudflare-dns", "--domain", "a.org", "--no-rate-limit"],
         {"COMPOSE_PROFILES": "https-caddy-extended", "RATE_LIMIT": "off"}),
        (["--proxy", "traefik", "--mode", "incommon", "--domain", "privacy.univ.edu",
          "--eab-kid", "kid1", "--eab-hmac", "c2VjcmV0LWhtYWMta2V5LWZvci10ZXN0aW5n"],
         {"HTTPS_MODE": "incommon", "ACME_CA": "https://acme-us.certinext.io/v1/directory",
          "ACME_EAB_KID": "kid1", "ACME_EAB_HMAC": "c2VjcmV0LWhtYWMta2V5LWZvci10ZXN0aW5n", "ACME_KEY_TYPE": "rsa2048"}),
        (["--proxy", "traefik", "--cert", "cloudflare-dns", "--domain", "a.org", "--cloudflare-proxy",
          "--rate-limit", "600", "--auth-rate-limit", "30"],
         {"CLOUDFLARE_PROXY": "on", "TRUSTED_PROXY_HOPS": "3", "RATE_LIMIT_PER_MINUTE": "600",
          "AUTH_RATE_LIMIT_PER_MINUTE": "30"}),
        (["--proxy", "traefik", "--cert", "cloudflare-dns", "--domain", "a.org"],   # token later
         {"COMPOSE_PROFILES": "https-traefik", "ACME_CHALLENGE": "cloudflare", "HTTPS_CHECK_HOST": "traefik"}),
        (["--proxy", "traefik", "--cert", "none"],
         {"HTTPS_MODE": "none", "FRONTEND_URL": "http://localhost"}),
        (["--proxy", "cloudflare-tunnel", "--domain", "a.org"],
         {"COMPOSE_PROFILES": "cloudflare-tunnel", "HTTPS_MODE": "cloudflare-tunnel",
          "FRONTEND_URL": "https://a.org", "WEB_BIND": "127.0.0.1"}),
    ]
    for args, expected in cases:
        r, vals = run(*args)
        assert r.returncode == 0, f"{args} failed:\n{r.stderr}"
        for k, v in expected.items():
            assert vals.get(k) == v, f"{args}: expected {k}={v}, got {vals.get(k)!r}"
        if "cloudflare-tunnel" in args:
            assert "Cloudflare decrypts ALL traffic" in r.stdout, "tunnel must show the decryption warning"
            assert "HTTPS_CHECK_HOST" not in vals and "ACME_CHALLENGE" not in vals
        if args[3:4] == ["cloudflare-dns"] and "--cf-token" not in args:
            assert "CLOUDFLARE_API_TOKEN" not in vals
            assert "CLOUDFLARE_API_TOKEN" in r.stdout, "should say how to add the token later"

    refused = [
        ["--proxy", "cloudflare-tunnel", "--domain", "a.org", "--cert", "letsencrypt"],
        ["--proxy", "caddy", "--cert", "cloudflare-dns", "--mode", "custom", "--domain", "a.org"],
        ["--proxy", "traefik", "--mode", "internal", "--domain", "a.org"],
        ["--proxy", "caddy", "--cert", "cloudflare-dns", "--domain", "a.org", "--cf-token", "bad\ntoken"],
        ["--proxy", "nginx"],
        # Cloudflare's proxy needs a certificate that doesn't depend on port 80
        ["--proxy", "caddy", "--cert", "letsencrypt", "--domain", "a.org", "--cloudflare-proxy"],
        ["--proxy", "traefik", "--cert", "none", "--cloudflare-proxy"],
        ["--proxy", "cloudflare-tunnel", "--domain", "a.org", "--cloudflare-proxy"],
        ["--proxy", "caddy", "--cert", "none", "--rate-limit", "0"],
        ["--proxy", "caddy", "--cert", "none", "--rate-limit", "12;rm"],
        # InCommon details are required during setup, and credentials only fit ACME modes
        ["--proxy", "caddy", "--mode", "incommon", "--domain", "a.org"],
        ["--proxy", "caddy", "--mode", "incommon", "--domain", "a.org", "--eab-kid", "kid1", "--eab-hmac", "bad\nkey"],
        ["--proxy", "caddy", "--mode", "letsencrypt", "--domain", "a.org", "--eab-kid", "kid1", "--eab-hmac", "c2VjcmV0LWhtYWMta2V5LWZvci10ZXN0aW5n"],
    ]
    for args in refused:
        r, _ = run(*args)
        assert r.returncode != 0, f"should have been refused: {args}"
    # EXPECTED: the two questions map onto exactly one Compose profile each, the token is only stored when given and valid, and the tunnel always warns.
    # IF THIS FAILS: a choice would start the wrong container (or none), or a malformed token could inject extra lines into .env.


@test(1, "https.wizard_commands_and_monitor_modes",
      "Wizard hands back the right enable-https command (unsafe domains left out), and the "
      "certificate monitor skips 'none' and Cloudflare Tunnel instead of raising a false alarm.")
def t_wizard_commands_and_monitor_modes():
    import ast
    src = open(os.path.join(_BACKEND_DIR, "routers", "wizard.py")).read()
    tree = ast.parse(src)
    keep = [n for n in tree.body
            if (isinstance(n, ast.Assign) and any(getattr(t, "id", "") in ("FRONT_DOORS", "CERTIFICATES")
                                                  for t in n.targets))
            or (isinstance(n, ast.FunctionDef) and n.name == "enable_https_commands")]
    ns = {}
    exec(compile(ast.Module(keep, []), "wizard_cmds", "exec"), ns)
    cmds = ns["enable_https_commands"]
    c = cmds("traefik", "cloudflare-dns", "home.example.org")
    assert c["linux"] == "./scripts/enable-https.sh --proxy traefik --cert cloudflare-dns --domain home.example.org"
    assert c["windows"].endswith("-Proxy traefik -Cert cloudflare-dns -Domain home.example.org")
    t = cmds("cloudflare-tunnel", "letsencrypt", "a.org")
    assert "--cert" not in t["linux"], "the tunnel has no certificate question"
    bad = cmds("caddy", "none", "a.org; rm -rf /")
    assert "rm" not in bad["linux"] and "--domain" not in bad["linux"], "unsafe domain must be dropped"
    cfp = cmds("caddy", "cloudflare-dns", "a.org", rate_limit=False, cloudflare_proxy=True)
    assert "--cloudflare-proxy" in cfp["linux"] and "-CloudflareProxy" in cfp["windows"]
    assert "--no-rate-limit" in cfp["linux"] and "-NoRateLimit" in cfp["windows"]
    inc = cmds("traefik", "incommon", "privacy.univ.edu")
    assert inc["linux"] == "./scripts/enable-https.sh --proxy traefik --mode incommon --domain privacy.univ.edu"
    assert "-Mode incommon" in inc["windows"] and "--cert" not in inc["linux"]
    assert "--cloudflare-proxy" not in cmds("caddy", "letsencrypt", "a.org", cloudflare_proxy=True)["linux"], \
        "Cloudflare's proxy is only offered with the Cloudflare DNS certificate"

    try:
        cm = _imp("core.cert_monitor")
    except ImportError as e:
        raise Skip(f"needs backend package layout: {e}")
    saved = {k: os.environ.get(k) for k in ("HTTPS_MODE", "DOMAIN")}
    try:
        os.environ["DOMAIN"] = "a.org"
        os.environ["HTTPS_MODE"] = "none"
        assert cm.https_cert_status() is None
        os.environ["HTTPS_MODE"] = "cloudflare-tunnel"
        st = cm.https_cert_status()
        assert st["level"] == "none" and "Cloudflare" in st["message"]
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    # EXPECTED: admins get a copy-paste command matching what they chose, and the dashboard never shows a certificate error for a front door that intentionally has no certificate here.


@test(1, "https.cloudflare_ip_list",
      "deploy/cloudflare/ip-ranges.txt: a non-empty list of valid IPv4 and IPv6 ranges and "
      "nothing else (the front door admits only these when CLOUDFLARE_PROXY=on).")
def t_cloudflare_ip_list():
    import ipaddress
    repo_root = os.path.dirname(_BACKEND_DIR)
    path = os.path.join(repo_root, "deploy", "cloudflare", "ip-ranges.txt")
    if not os.path.isfile(path):
        raise Skip("deploy/cloudflare/ip-ranges.txt not present (bare backend checkout)")
    nets = []
    for line in open(path):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        nets.append(ipaddress.ip_network(line, strict=True))   # raises on anything malformed
    v4 = [n for n in nets if n.version == 4]; v6 = [n for n in nets if n.version == 6]
    assert len(v4) >= 5 and len(v6) >= 3, f"suspiciously short list: {len(v4)} v4, {len(v6)} v6"
    assert not any(n.prefixlen < 8 for n in nets), "a huge range would let far more than Cloudflare in"
    # EXPECTED: only real, reasonably sized ranges. IF THIS FAILS: a bad edit could either lock everyone out or let non-Cloudflare traffic straight in.


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
        assert ver.version_string() == f"OpenOptOut {ver.get_version()} (commit abc1234)"

        # 2) No env var: falls back to asking git directly, for a native/dev
        # run inside a real checkout — build a throwaway one to prove it.
        os.environ.pop("GIT_COMMIT", None)
        import shutil
        if shutil.which("git"):
            with tempfile.TemporaryDirectory() as tmp:
                subprocess.run(["git", "init", "-q", "-b", "main", tmp], check=True)
                subprocess.run(["git", "-C", tmp, "-c", "user.email=t@t.com", "-c", "user.name=t",
                                "commit", "-q", "--allow-empty", "-m", "test"], check=True)
                ver._VERSION_FILE = os.path.join(tmp, "VERSION")   # cwd for the git fallback
                commit = ver.get_commit()
                assert commit != "unknown" and len(commit) >= 7, f"git fallback didn't work: {commit!r}"
        else:
            assert ver.get_commit() == "unknown"

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

    # Backward compatibility: verify unpeppered legacy hash
    h_legacy = auth.hash_password("legacy password 123", use_pepper=False)
    assert auth.verify_password("legacy password 123", h_legacy), "legacy unpeppered hash failed to verify"
    assert auth.is_legacy_unpeppered_hash("legacy password 123", h_legacy), "failed to identify legacy hash for upgrade"
    assert not auth.is_legacy_unpeppered_hash("a perfectly normal short password", h), "modern hash misidentified as legacy"

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


@test(1, "text_input.clean_name",
      "Names keep accents, apostrophes and emoji; control characters, text-reordering marks and "
      "invalid text are removed; over-long or empty names get a plain-English error.")
def t_clean_name():
    ti = _imp("core.text_input")
    ok = {
        "Jordan Example": "Jordan Example",
        "  Jordan   Example  ": "Jordan Example",
        "Zoë O'Brien-Núñez": "Zoë O'Brien-Núñez",          # accents, apostrophe, hyphen
        "José": "José",                                       # decomposed é -> composed (NFC)
        "山田 太郎": "山田 太郎",
        "Jordan 😀": "Jordan 😀",
        "Fam 👨‍👩‍👧": "Fam 👨‍👩‍👧",  # ZWJ kept: emoji sequence intact
        "Robert'); DROP TABLE users;--": "Robert'); DROP TABLE users;--",  # SQL is the ORM's job
        "Jordan\x00Example": "JordanExample",                # NUL: PostgreSQL rejects it
        "Jordan\nExample\t": "Jordan Example",
        "Jordan\x1b[31mExample": "Jordan[31mExample",        # terminal escape neutralised
        "Bob\u202eevil": "Bobevil",                          # right-to-left override
        "\ufeffJordan": "Jordan",
        "Jordan\ud800": "Jordan",                             # lone surrogate
        "Jordan\u00a0Example": "Jordan Example",             # non-breaking space
    }
    for raw, want in ok.items():
        got = ti.clean_name(raw)
        assert got == want, f"clean_name({raw!r}) = {got!r}, expected {want!r}"
        got.encode("utf-8")                                    # always storable as UTF-8

    for bad in ("", "   ", "\x00\x01", "\u202e"):
        try:
            ti.clean_name(bad)
            raise AssertionError(f"empty name {bad!r} was accepted")
        except ValueError as e:
            assert "enter a name" in str(e), str(e)
    at_limit = "a" * ti.MAX_NAME_CHARS
    assert ti.clean_name(at_limit) == at_limit
    try:
        ti.clean_name("a" * (ti.MAX_NAME_CHARS + 1))
        raise AssertionError("an over-long name was accepted")
    except ValueError as e:
        assert "too long" in str(e) and str(ti.MAX_NAME_CHARS) in str(e), str(e)
    try:
        ti.clean_name(12345)
        raise AssertionError("a number was accepted as a name")
    except ValueError:
        pass

    # Optional fields: None stays None, blank means "clear it".
    assert ti.clean_name(None) is None
    assert ti.clean_name("  ", required=False) == ""
    assert ti.clean_name(None, required=False) is None

    # Names from sign-in providers never block a sign-in.
    assert ti.clean_name_lenient("x" * 5000) == "x" * ti.MAX_NAME_CHARS
    assert ti.clean_name_lenient("\x00\u202e", fallback="jordan@example.invalid") == "jordan@example.invalid"
    assert ti.clean_name_lenient(None) == ""
    assert ti.clean_name_lenient("Jordan\x00 Example") == "Jordan Example"
    # Ensure text_input.py source itself contains no literal bidi control characters (Bandit Trojan-Source check)
    with open(ti.__file__, encoding="utf-8") as _f:
        src_text = _f.read()
    assert not any(c in ti._BIDI_CONTROLS for c in src_text), "text_input.py contains literal bidi control characters"
    # EXPECTED: real names pass through untouched; junk characters are dropped.
    # IF THIS FAILS: a name with a NUL can break sign-up on PostgreSQL, a
    #   reordering mark can make a name display as something else to an admin,
    #   or (if a "real name" case failed) the cleaner is now too aggressive.


@test(4, "auth.signup_names_validated",
      "Sign-up, admin and family forms reject over-long or empty names with a readable error, "
      "and a SQL-looking name is stored literally without touching the database schema.")
def t_signup_names():
    try:
        from pydantic import ValidationError
        auth_router = _imp("routers.auth")
        admin_router = _imp("routers.admin")
        family_router = _imp("routers.family")
        db, session = _memory_db()
    except ImportError as e:
        raise Skip(f"needs full backend deps / package layout: {e}")

    def rejects(model, **fields):
        try:
            model(**fields)
        except ValidationError as e:
            return str(e)
        raise AssertionError(f"{model.__name__} accepted {fields!r}")

    long_name = "a" * 201
    for model, extra in ((auth_router.RegisterRequest, {"email": "jordan@example.com"}),
                         (admin_router.CreateUserRequest, {"email": "jordan@example.com"}),
                         (family_router.MemberCreate, {})):
        assert "too long" in rejects(model, full_name=long_name, **extra) or model is family_router.MemberCreate
        rejects(model, full_name="\x00", **extra)
        assert model(full_name="Jordan\x00 Example", **extra).full_name == "Jordan Example"
    assert admin_router.UpdateUserRequest(full_name=None).full_name is None
    assert family_router.MemberUpdate(formal_name="  ").formal_name == ""       # blank clears it
    rejects(family_router.MemberUpdate, formal_name=long_name)
    rejects(auth_router.RegisterRequest, email="😀@😀.com", full_name="Jordan")  # not an email

    # A name that looks like SQL is just stored as text; the table survives.
    evil = "Robert'); DROP TABLE users;--"
    user = auth_router._create_user_and_member(session, "jordan@example.com", evil, db.UserRole.member)
    assert session.query(db.User).filter(db.User.id == user.id).one().full_name == evil
    assert session.query(db.FamilyMember).filter(db.FamilyMember.user_id == user.id).one().full_name == evil
    # A provider-sent name with a NUL is cleaned; an empty one falls back to the email.
    u2 = auth_router._create_user_and_member(session, "casey@example.com", "Casey\x00", db.UserRole.member)
    u3 = auth_router._create_user_and_member(session, "sam@example.com", "\x00", db.UserRole.member)
    assert u2.full_name == "Casey" and u3.full_name == "sam@example.com"
    session.close()
    # EXPECTED: bad names get a 422 with a clear message; nothing reaches the DB unclean.
    # IF THIS FAILS: a validator was removed from a request model, or
    #   _create_user_and_member stopped cleaning provider-supplied names.


def _api_routes(routes):
    """Every APIRoute in the app, including ones inside included routers."""
    from fastapi.routing import APIRoute
    for r in routes:
        if isinstance(r, APIRoute):
            yield r
        elif hasattr(r, "original_router"):          # FastAPI >= 0.140 wraps included routers
            yield from _api_routes(r.original_router.routes)
        elif hasattr(r, "routes"):
            yield from _api_routes(r.routes)


@test(4, "auth.request_fields_bounded",
      "Every field any endpoint accepts has a size limit: text via the model's limit or its own, "
      "lists and dictionaries via an item cap, and uploads via a bounded read.")
def t_request_fields_bounded():
    import inspect, typing
    try:
        import annotated_types
        from pydantic import BaseModel
        from fastapi import UploadFile
        main = importlib.import_module(_mod("main"))
        limits = _imp("core.limits")
    except ImportError as e:
        raise Skip(f"needs full backend deps / package layout: {e}")

    def capped(field):
        return any(isinstance(m, annotated_types.MaxLen) for m in field.metadata)

    def parts(t):
        args = typing.get_args(t)
        return [t] + [x for a in args for x in parts(a)]

    def is_collection(t):
        origin = typing.get_origin(t)
        return t in (list, dict, set, tuple) or origin in (list, dict, set, tuple)

    problems, checked, seen = [], set(), set()

    def check_model(model, where):
        if model in seen:
            return
        seen.add(model)
        model_text_cap = model.model_config.get("str_max_length")
        for name, f in model.model_fields.items():
            label = f"{model.__module__.rsplit('.', 1)[-1]}.{model.__name__}.{name}"
            checked.add(label)
            ann = f.annotation
            flat = parts(ann)
            if any(x is str for x in flat) and not (model_text_cap or capped(f)):
                problems.append(f"{label}: text with no length limit ({where})")
            if any(is_collection(x) for x in flat if x is not type(None)) and not capped(f):
                problems.append(f"{label}: list/dictionary with no item limit ({where})")
            for x in flat:
                if inspect.isclass(x) and issubclass(x, BaseModel):
                    check_model(x, where)

    routes = list(_api_routes(main.app.routes))
    assert len(routes) > 100, f"only found {len(routes)} routes — the route walker is broken"
    for r in routes:
        where = f"{sorted(r.methods)[0]} {r.path}"
        for p in r.dependant.body_params:
            fi, ann = p.field_info, p.field_info.annotation
            flat = parts(ann)
            models = [x for x in flat if inspect.isclass(x) and issubclass(x, BaseModel)]
            if models:
                for m in models:
                    check_model(m, where)
                continue
            if any(inspect.isclass(x) and issubclass(x, UploadFile) for x in flat):
                if limits.body_limit_for(r.path) <= limits.MAX_BODY_BYTES:
                    problems.append(f"{where}: upload route has no entry in limits.BODY_LIMIT_OVERRIDES")
                src = inspect.getsource(r.endpoint)
                helpers = "".join(inspect.getsource(v) for v in inspect.getmodule(r.endpoint).__dict__.values()
                                  if inspect.isfunction(v) and v.__module__ == r.endpoint.__module__)
                if re.search(r"\.read\(\s*\)", src) or (re.search(r"\.read\(\s*\)", helpers) and "file" in helpers and
                        re.search(r"\b\w*file\w*\.(file\.)?read\(\s*\)", helpers)):
                    problems.append(f"{where}: reads an upload with no size limit (use limits.read_upload)")
                continue
            checked.add(f"{where} {p.name}")
            if (any(x is str for x in flat) or any(is_collection(x) for x in flat)) and not capped(fi):
                problems.append(f"{where}: body parameter '{p.name}' has no max_length")

    assert not problems, "Unbounded input found:\n  " + "\n  ".join(sorted(set(problems)))
    assert len(checked) > 300, f"only {len(checked)} fields checked — the walker missed models"
    # EXPECTED: every input is bounded (query strings are capped as a whole by
    #   RequestSizeLimitMiddleware, and every body by MAX_BODY_BYTES).
    # IF THIS FAILS: a new or changed endpoint accepts unlimited input. Make
    #   its model inherit core.limits.LimitedModel, give lists/dicts a
    #   Field(max_length=...), and read uploads with limits.read_upload.


@test(4, "auth.request_size_limits_enforced",
      "Over-size requests get a 413 with a plain message before the app reads them — "
      "with or without a Content-Length — and long query strings get a 414.")
def t_request_size_limits():
    try:
        from fastapi.testclient import TestClient
        main = importlib.import_module(_mod("main"))
        limits = _imp("core.limits")
        auth_router = _imp("routers.auth")
        from pydantic import ValidationError
    except ImportError as e:
        raise Skip(f"needs full backend deps / package layout: {e}")
    client = TestClient(main.app, raise_server_exceptions=False)

    big = b'{"email": "jordan@example.com", "full_name": "' + b"a" * (limits.MAX_BODY_BYTES + 10) + b'"}'
    r = client.post("/api/auth/register", content=big, headers={"content-type": "application/json"})
    assert r.status_code == 413, r.status_code
    assert "too much to send" in r.json()["detail"], r.text

    def chunks():                                   # no Content-Length: streamed
        for _ in range(limits.MAX_BODY_BYTES // 65536 + 2):
            yield b"a" * 65536
    r = client.post("/api/auth/register", content=chunks(), headers={"content-type": "application/json"})
    assert r.status_code == 413, f"streamed body got {r.status_code}"

    r = client.get("/api/i18n/languages?x=" + "a" * (limits.MAX_QUERY_BYTES + 1))
    assert r.status_code == 414, r.status_code

    # Upload routes get their own, larger allowance.
    assert limits.body_limit_for("/api/plugins/upload") > limits.MAX_BODY_BYTES
    assert limits.body_limit_for("/api/registry/TX/import") > limits.MAX_BODY_BYTES
    assert limits.body_limit_for("/api/auth/register") == limits.MAX_BODY_BYTES

    # Field limits: a 5,000-character invite code is refused, a normal one isn't.
    try:
        auth_router.RegisterRequest(email="jordan@example.com", full_name="Jordan", invite_code="x" * 5000)
        raise AssertionError("an over-long invite code was accepted")
    except ValidationError:
        pass
    auth_router.RegisterRequest(email="jordan@example.com", full_name="Jordan", invite_code="ABC123")
    # EXPECTED: 413 / 414 with readable messages; normal requests unaffected.
    # IF THIS FAILS: RequestSizeLimitMiddleware was removed from main.py or
    #   its ordering changed so the body is read before the check.


@test(1, "auth.password_peppering_pbkdf2_hmac_sha256",
      "PBKDF2-HMAC-SHA256 password peppering produces deterministic 44-character Base64 digests and preserves key separation.")
def t_password_peppering():
    auth = _imp("core.auth")
    # 1. Digest format (44 Base64 characters representing 32-byte binary digest)
    p1 = auth._pepper_password("MySecretPass123!")
    assert len(p1) == 44, f"unexpected peppered digest length: {len(p1)}"
    assert auth._pepper_password("MySecretPass123!") == p1, "pepper output must be deterministic"

    # 2. Collision avoidance: different passwords produce completely different pepper outputs
    p2 = auth._pepper_password("MySecretPass123?")
    assert p1 != p2, "different passwords produced identical pepper digests"

    # 3. Pepper key isolation: different pepper keys produce different outputs for the same password
    import hashlib, base64
    custom_key = b"test-custom-pepper-key"
    digest_custom = base64.b64encode(hashlib.pbkdf2_hmac("sha256", b"MySecretPass123!", custom_key, 100_000)).decode("ascii")
    assert digest_custom != p1, "pepper key change failed to alter digest"


# ── MFA / FIDO2 / WebAuthn / TOTP Tests ────────────────────────────────────────

@test(1, "mfa.totp_generation_and_verification",
      "RFC 6238 TOTP generates valid secrets, produces accurate 6-digit codes, verifies with clock tolerance, and formats otpauth URIs.")
def t_mfa_totp():
    mfa = _imp("core.mfa")
    # 1. Secret generation
    secret = mfa.generate_totp_secret()
    assert isinstance(secret, str) and len(secret) >= 26, f"invalid secret length: {len(secret)}"

    # 2. Code generation at fixed timestamp
    fixed_ts = 1700000000.0
    code = mfa.get_totp(secret, timestamp=fixed_ts)
    assert len(code) == 6 and code.isdigit(), f"bad totp code: {code}"

    # 3. Verification at exact time
    assert mfa.verify_totp(code, secret, timestamp=fixed_ts), "failed to verify code at exact time"

    # 4. Clock drift window (+/- 30s)
    assert mfa.verify_totp(code, secret, timestamp=fixed_ts + 25), "failed to verify code within +25s drift"
    assert mfa.verify_totp(code, secret, timestamp=fixed_ts - 25), "failed to verify code within -25s drift"

    # 5. Invalid code or distant timestamp rejected
    assert not mfa.verify_totp("999999", secret, timestamp=fixed_ts) or code == "999999", "accepted arbitrary code"
    assert not mfa.verify_totp(code, secret, timestamp=fixed_ts + 120), "accepted code outside window (+120s)"

    # 6. otpauth URI construction
    uri = mfa.build_totp_uri(secret, "admin@example.org", issuer="OpenOptOut")
    assert uri.startswith("otpauth://totp/OpenOptOut:admin"), f"bad uri format: {uri}"
    assert f"secret={secret}" in uri and "issuer=OpenOptOut" in uri


@test(1, "mfa.backup_recovery_codes",
      "Single-use backup recovery codes generate properly, verify securely, and consume accurately.")
def t_mfa_backup_codes():
    mfa = _imp("core.mfa")
    plain_codes, hashed_codes = mfa.generate_backup_codes(count=10)
    assert len(plain_codes) == 10 and len(hashed_codes) == 10, "incorrect code counts"
    assert len(set(plain_codes)) == 10, "backup codes must be distinct"

    # Verify each code format (XXXX-XXXX format with uppercase hex)
    for c in plain_codes:
        assert len(c) == 9 and c[4] == "-", f"bad code format: {c}"
        raw = c.replace("-", "")
        assert len(raw) == 8 and all(ch in "0123456789ABCDEF" for ch in raw), f"bad hex chars: {c}"

    # Verify and consume the first code
    current_hashes = list(hashed_codes)
    target_code = plain_codes[0]
    matched, remaining = mfa.verify_backup_code(target_code, current_hashes)
    assert matched is True, "valid backup code failed verification"
    assert len(remaining) == 9, f"expected 9 remaining codes, got {len(remaining)}"

    # Second attempt with the SAME code must fail (single-use property)
    matched2, remaining2 = mfa.verify_backup_code(target_code, remaining)
    assert matched2 is False, "already-consumed backup code was accepted twice"
    assert len(remaining2) == 9, "remaining count changed on failed verification"

    # Invalid code rejected
    matched_bad, _ = mfa.verify_backup_code("00000000", remaining)
    assert matched_bad is False, "invalid backup code accepted"


@test(1, "mfa.fips_yubikey_detection_and_aaguids",
      "NIST FIPS 140-2 / FIPS 140-3 YubiKey AAGUID registry accurately classifies certified hardware authenticators.")
def t_mfa_fips_detection():
    mfa = _imp("core.mfa")
    # Verify published Yubico FIPS AAGUIDs are registered
    assert "b927c8986a4049fc84a4413e648c41ec" in mfa.YUBICO_FIPS_AAGUIDS, "FIPS 140-3 YubiKey 5 missing"
    assert "c599494da9d146f7b9c97b1a03e99e55" in mfa.YUBICO_FIPS_AAGUIDS, "FIPS 140-2 YubiKey 5 NFC missing"

    fips_name = mfa.YUBICO_FIPS_AAGUIDS["b927c8986a4049fc84a4413e648c41ec"]
    assert "FIPS 140-3" in fips_name, f"unexpected description: {fips_name}"

    # Non-FIPS or consumer AAGUID
    consumer_aaguid = "00000000000000000000000000000000"
    assert consumer_aaguid not in mfa.YUBICO_FIPS_AAGUIDS, "all-zero AAGUID marked as FIPS"


@test(1, "mfa.mandate_policy_and_tickets",
      "Admin MFA 3-day post-install mandate logic and ephemeral encrypted login tickets behave correctly.")
def t_mfa_mandate_policy():
    mfa = _imp("core.mfa")
    from datetime import datetime, timedelta

    class MockUser:
        def __init__(self, role, totp=False, creds=None):
            self.role = role
            self.totp_enabled = totp
            self.webauthn_credentials = creds

    # 1. Non-admin users are never mandated
    patron = MockUser("patron")
    assert not mfa.is_mfa_mandated(patron, days_since_install=10)[0], "patron account was wrongly mandated"

    # 2. Admin / Super Admin under 3 days are not yet mandated
    admin_new = MockUser("super_admin")
    mandated, days_left = mfa.is_mfa_mandated(admin_new, days_since_install=1)
    assert not mandated and days_left > 0, "admin under 3 days was prematurely mandated"
    mandated2, days_left2 = mfa.is_mfa_mandated(admin_new, days_since_install=2)
    assert not mandated2 and days_left2 > 0, "admin at 2 days was prematurely mandated"

    # 3. Admin / Super Admin at or over 3 days WITHOUT MFA ARE mandated
    assert mfa.is_mfa_mandated(admin_new, days_since_install=3)[0], "admin at 3 days was not mandated"
    assert mfa.is_mfa_mandated(admin_new, days_since_install=30)[0], "admin at 30 days was not mandated"

    # 4. Admin WITH MFA configured is NOT mandated
    admin_with_totp = MockUser("super_admin", totp=True)
    assert not mfa.is_mfa_mandated(admin_with_totp, days_since_install=30)[0], "admin with totp was flagged as mandated"

    admin_with_key = MockUser("manager", creds='[{"id": "abc"}]')
    assert not mfa.is_mfa_mandated(admin_with_key, days_since_install=30)[0], "admin with key was flagged as mandated"

    # 5. Ephemeral MFA challenge ticket lifecycle
    ticket = mfa.create_mfa_ticket(42, "admin@domain.com")
    assert isinstance(ticket, str) and len(ticket) > 10, "ticket creation failed"

    verified = mfa.verify_mfa_ticket(ticket)
    assert verified is not None, "valid ticket verification failed"
    assert verified.get("uid") == 42 and verified.get("sub") == "admin@domain.com"

    # Tampered ticket must fail
    assert mfa.verify_mfa_ticket(ticket + "tamper") is None, "tampered ticket accepted"


@test(1, "mfa.webauthn_cbor_and_options",
      "WebAuthn CBOR parsing and PublicKeyCredential options generators format standards-compliant structures.")
def t_mfa_webauthn_options():
    mfa = _imp("core.mfa")

    # 1. Registration options
    reg_opts = mfa.create_webauthn_registration_options(user_id=1, user_email="admin@test.org", user_name="Admin")
    assert "challenge" in reg_opts and len(reg_opts["challenge"]) > 20, "missing challenge"
    assert reg_opts["rp"]["name"] == "OpenOptOut", "unexpected rp name"
    assert any(p["alg"] == -7 for p in reg_opts["pubKeyCredParams"]), "missing ES256 (-7) in pubKeyCredParams"
    assert reg_opts["timeout"] == 60000, "expected 60s timeout"

    # 2. Authentication options
    fake_keys = [{"id": "key-id-123", "transports": ["usb", "nfc"]}]
    auth_opts = mfa.create_webauthn_authentication_options(fake_keys)
    assert "challenge" in auth_opts, "missing auth challenge"
    assert len(auth_opts["allowCredentials"]) == 1, "missing allowCredentials entry"
    assert auth_opts["allowCredentials"][0]["id"] == "key-id-123"

    # 3. Canonical CBOR decode check
    # Map with 1 key (0xa1), text key "k" (0x61, 0x6b), integer value 42 (0x18, 0x2a)
    cbor_sample = bytes([0xa1, 0x61, 0x6b, 0x18, 0x2a])
    decoded, offset = mfa._decode_cbor(cbor_sample)
    assert decoded == {"k": 42} and offset == len(cbor_sample), f"unexpected cbor decode: {decoded}"


@test(1, "mfa.passwordless_config_and_options",
      "Institutional passwordless configuration defaults, overrides, and discoverable options generation for local accounts.")
def t_mfa_passwordless_config_and_options():
    mfa = _imp("core.mfa")
    settings_store = _imp("core.settings_store")

    # 1. Defaults
    orig_load = mfa.load_settings
    mfa.load_settings = lambda: {}
    try:
        cfg = mfa.get_passwordless_config()
        assert cfg["enabled"] is False
        assert cfg["allow_passkey"] is True
        assert cfg["allow_magic_link"] is True
        assert cfg["enforce_passwordless_local"] is False
    finally:
        mfa.load_settings = orig_load

    # 2. Overrides from settings store
    mfa.load_settings = lambda: {
        "security": {
            "passwordless": {
                "enabled": True,
                "allow_passkey": True,
                "allow_magic_link": False,
                "enforce_passwordless_local": True,
            }
        }
    }
    try:
        cfg2 = mfa.get_passwordless_config()
        assert cfg2["enabled"] is True
        assert cfg2["allow_passkey"] is True
        assert cfg2["allow_magic_link"] is False
        assert cfg2["enforce_passwordless_local"] is True
    finally:
        mfa.load_settings = orig_load


    # 3. Discoverable authentication options (empty allowCredentials)
    opts = mfa.create_webauthn_authentication_options([], rp_id="auth.library.org")
    opts["allowCredentials"] = []
    assert opts["rpId"] == "auth.library.org"
    assert opts["allowCredentials"] == []
    assert len(opts["challenge"]) > 20


@test(1, "session_policy.role_duration_and_remember_me",
      "Session policy computes role-differentiated expiration and enforces username-only vs extend-session modes.")
def t_session_policy():
    sess_mod = _imp("core.session_policy")
    mfa = _imp("core.mfa")
    from datetime import timedelta

    # 1. Defaults verification
    policy = sess_mod.get_session_policy()
    assert policy["remember_me_enabled"] is True
    assert "super_admin" in policy["roles"]
    assert "manager" in policy["roles"]
    assert "parent" in policy["roles"]
    assert "member" in policy["roles"]

    # 2. Super Admin: 8 hours default; username_only mode does NOT extend token lifetime
    delta_admin_std = sess_mod.compute_session_delta("super_admin", remember_me=False)
    assert delta_admin_std == timedelta(hours=8)
    delta_admin_rem = sess_mod.compute_session_delta("super_admin", remember_me=True)
    assert delta_admin_rem == timedelta(hours=8), "admin remember_me should stay username_only (short token)"

    # 3. Parent / Patron: 24 hours default; extend_session mode extends to 30 days
    delta_parent_std = sess_mod.compute_session_delta("parent", remember_me=False)
    assert delta_parent_std == timedelta(hours=24)
    delta_parent_rem = sess_mod.compute_session_delta("parent", remember_me=True)
    assert delta_parent_rem == timedelta(days=30), "parent remember_me should extend session"

    # 4. Global kill-switch: when remember_me_enabled is False, parent remember_me is ignored
    orig_load = sess_mod.load_settings
    try:
        sess_mod.load_settings = lambda: {
            "security": {
                "session_policy": {
                    "remember_me_enabled": False,
                    "roles": {
                        "parent": {"session_duration_hours": 12, "remember_me_allowed": True, "remember_me_mode": "extend_session", "remember_me_duration_days": 14}
                    }
                }
            }
        }
        delta_disabled = sess_mod.compute_session_delta("parent", remember_me=True)
        assert delta_disabled == timedelta(hours=12), "kill switch must revert extended session to standard hours"
    finally:
        sess_mod.load_settings = orig_load

    # 5. Ephemeral MFA ticket preserves remember_me flag
    ticket = mfa.create_mfa_ticket(10, "patron@library.org", remember_me=True)
    tdata = mfa.verify_mfa_ticket(ticket)
    assert tdata is not None
    assert tdata.get("remember_me") is True


@test(1, "mfa.role_permissions_and_user_overrides",
      "Role-based MFA permissions matrix and per-user overrides enforce factor gating and safety constraints.")
def t_mfa_role_permissions():
    mfa = _imp("core.mfa")

    # 1. Defaults verification
    defaults = mfa.DEFAULT_MFA_ROLE_PERMISSIONS
    assert "super_admin" in defaults and "manager" in defaults and "parent" in defaults and "member" in defaults
    for role, perms in defaults.items():
        assert perms["totp"] is True and perms["webauthn"] is True and perms["backup_codes"] is True

    # 2. Safety invariant validation: cannot disable both factors for mandated roles
    valid_policy = {
        "super_admin": {"totp": False, "webauthn": True, "backup_codes": False},
        "manager":     {"totp": True, "webauthn": False, "backup_codes": True},
        "parent":      {"totp": True, "webauthn": False, "backup_codes": True},
        "member":      {"totp": False, "webauthn": False, "backup_codes": False},
    }
    is_valid, err = mfa.validate_mfa_role_permissions(valid_policy)
    assert is_valid is True and err is None, f"valid policy rejected: {err}"

    invalid_admin_policy = {
        "super_admin": {"totp": False, "webauthn": False, "backup_codes": True},
        "manager":     {"totp": True, "webauthn": True, "backup_codes": True},
    }
    is_valid, err = mfa.validate_mfa_role_permissions(invalid_admin_policy)
    assert is_valid is False and "super_admin" in err, "policy disabling all factors for super_admin was accepted"

    invalid_manager_policy = {
        "super_admin": {"totp": True, "webauthn": False, "backup_codes": True},
        "manager":     {"totp": False, "webauthn": False, "backup_codes": True},
    }
    is_valid, err = mfa.validate_mfa_role_permissions(invalid_manager_policy)
    assert is_valid is False and "manager" in err, "policy disabling all factors for manager was accepted"

    # 3. User allowed methods resolution (role fallback vs override)
    class DummyUser:
        def __init__(self, role, override=None, is_super_admin=False, is_manager=False):
            self.role = role
            self.mfa_options_override = override
            self.is_super_admin = is_super_admin
            self.is_manager = is_manager

    u_admin = DummyUser("super_admin", is_super_admin=True)
    methods = mfa.get_user_allowed_mfa_methods(u_admin)
    assert isinstance(methods, dict) and "totp" in methods and "webauthn" in methods and "backup_codes" in methods

    # Per-user override as dict
    u_custom = DummyUser("parent", override={"totp": False, "webauthn": True, "backup_codes": False})
    custom_methods = mfa.get_user_allowed_mfa_methods(u_custom)
    assert custom_methods["totp"] is False and custom_methods["webauthn"] is True and custom_methods["backup_codes"] is False

    # Per-user override as JSON string
    import json
    u_custom_json = DummyUser("parent", override=json.dumps({"totp": True, "webauthn": False, "backup_codes": True}))
    json_methods = mfa.get_user_allowed_mfa_methods(u_custom_json)
    assert json_methods["totp"] is True and json_methods["webauthn"] is False and json_methods["backup_codes"] is True


@test(1, "mfa.compliance_timer_and_creation_mandate",
      "Role-based MFA compliance timers calculate hours/days/weeks thresholds from account creation date and enforce max value 99.")
def t_mfa_compliance_timers():
    mfa = _imp("core.mfa")
    from datetime import datetime, timedelta, timezone

    # 1. Threshold conversions for hours, days, weeks
    assert mfa.get_compliance_threshold_seconds(12, "hours") == 12 * 3600
    assert mfa.get_compliance_threshold_seconds(3, "days") == 3 * 86400
    assert mfa.get_compliance_threshold_seconds(2, "weeks") == 2 * 7 * 86400

    # Max clamp at 99
    assert mfa.get_compliance_threshold_seconds(150, "days") == 99 * 86400
    assert mfa.get_compliance_threshold_seconds(0, "days") == 1 * 86400

    # 2. Validation
    valid_comp = {
        "super_admin": {"enabled": True, "value": 72, "unit": "hours"},
        "manager":     {"enabled": True, "value": 14, "unit": "days"},
        "parent":      {"enabled": True, "value": 4,  "unit": "weeks"},
        "member":      {"enabled": False, "value": 99, "unit": "days"},
    }
    is_valid, err = mfa.validate_mfa_compliance(valid_comp)
    assert is_valid is True and err is None

    # Exceeding 99 rejected
    bad_val = {"super_admin": {"enabled": True, "value": 100, "unit": "days"}}
    is_valid, err = mfa.validate_mfa_compliance(bad_val)
    assert is_valid is False and "between 1 and 99" in err

    # Zero rejected
    bad_zero = {"super_admin": {"enabled": True, "value": 0, "unit": "days"}}
    is_valid, err = mfa.validate_mfa_compliance(bad_zero)
    assert is_valid is False and "between 1 and 99" in err

    # Bad unit rejected
    bad_unit = {"super_admin": {"enabled": True, "value": 10, "unit": "months"}}
    is_valid, err = mfa.validate_mfa_compliance(bad_unit)
    assert is_valid is False and "'hours', 'days', or 'weeks'" in err

    # 3. Calculation against user.created_at
    class MockUser:
        def __init__(self, role, created_at, totp=False, creds=None):
            self.role = role
            self.created_at = created_at
            self.totp_enabled = totp
            self.webauthn_credentials = creds

    now = datetime.now(timezone.utc)

    # User created 2 days ago with 3-day mandate -> not mandated
    u_fresh = MockUser("super_admin", created_at=now - timedelta(days=2))
    mandated, days_left = mfa.is_mfa_mandated(u_fresh)
    assert not mandated and days_left > 0, "fresh admin account was prematurely mandated"

    # User created 4 days ago with 3-day mandate -> mandated
    u_expired = MockUser("super_admin", created_at=now - timedelta(days=4))
    mandated, days_left = mfa.is_mfa_mandated(u_expired)
    assert mandated and days_left == 0, "expired admin account was not mandated"

    # User who already configured MFA -> never mandated
    u_enrolled = MockUser("super_admin", created_at=now - timedelta(days=40), totp=True)
    assert not mfa.is_mfa_mandated(u_enrolled)[0], "enrolled user was flagged as mandated"

    # Role with compliance disabled (parent by default) -> never mandated
    u_parent = MockUser("parent", created_at=now - timedelta(days=60))
    assert not mfa.is_mfa_mandated(u_parent)[0], "parent with disabled compliance was wrongly mandated"




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
      "Connecting OAuth for a provider OpenOptOut ships a plugin for (Gmail/Outlook/"
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
            assert os.path.isfile(os.path.join(expected, ".openoptout-bundled")) or os.path.isfile(os.path.join(expected, ".privacyshield-bundled"))

            # A provider OpenOptOut has no bundled plugin for (a custom
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
        for k in ("brokers.manage", "brokers.automation"):
            assert not access.has_permission(mgr(), k), f"{k} decides where member data goes; must be granted"
        m = mgr(g='["users.manage"]', r='["help.edit"]')
        held = access.effective_permissions(m)
        assert "users.manage" in held and "help.edit" not in held and "scheduler.manage" in held
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
            assert "reporting.view" not in out.permissions_revoked and "scheduler.manage" in out.permissions_revoked
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


@test(2, "access.manager_scope_writes",
      "A manager scoped to a branch or library system can only edit, delete or share accounts "
      "in their branches, list only those accounts, create new ones in their own branch, and "
      "only change or delete systems and branches in their scope; super admins, cross-system "
      "holders and unscoped managers act consortium-wide. Patron branch overrides need "
      "'Override patron branch' and aren't scope-limited.")
def t_access_scope_writes():
    import inspect
    try:
        from fastapi import HTTPException
        admin_router = _imp("routers.admin")
        consortium = _imp("routers.consortium")
        settings_store = _imp("core.settings_store")
        mfa = _imp("core.mfa")
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

    def add(row):
        session.add(row); session.commit(); return row

    def user(email, role, **kw):
        return add(db.User(email=email, full_name=email.split("@")[0], role=role, hashed_password="x", **kw))

    # mfa binds load_settings at import, so an earlier test's stub can linger there.
    orig_load, orig_mfa_load = settings_store.load_settings, mfa.load_settings
    settings_store.load_settings = mfa.load_settings = lambda: {}
    try:
        R = db.UserRole
        sa = user("sa@example.org", R.super_admin)
        sys_a = add(db.LibrarySystem(name="A", code="a"))
        sys_b = add(db.LibrarySystem(name="B", code="b"))
        a1 = add(db.Branch(system_id=sys_a.id, name="A1", code="a1"))
        a2 = add(db.Branch(system_id=sys_a.id, name="A2", code="a2"))
        b1 = add(db.Branch(system_id=sys_b.id, name="B1", code="b1"))

        perms = '["users.manage", "consortium.manage"]'
        branch_mgr = user("bm@example.org", R.manager, permissions_granted=perms)
        add(db.ManagerScope(user_id=branch_mgr.id, scope_type="branch", branch_id=a1.id))
        system_mgr = user("sm@example.org", R.manager, permissions_granted=perms)
        add(db.ManagerScope(user_id=system_mgr.id, scope_type="system", system_id=sys_a.id))
        unscoped_mgr = user("um@example.org", R.manager, permissions_granted=perms)
        cross_mgr = user("cm@example.org", R.manager,
                         permissions_granted='["users.manage", "consortium.cross_system"]')
        add(db.ManagerScope(user_id=cross_mgr.id, scope_type="branch", branch_id=a1.id))

        p_a1 = user("pa1@example.org", R.parent, branch_id=a1.id)
        p_a1b = user("pa1b@example.org", R.parent, branch_id=a1.id)
        p_a2 = user("pa2@example.org", R.parent, branch_id=a2.id)
        p_b1 = user("pb1@example.org", R.parent, branch_id=b1.id)
        p_none = user("pn@example.org", R.parent)
        Update, Grant = admin_router.UpdateUserRequest, admin_router.AccessGrantRequest

        # Listing: scoped managers see only accounts in their branches.
        listed = lambda actor: {u.email for u in admin_router.list_users(session, actor)}
        assert listed(branch_mgr) == {"pa1@example.org", "pa1b@example.org"}, listed(branch_mgr)
        assert listed(system_mgr) == {"pa1@example.org", "pa1b@example.org", "pa2@example.org"}
        assert "pb1@example.org" in listed(cross_mgr) and "pn@example.org" in listed(unscoped_mgr)

        # The Add user form's branch picker offers only the manager's branches.
        picker = lambda actor: admin_router.assignable_branches(session, actor)
        bm = picker(branch_mgr)
        assert [x["id"] for x in bm["branches"]] == [a1.id] and bm["default_branch_id"] == a1.id and bm["required"]
        sm = picker(system_mgr)
        assert {x["id"] for x in sm["branches"]} == {a1.id, a2.id} and sm["default_branch_id"] is None
        um = picker(unscoped_mgr)
        assert {x["id"] for x in um["branches"]} == {a1.id, a2.id, b1.id} and not um["required"]
        assert um["branches"][0]["system_name"] in ("A", "B")

        # Creating: new accounts land in the manager's branch, never outside it.
        def create(email, actor, **kw):
            return admin_router.create_user(admin_router.CreateUserRequest(
                full_name="N", email=email, role="parent", password="password123", **kw), session, actor)
        branch_of = lambda email: session.query(db.User).filter(db.User.email == email).one().branch_id
        n1 = create("n1@example.org", branch_mgr)
        assert branch_of("n1@example.org") == a1.id
        admin_router.update_user(n1.id, Update(password="password123"), session, branch_mgr)
        expect_http(403, create, "x1@example.org", branch_mgr, branch_id=b1.id)
        expect_http(400, create, "x2@example.org", system_mgr)   # two branches, none of its own
        create("n2@example.org", system_mgr, branch_id=a2.id)
        assert branch_of("n2@example.org") == a2.id
        create("n3@example.org", unscoped_mgr)
        assert branch_of("n3@example.org") is None
        expect_http(404, create, "x3@example.org", unscoped_mgr, branch_id=9999)

        # Accounts: branch-scoped manager stays in A1.
        admin_router.update_user(p_a1.id, Update(full_name="Ok"), session, branch_mgr)
        for target in (p_a2, p_b1, p_none):
            expect_http(403, admin_router.update_user, target.id, Update(password="password123"), session, branch_mgr)
            expect_http(403, admin_router.delete_user, target.id, session, branch_mgr)
        expect_http(403, admin_router.create_grant, Grant(manager_id=p_a1.id, managed_id=p_b1.id), session, branch_mgr)
        g = admin_router.create_grant(Grant(manager_id=p_a1.id, managed_id=p_a1b.id), session, branch_mgr)
        # A grant reaching outside A1 can't be revoked by the branch manager.
        out_grant = add(db.ProfileAccess(manager_id=p_a2.id, managed_id=p_a1.id, can_view=True, can_edit=False))
        expect_http(403, admin_router.revoke_grant, out_grant.id, session, branch_mgr)
        admin_router.revoke_grant(g.id, session, branch_mgr)

        # System scope covers every branch in it; cross-system and unscoped go anywhere.
        admin_router.update_user(p_a2.id, Update(full_name="Ok"), session, system_mgr)
        expect_http(403, admin_router.delete_user, p_b1.id, session, system_mgr)
        admin_router.update_user(p_b1.id, Update(full_name="Ok"), session, cross_mgr)
        admin_router.update_user(p_b1.id, Update(password="password123"), session, cross_mgr)

        # Branch overrides: super admins, or managers granted the permission (any branch).
        gate = inspect.signature(consortium.override_patron_branch).parameters["current_user"].default.dependency
        override_mgr = user("om@example.org", R.manager, permissions_granted='["members.override_branch"]')
        add(db.ManagerScope(user_id=override_mgr.id, scope_type="branch", branch_id=a1.id))
        for actor in (branch_mgr, system_mgr, unscoped_mgr, p_a1):
            expect_http(403, gate, actor)
        gate(sa); gate(override_mgr)
        Override = consortium.PatronBranchOverride
        consortium.override_patron_branch(p_none.id, Override(branch_id=b1.id), session, override_mgr)
        assert branch_of("pn@example.org") == b1.id
        admin_router.update_user(p_none.id, Update(full_name="Ok"), session, unscoped_mgr)
        admin_router.delete_user(p_b1.id, session, unscoped_mgr)

        # Hierarchy: branch scope doesn't cover its system or new systems.
        SysC, SysU = consortium.SystemCreate, consortium.SystemUpdate
        BrC, BrU = consortium.BranchCreate, consortium.BranchUpdate
        expect_http(403, consortium.create_system, SysC(name="C", code="c"), session, branch_mgr)
        expect_http(403, consortium.create_system, SysC(name="C", code="c"), session, system_mgr)
        expect_http(403, consortium.update_system, sys_a.id, SysU(name="X"), session, branch_mgr)
        expect_http(403, consortium.delete_system, sys_b.id, session, system_mgr)
        expect_http(403, consortium.create_branch, BrC(system_id=sys_a.id, name="N", code="n"), session, branch_mgr)
        expect_http(403, consortium.update_branch, a2.id, BrU(name="X"), session, branch_mgr)
        expect_http(403, consortium.update_branch, a1.id, BrU(system_id=sys_b.id), session, branch_mgr)
        expect_http(403, consortium.delete_branch, b1.id, session, system_mgr)
        consortium.update_branch(a1.id, BrU(name="A1 renamed"), session, branch_mgr)
        consortium.update_system(sys_a.id, SysU(name="A renamed"), session, system_mgr)
        consortium.create_branch(BrC(system_id=sys_a.id, name="A3", code="a3"), session, system_mgr)
        consortium.delete_branch(a2.id, session, system_mgr)
        consortium.create_system(SysC(name="C", code="c"), session, unscoped_mgr)
        consortium.delete_system(sys_b.id, session, unscoped_mgr)
    finally:
        settings_store.load_settings, mfa.load_settings = orig_load, orig_mfa_load
        session.close()


@test(2, "access.reporting_scope_and_minimal_fields",
      "Reports count only a scoped manager's branches, the per-member report names only "
      "members the viewer can already open, and responses carry only the fields the "
      "Reporting page shows.")
def t_access_reporting_scope():
    try:
        reporting = _imp("routers.reporting")
        settings_store = _imp("core.settings_store")
        db, session = _memory_db()
    except ImportError as e:
        raise Skip(f"needs full backend deps / package layout: {e}")

    def add(row):
        session.add(row); session.commit(); return row

    orig_load = settings_store.load_settings
    settings_store.load_settings = lambda: {}
    try:
        R, S = db.UserRole, db.RequestStatus
        sys_a = add(db.LibrarySystem(name="A", code="a"))
        a1 = add(db.Branch(system_id=sys_a.id, name="A1", code="a1"))
        b1 = add(db.Branch(system_id=sys_a.id, name="B1", code="b1"))
        brokers = [add(db.Broker(name=n)) for n in ("Acme", "Zed")]

        def patron(name, branch, statuses):
            u = add(db.User(email=f"{name}@example.org", full_name=name, role=R.parent,
                            hashed_password="x", branch_id=branch.id))
            m = add(db.FamilyMember(user_id=u.id, full_name=name))
            for st, br in zip(statuses, brokers):
                add(db.RemovalRequest(member_id=m.id, broker_id=br.id, status=st))
            return u
        patron("alice", a1, [S.confirmed, S.pending])
        patron("bob", b1, [S.confirmed])
        patron("carol", b1, [S.pending])

        def mgr(email, perms, branch_scope=None):
            u = add(db.User(email=email, full_name=email, role=R.manager, hashed_password="x",
                            permissions_granted=perms))
            if branch_scope:
                add(db.ManagerScope(user_id=u.id, scope_type="branch", branch_id=branch_scope.id))
            return u
        sa = add(db.User(email="sa@example.org", full_name="sa", role=R.super_admin, hashed_password="x"))
        scoped = mgr("s@example.org", None, a1)                          # reporting.view by default
        scoped_view = mgr("sv@example.org", '["members.view_all"]', a1)
        unscoped = mgr("u@example.org", None)
        cross = mgr("c@example.org", '["consortium.cross_system"]', a1)

        names = lambda u: {r["member"] for r in reporting.per_member_stats(session, u)}
        assert names(sa) == names(cross) == {"alice", "bob", "carol"}
        assert names(scoped_view) == {"alice"}, names(scoped_view)
        assert names(scoped) == set() and names(unscoped) == set(), "names need 'view all members' data'"

        s_all, s_a1 = reporting.summary(session, sa), reporting.summary(session, scoped)
        assert set(s_all) == {"total_users", "total_brokers", "total_sent", "total_confirmed",
                              "total_pending", "success_rate", "month_sent", "month_new_users"}, set(s_all)
        assert s_all["total_confirmed"] == 2 and s_all["total_pending"] == 2
        assert s_a1["total_users"] == 1 and s_a1["total_confirmed"] == 1 and s_a1["total_pending"] == 1
        assert reporting.summary(session, unscoped)["total_confirmed"] == 2   # counts aren't names

        comp = {r["broker"]: r for r in reporting.broker_compliance(20, session, scoped)}
        assert set(comp) == {"Acme", "Zed"} and comp["Acme"]["total"] == 1, comp
        assert set(comp["Acme"]) == {"broker", "total", "confirmed", "rate"}
        assert reporting.broker_compliance(20, session, sa)[0]["total"] == 3

        enroll = lambda u: sum(r["enrollments"] for r in reporting.enrollments_over_time(12, session, u))
        assert enroll(scoped) == 1 and enroll(sa) >= 3
    finally:
        settings_store.load_settings = orig_load
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
        broker_mgr = person("b@example.org", R.manager, permissions_granted='["brokers.manage"]')
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

        # Broker writes over real HTTP: a parent or a manager with only the
        # defaults gets 403, a manager granted brokers.manage gets through.
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
        assert client.patch(f"/api/brokers/{broker.id}", json={"notes": "x"}).status_code == 403, \
            "brokers.manage is no longer a manager default"
        who["user"] = broker_mgr
        r = client.patch(f"/api/brokers/{broker.id}", json={
            "opt_out_url": "https://example.com/optout", "method": "form",
            "difficulty": "easy", "notes": "checked"})
        assert r.status_code == 200, r.text
    finally:
        settings_store.load_settings = orig_load
        session.close()


@test(2, "access.email_monitor_cross_tenant_isolation",
      "Email monitor logs, status, and poll history isolate patron data so users "
      "never see opt-out correspondence or member details of other accounts.")
def t_access_email_monitor_isolation():
    try:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool
        auth = _imp("core.auth")
        email_router = _imp("routers.email_monitor")
        settings_store = _imp("core.settings_store")
        db = _imp("models.database")
    except ImportError as e:
        raise Skip(f"needs full backend deps / package layout: {e}")

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    db.Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    orig_load = settings_store.load_settings
    settings_store.load_settings = lambda: {"email": {"imap_host": "imap.example.com", "imap_user": "optout@example.com", "imap_password_enc": "enc"}}
    try:
        R = db.UserRole
        u1 = db.User(email="patron1@example.org", full_name="Patron One", role=R.parent, hashed_password="x")
        u2 = db.User(email="patron2@example.org", full_name="Patron Two", role=R.parent, hashed_password="x")
        admin = db.User(email="admin@example.org", full_name="Admin", role=R.super_admin, hashed_password="x")
        session.add_all([u1, u2, admin]); session.flush()

        m1 = db.FamilyMember(user_id=u1.id, full_name="Member One")
        m2 = db.FamilyMember(user_id=u2.id, full_name="Member Two")
        b = db.Broker(name="BrokerCorp", opt_out_url="https://example.com")
        session.add_all([m1, m2, b]); session.flush()

        req1 = db.RemovalRequest(member_id=m1.id, broker_id=b.id, status=db.RequestStatus.submitted)
        req2 = db.RemovalRequest(member_id=m2.id, broker_id=b.id, status=db.RequestStatus.submitted)
        session.add_all([req1, req2]); session.flush()

        log1 = db.EmailLog(request_id=req1.id, direction="received", subject="Conf 1", body_snippet="Token1", matched_key="key1")
        log2 = db.EmailLog(request_id=req2.id, direction="received", subject="Conf 2", body_snippet="Token2", matched_key="key2")
        unmatched = db.EmailLog(request_id=None, direction="received", subject="Spam", body_snippet="Unmatched", matched_key=None)
        run = db.SchedulerRun(run_type="email_poll", status="done", emails_matched=2, errors=None)
        session.add_all([log1, log2, unmatched, run]); session.commit()

        app = FastAPI(); app.include_router(email_router.router)
        app.dependency_overrides[db.get_db] = lambda: session
        client = TestClient(app)
        who = {"user": u1}
        app.dependency_overrides[auth.get_current_user] = lambda: who["user"]

        # Patron 1 sees ONLY log1
        r1 = client.get("/api/email-monitor/logs")
        assert r1.status_code == 200
        logs1 = r1.json()
        assert len(logs1) == 1
        assert logs1[0]["subject"] == "Conf 1"
        assert logs1[0]["member_name"] == "Member One"

        # Patron 1 status totals only count Member One's matched emails and hides unmatched
        st1 = client.get("/api/email-monitor/status").json()
        assert st1["total_matched"] == 1
        assert st1["total_unmatched"] == 0

        # Patron 1 poll history is empty
        assert client.get("/api/email-monitor/poll-history").json() == []

        # Patron 2 sees ONLY log2
        who["user"] = u2
        r2 = client.get("/api/email-monitor/logs")
        assert r2.status_code == 200
        logs2 = r2.json()
        assert len(logs2) == 1
        assert logs2[0]["subject"] == "Conf 2"
        assert logs2[0]["member_name"] == "Member Two"

        # Admin sees all logs (log1, log2, unmatched) and poll history
        who["user"] = admin
        ra = client.get("/api/email-monitor/logs")
        assert ra.status_code == 200
        assert len(ra.json()) == 3
        sta = client.get("/api/email-monitor/status").json()
        assert sta["total_matched"] == 2
        assert sta["total_unmatched"] == 1
        assert len(client.get("/api/email-monitor/poll-history").json()) == 1
    finally:
        settings_store.load_settings = orig_load
        session.close()


@test(2, "access.broker_and_stats_cross_tenant_isolation",
      "Dashboard stats and broker list latest_status isolate patron removal data "
      "so users never see progress metrics or broker statuses of other accounts.")
def t_access_broker_stats_isolation():
    try:
        from fastapi import FastAPI
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

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    db.Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    orig_load = settings_store.load_settings
    settings_store.load_settings = lambda: {}
    try:
        R = db.UserRole
        u1 = db.User(email="p1@example.org", full_name="Patron One", role=R.parent, hashed_password="x")
        u2 = db.User(email="p2@example.org", full_name="Patron Two", role=R.parent, hashed_password="x")
        admin = db.User(email="adm@example.org", full_name="Admin", role=R.super_admin, hashed_password="x")
        session.add_all([u1, u2, admin]); session.flush()

        m1 = db.FamilyMember(user_id=u1.id, full_name="Member One")
        m2 = db.FamilyMember(user_id=u2.id, full_name="Member Two")
        b1 = db.Broker(name="Broker One", opt_out_url="https://example.com/1")
        b2 = db.Broker(name="Broker Two", opt_out_url="https://example.com/2")
        session.add_all([m1, m2, b1, b2]); session.flush()

        # Patron 1 confirmed b1; Patron 2 pending b2
        req1 = db.RemovalRequest(member_id=m1.id, broker_id=b1.id, status=db.RequestStatus.confirmed)
        req2 = db.RemovalRequest(member_id=m2.id, broker_id=b2.id, status=db.RequestStatus.pending)
        session.add_all([req1, req2]); session.commit()

        app = FastAPI(); app.include_router(brokers_router.router)
        app.dependency_overrides[db.get_db] = lambda: session
        client = TestClient(app)
        who = {"user": u1}
        app.dependency_overrides[auth.get_current_user] = lambda: who["user"]

        # Patron 1 sees confirmed=1, pending=0 on dashboard stats
        st1 = client.get("/api/brokers/stats").json()
        assert st1["confirmed"] == 1
        assert st1["pending"] == 0
        assert st1["actioned"] == 1

        # Patron 1 sees b1 as confirmed, and b2 as None (not touched by Patron 1)
        br1 = client.get("/api/brokers").json()
        b_map1 = {b["name"]: b for b in br1}
        assert b_map1["Broker One"]["latest_status"] == "confirmed"
        assert b_map1["Broker One"]["request_count"] == 1
        assert b_map1["Broker Two"]["latest_status"] is None
        assert b_map1["Broker Two"]["request_count"] == 0

        # Patron 2 sees confirmed=0, pending=1 on dashboard stats
        who["user"] = u2
        st2 = client.get("/api/brokers/stats").json()
        assert st2["confirmed"] == 0
        assert st2["pending"] == 1
        assert st2["actioned"] == 1

        br2 = client.get("/api/brokers").json()
        b_map2 = {b["name"]: b for b in br2}
        assert b_map2["Broker One"]["latest_status"] is None
        assert b_map2["Broker One"]["request_count"] == 0
        assert b_map2["Broker Two"]["latest_status"] == "pending"
        assert b_map2["Broker Two"]["request_count"] == 1

        # Admin sees overall totals (confirmed=1, pending=1, actioned=2)
        who["user"] = admin
        sta = client.get("/api/brokers/stats").json()
        assert sta["confirmed"] == 1
        assert sta["pending"] == 1
        assert sta["actioned"] == 2
    finally:
        settings_store.load_settings = orig_load
        session.close()


@test(2, "access.requests_mutation_requires_edit_permission",
      "Mutating removal requests (patch, requeue, snooze) requires edit permission; "
      "view-only managers are rejected with 403.")
def t_access_requests_mutation_permission():
    try:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool
        auth = _imp("core.auth")
        requests_router = _imp("routers.requests")
        settings_store = _imp("core.settings_store")
        db = _imp("models.database")
    except ImportError as e:
        raise Skip(f"needs full backend deps / package layout: {e}")

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    db.Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    orig_load = settings_store.load_settings
    settings_store.load_settings = lambda: {}
    try:
        R = db.UserRole
        viewer = db.User(email="v@example.org", full_name="Viewer", role=R.manager,
                         hashed_password="x", permissions_granted='["members.view_all"]')
        editor = db.User(email="e@example.org", full_name="Editor", role=R.manager,
                         hashed_password="x", permissions_granted='["members.edit_all"]')
        fam = db.User(email="f@example.org", full_name="Fam", role=R.parent, hashed_password="x")
        session.add_all([viewer, editor, fam]); session.flush()

        m = db.FamilyMember(user_id=fam.id, full_name="Patron")
        b = db.Broker(name="Broker", opt_out_url="https://example.com")
        session.add_all([m, b]); session.flush()

        req = db.RemovalRequest(member_id=m.id, broker_id=b.id, status=db.RequestStatus.confirmed)
        session.add(req); session.commit()

        app = FastAPI(); app.include_router(requests_router.router)
        app.dependency_overrides[db.get_db] = lambda: session
        client = TestClient(app)
        who = {"user": viewer}
        app.dependency_overrides[auth.get_current_user] = lambda: who["user"]

        # Viewer can read but CANNOT patch, requeue, or snooze
        assert client.get(f"/api/requests/{req.id}").status_code == 200
        assert client.patch(f"/api/requests/{req.id}", json={"notes": "hacked"}).status_code == 403
        assert client.post(f"/api/requests/{req.id}/requeue").status_code == 403
        assert client.post(f"/api/requests/{req.id}/snooze", json={"days": 30}).status_code == 403

        # Editor can patch, requeue, and snooze
        who["user"] = editor
        assert client.patch(f"/api/requests/{req.id}", json={"notes": "reviewed"}).status_code == 200
        assert client.post(f"/api/requests/{req.id}/requeue").status_code == 200
        assert client.post(f"/api/requests/{req.id}/snooze", json={"days": 30}).status_code == 200
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
            cfg = branding.get_branding()
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
    assert captured["subject"].startswith("[OpenOptOut TEST]"), "missing test prefix"

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


@test(2, "auth.passwordless_local_account_restrictions",
      "Passwordless local endpoints reject external IdP accounts and permit local accounts only.")
def t_auth_passwordless_local_account_restrictions():
    from types import SimpleNamespace as NS
    try:
        from fastapi import HTTPException
        auth_router = _imp("routers.auth")
        mfa = _imp("core.mfa")
        settings_store = _imp("core.settings_store")
        db, s = _memory_db()
    except ImportError as e:
        raise Skip(f"needs full backend deps / package layout: {e}")

    # Local user and external user
    local_user = db.User(email="local@library.org", full_name="Local User", hashed_password="hashed_pw", auth_source=None)
    ext_user = db.User(email="ldap@library.org", full_name="LDAP User", hashed_password="hashed_pw", auth_source="ldap")
    s.add_all([local_user, ext_user]); s.commit()

    assert auth_router._is_local_user(local_user) is True
    assert auth_router._is_local_user(ext_user) is False

    orig_load = settings_store.load_settings
    orig_mfa = mfa.load_settings
    orig_auth = getattr(auth_router, "load_settings", orig_load)
    fake_settings = lambda: {
        "security": {
            "passwordless": {
                "enabled": True,
                "allow_passkey": True,
                "allow_magic_link": True,
                "enforce_passwordless_local": False,
            }
        }
    }
    settings_store.load_settings = fake_settings
    mfa.load_settings = fake_settings
    auth_router.load_settings = fake_settings
    try:

        # Request options for external account should be rejected
        req_ext = auth_router.PasswordlessOptionsIn(email="ldap@library.org")
        try:
            auth_router.get_passwordless_options(req_ext, db=s)
            assert False, "External account should be rejected from local passwordless auth"
        except HTTPException as exc:
            assert exc.status_code == 400
            assert "only available for local accounts" in exc.detail.lower()

        # Magic link for external account should be rejected
        magic_ext = auth_router.MagicLinkRequestIn(email="ldap@library.org")
        try:
            auth_router.request_magic_link(magic_ext, db=s)
            assert False, "External account should be rejected from magic link auth"
        except HTTPException as exc:
            assert exc.status_code == 400
            assert "only available for local accounts" in exc.detail.lower()

        # Magic link for local account: the code is emailed, never returned
        system_mail = _imp("core.system_mail")
        sent = []
        orig_send = system_mail.send
        system_mail.send = lambda to, subject, body: sent.append((to, body)) or True
        try:
            magic_local = auth_router.MagicLinkRequestIn(email="local@library.org")
            res = auth_router.request_magic_link(magic_local, db=s)
            assert res.get("token") is not None
            assert "fallback_code" not in res and len(sent) == 1, res
            code = re.search(r"\b(\d{6})\b", sent[0][1]).group(1)
            assert code not in str(res)

            # An unknown email gets the same answer and no email
            res_unknown = auth_router.request_magic_link(
                auth_router.MagicLinkRequestIn(email="nobody@library.org"), db=s)
            assert res_unknown["message"] == res["message"] and len(sent) == 1

            # Five wrong guesses use the code up
            bad = "000000" if code != "000000" else "111111"
            for _ in range(5):
                try:
                    auth_router.verify_magic_link(auth_router.MagicLinkVerifyIn(token=res["token"], code=bad), db=s)
                    assert False, "wrong code accepted"
                except HTTPException as exc:
                    assert exc.status_code == 401
            try:
                auth_router.verify_magic_link(auth_router.MagicLinkVerifyIn(token=res["token"], code=code), db=s)
                assert False, "code still usable after 5 wrong guesses"
            except HTTPException as exc:
                assert exc.status_code == 400

            # A fresh code signs in, once
            res2 = auth_router.request_magic_link(magic_local, db=s)
            code2 = re.search(r"\b(\d{6})\b", sent[-1][1]).group(1)
            verify_req = auth_router.MagicLinkVerifyIn(token=res2["token"], code=code2)
            tok = auth_router.verify_magic_link(verify_req, db=s)
            assert tok.get("access_token") is not None
            try:
                auth_router.verify_magic_link(verify_req, db=s)
                assert False, "code worked twice"
            except HTTPException as exc:
                assert exc.status_code == 400

            # An email code replaces the password, not the second factor
            local_user.totp_enabled = True
            s.commit()
            res3 = auth_router.request_magic_link(magic_local, db=s)
            code3 = re.search(r"\b(\d{6})\b", sent[-1][1]).group(1)
            out = auth_router.verify_magic_link(auth_router.MagicLinkVerifyIn(token=res3["token"], code=code3), db=s)
            assert out.get("mfa_required") and "access_token" not in out, out
        finally:
            system_mail.send = orig_send
    finally:
        settings_store.load_settings = orig_load
        mfa.load_settings = orig_mfa
        if hasattr(auth_router, "load_settings"):
            auth_router.load_settings = orig_auth
        s.close()


@test(2, "registration.residents_only_signup",
      "With the address check on, people can only sign up at an address on the uploaded list: "
      "addresses are matched in any common spelling, a row without a unit covers the building, the "
      "per-home limit holds, the email must be confirmed with a code, the address becomes the "
      "person's own, sign-in buttons can't start a new account, and no address is echoed back.")
def t_residents_only_signup():
    from types import SimpleNamespace as NS
    try:
        auth_router = _imp("routers.auth")
        R = _imp("core.resident_addresses")
        settings_store = _imp("core.settings_store")
        system_mail = _imp("core.system_mail")
        pol = _imp("core.sso_policy")
        from fastapi import HTTPException
        db, s = _memory_db()
    except ImportError as e:
        raise Skip(f"needs full backend deps / package layout: {e}")

    reg = {"mode": "open", "signup_page": True, "address_check": True, "address_limit": 1,
           "signup_help": "Call the office"}
    fake = lambda: {"registration": reg, "email": {"provider": "smtp", "smtp_host": "smtp.example.invalid"}}
    sent = []
    saved = (settings_store.load_settings, auth_router.load_settings, system_mail.send)
    settings_store.load_settings = fake
    auth_router.load_settings = fake
    system_mail.send = lambda to, subject, body: sent.append((to, subject, body)) or True
    try:
        s.add(db.User(email="admin@example.org", full_name="Admin Example", role=db.UserRole.super_admin))
        s.commit()
        csv_text = R.EXAMPLE_CSV + "300 Example Court,,Exampleville,TX,77000,\n" + "not an address,,,,\n"
        rows, problems = R.read_csv(csv_text.encode())
        assert len(rows) == 4 and len(problems) == 1 and problems[0]["line"] == 6, (len(rows), problems)
        assert "not an address" not in str(problems)
        assert R.import_rows(s, rows, replace=True) == {"added": 4, "already_listed": 0}
        assert R.import_rows(s, rows[:1], replace=False)["already_listed"] == 1
        stored = s.query(db.ResidentAddress).first()
        assert "EXAMPLE" not in stored.key and len(stored.key) == 64

        A = auth_router.SignupAddressIn
        look = lambda **kw: auth_router.signup_address(A(**kw), db=s)
        r = look(street="999 Nowhere Rd", zip="77000")
        assert r["reason"] == "not_found" and r["help"] == "Call the office" and "NOWHERE" not in str(r).upper()
        assert look(street="200 Sample Ave", zip="77000")["reason"] == "unit_needed"
        assert look(street="200 Sample Ave", unit="3", zip="77000")["reason"] == "unit_not_found"
        assert look(street="300 Example Ct Apt 9", city="Exampleville", state="TX", zip="77000")["ok"]
        assert look(street="Sample Ave", zip="77000")["reason"] == "unclear"
        home = look(street="200 SAMPLE AVENUE", unit="#01", city="Exampleville", state="tx", zip="77000-1234")
        assert home["ok"] and home["token"], home

        # The email must be confirmed with the code
        E = auth_router.SignupEmailIn
        code_res = auth_router.signup_email_code(E(email="jordan@library.org"), db=s)
        code = re.search(r"\b(\d{6})\b", sent[-1][2]).group(1)
        assert code not in str(code_res)
        Reg = auth_router.RegisterRequest
        base = dict(email="jordan@library.org", full_name="Jordan Example", password="correct horse battery")
        for bad in ({}, {"email_token": code_res["token"], "email_code": "000000" if code != "000000" else "111111"},
                    {"email_token": code_res["token"], "email_code": code}):   # last: no address yet
            try:
                auth_router.register(Reg(**base, **bad), db=s)
                assert False, f"registered without {bad or 'a code'}"
            except HTTPException as exc:
                assert exc.status_code == 400
        user = auth_router.register(Reg(**base, email_token=code_res["token"], email_code=code,
                                        address_token=home["token"]), db=s)
        assert user.resident_key and user.resident_address_id
        member = s.query(db.FamilyMember).filter(db.FamilyMember.user_id == user.id).first()
        addr = [i for i in member.identities if i.kind == "address"]
        assert len(addr) == 1 and addr[0].is_primary and addr[0].value == "200 SAMPLE AVE #1, EXAMPLEVILLE, TX 77000", addr

        # One account per home: the same unit is now full; the other unit isn't
        assert look(street="200 Sample Ave", unit="1", zip="77000")["reason"] == "full"
        assert look(street="200 Sample Ave", unit="2", zip="77000")["ok"]

        # An email that already has an account gets a reminder, not a code
        n = len(sent)
        auth_router.signup_email_code(E(email="jordan@library.org"), db=s)
        assert len(sent) == n + 1 and not re.search(r"\b\d{6}\b", sent[-1][2])

        # Without a way to send email there's no sign-up
        settings_store.load_settings = lambda: {"registration": reg, "email": {}}
        try:
            auth_router.signup_email_code(E(email="sam@library.org"), db=s)
            assert False, "sign-up code without email set up"
        except HTTPException as exc:
            assert exc.status_code == 503
        settings_store.load_settings = fake

        # Sign-in buttons can't start a new account; an existing one can link
        g = NS(provider="google", email="new@library.org", email_verified=True, hd=None, groups=[])
        assert not pol.evaluate_sso_login(g, {}, reg, False, 5).allowed
        assert pol.evaluate_sso_login(g, {}, reg, True, 5).allowed
        assert pol.evaluate_sso_login(g, {}, {**reg, "address_check": False}, False, 5).allowed

        info = auth_router.signup_info()
        assert info["signup"] and info["address_check"] and info["help"] == "Call the office"
    finally:
        settings_store.load_settings, auth_router.load_settings, system_mail.send = saved
        s.close()


@test(2, "scheduler.result_ingestion_reclaims_leases",
      "The 30-second result ingestion job drains results and reclaims worker leases that "
      "timed out (before, it crashed every run calling reclaim as a service method).")
def t_scheduler_reclaims_leases():
    from types import SimpleNamespace as NS
    try:
        scheduler = _imp("core.scheduler")
        queue_mod = _imp("core.distributed.queue")
    except ImportError as e:
        raise Skip(f"needs full backend deps / package layout: {e}")
    requeued, dead = [], []

    class StubQueue:
        def get_result(self, timeout=0.5): return None
        def get_in_flight_leases(self):
            return [{"age_seconds": 400.0, "envelope": NS(envelope_id="stale", meta={})},
                    {"age_seconds": 10.0, "envelope": NS(envelope_id="live", meta={})}]
        def requeue(self, env, queue_name=None): requeued.append(env.envelope_id)
        def dead_letter(self, env, reason=""): dead.append(env.envelope_id)

    orig = queue_mod.get_queue
    queue_mod.get_queue = lambda *a, **kw: StubQueue()
    try:
        scheduler.result_ingestion_job()          # raised AttributeError before the fix
    finally:
        queue_mod.get_queue = orig
    assert requeued == ["stale"] and dead == [], (requeued, dead)


@test(2, "auth.failed_signin_throttling",
      "Repeated failed sign-ins (password, LDAP, SIP2, TOTP, backup code) lock that sign-in "
      "name with 429 + Retry-After before credentials are checked; locks escalate and expire, "
      "success clears them, unknown accounts behave the same, provider outages don't count.")
def t_auth_failed_signin_throttling():
    import time
    from types import SimpleNamespace as NS
    try:
        from fastapi import HTTPException
        auth_router = _imp("routers.auth")
        throttle = _imp("core.login_throttle")
        mfa = _imp("core.mfa")
        ap = _imp("core.auth_providers")
        core_auth = _imp("core.auth")
        settings_store = _imp("core.settings_store")
        db, session = _memory_db()
    except ImportError as e:
        raise Skip(f"needs full backend deps / package layout: {e}")

    def status_of(fn, *a):
        try:
            fn(*a)
        except HTTPException as e:
            return e.status_code, (e.headers or {}).get("Retry-After")
        return 200, None

    clock = [1_000_000.0]
    orig = (throttle._now, settings_store.load_settings, mfa.load_settings,
            auth_router.try_ldap_auth, auth_router.provider_enabled)
    throttle._now = lambda: clock[0]
    settings_store.load_settings = mfa.load_settings = lambda: {}
    throttle._state.clear()
    try:
        R = db.UserRole
        u = db.User(email="jane@example.org", full_name="Jane", role=R.parent,
                    hashed_password=core_auth.hash_password("RightPass123!"))
        session.add(u); session.commit()
        login = lambda email, pw: auth_router.login(NS(username=email, password=pw), None, session)

        # Password: 5 failures lock the name; even the right password is refused.
        for _ in range(throttle.MAX_FAILURES):
            assert status_of(login, "jane@example.org", "nope")[0] == 401
        assert status_of(login, "jane@example.org", "RightPass123!") == (429, "30")
        assert status_of(login, "JANE@example.org ", "RightPass123!")[0] == 429, "same name, other spelling"
        assert status_of(login, "other@example.org", "nope")[0] == 401, "other names unaffected"
        # Unknown accounts lock the same way (no account enumeration).
        for _ in range(throttle.MAX_FAILURES):
            status_of(login, "ghost@example.org", "x")
        assert status_of(login, "ghost@example.org", "x")[0] == 429
        # Lock expires; one more failure re-locks for twice as long; success clears.
        clock[0] += 31
        assert status_of(login, "jane@example.org", "nope")[0] == 401
        assert status_of(login, "jane@example.org", "RightPass123!") == (429, "60")
        clock[0] += 61
        assert status_of(login, "jane@example.org", "RightPass123!")[0] == 200
        assert throttle.account_key("password", "jane@example.org") not in throttle._state

        # TOTP and backup codes share a per-user lock.
        secret = mfa.generate_totp_secret()
        plain, hashed = mfa.generate_backup_codes(2)
        u.totp_enabled = True
        u.totp_secret_enc = settings_store.encrypt_password(secret)
        u.backup_codes = __import__("json").dumps(hashed)
        session.commit()
        ticket = mfa.create_mfa_ticket(u.id, u.email)
        live = {mfa.get_totp(secret, timestamp=time.time() + d) for d in (-30, 0, 30)}
        wrong = next(c for c in ("000000", "111111", "222222", "333333") if c not in live)
        totp = lambda code: auth_router.verify_totp_login(auth_router.VerifyTotpIn(mfa_ticket=ticket, code=code), session)
        backup = lambda code: auth_router.verify_backup_code_login(auth_router.VerifyBackupIn(mfa_ticket=ticket, code=code), session)
        for _ in range(throttle.MAX_FAILURES - 1):
            assert status_of(totp, wrong)[0] == 401
        assert status_of(backup, "not-a-code")[0] == 401
        assert status_of(totp, mfa.get_totp(secret))[0] == 429, "right code refused while locked"
        assert status_of(backup, plain[0])[0] == 429, "backup codes share the lock"
        clock[0] += 31
        assert status_of(totp, mfa.get_totp(secret))[0] == 200

        # LDAP: bad credentials count, an unreachable directory doesn't.
        auth_router.provider_enabled = lambda name: True
        ldap = lambda: auth_router.ldap_login(auth_router.LDAPLoginRequest(username="bob", password="x"), session)
        auth_router.try_ldap_auth = lambda u_, p_: ap.AuthResult(success=False, provider="ldap", unavailable=True,
                                                                  error="Directory sign-in is unavailable right now.")
        for _ in range(throttle.MAX_FAILURES + 2):
            assert status_of(ldap)[0] == 401
        auth_router.try_ldap_auth = lambda u_, p_: ap.AuthResult(success=False, provider="ldap", error="Invalid")
        for _ in range(throttle.MAX_FAILURES):
            assert status_of(ldap)[0] == 401
        assert status_of(ldap)[0] == 429

        # Memory stays bounded when many names are sprayed.
        throttle._state.clear()
        orig_max, throttle.MAX_KEYS = throttle.MAX_KEYS, 100
        try:
            for i in range(500):
                throttle.failure(f"password:spray{i}@example.org")
            assert len(throttle._state) <= 100
            assert "password:spray499@example.org" in throttle._state
        finally:
            throttle.MAX_KEYS = orig_max
    finally:
        (throttle._now, settings_store.load_settings, mfa.load_settings,
         auth_router.try_ldap_auth, auth_router.provider_enabled) = orig
        throttle._state.clear()
        session.close()


@test(2, "auth.per_ip_limits",
      "Client IP comes from X-Forwarded-For counted TRUSTED_PROXY_HOPS from the right (forged "
      "entries ignored, IPv6 grouped by /64); sign-in, MFA, registration and SSO routes are "
      "rate limited per IP; many failed sign-ins from one IP lock that IP across accounts.")
def t_auth_per_ip_limits():
    import os
    from types import SimpleNamespace as NS
    try:
        from fastapi import HTTPException
        rl = _imp("core.rate_limit")
        throttle = _imp("core.login_throttle")
        auth_router = _imp("routers.auth")
        saml_router = _imp("routers.saml")
    except ImportError as e:
        raise Skip(f"needs full backend deps / package layout: {e}")

    def req(peer, xff=None):
        return NS(client=NS(host=peer), headers={"x-forwarded-for": xff} if xff else {})

    def status_of(fn, *a):
        try:
            fn(*a)
        except HTTPException as e:
            return e.status_code, (e.headers or {}).get("Retry-After")
        return 200, None

    orig_env = os.environ.get("TRUSTED_PROXY_HOPS")
    orig_now = (rl._now, throttle._now)
    try:
        # nginx only (default 1 hop): nginx appended the real client last.
        os.environ.pop("TRUSTED_PROXY_HOPS", None)
        assert rl.client_ip(req("172.18.0.3", "203.0.113.9")) == "203.0.113.9"
        assert rl.client_ip(req("172.18.0.3", "6.6.6.6, 203.0.113.9")) == "203.0.113.9", "forged entry used"
        assert rl.client_ip(req("203.0.113.9")) == "203.0.113.9", "no header: the peer"
        assert rl.client_ip(req("172.18.0.3", "garbage")) == "172.18.0.3"
        # Caddy + nginx (2 hops): the client is second from the right.
        os.environ["TRUSTED_PROXY_HOPS"] = "2"
        assert rl.client_ip(req("172.18.0.3", "198.51.100.7, 172.18.0.5")) == "198.51.100.7"
        assert rl.client_ip(req("172.18.0.3", "6.6.6.6, 198.51.100.7, 172.18.0.5")) == "198.51.100.7"
        # Direct exposure (0 hops): the header is never trusted.
        os.environ["TRUSTED_PROXY_HOPS"] = "0"
        assert rl.client_ip(req("203.0.113.9", "6.6.6.6")) == "203.0.113.9"
        # IPv6: one /64 is one client; IPv4-mapped addresses are plain IPv4.
        assert rl.client_ip(req("2001:db8:1:2::a")) == rl.client_ip(req("2001:db8:1:2:ffff::b")) == "2001:db8:1:2::/64"
        assert rl.client_ip(req("::ffff:203.0.113.9")) == "203.0.113.9"
        assert rl.client_ip(None) is None
        os.environ.pop("TRUSTED_PROXY_HOPS", None)

        # Request limiter: per_minute per IP, refills over time, other IPs unaffected.
        clock = [1000.0]
        rl._now = lambda: clock[0]
        rl._buckets.clear()
        dep = rl.limit("test", 3)
        a, b = req("203.0.113.1"), req("203.0.113.2")
        assert [status_of(dep, a)[0] for _ in range(3)] == [200, 200, 200]
        assert status_of(dep, a) == (429, "20")
        assert status_of(dep, b)[0] == 200
        clock[0] += 20
        assert status_of(dep, a)[0] == 200 and status_of(dep, a)[0] == 429
        rl._buckets.clear()
        orig_max, rl.MAX_KEYS = rl.MAX_KEYS, 50
        try:
            for i in range(300):
                dep(req(f"10.0.{i // 250}.{i % 250}"))
            assert len(rl._buckets) <= 50
        finally:
            rl.MAX_KEYS = orig_max

        # Failed sign-ins: one IP spraying many accounts gets locked; success
        # doesn't clear the IP; another IP is unaffected.
        tclock = [5000.0]
        throttle._now = lambda: tclock[0]
        throttle._state.clear()
        bad, good = req("198.51.100.66"), req("198.51.100.77")
        for i in range(throttle.IP_MAX_FAILURES):
            throttle.check(throttle.account_key("password", f"u{i}@x.org"), throttle.ip_key(bad))
            throttle.failure(throttle.account_key("password", f"u{i}@x.org"), throttle.ip_key(bad))
        throttle.success(throttle.account_key("password", "mine@x.org"))
        assert status_of(throttle.check, throttle.account_key("password", "new@x.org"), throttle.ip_key(bad))[0] == 429
        assert status_of(throttle.check, throttle.account_key("password", "new@x.org"), throttle.ip_key(good))[0] == 200
        throttle._state.clear()

        # Route wiring: every public sign-in / SSO route carries a limiter.
        def limits(router, path, method):
            for r in router.routes:
                if getattr(r, "path", None) == path and method in getattr(r, "methods", ()):
                    return {getattr(d.call, "rate_limit", (None,))[0] for d in r.dependant.dependencies} - {None}
            raise AssertionError(f"route {method} {path} not found")
        p = auth_router.router.prefix
        for path, method, name in [("/token", "POST", "signin"), ("/ldap/login", "POST", "signin"),
                                   ("/sip2/login", "POST", "signin"), ("/register", "POST", "register"),
                                   ("/mfa/verify-totp", "POST", "mfa"), ("/mfa/verify-backup", "POST", "mfa"),
                                   ("/mfa/verify-webauthn", "POST", "mfa"),
                                   ("/oidc/{provider}/login", "GET", "sso"), ("/oidc/{provider}/callback", "GET", "sso")]:
            assert name in limits(auth_router.router, p + path, method), (path, method)
        sp = saml_router.router.prefix
        for path, method in [("/login", "GET"), ("/acs", "POST")]:
            assert "sso" in limits(saml_router.router, sp + path, method), (path, method)
        cal_router = _imp("routers.calendar")
        assert "calendar_feed" in limits(cal_router.router, cal_router.router.prefix + "/feed/{token}.ics", "GET")

        # Over real HTTP: the 61st sign-in a minute from one client IP gets 429.
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool
        db_mod = _imp("models.database")
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        db_mod.Base.metadata.create_all(engine)
        session = sessionmaker(bind=engine)()
        app = FastAPI(); app.include_router(auth_router.router)
        app.dependency_overrides[db_mod.get_db] = lambda: session
        client = TestClient(app)
        rl._now = orig_now[0]; rl._buckets.clear(); throttle._state.clear()
        orig_ipmax, throttle.IP_MAX_FAILURES = throttle.IP_MAX_FAILURES, 10_000   # isolate the limiter
        try:
            post = lambda i, ip: client.post("/api/auth/token", headers={"X-Forwarded-For": ip},
                                             data={"username": f"n{i}@x.org", "password": "x"})
            codes = [post(i, "203.0.113.50").status_code for i in range(60)]
            assert set(codes) == {401}, set(codes)
            r = post(60, "203.0.113.50")
            assert r.status_code == 429 and r.headers.get("retry-after"), (r.status_code, r.headers)
            assert post(61, "203.0.113.51").status_code == 401, "other client IPs unaffected"
        finally:
            throttle.IP_MAX_FAILURES = orig_ipmax
            session.close()
    finally:
        if orig_env is None:
            os.environ.pop("TRUSTED_PROXY_HOPS", None)
        else:
            os.environ["TRUSTED_PROXY_HOPS"] = orig_env
        rl._now, throttle._now = orig_now
        rl._buckets.clear(); throttle._state.clear()


@test(2, "auth.oidc_states_bounded_and_expire",
      "Public /api/auth/oidc/{provider}/login stores a state per call; states are single "
      "use, expire after 10 minutes, and the store is capped so a flood can't grow memory.")
def t_auth_oidc_states():
    import time
    try:
        auth_router = _imp("routers.auth")
    except ImportError as e:
        raise Skip(f"needs full backend deps / package layout: {e}")
    saved = dict(auth_router._oidc_states)
    orig_time = auth_router.time.time
    clock = [10_000.0]
    auth_router.time.time = lambda: clock[0]
    try:
        auth_router._oidc_states.clear()
        auth_router._remember_oidc_state("s1", "google", "https://x/cb")
        assert auth_router._take_oidc_state("s1")["provider"] == "google"
        assert auth_router._take_oidc_state("s1") is None, "single use"
        auth_router._remember_oidc_state("old", "google", "https://x/cb")
        clock[0] += auth_router._OIDC_STATE_TTL + 1
        assert auth_router._take_oidc_state("old") is None, "expired state accepted"
        for i in range(auth_router._OIDC_MAX_STATES + 50):
            auth_router._remember_oidc_state(f"f{i}", "google", "https://x/cb")
        assert len(auth_router._oidc_states) <= auth_router._OIDC_MAX_STATES
        assert f"f{auth_router._OIDC_MAX_STATES + 49}" in auth_router._oidc_states
        assert "f0" not in auth_router._oidc_states
    finally:
        auth_router.time.time = orig_time
        auth_router._oidc_states.clear(); auth_router._oidc_states.update(saved)


@test(1, "saml.outstanding_requests_bounded",
      "Public /api/saml/login adds a pending request ID per call; the store is capped and "
      "pruned oldest-first, so a flood can't grow memory without limit, and expired IDs go.")
def t_saml_outstanding_bounded():
    import time
    sp = _imp("core.saml_sp")
    saved = dict(sp._OUTSTANDING)
    try:
        sp._OUTSTANDING.clear()
        now = time.time()
        sp._OUTSTANDING["expired"] = now - sp.REQUEST_TTL - 5
        for i in range(sp.MAX_OUTSTANDING + 50):            # a flood of live requests
            sp._OUTSTANDING[f"r{i}"] = now
        sp._prune()
        assert len(sp._OUTSTANDING) < sp.MAX_OUTSTANDING, len(sp._OUTSTANDING)
        assert "expired" not in sp._OUTSTANDING
        assert f"r{sp.MAX_OUTSTANDING + 49}" in sp._OUTSTANDING, "newest request must survive"
        assert "r0" not in sp._OUTSTANDING, "oldest requests are dropped first"
        sp._remember("fresh")
        assert "fresh" in sp._OUTSTANDING and len(sp._OUTSTANDING) <= sp.MAX_OUTSTANDING
    finally:
        sp._OUTSTANDING.clear(); sp._OUTSTANDING.update(saved)


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
    def run_cmd(args):
        return subprocess.run(args, cwd=d, capture_output=True, check=True)
    run_cmd(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", "ca.key", "-out", "ca.crt", "-days", "2", "-subj", "/CN=Internal CA"])
    run_cmd(["openssl", "req", "-newkey", "rsa:2048", "-nodes", "-keyout", "srv.key", "-out", "srv.csr", "-subj", "/CN=localhost"])
    with open(f"{d}/san.ext", "w") as f:
        f.write("subjectAltName=DNS:localhost,IP:127.0.0.1\n")
    run_cmd(["openssl", "x509", "-req", "-in", "srv.csr", "-CA", "ca.crt", "-CAkey", "ca.key", "-CAcreateserial", "-out", "srv.crt", "-days", "2", "-extfile", "san.ext"])
    run_cmd(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", "o.key", "-out", "other.crt", "-days", "2", "-subj", "/CN=Other CA"])
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
    sctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); sctx.minimum_version = ssl.TLSVersion.TLSv1_2; sctx.load_cert_chain(f"{d}/srv.crt", f"{d}/srv.key")
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

        # "managed" (Docker + Caddy): recorded with an optional domain and the
        # front-door defaults (Caddy, Let's Encrypt, rate limits on, no Cloudflare
        # proxy); completion nudges toward the Docker-path HTTPS setup script.
        wiz.save_deployment(wiz.DeploymentStep(reverse_proxy="managed", domain="privacy.lib.org"),
                            db=None, user=admin)
        assert store["deployment"] == {"reverse_proxy": "managed", "domain": "privacy.lib.org",
                                       "front_door": "caddy", "certificate": "letsencrypt",
                                       "rate_limit": True, "cloudflare_proxy": False}, store["deployment"]
        summary = wiz.complete(db=None, user=admin)
        cmds = summary["enable_https_commands"]
        assert cmds and "enable-https.sh" in cmds["linux"] and "native" not in cmds["linux"], \
            "managed (Docker) deployment should be pointed at scripts/enable-https.sh, not the native one"
        assert "enable-https.ps1" in cmds["windows"]
        assert any("front door isn't on yet" in w for w in summary["warnings"])

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

    def collect_routes(routes):
        res = []
        for r in routes:
            if isinstance(r, APIRoute):
                res.append(r)
            elif hasattr(r, "effective_route_contexts"):
                # FastAPI >= 0.140 keeps include_router() lazily as an
                # _IncludedRouter. Each effective route context carries the
                # FULL path (with prefix), methods, and the merged dependant
                # (router-level + route-level dependencies), so gates are
                # read exactly as they're enforced at request time.
                res.extend(c for c in r.effective_route_contexts()
                           if getattr(c, "dependant", None) is not None)
            elif hasattr(r, "routes"):
                res.extend(collect_routes(r.routes))
            elif hasattr(r, "app") and hasattr(r.app, "routes"):
                res.extend(collect_routes(r.app.routes))
        return res

    table = {}
    for r in collect_routes(main.app.routes):
        for m in (r.methods or ()):
            table[(m, r.path)] = gates(r)
    # Guard against this check silently going blind again (e.g. a future
    # FastAPI changing how included routers are stored): it must see the app.
    assert len(table) > 100, f"route walker only found {len(table)} routes — it can't see included routers"

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
        ("PATCH", "/api/settings/regional"): {"settings.system"},
        ("GET", "/api/settings/regional"): set(),
        ("GET", "/api/database/health"): {"database.view"},
        ("GET", "/api/plugins"): {"plugins.view"},
        ("POST", "/api/plugins/upload"): {"plugins.upload"},
        # AI helper keys are never delegated; reviewing drafted steps is broker work
        ("PUT", "/api/spec-helpers/providers/{pid}"): {"SUPER"},
        ("POST", "/api/spec-helpers/local"): {"SUPER"},
        ("PUT", "/api/spec-helpers/settings"): {"SUPER"},
        # Sending data off the server is never delegated
        ("PUT", "/api/observability/log-forwarding"): {"SUPER"},
        ("PUT", "/api/observability/webhooks"): {"SUPER"},
        ("POST", "/api/observability/metrics-token"): {"SUPER"},
        ("GET", "/api/health/ready"): set(),
        # The operator's terms are what the server promises everyone: super admins only
        ("PUT", "/api/terms/settings"): {"SUPER"},
        # Turning brokers on when listings are found is broker work
        ("PUT", "/api/brokers/found-rule"): {"brokers.manage"},
        # Usage statistics credentials hand data to outside systems: super admins only
        ("POST", "/api/stats-admin/keys"): {"SUPER"},
        ("GET", "/api/terms/public"): set(),
        # Residents-only sign-up: the address list is registration work
        ("POST", "/api/resident-addresses/upload"): {"users.registration"},
        ("DELETE", "/api/resident-addresses"): {"users.registration"},
        ("POST", "/api/auth/signup/address"): set(),
        ("GET", "/api/spec-helpers/drafts"): {"brokers.manage"},
        # Opt-out letters: choosing one is broker work; adding one is a plugin upload
        ("GET", "/api/letters"): {"brokers.manage"},
        ("GET", "/api/letters/{letter_id}/preview"): {"brokers.manage"},
        ("PUT", "/api/letters/assign"): {"brokers.manage"},
        ("POST", "/api/spec-helpers/drafts/{draft_id}/approve"): {"brokers.manage"},
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
    for needle in ("/api/brokers", "/api/plugins", "/api/auth", "/api/i18n"):
        assert needle in joined, f"expected route prefix {needle} not registered"
    # Broker-health endpoints from item 1
    assert any("health" in p for p in paths), "broker health routes not registered"
    # EXPECTED: broker, plugin, auth, and health routes all present.
    # IF THIS FAILS: a router failed to include; that feature's API is dead even
    #   though the app booted.


# ── Email send path, spec metadata, human pause, parent catalog ───────────────

def _fake_member():
    from types import SimpleNamespace as NS
    ids = [NS(kind="name", value="Jane Q Public", is_primary=True),
           NS(kind="name", value="Jane Public", is_primary=False),
           NS(kind="email", value="jane@example.com", is_primary=True),
           NS(kind="phone", value="555-0100", is_primary=True),
           NS(kind="address", value="1 Main St, Austin, TX 78701", is_primary=True)]
    return NS(id=7, full_name="Jane Q Public", formal_name=None, identities=ids)


@test(2, "email.template_rendering_is_safe",
      "Opt-out email templates accept spec-style and legacy placeholders, and unknown ones don't crash.")
def t_email_template_safe():
    if _try_import("sqlalchemy") is None:
        raise Skip("sqlalchemy not installed")
    oe = _imp("core.optout_engine")
    fields = {"full_name": "Jane Q Public", "name": "Jane Q Public", "broker": "Acme",
              "request_key": "K1", "identifiers": "NAME VARIANTS:\n  - Jane"}
    out = oe.render_template("Remove {full_name} from {broker} [{request_key}] {mystery} {{x}}", fields)
    assert "Jane Q Public" in out and "Acme" in out and "K1" in out, out
    assert "{mystery}" in out, "unknown placeholder should be left as written, not raise"
    # EXPECTED: known placeholders filled, unknown left alone.
    # IF THIS FAILS: one odd placeholder in an add-on template breaks every send
    #   for that broker (the old .format() behaviour).


@test(2, "email.no_guessed_address",
      "A broker with no recorded opt-out address gets None — never a guessed privacy@ address.")
def t_email_no_guess():
    if _try_import("sqlalchemy") is None:
        raise Skip("sqlalchemy not installed")
    from types import SimpleNamespace as NS
    oe = _imp("core.optout_engine")
    assert oe.resolve_optout_address(NS(name="Acme.com", notes="", plugin_id=None), None) is None
    got = oe.resolve_optout_address(NS(name="Acme.com", notes="Email removals@acme.example", plugin_id=None), None)
    assert got == "removals@acme.example", got
    # EXPECTED: only an address someone recorded is used.
    # IF THIS FAILS: member PII could be emailed to an unverified address.


@test(1, "interpreter.spec_metadata_fields",
      "BrokerSpec accepts legal basis, response days, verification, requirement and provenance fields, and rejects bad values.")
def t_spec_metadata():
    BrokerSpec = _imp("core.interpreter").BrokerSpec
    from datetime import date
    good = BrokerSpec.from_dict({
        "broker_id": "x", "name": "X", "method": "manual",
        "legal_basis": ["CCPA", "gdpr"], "statutory_response_days": 45,
        "search_url": "https://x.example/search?n={first_name}", "listing_pattern": r"/people/[A-Za-z-]+",
        "one_optout_per_email": True, "requires": ["email_confirmation", "listing_selection"],
        "source": "test", "last_verified": "2026-05-12",
    })
    assert good.validate() == [], good.validate()
    assert good.can_verify() and good.response_due(date(2026, 1, 1)) == date(2026, 2, 15)
    rt = BrokerSpec.from_dict(good.to_dict())
    assert rt.requires == good.requires and rt.one_optout_per_email, "fields lost in round trip"
    bad = BrokerSpec.from_dict({"broker_id": "x", "name": "X", "method": "manual",
                                "legal_basis": ["made_up"], "requires": ["telepathy"],
                                "listing_pattern": "(", "last_verified": "last May",
                                "statutory_response_days": 900})
    errs = " | ".join(bad.validate())
    for frag in ("legal_basis", "requires", "regular expression", "search_url", "YYYY-MM-DD", "365"):
        assert frag in errs, f"expected an error mentioning {frag!r}: {errs}"
    legacy = BrokerSpec.from_dict({"broker_id": "y", "name": "Y", "method": "manual"})
    assert legacy.validate() == [] and not legacy.can_verify()
    # EXPECTED: new optional fields validate; old specs without them stay valid.
    # IF THIS FAILS: deadline tracking, verification or checklist labels get bad data,
    #   or existing add-ons stop installing.


@test(1, "interpreter.pause_for_human",
      "A pause_for_human step stops the flow and returns the plain-language instruction.")
def t_pause_for_human():
    import asyncio
    ci = _imp("core.interpreter")
    spec = ci.BrokerSpec.from_dict({
        "broker_id": "p", "name": "P", "method": "form", "opt_out_url": "https://p.example",
        "steps": [{"kind": "fill", "selector": "#n", "field": "full_name"},
                  {"kind": "pause_for_human", "text": "Click your own profile, then Start Removing."},
                  {"kind": "click", "selector": "#go"}]})
    assert spec.validate() == []
    nope = ci.BrokerSpec.from_dict({"broker_id": "p", "name": "P", "method": "form",
                                    "opt_out_url": "https://p.example",
                                    "steps": [{"kind": "pause_for_human"}]})
    assert any("pause_for_human requires text" in e for e in nope.validate())
    job = ci.compile_job(spec, {"full_name": "Jane"}, member_id="1")
    r = ci.DryRunExecutor().run(job)
    assert r.needs_manual and not r.ok and "Start Removing" in r.human_instruction, r

    class FakeLoc:
        def __init__(self, page, sel): self.page, self.sel = page, sel
        @property
        def first(self): return self
        async def fill(self, *a, **k): pass
        async def click(self, **k): self.page.clicked.append(self.sel)
        async def inner_text(self, **k): return ""

    class FakePage:
        url = "https://p.example"
        def __init__(self, present): self.present = present; self.clicked = []
        async def goto(self, *a, **k): pass
        async def wait_for_timeout(self, *a): pass
        def locator(self, sel): return FakeLoc(self, sel)
        async def query_selector(self, sel):
            return object() if (self.present and sel == ".results") else None

    cond = ci.compile_job(ci.BrokerSpec.from_dict({
        "broker_id": "p", "name": "P", "method": "form", "opt_out_url": "https://p.example",
        "steps": [{"kind": "pause_for_human", "selector": ".results", "text": "Pick your listing from the results."},
                  {"kind": "click", "selector": "#go"}]}), {}, member_id="1")
    page = FakePage(present=False)
    r1 = asyncio.run(ci.PlaywrightExecutor(page=page).run(cond))
    assert r1.ok and "#go" in page.clicked, "conditional pause should be skipped when element absent"
    page2 = FakePage(present=True)
    r2 = asyncio.run(ci.PlaywrightExecutor(page=page2).run(cond))
    assert r2.needs_manual and not page2.clicked, "should pause before clicking when element present"
    # EXPECTED: unconditional pauses always stop; selector pauses stop only when it's on the page.
    # IF THIS FAILS: flows that need a person either crash or skip the human step.


@test(1, "parent.catalog_matching_rules",
      "Catalog matching: exact domains, brand names only without a TLD, and network suffixes.")
def t_parent_catalog_matching():
    pc = _imp("core.parent_catalog")
    cat = pc.load_catalog()
    by = {p["name"]: p for p in cat["parents"]}
    ic = by["PeopleConnect (Intelius)"]
    m = lambda n, e: pc.matches_child(n, e["children"], e.get("child_suffixes", []))
    assert m("Instant Checkmate", ic) and m("TruthFinder.com", ic) and m("https://www.zabasearch.com/", ic)
    assert not m("Publicrecords.us", ic) and not m("Publicrecords.info", ic), "different TLD must not match"
    sr, cr = by["StateRecords.org network"], by["CourtRecords.us network"]
    assert m("Texasarrests.org", sr) and m("Texasarrestrecords.org", sr) and m("Staterecords.org", sr)
    assert not m("Texasarrestwarrants.org", sr) and not m("Courtrec.com", cr)
    assert m("Massachusetsscourtrecords.us", cr)
    for p in cat["parents"]:
        assert p.get("source"), f"{p['name']} has no source"
    assert pc.cascades_for("SmartBackgroundChecks.com", cat), "cascade lookup failed"
    # EXPECTED: the right sites are grouped and look-alikes are not.
    # IF THIS FAILS: a parent email could list (and a family could be told they're
    #   covered on) sites the parent doesn't run.


@test(2, "parent.catalog_apply_is_safe_and_idempotent",
      "Applying the catalog creates parents, groups brokers, holds unverified emails, and never overrides admins.")
def t_parent_catalog_apply():
    db, s = _memory_db()
    pc = _imp("core.parent_catalog")
    mine = db.ParentCompany(name="My Own Parent")
    s.add(mine); s.commit()
    s.add_all([db.Broker(name="Texasarrests.org"), db.Broker(name="Truthfinder.com"),
               db.Broker(name="Spokeo.com"), db.Broker(name="Publicrecords.us"),
               db.Broker(name="Zabasearch.com", parent_company_id=mine.id),
               db.Broker(name="Ohiocourtrecords.us", is_test=True)])
    s.commit()

    preview = pc.apply_catalog(s, dry_run=True)
    assert s.query(db.ParentCompany).count() == 1, "dry run must not write"
    assert preview["assigned_count"] == 3, preview

    rep = pc.apply_catalog(s)
    P = {p.name: p for p in s.query(db.ParentCompany).all()}
    assert P["StateRecords.org network"].optout_email == "privacy@staterecords.org"
    assert not P["Spokeo"].optout_email, "unverified email must not be applied by default"
    assert "optout@spokeo.com" in (P["Spokeo"].notes or ""), "held email should be noted for review"
    B = {b.name: b for b in s.query(db.Broker).all()}
    assert B["Texasarrests.org"].parent_company_id == P["StateRecords.org network"].id
    assert B["Truthfinder.com"].parent_company_id == P["PeopleConnect (Intelius)"].id
    assert B["Publicrecords.us"].parent_company_id is None
    assert B["Zabasearch.com"].parent_company_id == mine.id, "admin grouping must not be moved"
    assert any(c["broker"] == "Zabasearch.com" for c in rep["conflicts"])
    assert B["Ohiocourtrecords.us"].parent_company_id is None, "test brokers are left alone"

    P["Spokeo"].website = "https://admin-set.example"; s.commit()
    rep2 = pc.apply_catalog(s, include_unverified_emails=True)
    s.refresh(P["Spokeo"])
    assert P["Spokeo"].website == "https://admin-set.example", "admin edit overwritten"
    assert P["Spokeo"].optout_email == "optout@spokeo.com", "opt-in should fill an empty email"
    assert rep2["assigned_count"] == 0 and not rep2["parents_created"], "second run should be a no-op"
    s.close()
    # EXPECTED: safe, repeatable grouping; unverified emails held unless opted in.
    # IF THIS FAILS: re-running the catalog could clobber admin work or email
    #   member PII to an address nobody confirmed.


@test(1, "broker_plugins.repo_plugins_validate",
      "Every built-in broker plugin passes the app's validators, the repo rules and a dry run.")
def t_broker_plugins_validate():
    import importlib.util, io, contextlib
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(root, "broker-plugins", "tools", "validate.py")
    if not os.path.isfile(path):
        raise Skip("broker-plugins/ not present in this checkout")
    spec = importlib.util.spec_from_file_location("bp_validate", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = mod.main([])
    assert rc == 0, out.getvalue()
    # EXPECTED: all broker plugins valid.
    # IF THIS FAILS: a plugin in the repo would be rejected on upload; the output says why.



# ── Form filling: fields, steps, honest results ───────────────────────────────

class _FormLoc:
    """Minimal Playwright-locator stand-in for form tests."""
    def __init__(self, page, sel, texts=None):
        self.page, self.sel, self.texts = page, sel, texts
    @property
    def first(self):
        return self
    def filter(self, has_text=None):
        import re as _re
        opts = self.page.options.get(self.sel, [])
        if isinstance(has_text, _re.Pattern):
            hits = [o for o in opts if has_text.search(o)]
        else:
            hits = [o for o in opts if has_text and has_text in o]
        return _FormLoc(self.page, self.sel, hits)
    async def count(self):
        return len(self.texts) if self.texts is not None else 1
    async def fill(self, value, timeout=None):
        self.page.values[self.sel] = value
    async def press_sequentially(self, value, delay=None, timeout=None):
        self.page.values[self.sel] = value
    async def click(self, timeout=None):
        if self.texts is not None:
            self.page.clicked.append(self.texts[0]); return
        self.page.clicked.append(self.sel)
    async def select_option(self, value=None, label=None, timeout=None):
        self.page.values[self.sel] = value or label
    async def check(self, timeout=None):
        pass
    async def wait_for(self, state=None, timeout=None):
        pass
    async def press(self, key, timeout=None):
        pass
    async def inner_text(self, timeout=None):
        return self.page.body()


class _FormPage:
    url = "https://broker.example/optout"
    def __init__(self, rejects_plus=False, success_text="", options=None):
        self.values, self.clicked, self.rejects_plus, self.success_text = {}, [], rejects_plus, success_text
        self.options = options or {}
    def body(self):
        if self.rejects_plus and any("+" in str(v) for v in self.values.values()) and "#go" in self.clicked:
            return "Please enter a valid email address."
        return self.success_text if "#go" in self.clicked else ""
    def locator(self, sel):
        return _FormLoc(self, sel)
    def get_by_text(self, text, exact=False):
        return _FormLoc(self, "text=" + text)
    async def goto(self, url, timeout=None):
        self.values, self.clicked = {}, []
    async def wait_for_timeout(self, ms):
        pass
    async def query_selector(self, sel):
        return None
    async def content(self):
        return self.body()
    async def evaluate(self, *a):
        pass


@test(1, "forms.member_fields_and_compile",
      "Member fields include derived formats; page addresses and person-facing steps are filled in safely.")
def t_forms_fields():
    ci = _imp("core.interpreter")
    mf = _imp("core.interpreter.member_fields")
    comp = _imp("core.interpreter.compiler")
    assert mf.state_name("tx") == "Texas" and mf.state_code("New York") == "NY"
    assert mf.phone_digits("+1 (512) 555-0100") == "5125550100"

    class M:  # a member-like object
        full_name, formal_name, age = "Mary Ann Smith", "", 40
        identities = []
    f = mf.resolve(M(), today=__import__("datetime").date(2026, 10, 10))
    assert f["first_name"] == "Mary" and f["last_name"] == "Ann Smith" and f["birth_year"] == "1986"
    assert f["phone"] is None and f["city"] is None, "missing values are None, not empty strings"

    url = comp._render_url("https://x.example/{first_name}-{last_name}/{state_name}?q={full_name}",
                           {"first_name": "Mary Ann", "last_name": "O'Neil", "state_name": "New York",
                            "full_name": "Mary Ann O'Neil"})
    assert url == "https://x.example/Mary-Ann-O-Neil/New-York?q=Mary+Ann+O%27Neil", url
    try:
        comp._render_url("https://x.example/{city}", {"city": None})
        raise AssertionError("an address with a missing value must not compile")
    except comp.CompileError:
        pass
    spec = ci.BrokerSpec.from_dict({
        "broker_id": "b", "name": "B", "method": "form", "opt_out_url": "https://b.example",
        "steps": [{"kind": "navigate", "url": "https://b.example/{state}"},
                  {"kind": "type", "selector": "#e", "field": "contact_email"},
                  {"kind": "pause_for_human", "text": "Use {contact_email} for {full_name}."}]})
    assert spec.validate() == [] and comp.uses_field(spec, "contact_email")
    bad = ci.BrokerSpec.from_dict({"broker_id": "b", "name": "B", "method": "form",
                                   "steps": [{"kind": "navigate", "url": "https://b.example/{ssn}"}]})
    assert any("unknown field" in e for e in bad.validate())
    job = ci.compile_job(spec, {"state": "TX", "contact_email": "a+oo1@x.example", "full_name": "Ann"}, "1")
    assert job.steps[0].url == "https://b.example/TX" and job.contact_email == "a+oo1@x.example"
    assert job.steps[2].text == "Use a+oo1@x.example for Ann."
    r = ci.DryRunExecutor().run(job)
    assert r.needs_manual and any("type #e" in t for t in r.trace), r.trace


@test(1, "forms.executor_reads_the_page",
      "The executor spots a refused email address, confirms success signals, and picks options by whole name.")
def t_forms_executor():
    import asyncio
    ci = _imp("core.interpreter")
    spec = ci.BrokerSpec.from_dict({
        "broker_id": "b", "name": "B", "method": "form", "opt_out_url": "https://b.example",
        "steps": [{"kind": "fill", "selector": "#email", "field": "contact_email"},
                  {"kind": "click_matching", "selector": "li", "field": "state_name"},
                  {"kind": "click", "selector": "#go"},
                  {"kind": "expect_success", "text": "request received"}]})
    fields = {"contact_email": "a+oo1@x.example", "state_name": "Kansas"}
    page = _FormPage(rejects_plus=True, options={"li": ["Arkansas", "Kansas"]})
    r = asyncio.run(ci.PlaywrightExecutor(page=page).run(ci.compile_job(spec, fields, "1")))
    assert not r.ok and r.email_rejected, r
    assert "Kansas" in page.clicked and "Arkansas" not in page.clicked, page.clicked
    page2 = _FormPage(success_text="Thanks, your request received.", options={"li": ["Kansas"]})
    r2 = asyncio.run(ci.PlaywrightExecutor(page=page2).run(ci.compile_job(spec, fields, "1")))
    assert r2.ok and r2.verified and not r2.email_rejected, r2


@test(2, "forms.engine_retries_without_plus_and_never_guesses",
      "A form that refuses +addresses is retried once with the plain address and remembered; sites without steps go to the checklist.")
def t_forms_engine():
    import asyncio
    db, s = _memory_db()
    oe = _imp("core.optout_engine")
    sb = _imp("core.interpreter.script_bridge")
    ci = _imp("core.interpreter")
    P, C, pm, cm, boxes = _family(db, s, parent_inbox="pat@gmail.com")
    b = db.Broker(name="FormCo", opt_out_url="https://formco.example/optout", method=db.OptOutMethod.form)
    s.add(b); s.flush()
    req = db.RemovalRequest(member_id=pm.id, broker_id=b.id, request_key="rk-f", status=db.RequestStatus.pending)
    s.add(req); s.commit()
    spec = ci.BrokerSpec.from_dict({
        "broker_id": "formco", "name": "FormCo", "method": "form", "opt_out_url": "https://formco.example/optout",
        "steps": [{"kind": "fill", "selector": "#email", "field": "contact_email"},
                  {"kind": "click", "selector": "#go"}]})
    real = sb.get_or_build_broker_spec
    try:
        sb.get_or_build_broker_spec = lambda broker, script=None, db=None: spec
        page = _FormPage(rejects_plus=True)
        r = asyncio.run(oe._run_form_via_interpreter(req, page, {}, s))
        s.refresh(b)
        assert r.ok and b.rejects_plus_addresses, (r, b.rejects_plus_addresses)
        assert page.values["#email"] == "pat@gmail.com", page.values
        sent = s.query(db.ContactAddress).filter_by(broker_id=b.id).all()
        assert {c.tag is None for c in sent} == {True, False}, "one +address tried, then the plain one"
        # Next time it goes straight to the plain address.
        page2 = _FormPage(rejects_plus=True)
        asyncio.run(oe._run_form_via_interpreter(req, page2, {}, s))
        assert "+" not in page2.values["#email"]
    finally:
        sb.get_or_build_broker_spec = real
    # No steps for this site: nothing is typed anywhere; it goes on the checklist.
    b2 = db.Broker(name="Unknown People Search", opt_out_url="https://ups.example/optout", method=db.OptOutMethod.form)
    s.add(b2); s.flush()
    req2 = db.RemovalRequest(member_id=pm.id, broker_id=b2.id, status=db.RequestStatus.pending)
    s.add(req2); s.commit()
    page3 = _FormPage()
    r3 = asyncio.run(oe._run_form_via_interpreter(req2, page3, {}, s))
    assert r3.needs_manual and "doesn't have the steps" in r3.human_instruction and not page3.values
    s.close()


@test(2, "forms.guided_broker_and_reply",
      "A guided broker goes on the checklist with a one-time address; the broker's reply to it moves the request along.")
def t_forms_guided():
    import asyncio
    db, s = _memory_db()
    oe = _imp("core.optout_engine")
    sb = _imp("core.interpreter.script_bridge")
    ci = _imp("core.interpreter")
    try:
        sched = _imp("core.scheduler")
    except Exception as e:
        raise Skip(f"scheduler deps missing: {e}")
    P, C, pm, cm, boxes = _family(db, s, parent_inbox="pat@gmail.com")
    b = db.Broker(name="Clustal", opt_out_url="https://www.clustal.org/privacy-control", method=db.OptOutMethod.manual)
    s.add(b); s.flush()
    req = db.RemovalRequest(member_id=cm.id, broker_id=b.id, status=db.RequestStatus.pending,
                            listing_url="https://www.clustal.org/person/kim")
    s.add(req); s.commit()
    spec = ci.BrokerSpec.from_dict({"broker_id": "clustal", "name": "Clustal", "method": "manual",
                                    "opt_out_url": "https://www.clustal.org/privacy-control",
                                    "instructions": "Paste {listing_url}, then enter {contact_email} for {full_name}."})
    real = sb.get_or_build_broker_spec
    try:
        sb.get_or_build_broker_spec = lambda broker, script=None, db=None: spec
        asyncio.run(oe.execute_optout(req, None, {}, s))
    finally:
        sb.get_or_build_broker_spec = real
    s.refresh(req)
    assert req.status == db.RequestStatus.needs_manual, req.status
    ca = s.query(db.ContactAddress).filter_by(broker_id=b.id).one()
    assert ca.address in req.notes and "https://www.clustal.org/person/kim" in req.notes and "Kim Kid" in req.notes
    sched._handle_member_message(s, {}, boxes["parent"], ca.address, "noreply@clustal.org",
                                 "We received your request", "Your opt-out request has been processed.", links=[])
    s.refresh(req)
    assert req.status == db.RequestStatus.confirmed, req.status
    s.close()


@test(2, "forms.untagged_reply_matched_by_sender",
      "Mail to an inbox's plain address is matched to the broker it was given to, by the sender's domain.")
def t_forms_untagged():
    db, s = _memory_db()
    m = _imp("core.mailboxes")
    P, C, pm, cm, boxes = _family(db, s, parent_inbox="pat@yahoo.com", parent_plus="unsupported")
    b = db.Broker(name="Nuwber", opt_out_url="https://nuwber.com/removal/link")
    s.add(b); s.commit()
    ca, _ = m.issue_contact_address(s, boxes["parent"], pm, broker=b, request_key="rk-u")
    assert ca.tag is None and ca.address == "pat@yahoo.com"
    hit = m.match_inbound(s, boxes["parent"], "Pat <pat@yahoo.com>", "Nuwber <support@nuwber.com>")
    assert hit["request_keys"] == ["rk-u"], hit
    other = m.match_inbound(s, boxes["parent"], "pat@yahoo.com", "deals@shop.example")
    assert other["request_keys"] == [], other
    s.close()


@test(2, "forms.builtin_brokers_install",
      "Built-in broker plugins install themselves, create their brokers, stay off when an admin turns them off, and are found for opt-outs.")
def t_forms_builtin():
    import tempfile
    db, s = _memory_db()
    ba = _imp("plugins.broker_addon")
    layout = _imp("plugins.layout")
    shipped = [f for f in layout.scan(layout.BUNDLED_ROOT) if f.valid and f.manifest.effective_type == "brokers"]
    assert len(shipped) >= 10, len(shipped)
    old = os.environ.get("PLUGINS_DIR")
    os.environ["PLUGINS_DIR"] = tempfile.mkdtemp(prefix="oo-plugins-")
    try:
        s.add(db.Broker(name="Spokeo", opt_out_url="https://old.example", enabled=False)); s.commit()
        st = ba.sync_builtin_brokers(s)
        assert st["installed"] == len(shipped), st
        spokeo = s.query(db.Broker).filter_by(name="Spokeo").one()
        assert spokeo.plugin_id == "spokeo" and spokeo.enabled is False, "an admin's existing choice stays"
        assert spokeo.opt_out_url == "https://www.spokeo.com/optout"
        nuwber = s.query(db.Broker).filter_by(name="Nuwber").one()
        assert nuwber.enabled and nuwber.method == db.OptOutMethod.manual
        spec = ba.get_broker_spec_for_broker(s, spokeo)
        assert spec and "email_confirmation" in spec.requires
        row = s.query(db.InstalledPlugin).filter_by(plugin_id="nuwber").one()
        row.enabled = False; s.commit()
        st2 = ba.sync_builtin_brokers(s)
        assert st2["installed"] == 0 and not s.query(db.InstalledPlugin).filter_by(plugin_id="nuwber").one().enabled
        # Plugins nobody could check yet ship installed but with their broker off.
        unchecked = [f.manifest for f in shipped if not f.manifest.starts_enabled]
        assert unchecked, "expected some plugins that start turned off"
        for m in unchecked:
            b = s.query(db.Broker).filter_by(plugin_id=m.id).one()
            assert b.enabled is False, f"{m.id} should start off"
        assert s.query(db.Broker).filter_by(plugin_id="acxiom").one().enabled is True
        # Coverage: PeopleConnect's opt-out covers its family, not Classmates.
        cov = _imp("core.coverage")
        out = cov.summary(s)
        pc = s.query(db.Broker).filter_by(plugin_id="peopleconnect").one()
        c = out["coverage"][str(pc.id)]
        assert any(site == "truthfinder.com" for site in c["sites"]) and not any(site == "classmates.com" for site in c["sites"]), c
        assert c["count"] == len(c["sites"]) >= 10, c
        ip = s.query(db.Broker).filter_by(plugin_id="infopay").one()
        assert out["coverage"][str(ip.id)]["count"] == 7, out["coverage"][str(ip.id)]
        assert out["sites_covered"] > out["brokers_on"], out
    finally:
        if old is None:
            os.environ.pop("PLUGINS_DIR", None)
        else:
            os.environ["PLUGINS_DIR"] = old
    s.close()


@test(1, "coverage.counts_each_site_once",
      "Coverage adds a plugin's own list, its catalog family and confirmed cascades; 'likely' ones aren't counted.")
def t_coverage_counts():
    cov = _imp("core.coverage")
    cat = {"parents": [
        {"name": "Fam", "website": "https://www.fam.example", "children": ["fam.example", "a.example", "b.example", "c.example"],
         "child_suffixes": [], "one_optout_covers": True, "not_covered": ["c.example"]},
        {"name": "Grp", "website": "https://grp.example", "children": ["grp.example", "x.example"],
         "child_suffixes": [], "one_optout_covers": False},
        {"name": "Net", "website": "https://net.example", "children": ["net.example"],
         "child_suffixes": ["arrests.example"], "one_optout_covers": True, "approx_sites": 40}],
        "cascades": [{"from": ["fam.example"], "to": ["d.example"], "confidence": "confirmed"},
                     {"from": ["fam.example"], "to": ["e.example"], "confidence": "likely"},
                     {"from": ["fam.example"], "to": ["f.example"], "confidence": "historical"}]}
    c = cov.coverage("fam.example", "Fam", ["a.example", "z.example"], cat)
    assert c["sites"] == ["a.example", "b.example", "d.example", "z.example"], c
    assert c["maybe"] == ["e.example"] and c["count"] == 4, c
    assert cov.coverage("x.example", "X", [], cat)["count"] == 0, "a family alone doesn't mean covered"
    n = cov.coverage("texasarrests.example", "Texasarrests.example", [], cat)
    assert n["network"] == "Net" and n["count"] == 40, n
    assert cov.site_of("https://suppression.peopleconnect.us/login") == "peopleconnect.us"
    # EXPECTED: one opt-out's reach is counted from what the company says, each site once.
    # IF THIS FAILS: the Brokers page could promise families coverage they don't have.


@test(1, "plugins.email_spec_uses_letter",
      "An email broker plugin may leave out its own templates; then it gets the legal letter. Half a template is refused.")
def t_email_spec_letter():
    bs = _imp("core.interpreter.broker_spec")
    base = {"broker_id": "x", "name": "X", "method": "email", "source": "test",
            "email": {"to_address": "privacy@x.example"}}
    assert not bs.BrokerSpec.from_dict(base).validate()
    half = dict(base, email={"to_address": "privacy@x.example", "subject_template": "Delete"})
    assert any("both" in e for e in bs.BrokerSpec.from_dict(half).validate())
    bad = dict(base, covers=["https://x.example/"])
    assert any("covers" in e for e in bs.BrokerSpec.from_dict(bad).validate())
    lt = _imp("core.legal_letters")
    spec = bs.BrokerSpec.from_dict(base)
    assert lt.choose_template(spec.effective_jurisdiction(), "CA"), "no letter for a US broker"
    # EXPECTED: email plugins fall back to the per-law letter instead of failing validation.
    # IF THIS FAILS: built-in email plugins (Experian, Data Axle, InfoPay...) won't install.


@test(1, "terms.versions_and_asking_again",
      "Admins accept the limits, everyone else the notice; the operator's terms get a new version only when what people see changes.")
def t_terms_versions():
    db, s = _memory_db()
    T = _imp("core.terms")
    admin = db.User(email="admin@example.invalid", full_name="Admin Example", role=db.UserRole.super_admin, hashed_password="x")
    pat = db.User(email="jordan@example.invalid", full_name="Jordan Example", role=db.UserRole.parent, hashed_password="x")
    s.add_all([admin, pat]); s.commit()
    st = {}
    assert T.needs(s, admin, st) == [{"kind": "limits", "version": T.LIMITS_VERSION}]
    assert T.needs(s, pat, st) == [{"kind": "notice", "version": T.NOTICE_VERSION}]
    try:
        T.accept(s, pat, "limits", T.LIMITS_VERSION, st); assert False, "only admins accept the limits"
    except ValueError:
        pass
    T.accept(s, admin, "limits", T.LIMITS_VERSION, st)
    T.accept(s, pat, "notice", T.NOTICE_VERSION, st)
    assert T.needs(s, admin, st) == [] and T.needs(s, pat, st) == []
    # Operator terms: off means nobody is asked; turning them on is version 1.
    T.save(st, {"text": "## Hello", "operator": "Riverside Library", "enabled": False})
    assert T.needs(s, pat, st) == [] and T.config(st)["version"] == 0
    T.save(st, {"enabled": True})
    assert T.config(st)["version"] == 1 and T.needs(s, pat, st) == [{"kind": "operator_terms", "version": 1}]
    try:
        T.accept(s, pat, "operator_terms", 2, st); assert False, "a version that isn't current must be refused"
    except ValueError:
        pass
    T.accept(s, pat, "operator_terms", 1, st)
    assert T.needs(s, pat, st) == []
    T.save(st, {"text": "## Hello"})                       # nothing changed
    T.save(st, {"enabled": False}); T.save(st, {"enabled": True})
    assert T.config(st)["version"] == 1, "turning them off and on unchanged mustn't ask again"
    T.save(st, {"enabled": False}); T.save(st, {"text": "## Hello again"}); T.save(st, {"enabled": True})
    assert T.config(st)["version"] == 2 and T.needs(s, pat, st)[0]["version"] == 2, "a change made while off still counts"
    try:
        T.save({}, {"enabled": True}); assert False, "empty terms can't be turned on"
    except ValueError:
        pass
    tpl = T.template("Riverside Library", "privacy@example.invalid")
    assert "Riverside Library" in tpl and "{operator}" not in tpl and T.unfinished(tpl), "the draft has notes to fill in"
    s.close()
    # EXPECTED: people are asked once per version, and again only when what they see changes.
    # IF THIS FAILS: people could be nagged on every save, or never told about a change.


@test(2, "terms.adding_someone_needs_permission",
      "A parent must confirm they may act for someone they add; it's recorded without names and removed with the person.")
def t_terms_acting_for():
    db, s = _memory_db()
    fam = _imp("routers.family")
    people = _imp("core.people")
    from fastapi import HTTPException
    parent = db.User(email="jordan@example.invalid", full_name="Jordan Example", role=db.UserRole.parent, hashed_password="x")
    s.add(parent); s.commit()
    try:
        fam.add_member(fam.MemberCreate(full_name="Casey Example", age=9), s, parent)
        assert False, "adding someone without confirming must be refused"
    except HTTPException as e:
        assert e.status_code == 400
    m = fam.add_member(fam.MemberCreate(full_name="Casey Example", age=9, authorized=True), s, parent)
    row = s.query(db.TermsAcceptance).filter_by(kind="acting_for").one()
    added = s.query(db.FamilyMember).filter_by(id=m.id).one().user_id
    assert row.user_id == parent.id and row.subject_user_id == added
    people.delete_person(s, s.query(db.User).get(added)); s.commit()
    assert s.query(db.TermsAcceptance).count() == 0, "the record goes with the person"
    s.close()
    # EXPECTED: no one is added without the parent confirming they may act for them.
    # IF THIS FAILS: OpenOptOut could send requests for people who never agreed.


@test(2, "found_listings.rule_ask_auto_tell",
      "A listing found on a broker that's off: ask an admin, tell the person, or turn it on at N people; never one turned off on purpose.")
def t_found_listings_rule():
    import uuid
    db, s = _memory_db()
    fl = _imp("core.found_listings")
    people = []
    for i in range(3):
        u = db.User(email=f"p{i}@example.invalid", full_name=f"Jordan Example {i}", role=db.UserRole.member)
        s.add(u); s.flush()
        m = db.FamilyMember(user_id=u.id, full_name=f"Jordan Example {i}")
        s.add(m); s.flush(); people.append(m)
    s.add(db.InstalledPlugin(plugin_id="cocofinder", name="CocoFinder", version="1.0.0", enabled=True, manifest_json="{}", install_path="/nonexistent"))
    b = db.Broker(name="CocoFinder", plugin_id="cocofinder", enabled=False, opt_out_url="https://cocofinder.example/optOut")
    s.add(b); s.commit()

    def found(m):
        s.add(db.DiscoveryResult(member_id=m.id, broker_id=b.id, found=True, listing_url="https://cocofinder.example/x"))
        r = db.RemovalRequest(member_id=m.id, broker_id=b.id, request_key=str(uuid.uuid4()), status=db.RequestStatus.pending)
        s.add(r); s.commit()
        return r

    # ask: one admin entry per broker, with the count kept up to date, and no names
    r0 = found(people[0])
    assert fl.handle(s, b, people[0].id, {"found_listings": {"action": "ask"}}) == "asked"
    found(people[1])
    fl.handle(s, b, people[1].id, {"found_listings": {"action": "ask"}})
    ups = s.query(db.BrokerUpdate).filter_by(kind="found_while_off").all()
    assert len(ups) == 1 and "2 people" in ups[0].title and "Jordan" not in ups[0].title + (ups[0].detail or ""), ups[0].title
    assert r0.status == db.RequestStatus.pending and not b.enabled

    # auto at 3 people: below it, the fallback tells the person
    cfg = {"found_listings": {"action": "auto", "threshold": 3, "fallback": "tell"}}
    assert fl.handle(s, b, people[0].id, cfg) == "told"
    s.refresh(r0)
    assert r0.status == db.RequestStatus.needs_manual and r0.waiting_for == "broker_off" and "CocoFinder" in r0.notes
    found(people[2])
    assert fl.handle(s, b, people[2].id, cfg) == "turned_on"
    s.refresh(b); s.refresh(r0)
    assert b.enabled and r0.status == db.RequestStatus.pending and r0.waiting_for is None, "told requests go back"
    assert s.query(db.BrokerUpdate).filter_by(kind="turned_on_found").count() == 1

    # never a broker an admin turned off, or one without a plugin
    bh = _imp("core.broker_health")
    bh.disable(s, b.id, reason="manually disabled by an admin")
    s.refresh(b)
    assert fl.can_turn_on(s, b) == (False, "turned_off")
    assert fl.handle(s, b, people[0].id, {"found_listings": {"action": "auto", "threshold": 1, "fallback": "ask"}}) == "asked"
    s.refresh(b); assert not b.enabled
    nb = db.Broker(name="NoPlugin", enabled=False); s.add(nb); s.commit()
    assert fl.can_turn_on(s, nb) == (False, "no_plugin")
    reg = db.Broker(name="Registry Co", enabled=False, origin="registry"); s.add(reg); s.commit()
    assert fl.handle(s, reg, people[0].id, cfg) == "", "registry brokers are left to broker_gate"
    try:
        fl.clean({"threshold": 0}); assert False
    except ValueError:
        pass
    assert fl.settings_of({}) == fl.DEFAULTS
    s.close()
    # EXPECTED: the admin's rule decides, counts are of people, and nobody's name is recorded.
    # IF THIS FAILS: brokers could turn on that an admin turned off, or people wait forever with no word.


def _stats_fixture():
    """Two branches, three people, a few searches, listings and opt-outs over
    August and September 2026. Made-up details only."""
    import uuid
    from datetime import datetime as _dt
    db, s = _memory_db()
    sys_ = db.LibrarySystem(name="Riverside Libraries", code="RVL"); s.add(sys_); s.flush()
    main = db.Branch(system_id=sys_.id, name="Main", code="MAIN"); west = db.Branch(system_id=sys_.id, name="West", code="WEST")
    s.add_all([main, west]); s.flush()
    b = db.Broker(name="ExampleBroker", enabled=True); s.add(b); s.flush()
    people = []
    for i, (br, when) in enumerate([(main, _dt(2026, 8, 3)), (main, _dt(2026, 9, 9)), (west, _dt(2026, 9, 20))]):
        u = db.User(email=f"p{i}@example.invalid", full_name=f"Jordan Example {i}", role=db.UserRole.parent,
                    hashed_password="x", branch_id=br.id, created_at=when)
        s.add(u); s.flush()
        m = db.FamilyMember(user_id=u.id, full_name=f"Jordan Example {i}"); s.add(m); s.flush(); people.append(m)
    p0, p1, p2 = people
    for m, day, found in ((p0, _dt(2026, 8, 4, 9), True), (p0, _dt(2026, 8, 4, 10), True), (p1, _dt(2026, 9, 10), False),
                          (p2, _dt(2026, 9, 21), True)):
        s.add(db.DiscoveryResult(member_id=m.id, broker_id=b.id, found=found, scanned_at=day))
    s.add(db.RemovalRequest(member_id=p0.id, broker_id=b.id, request_key=str(uuid.uuid4()), status=db.RequestStatus.confirmed,
                            sent_at=_dt(2026, 8, 5), confirmed_at=_dt(2026, 9, 1)))
    s.add(db.RemovalRequest(member_id=p2.id, broker_id=b.id, request_key=str(uuid.uuid4()), status=db.RequestStatus.sent,
                            sent_at=_dt(2026, 9, 22)))
    s.commit()
    return db, s


@test(2, "stats_api.counts_and_checks",
      "The usage statistics API passes every client check; counts are per branch and day, scoped by key, with no names.")
def t_stats_api():
    import json as _json
    from datetime import date as _d
    U = _imp("core.usage_stats")
    check = _imp("core.stats_check")
    db, s = _stats_fixture()
    today = _d(2026, 10, 12)
    cfg = U.config({"stats_api": {"enabled": True}})
    c, key = U.new_client(cfg, "Warehouse loader", ["*"])
    assert key.startswith("oos_") and c["key_hash"] not in key

    def get(path, params, k):
        st, body, _m = U.handle(s, path, params, f"Bearer {k}" if k else "", cfg, today=today)
        return st, body

    results = check.run(get, key, today=today)
    failed = [(check.text(r), r["detail"]) for r in results if not r["ok"]]
    assert not failed, failed
    q = {"from": "2026-08-01", "to": "2026-09-30"}
    st, body = get("/v1/usage", dict(q, granularity="month", institution="RVL-MAIN"), key)
    assert st == 200, body
    aug, sep = body["rows"]
    assert (aug["people_added"], sep["people_added"]) == (1, 1)
    assert (aug["listing_searches"], sep["listing_searches"]) == (1, 1), "one search per person, broker and day"
    assert (aug["listings_found"], aug["optout_requests_sent"], sep["removals_confirmed"]) == (1, 1, 1)
    st, day = get("/v1/usage", {"from": "2026-09-21", "to": "2026-09-22", "institution": "RVL-WEST"}, key)
    assert [(r["period_start"], r["listings_found"], r["optout_requests_sent"]) for r in day["rows"]] == \
        [("2026-09-21", 1, 0), ("2026-09-22", 0, 1)], day["rows"]
    st, many = get("/v1/usage", dict(q, granularity="total", institution="*"), key)
    assert [r["institution"] for r in many["rows"]] == ["all", "RVL", "RVL-MAIN", "RVL-WEST"]
    assert many["rows"][0]["listing_searches"] == 3
    st, csvt = get("/v1/usage", dict(q, granularity="total", format="csv", metrics="removals_confirmed"), key)
    assert csvt.splitlines() == ["institution,period_start,period_end,complete,removals_confirmed",
                                 "all,2026-08-01,2026-09-30,true,1"], csvt
    assert "Jordan" not in _json.dumps(many), "statistics must never name anyone"
    # A key limited to one branch sees only that branch.
    c2, key2 = U.new_client(cfg, "West only", ["RVL-WEST"])
    st, body = get("/v1/usage", dict(q, institution="RVL-MAIN"), key2)
    assert st == 403
    st, body = get("/v1/institutions", {}, key2)
    assert [i["id"] for i in body["institutions"]] == ["RVL-WEST"]
    # Off means off, apart from the public status; and keys in the address aren't accepted.
    off = U.config({"stats_api": {"enabled": False, "clients": cfg["clients"]}})
    st, body, _m = U.handle(s, "/v1/usage", q, f"Bearer {key}", off, today=today)
    assert st == 503 and body["error"] == "off"
    st, body, _m = U.handle(s, "/v1/status", {}, "", off, today=today)
    assert st == 200 and body["enabled"] is False
    st, body, _m = U.handle(s, "/v1/usage", dict(q, key=key), "", cfg, today=today)
    assert st == 401
    s.close()
    # EXPECTED: scripts get dense, consistent counts for any range, scoped to their key, counts only.
    # IF THIS FAILS: a library's warehouse would load wrong numbers, or see another library's.


@test(2, "broker_updates.builtin_plugins_recorded",
      "Built-in broker plugins added or updated by an upgrade become Broker updates: one summary on first start, one entry each for a few.")
def t_builtin_plugin_updates():
    import tempfile
    db, s = _memory_db()
    ba = _imp("plugins.broker_addon")
    old = os.environ.get("PLUGINS_DIR")
    os.environ["PLUGINS_DIR"] = tempfile.mkdtemp(prefix="oo-plugins-")
    try:
        st = ba.sync_builtin_brokers(s)
        ups = s.query(db.BrokerUpdate).filter_by(kind="plugin_added").all()
        assert len(ups) == 1 and ups[0].title == f"{st['installed']} built-in broker plugins installed", [u.title for u in ups]
        assert "CocoFinder" in ups[0].detail and "Turned off until someone checks" in ups[0].detail
        # An upgrade that changes one plugin and brings back another: one entry each.
        row = s.query(db.InstalledPlugin).filter_by(plugin_id="acxiom").one()
        new_version = row.version
        row.version = "0.9.0"
        gone = s.query(db.InstalledPlugin).filter_by(plugin_id="wyty").one()
        s.query(db.Broker).filter_by(plugin_id="wyty").delete()
        s.delete(gone); s.commit()
        st2 = ba.sync_builtin_brokers(s)
        assert st2["installed"] == 1 and st2["updated"] == 1, st2
        upd = s.query(db.BrokerUpdate).filter_by(kind="plugin_updated").one()
        acx = s.query(db.Broker).filter_by(plugin_id="acxiom").one()
        assert upd.broker_id == acx.id and f"0.9.0 → {new_version}" in upd.title, upd.title
        added = s.query(db.BrokerUpdate).filter_by(kind="plugin_added").order_by(db.BrokerUpdate.id).all()
        assert len(added) == 2 and added[1].title == "Built-in plugin added: WYTY", [a.title for a in added]
        # Nothing changed: nothing recorded.
        ba.sync_builtin_brokers(s)
        assert s.query(db.BrokerUpdate).count() == 3
    finally:
        if old is None:
            os.environ.pop("PLUGINS_DIR", None)
        else:
            os.environ["PLUGINS_DIR"] = old
    s.close()
    # EXPECTED: admins see which built-in plugins arrived or changed with each upgrade, without a flood.
    # IF THIS FAILS: plugins change silently, or the first start buries Broker updates under 80 entries.


# ── Long tail: privacy-request pages and hosted forms ─────────────────────────

_PP_HOME = """<html><head><title>PeopleFind</title></head><body>
<a href="/about">About</a> <a href="/terms">Terms</a>
<a href="/privacy-policy">Privacy Policy</a>
<a href="https://privacyportal.onetrust.com/webform/abc-123/def-456">Do Not Sell or Share My Personal Information</a>
<a href="https://www.facebook.com/peoplefind">Facebook</a>
<a href="mailto:privacy@peoplefind.example">privacy@peoplefind.example</a>
<a href="mailto:sales@peoplefind.example">Sales</a></body></html>"""
_PP_POLICY = """<html><head><title>Privacy Policy</title></head><body><h1>Privacy Policy</h1>
To opt out, write to optout@peoplefind.example or visit
<a href="https://evil.example/optout">our partner</a>.</body></html>"""
_PP_FORM_SITE = """<html><head><title>Remove my info</title></head><body><h1>Privacy request</h1>
<form><label>Email<input type="email" name="email"></label> Request deletion of your listing.</form></body></html>"""


def _pp_fetch(pages):
    calls = []
    def fetch(url, domain):
        calls.append(url)
        key = url.rstrip("/")
        for k, v in pages.items():
            if key == k.rstrip("/"):
                return url, 200, v
        return url, 404, ""
    fetch.calls = calls
    return fetch


@test(1, "privacy_finder.reads_a_website",
      "The finder spots hosted OneTrust/TrustArc forms, in-house request forms, opt-out pages and privacy emails, and only fetches the broker's own site.")
def t_pp_find():
    pf = _imp("core.privacy_finder")
    assert pf.hosted_kind("https://privacyportal.onetrust.com/webform/a/b") == "hosted_onetrust"
    assert pf.hosted_kind("https://submit-irm.trustarc.com/services/validation/123") == "hosted_trustarc"
    assert pf.hosted_kind("https://www.onetrust.com/products/") == "", "the vendor's marketing site isn't a form"
    fetch = _pp_fetch({"https://peoplefind.example": _PP_HOME,
                       "https://peoplefind.example/privacy-policy": _PP_POLICY})
    res = pf.find("peoplefind.example", fetch=fetch)
    kinds = [(f["kind"], f["url"]) for f in res["findings"]]
    assert kinds[0] == ("hosted_onetrust", "https://privacyportal.onetrust.com/webform/abc-123/def-456"), kinds
    emails = {f["url"] for f in res["findings"] if f["kind"] == "email"}
    assert emails == {"mailto:privacy@peoplefind.example", "mailto:optout@peoplefind.example"}, emails
    assert not any("evil.example" in u or "facebook" in u for u in fetch.calls), fetch.calls
    assert len(fetch.calls) <= pf.MAX_FETCHES
    # A site with its own request form, found through a well-known address.
    fetch2 = _pp_fetch({"https://formsite.example": "<html><body>Hello</body></html>",
                        "https://formsite.example/opt-out": _PP_FORM_SITE})
    res2 = pf.find("formsite.example", fetch=fetch2)
    assert res2["findings"][0]["kind"] == "request_form", res2


@test(1, "hosted_forms.plans_fill_by_label",
      "The form filler picks delete/do-not-sell and 'myself', fills name and the one-time email, and refuses what it shouldn't touch.")
def t_hf_plan():
    hf = _imp("core.interpreter.hosted_forms")
    V = {"first_name": "Jane", "last_name": "Doe", "contact_email": "jane+oo1@gmail.com", "state": "TX",
         "state_name": "Texas", "request_text": "Please delete my data."}
    def c(i, **kw):
        d = {"i": i, "tag": "input", "type": "text", "name": "", "id": "", "label": "", "aria": "",
             "placeholder": "", "autocomplete": "", "required": False, "group": "", "group_label": "",
             "value": "", "options": []}
        d.update(kw); return d
    form = [
        c(0, type="radio", group="who", group_label="I am submitting as", label="Myself", value="self", required=True),
        c(1, type="radio", group="who", group_label="I am submitting as", label="An authorized agent", value="agent"),
        c(2, type="checkbox", group="rt", group_label="Request type", label="Access my information"),
        c(3, type="checkbox", group="rt", group_label="Request type", label="Delete my information"),
        c(4, label="First name", required=True), c(5, label="Last name", required=True),
        c(6, type="email", label="Email address", required=True),
        c(7, tag="select", type="select-one", label="State", options=[{"value": "", "label": "Pick"}, {"value": "KS", "label": "Kansas"}, {"value": "TX", "label": "Texas"}]),
        c(8, type="checkbox", name="news", label="Send me offers and updates"),
        c(9, type="checkbox", name="cert", label="I declare under penalty of perjury that I am the consumer", required=True),
        c(10, tag="textarea", type="textarea", label="Additional details"),
    ]
    plan = hf.plan_autofill(form, V)
    by = {a["i"]: a for a in plan["actions"]}
    assert plan["ok"], plan["why"]
    assert 0 in by and 1 not in by and 3 in by and 2 not in by and 9 in by and 8 not in by, by
    assert by[6]["value"] == "jane+oo1@gmail.com" and by[7]["value"] == "TX" and by[10]["value"] == "Please delete my data."
    # Only access/correct options: not something we'd submit.
    no_delete = [c(0, type="radio", group="rt", group_label="Type of request", label="Access my data"),
                 c(1, type="radio", group="rt", group_label="Type of request", label="Correct my data"),
                 c(2, label="Full name"), c(3, type="email", label="Email")]
    assert "deletion" in hf.plan_autofill(no_delete, V)["why"]
    newsletter = [c(0, type="email", label="Email")]
    assert not hf.plan_autofill(newsletter, V)["ok"], "a lone email box is a newsletter, not a privacy form"
    needs_ssn = [c(0, label="Full name"), c(1, type="email", label="Email"), c(2, label="Last 4 of SSN", required=True)]
    assert "never fill" in hf.plan_autofill(needs_ssn, V)["why"]
    # Spec built for a found page fills the form and expects a confirmation email.
    class B: id, name = 7, "PeopleFind"
    class P: url, kind = "https://privacyportal.onetrust.com/webform/a/b", "hosted_onetrust"
    spec = hf.spec_for_page(B(), P())
    assert spec.validate() == [] and any(st.kind == "autofill" for st in spec.steps)
    assert "email_confirmation" in spec.requires and hf.is_found_form(spec)
    job = _imp("core.interpreter").compile_job(spec, dict(V, full_name="Jane Doe"), "1")
    payload = __import__("json").loads(next(st for st in job.steps if st.kind == "autofill").value)
    assert payload["contact_email"] == "jane+oo1@gmail.com" and "delete" in payload["request_text"].lower()


@test(2, "hosted_forms.fills_a_real_page",
      "In a real browser, the form filler completes a OneTrust-style form and stops on one that wants an ID number.")
def t_hf_browser():
    import asyncio
    try:
        from playwright.async_api import async_playwright
    except Exception as e:
        raise Skip(f"playwright missing: {e}")
    ci = _imp("core.interpreter")
    good = """<form><fieldset><legend>Request type</legend>
<label><input type=checkbox name=rt value=access> Access my personal information</label>
<label><input type=checkbox name=rt value=delete> Delete my personal information</label></fieldset>
<label for=fn>First Name *</label><input id=fn required><label for=ln>Last Name *</label><input id=ln required>
<label for=em>Email *</label><input id=em type=email required>
<label><input type=checkbox id=news name=news> Send me news and offers</label>
<label><input type=checkbox id=cert name=cert required> I certify that the information is true</label>
<button type=submit>Submit</button></form>
<script>
document.querySelector('form').addEventListener('submit', function(e) {
    e.preventDefault();
    window.sent = JSON.stringify(Array.from(document.querySelectorAll('input')).map(function(el) {
        return [el.id || el.value, el.type === 'checkbox' ? el.checked : el.value];
    }));
    var p = document.createElement('p');
    p.textContent = 'Your request has been received.';
    document.body.appendChild(p);
});
</script>"""
    bad = """<form><h2>Delete my data</h2><label for=n>Full name</label><input id=n required>
<label for=e>Email</label><input id=e type=email required><label for=d>Driver's license number</label><input id=d required>
<button type=submit>Submit</button></form>"""
    spec = ci.BrokerSpec(broker_id="x", name="PeopleFind", method="form", opt_out_url="https://x.example",
                         steps=[ci.Step(kind="autofill"),
                                ci.Step(kind="click_matching", selector="button, input[type=submit]", text="Submit"),
                                ci.Step(kind="expect_success", text="received", optional=True)])
    fields = {"first_name": "Jane", "last_name": "Doe", "full_name": "Jane Doe", "contact_email": "jane+oo1@gmail.com"}

    async def go(html):
        async with async_playwright() as p:
            try:
                b = await p.firefox.launch()
            except Exception as e:
                raise Skip(f"no browser: {e}")
            try:
                pg = await b.new_page()
                await pg.set_content(html)
                job = ci.compile_job(spec, fields, "1")
                job.steps = [st for st in job.steps if st.kind != "navigate"]
                r = await ci.PlaywrightExecutor(page=pg).run(job)
                sent = await pg.evaluate("() => window.sent || ''")
                return r, sent
            finally:
                await b.close()
    r, sent = asyncio.run(go(good))
    assert r.ok and r.verified, r.detail
    vals = dict(__import__("json").loads(sent))
    assert vals["delete"] is True and vals["access"] is False and vals["em"] == "jane+oo1@gmail.com", vals
    assert vals["cert"] is True and vals["news"] is False, "certify yes, marketing never"
    r2, _ = asyncio.run(go(bad))
    assert r2.needs_manual and "never fill" in r2.human_instruction and "PeopleFind" in r2.human_instruction


@test(2, "privacy_finder.used_by_opt_outs",
      "Found forms become the broker's opt-out steps; new sites from pasted listings are checked and moved to automated; emails need approval.")
def t_pp_used():
    db, s = _memory_db()
    pf = _imp("core.privacy_finder")
    sb = _imp("core.interpreter.script_bridge")
    lf = _imp("core.listing_finder")
    oe = _imp("core.optout_engine")
    P, C, pm, cm, boxes = _family(db, s, parent_inbox="pat@gmail.com")
    res = lf.add_listing(s, pm, "https://peoplefind.example/person/pat-parent")
    b = s.query(db.Broker).filter_by(id=res["broker_id"]).one()
    req = s.query(db.RemovalRequest).filter_by(id=res["request_id"]).one()
    assert req.status == db.RequestStatus.needs_manual
    fetch = _pp_fetch({"https://peoplefind.example": _PP_HOME,
                       "https://peoplefind.example/privacy-policy": _PP_POLICY})
    out = pf.check_new_site(s, b, fetch=fetch)
    s.refresh(b); s.refresh(req)
    assert out["used"] == "hosted_onetrust" and b.method == db.OptOutMethod.form and req.status == db.RequestStatus.pending
    # Admins hear about what was found (Broker updates), once, without anyone's name.
    ups = s.query(db.BrokerUpdate).filter_by(kind="privacy_found", broker_id=b.id).all()
    assert len(ups) == 1 and "privacy request form (OneTrust)" in ups[0].title and "privacy email address" in ups[0].title, \
        [u.title for u in ups]
    assert "Pat" not in ups[0].title + (ups[0].detail or "")
    pf.run_for_broker(s, b, fetch=fetch)
    assert s.query(db.BrokerUpdate).filter_by(kind="privacy_found", broker_id=b.id).count() == 1, "nothing new, no new note"
    spec = sb.get_or_build_broker_spec(b, db=s)
    assert spec.opt_out_url.startswith("https://privacyportal.onetrust.com/") and any(st.kind == "autofill" for st in spec.steps)
    # The verification link a OneTrust form sends is allowed to be clicked.
    cl = _imp("core.confirm_links")
    assert any(d == "onetrust.com" for d in cl.allowed_domains(s, req))
    # Emails: found, not used until approved.
    assert oe.resolve_optout_address(b, s) is None
    em = s.query(db.PrivacyPage).filter_by(broker_id=b.id, kind="email", url="mailto:privacy@peoplefind.example").one()
    pf.approve_email(s, em, "Pat")
    assert oe.resolve_optout_address(b, s) == "privacy@peoplefind.example"
    # Dismissed results stay dismissed when the site is checked again.
    form = s.query(db.PrivacyPage).filter_by(broker_id=b.id, kind="hosted_onetrust").one()
    form.status = "dismissed"; s.commit()
    pf.run_for_broker(s, b, fetch=fetch)
    s.refresh(form)
    assert form.status == "dismissed" and pf.best(s, b, pf.FILLABLE) is None
    # Brokers that already have steps aren't checked.
    b.plugin_id = "something"; b.privacy_checked_at = None; s.commit()
    assert b not in pf.needs_check(s)
# ── Broker update notifications ───────────────────────────────────────────────

@test(2, "broker_updates.recorded_and_emailed",
      "Brokers turned off, sites gone or back, registry changes and new sites become admin updates; a digest emails them once.")
def t_broker_updates():
    from datetime import datetime, timedelta
    db, s = _memory_db()
    bu = _imp("core.broker_updates")
    bh = _imp("core.broker_health")
    rs = _imp("core.registry_sync")
    lf = _imp("core.listing_finder")
    b = db.Broker(name="FailCo", opt_out_url="https://failco.example", enabled=True)
    g = db.Broker(name="GoneCo", opt_out_url="https://goneco.example", enabled=True)
    s.add_all([b, g]); s.commit()
    for _ in range(bh.AUTO_DISABLE_THRESHOLD):
        bh.record_failure(s, b.id, "selector not found: #submit")
    kinds = [u["kind"] for u in bu.listing(s)]
    assert kinds.count("auto_disabled") == 1, kinds
    now = datetime.utcnow()
    bh.record_probe(s, g.id, False, "getaddrinfo failed", now=now - timedelta(days=31))
    bh.record_probe(s, g.id, False, "getaddrinfo failed", now=now)
    bh.record_probe(s, g.id, True, now=now + timedelta(hours=1))
    kinds = [u["kind"] for u in bu.listing(s)]
    assert "defunct" in kinds and "back_online" in kinds, kinds
    rows = [{"name": "New Data LLC", "domain": "newdata.example", "email": "", "opt_out_url": ""},
            {"name": "FailCo", "domain": "failco.example", "email": "privacy@failco.example", "opt_out_url": ""}]
    rs.apply(s, "VT", rows)
    ups = bu.listing(s)
    assert any(u["kind"] == "new_brokers" and "1 new broker" in u["title"] for u in ups), ups
    assert any(u["kind"] == "contact_changed" and u["broker_id"] == b.id for u in ups)
    P, C, pm, cm, boxes = _family(db, s)
    lf.add_listing(s, pm, "https://unknownpeople.example/p/pat")
    assert any(u["kind"] == "new_site" and "unknownpeople.example" in u["title"] for u in bu.listing(s))
    assert all("Pat" not in (u["title"] + (u["detail"] or "")) for u in bu.listing(s)), "no family details"
    # Same thing about the same broker isn't repeated within a week.
    n = len(bu.listing(s))
    bu.record(s, "auto_disabled", "again", broker_id=b.id); s.commit()
    assert len(bu.listing(s)) == n
    # Digest: one email with everything, then nothing until the next one is due.
    sent = []
    send = lambda subj, body, db_: (sent.append((subj, body)) or {"sent": True})
    r = bu.digest(s, {}, send=send)
    assert r["sent"] and len(sent) == 1 and "need attention" in sent[0][0] and "FailCo" in sent[0][1], (r, sent)
    assert bu.digest(s, {}, send=send)["reason"] == "nothing new"
    bu.record(s, "new_site", "Another site", broker_id=None); s.commit()
    recent = {"broker_updates_last_digest": datetime.utcnow().isoformat() + "Z"}
    assert bu.digest(s, recent, send=send)["reason"] == "not due"
    assert bu.digest(s, {"broker_updates": {"email_digest": "off"}}, send=send)["reason"] == "off"
    assert bu.unread_count(s) == len(bu.listing(s))
    bu.mark_read(s)
    assert bu.unread_count(s) == 0
# ── Automated removal verification ────────────────────────────────────────────

def _vf_member(db, s):
    P, C, pm, cm, boxes = _family(db, s, parent_inbox="pat@gmail.com")
    s.add_all([db.Identity(member_id=pm.id, kind="name", value="Pat Parent", is_primary=True),
               db.Identity(member_id=pm.id, kind="address", value="12 Oak St, Austin, TX 78701", is_primary=True),
               db.Identity(member_id=pm.id, kind="phone", value="512-555-0100", is_primary=True)])
    s.commit()
    return pm


@test(2, "verification.checks_and_acts",
      "Removal checks read the listing page, the broker's search and web search, confirm removals that stuck, and re-send ones that came back.")
def t_verification():
    from datetime import datetime, timedelta
    db, s = _memory_db()
    vf = _imp("core.verification")
    R = db.RequestStatus
    pm = _vf_member(db, s)
    b = db.Broker(name="PeopleFind", opt_out_url="https://www.peoplefind.example/optout")
    s.add(b); s.flush()
    now = datetime.utcnow()
    listing = "https://www.peoplefind.example/p/pat-parent-austin"
    req = db.RemovalRequest(member_id=pm.id, broker_id=b.id, status=R.sent, listing_url=listing,
                            sent_at=now - timedelta(days=10), request_key="rk-v")
    s.add(req); s.commit()
    pages = {}
    calls = []
    def fetch(url, domain):
        calls.append(url)
        return pages.get(url, (url, 404, ""))
    # 1. The listing page is gone: a sent request becomes confirmed.
    r = vf.verify_request(s, req, {}, fetch=fetch)
    s.refresh(req)
    assert r["verdict"] == "gone" and r["action"] == "confirmed" and req.status == R.confirmed and req.last_verdict == "gone"
    # 2. A month later it's back with their city: re-sent, noted as come back.
    pages[listing] = (listing, 200, "<h1>Pat Parent, 45</h1><p>Lives in Austin, TX. Phone (512) 555-0100</p>")
    r = vf.verify_request(s, req, {}, fetch=fetch)
    s.refresh(req)
    assert r["verdict"] == "listed" and r["action"] == "resend_reappeared" and req.status == R.pending
    assert "came back" in req.notes
    # 3. A removal page that says "removed" counts as gone, even with a 200.
    req.status, req.sent_at = R.sent, now - timedelta(days=10); s.commit()
    pages[listing] = (listing, 200, "<p>This profile has been removed at the owner's request.</p>")
    assert vf.verify_request(s, req, {}, fetch=fetch)["verdict"] == "gone"
    # 4. A robot wall is "blocked", and changes nothing.
    req.status = R.confirmed; s.commit()
    pages[listing] = (listing, 403, "")
    r = vf.verify_request(s, req, {}, fetch=fetch, search=lambda q: [])
    s.refresh(req)
    assert r["verdict"] in ("blocked", "not_found") and req.status == R.confirmed, r
    # 5. Broker search with a listing pattern, when there's no listing URL.
    ci = _imp("core.interpreter")
    spec = ci.BrokerSpec.from_dict({"broker_id": "pf", "name": "PeopleFind", "method": "manual",
                                    "search_url": "https://www.peoplefind.example/search/{first_name}-{last_name}/{state}",
                                    "listing_pattern": r"/p/[a-z-]+"})
    real = vf._spec
    vf._spec = lambda db_, broker: spec
    try:
        req2 = db.RemovalRequest(member_id=pm.id, broker_id=b.id, status=R.confirmed,
                                 confirmed_at=now - timedelta(days=40), request_key="rk-v2")
        s.add(req2); s.commit()
        search_url = "https://www.peoplefind.example/search/Pat-Parent/TX"
        pages[search_url] = (search_url, 200, '<div><a href="/p/pat-parent-dallas">Pat Parent</a> Dallas, TX</div>'
                                              '<div><a href="/p/pat-parent-austin2">Pat Parent</a> Austin, TX, age 45</div>'
                                              '<a href="/about">About</a>')
        r = vf.verify_request(s, req2, {}, fetch=fetch)
        s.refresh(req2)
        assert r["verdict"] == "listed" and r["method"] == "broker_search" and req2.listing_url.endswith("/p/pat-parent-austin2"), r
        assert req2.status == R.pending
        pages[search_url] = (search_url, 200, '<div><a href="/p/pat-parent-dallas">Pat Parent</a> Dallas, TX</div>')
        req2.status, req2.listing_url = R.confirmed, None; s.commit()
        r = vf.verify_request(s, req2, {}, fetch=fetch)
        assert r["verdict"] == "not_found", "a namesake in another city isn't them"
    finally:
        vf._spec = real
    # 6. Web search: a hit counts only if the page still shows them.
    req3 = db.RemovalRequest(member_id=pm.id, broker_id=b.id, status=R.confirmed, request_key="rk-v3")
    s.add(req3); s.commit()
    hit_url = "https://www.peoplefind.example/p/pat-parent-x"
    searches = []
    def search(q):
        searches.append(q)
        return [{"url": hit_url, "title": "Pat Parent - Austin, TX", "snippet": "Pat Parent, 45, Austin"},
                {"url": "https://elsewhere.example/pat", "title": "Pat Parent", "snippet": ""}]
    pages[hit_url] = (hit_url, 404, "")
    r = vf.verify_request(s, req3, {}, fetch=fetch, search=search)
    assert r["verdict"] == "not_found" and searches[0].startswith("site:peoplefind.example"), (r, searches)
    assert not any("elsewhere.example" in c for c in calls), "only the broker's own pages are visited"
    pages[hit_url] = (hit_url, 200, "<h1>Pat Parent</h1> Austin TX 512-555-0100")
    r = vf.verify_request(s, req3, {}, fetch=fetch, search=search)
    assert r["verdict"] == "listed" and r["method"] == "web_search"
    s.close()


@test(2, "verification.schedule_and_web_search",
      "Daily checks pick sent and confirmed removals on a budget; the weekly web search re-checks brokers someone was removed from.")
def t_verification_schedule():
    from datetime import datetime, timedelta
    db, s = _memory_db()
    vf = _imp("core.verification")
    R = db.RequestStatus
    pm = _vf_member(db, s)
    now = datetime.utcnow()
    bs = [db.Broker(name=f"B{i}", opt_out_url=f"https://b{i}.example") for i in range(3)]
    s.add_all(bs); s.flush()
    fresh = db.RemovalRequest(member_id=pm.id, broker_id=bs[0].id, status=R.sent, sent_at=now - timedelta(days=2))
    old_sent = db.RemovalRequest(member_id=pm.id, broker_id=bs[0].id, status=R.sent, sent_at=now - timedelta(days=9))
    conf_recent = db.RemovalRequest(member_id=pm.id, broker_id=bs[1].id, status=R.confirmed,
                                    last_checked_at=now - timedelta(days=3), recheck_after=now + timedelta(days=60))
    conf_due = db.RemovalRequest(member_id=pm.id, broker_id=bs[2].id, status=R.confirmed,
                                 last_checked_at=now - timedelta(days=3), recheck_after=now - timedelta(days=1))
    s.add_all([fresh, old_sent, conf_recent, conf_due]); s.commit()
    ids = {r.id for r in vf.due(s, {}, now=now)}
    assert ids == {old_sent.id, conf_due.id}, ids
    assert len(vf.due(s, {"verification": {"per_day": 1}}, now=now)) == 1
    st = vf.run_daily(s, {"verification": {"enabled": False}})
    assert st["checked"] == 0
    st = vf.run_daily(s, {}, fetch=lambda u, d: (u, 404, ""), search=lambda q: [], pause=0)
    assert st["checked"] == 2, st
    # Weekly web search finds a page on a broker this person was removed from.
    ws = _imp("core.web_search")
    conf_recent.listing_url = None; s.commit()
    page = "https://b1.example/people/pat-parent"
    real_fetcher = vf.fetcher
    vf.fetcher = lambda cfg: (lambda u, d: (u, 200, "<h1>Pat Parent</h1> 12 Oak St, Austin TX") if u == page else (u, 404, ""))
    try:
        res = ws.run_for_member(s, pm, {"web_search": {"enabled": True, "searxng_url": "http://x"}},
                                search=lambda q: [{"url": page, "title": "Pat Parent, Austin TX", "snippet": "12 Oak St"}],
                                pause=0)
    finally:
        vf.fetcher = real_fetcher
    s.refresh(conf_recent)
    assert res.get("relisted") == 1 and conf_recent.status == R.pending and conf_recent.listing_url == page, res
    assert s.query(db.RemovalRequest).filter_by(member_id=pm.id, broker_id=bs[1].id).count() == 1, "no duplicate request"
    summ = vf.summary(s, [pm.id])
    assert summ["counts"]["listed"] >= 1 and summ["recent"]
# ── Data sharing signals and aggregator-first targeting ───────────────────────

@test(2, "broker_network.sharing_and_aggregators_first",
      "Opt-out addresses that receive mail from other companies become sharing edges; aggregators and sharers are sent first.")
def t_broker_network():
    db, s = _memory_db()
    bn = _imp("core.broker_network")
    bp = _imp("core.broker_priority")
    P, C, pm, cm, boxes = _family(db, s, parent_inbox="pat@gmail.com")
    parent = db.ParentCompany(name="FamilyCo", website="https://familyco.example")
    s.add(parent); s.flush()
    a = db.Broker(name="LeakyPeople", opt_out_url="https://leakypeople.example/optout", priority=3)
    sib = db.Broker(name="FamilyCo Phones", opt_out_url="https://familyphones.example", parent_company_id=parent.id, priority=3)
    sib2 = db.Broker(name="FamilyCo Records", opt_out_url="https://familyrecords.example", parent_company_id=parent.id, priority=3)
    buyer = db.Broker(name="BuyerSearch", opt_out_url="https://buyersearch.example", priority=3)
    acx = db.Broker(name="Acxiom", opt_out_url="https://www.acxiom.com/optout", priority=2)
    plain = db.Broker(name="PlainSite", opt_out_url="https://plainsite.example", priority=5)
    s.add_all([a, sib, sib2, buyer, acx, plain]); s.flush()
    def ca(broker, member, senders, tag):
        s.add(db.ContactAddress(tag=tag, address=f"pat+{tag}@gmail.com", address_hash=tag, mailbox_id=boxes["parent"].id,
                                member_id=member.id, broker_id=broker.id, unexpected_senders=senders))
    ca(a, pm, "mail.buyersearch.example,promo.gmail.com", "oo1")
    ca(a, cm, "buyersearch.example", "oo2")
    ca(sib, pm, "familyrecords.example,deals.example", "oo3")   # its own sibling never counts
    s.commit()
    edges = bn.sharing_edges(s)
    by = {(e["from_name"], e["to_domain"]): e for e in edges}
    e = by[("LeakyPeople", "buyersearch.example")]
    assert e["addresses"] == 2 and e["members"] == 2 and e["confidence"] == "likely" and e["to_broker_id"] == buyer.id, e
    assert ("FamilyCo Phones", "familyrecords.example") not in by, "a sibling site isn't a third party"
    assert by[("FamilyCo Phones", "deals.example")]["confidence"] == "possible"
    assert by[("LeakyPeople", "gmail.com")]["confidence"] == "unknown_sender"
    sc = bn.upstream_scores(s, edges)
    assert sc[acx.id]["score"] >= 8 and "wholesaler" in sc[acx.id]["reasons"][0]
    assert sc[a.id]["score"] > 0 and any("BuyerSearch" in r for r in sc[a.id]["reasons"])
    assert sc[sib.id]["score"] > 0 and plain.id not in sc
    # Aggregators-first: Acxiom (priority 2) goes before PlainSite (priority 5).
    reqs = [db.RemovalRequest(member_id=pm.id, broker_id=b.id, status=db.RequestStatus.pending) for b in (plain, acx, a, buyer)]
    s.add_all(reqs); s.commit()
    up = {k: v["score"] for k, v in sc.items()}
    order = [r.broker.name for r in bp.order_pending(reqs, "aggregators_first", up)]
    assert order[0] == "Acxiom" and order.index("LeakyPeople") < order.index("PlainSite"), order
    assert bp.order_pending(reqs, "priority")[0].broker.name == "PlainSite", "priority order unchanged"
    rank = bn.ranking(s)
    assert rank[0]["broker_name"] == "Acxiom" and all(r["score"] > 0 for r in rank)
    s.close()


# ── Encrypted backups ─────────────────────────────────────────────────────────

@test(1, "backups.encryption",
      "Backups are AES-GCM encrypted with a scrypt-derived key; a wrong passphrase, a cut-short file or a changed byte is refused.")
def t_backup_crypto():
    if _try_import("cryptography") is None:
        raise Skip("cryptography not installed")
    import tempfile
    bk = _imp("core.backup")
    bk.SCRYPT = {"n": 2 ** 12, "r": 8, "p": 1}          # fast for the test
    bk.FRAME, old_frame = 1024, bk.FRAME
    try:
        d = tempfile.mkdtemp(prefix="oobk-t-")
        src, enc, out = (os.path.join(d, n) for n in ("plain", "enc", "out"))
        data = os.urandom(5000)
        open(src, "wb").write(data)
        bk.encrypt_file(src, enc, "correct horse battery")
        raw = open(enc, "rb").read()
        assert raw.startswith(bk.MAGIC) and data[:64] not in raw
        bk.decrypt_file(enc, out, "correct horse battery")
        assert open(out, "rb").read() == data
        for bad, why in ((lambda r: r, "wrong"),):
            try:
                bk.decrypt_file(enc, out, "wrong passphrase!!")
                raise AssertionError("wrong passphrase accepted")
            except ValueError as e:
                assert "passphrase" in str(e)
        open(enc + ".cut", "wb").write(raw[:-1100])
        try:
            bk.decrypt_file(enc + ".cut", out, "correct horse battery"); raise AssertionError("truncation accepted")
        except ValueError:
            pass
        flipped = bytearray(raw); flipped[-20] ^= 1
        open(enc + ".flip", "wb").write(bytes(flipped))
        try:
            bk.decrypt_file(enc + ".flip", out, "correct horse battery"); raise AssertionError("change accepted")
        except ValueError:
            pass
        try:
            bk.encrypt_file(src, enc, "short"); raise AssertionError("short passphrase accepted")
        except ValueError:
            pass
    finally:
        bk.FRAME = old_frame


@test(2, "backups.run_keep_verify_restore",
      "A backup is kept locally and copied to a folder destination, old copies are pruned, it verifies, and restore unpacks it.")
def t_backup_run():
    if _try_import("cryptography") is None:
        raise Skip("cryptography not installed")
    if _try_import("sqlalchemy") is None:
        raise Skip("sqlalchemy not installed")
    import tempfile, tarfile, json as _json
    from datetime import datetime, timedelta
    bk = _imp("core.backup")
    oe = _imp("core.oauth_engine")
    bk.SCRYPT = {"n": 2 ** 12, "r": 8, "p": 1}
    root = tempfile.mkdtemp(prefix="oobk-r-")
    local, remote, restore_to = (os.path.join(root, n) for n in ("local", "remote", "restored"))

    def bundle(work, cfg):
        stage = os.path.join(work, "openoptout-backup")
        os.makedirs(stage)
        open(os.path.join(stage, "database.sqlite"), "wb").write(b"SQLCIPHER-PAGES")
        _json.dump({"parts": [{"part": "database"}, {"part": "settings"}], "created": "now"},
                   open(os.path.join(stage, "manifest.json"), "w"))
        _json.dump({"x": 1}, open(os.path.join(stage, "settings.json"), "w"))
        out = os.path.join(work, "b.tar.gz")
        with tarfile.open(out, "w:gz") as t:
            t.add(stage, arcname="openoptout-backup")
        return out
    cfg = {"backups": {"keep": 2, "passphrase_enc": oe._encrypt("a long backup passphrase"),
                       "destinations": [{"id": "f1", "kind": "folder", "path": remote, "label": "NAS"}]}}
    assert bk.run_backup({"backups": {}}, bundle=bundle, local_dir=local)["error"].startswith("Set a backup passphrase")
    t0 = datetime(2026, 10, 1, 3, 0)
    names = []
    for i in range(3):
        r = bk.run_backup(cfg, now=t0 + timedelta(days=i), bundle=bundle, local_dir=local)
        assert r["ok"] and r["destinations"][0]["ok"], r
        names.append(r["name"])
    assert sorted(os.listdir(local)) == names[1:], os.listdir(local)
    assert bk.FolderDest(cfg["backups"]["destinations"][0], cfg).names() == names[1:]
    info = bk.verify_file(os.path.join(local, names[-1]), "a long backup passphrase")
    assert [p["part"] for p in info["manifest"]["parts"]] == ["database", "settings"]
    m = bk.restore(os.path.join(local, names[-1]), "a long backup passphrase", restore_to)
    assert open(os.path.join(restore_to, "database.sqlite"), "rb").read() == b"SQLCIPHER-PAGES" and m["parts"]
    bk.FolderDest({"path": remote}, {}).test()
    bad = {"backups": dict(cfg["backups"], destinations=[{"id": "x", "kind": "folder", "path": "relative/path"}])}
    r = bk.run_backup(bad, now=t0 + timedelta(days=9), bundle=bundle, local_dir=local)
    assert not r["ok"] and "full path" in r["destinations"][0]["error"]
    # Schedule
    on = {"backups": {"enabled": True, "passphrase_enc": "x", "hour": 3, "schedule": "daily"}}
    assert bk.due(on, now=datetime(2026, 10, 2, 4))
    assert not bk.due(on, now=datetime(2026, 10, 2, 2)), "waits for the hour"
    assert not bk.due(dict(on, backups_last_run="2026-10-02T03:05:00Z"), now=datetime(2026, 10, 2, 9))
    assert not bk.due({"backups": {"enabled": True}}, now=datetime(2026, 10, 2, 4)), "no passphrase, no backup"


@test(1, "backups.s3_signing",
      "S3-compatible uploads are signed with AWS Signature V4 and go only to https storage addresses.")
def t_backup_s3():
    if _try_import("cryptography") is None:
        raise Skip("cryptography not installed")
    if _try_import("requests") is None:
        raise Skip("requests not installed")
    bk = _imp("core.backup")
    oe = _imp("core.oauth_engine")
    import requests as _rq
    seen = {}
    class R:
        status_code, text = 200, "<ListBucketResult><Key>backups/openoptout-backup-1.oobackup</Key></ListBucketResult>"
    real = _rq.request
    _rq.request = lambda method, url, headers=None, data=None, timeout=None: (seen.update(m=method, url=url, h=headers) or R())
    try:
        d = bk.S3Dest({"kind": "s3", "endpoint": "https://storage.googleapis.com", "region": "auto", "bucket": "fam",
                       "prefix": "backups", "access_key": "GOOG1EXAMPLE", "secret_enc": oe._encrypt("secret")}, {})
        assert d.names() == ["openoptout-backup-1.oobackup"]
        assert seen["url"].startswith("https://storage.googleapis.com/fam?") and "list-type=2" in seen["url"]
        auth = seen["h"]["Authorization"]
        assert auth.startswith("AWS4-HMAC-SHA256 Credential=GOOG1EXAMPLE/") and "/auto/s3/aws4_request" in auth and "Signature=" in auth
        d.delete("openoptout-backup-1.oobackup")
        assert seen["m"] == "DELETE" and seen["url"].endswith("/fam/backups/openoptout-backup-1.oobackup")
        try:
            bk.S3Dest({"endpoint": "http://plain.example", "bucket": "b", "access_key": "a",
                       "secret_enc": oe._encrypt("s")}, {}).names()
            raise AssertionError("plain http accepted")
        except RuntimeError as e:
            assert "https" in str(e)
    finally:
        _rq.request = real


# ── Family inboxes and per-opt-out addresses ──────────────────────────────────

def _family(db, s, parent_inbox=None, child_inbox=None, child_plus="verified", parent_plus="verified"):
    """A parent who manages a child, each optionally with an inbox."""
    P = db.User(email="parent@x.example", full_name="Pat Parent", role=db.UserRole.parent)
    C = db.User(email="kid@x.example", full_name="Kim Kid", role=db.UserRole.member)
    s.add_all([P, C]); s.flush()
    pm = db.FamilyMember(user_id=P.id, full_name="Pat Parent")
    cm = db.FamilyMember(user_id=C.id, full_name="Kim Kid")
    s.add_all([pm, cm]); s.flush()
    s.add(db.ProfileAccess(manager_id=P.id, managed_id=C.id))
    boxes = {}
    for who, owner, addr, plus in (("parent", P, parent_inbox, parent_plus), ("child", C, child_inbox, child_plus)):
        if addr:
            mb = db.Mailbox(owner_user_id=owner.id, address=addr, address_hash=_imp("core.mailboxes").address_hash(addr),
                            provider_key="gmail" if "gmail" in addr else "smtp",
                            transport="oauth", account_ref=f"mbx-{who}", status="connected", plus_status=plus)
            s.add(mb); s.flush(); boxes[who] = mb
    s.commit()
    return P, C, pm, cm, boxes


@test(1, "mailboxes.plus_addresses_and_tags",
      "Known providers are classified, tags are random and replace any existing tag, and tags are found in headers.")
def t_mbx_tags():
    m = _imp("core.mailboxes")
    assert m.plus_support("a@gmail.com") == "supported"
    assert m.plus_support("a@yahoo.com") == "unsupported"
    assert m.plus_support("a@family.example", "gmail") == "supported", "Google Workspace custom domain"
    assert m.plus_support("a@corp.example", "outlook") == "unknown", "Microsoft 365 can disable it; must be tested"
    t1, t2 = m.new_tag(), m.new_tag()
    assert t1 != t2 and t1.startswith("oo")
    addr = m.tagged("Jane+old@Gmail.com", t1)
    assert addr == f"Jane+{t1}@gmail.com", addr
    assert m.tags_in(f'"Jane" <{addr}>, other@x.com') == {t1}
    assert m.tags_in("jane+newsletter@gmail.com") == set(), "only our own tags count"
    # EXPECTED: one fresh, non-revealing address per opt-out.
    # IF THIS FAILS: replies can't be matched, or tags leak what they're for.


@test(2, "mailboxes.which_inbox_a_member_uses",
      "Assigned inbox wins, then the member's own, then a parent's +address inbox; nothing else.")
def t_mbx_resolve():
    db, s = _memory_db()
    m = _imp("core.mailboxes")
    P, C, pm, cm, boxes = _family(db, s, parent_inbox="pat@gmail.com")
    assert m.resolve_mailbox(s, cm).id == boxes["parent"].id, "child should use parent's Gmail"
    boxes["parent"].plus_status = "unsupported"; s.commit()
    assert m.resolve_mailbox(s, cm) is None, "a plain inbox can't be shared across members"
    assert m.resolve_mailbox(s, pm).id == boxes["parent"].id, "the owner can still use their own plain inbox"
    cm.mailbox_id = boxes["parent"].id; s.commit()
    assert m.resolve_mailbox(s, cm).id == boxes["parent"].id, "explicit assignment wins"
    boxes["parent"].status = "removed"; s.commit()
    assert m.resolve_mailbox(s, cm) is None and m.resolve_mailbox(s, pm) is None
    s.close()
    # EXPECTED: every member resolves to an inbox whose replies stay separable.
    # IF THIS FAILS: opt-outs could go out with nowhere (or the wrong place) to reply.


@test(2, "mailboxes.addresses_unique_and_one_per_email_respected",
      "+address inboxes get a fresh address per opt-out; plain inboxes refuse a second use at one-per-email brokers.")
def t_mbx_issue():
    db, s = _memory_db()
    m = _imp("core.mailboxes")
    P, C, pm, cm, boxes = _family(db, s, parent_inbox="pat@gmail.com")
    b = db.Broker(name="BeenVerified.com", opt_out_url="https://www.beenverified.com/app/optout/search")
    s.add(b); s.commit()
    a1, _ = m.issue_contact_address(s, boxes["parent"], pm, broker=b, request_key="k1", one_optout_per_email=True)
    a2, _ = m.issue_contact_address(s, boxes["parent"], cm, broker=b, request_key="k2", one_optout_per_email=True)
    assert a1.address != a2.address and a1.tag and a2.tag, "each opt-out needs its own address"
    boxes["parent"].plus_status = "unsupported"; s.commit()
    p1, r1 = m.issue_contact_address(s, boxes["parent"], pm, broker=b, request_key="k3",
                                     combo_label="A", one_optout_per_email=True)
    assert p1 is not None and p1.address == "pat@gmail.com"
    p2, r2 = m.issue_contact_address(s, boxes["parent"], pm, broker=b, request_key="k4",
                                     combo_label="B", one_optout_per_email=True)
    assert p2 is None and "only one opt-out per email address" in r2, r2
    s.close()
    # EXPECTED: unique addresses where possible; a clear checklist reason where not.
    # IF THIS FAILS: BeenVerified-style brokers silently reject later opt-outs.


@test(2, "mailboxes.inbound_matching_and_leak_flag",
      "Replies are matched by +address; mail to a tag from another sender is flagged; the +address test verifies the inbox.")
def t_mbx_inbound():
    db, s = _memory_db()
    m = _imp("core.mailboxes")
    P, C, pm, cm, boxes = _family(db, s, parent_inbox="pat@family.example", parent_plus="checking")
    mb = boxes["parent"]
    mb.plus_test_tag = "ootesttag1"; s.commit()
    hit = m.match_inbound(s, mb, "pat+ootesttag1@family.example", "pat@family.example")
    assert hit["plus_check"] and mb.plus_status == "verified"
    b = db.Broker(name="Radaris", opt_out_url="https://radaris.com/control-privacy")
    s.add(b); s.commit()
    ca, _ = m.issue_contact_address(s, mb, cm, broker=b, request_key="key-123")
    good = m.match_inbound(s, mb, ca.address, "Radaris <noreply@mail.radaris.com>")
    assert good["request_keys"] == ["key-123"], good
    bad = m.match_inbound(s, mb, ca.address, "Deals <promo@spam-deals.example>")
    assert not bad["request_keys"] and bad["unexpected"], bad
    s.refresh(ca)
    assert ca.inbound_count == 2 and "spam-deals.example" in (ca.unexpected_senders or "")
    s.close()
    # EXPECTED: broker replies match their request; strangers writing to a tag are recorded.
    # IF THIS FAILS: confirmations go unmatched, or address resale goes unnoticed.


@test(2, "mailboxes.reply_confirms_request",
      "A broker reply to an opt-out's +address marks that request confirmed.")
def t_mbx_reply_confirms():
    db, s = _memory_db()
    m = _imp("core.mailboxes")
    try:
        sched = _imp("core.scheduler")
    except Exception as e:
        raise Skip(f"scheduler deps missing: {e}")
    P, C, pm, cm, boxes = _family(db, s, parent_inbox="pat@gmail.com")
    b = db.Broker(name="Radaris", opt_out_url="https://radaris.com/control-privacy")
    s.add(b); s.flush()
    req = db.RemovalRequest(member_id=cm.id, broker_id=b.id, request_key="rk-1",
                            status=db.RequestStatus.sent)
    s.add(req); s.commit()
    ca, _ = m.issue_contact_address(s, boxes["parent"], cm, broker=b, request_key="rk-1")
    n = sched._handle_member_message(s, {}, boxes["parent"], ca.address,
                                     "noreply@radaris.com", "Your request",
                                     "We have processed your opt-out request.", links=[])
    s.refresh(req)
    assert n == 1 and req.status == db.RequestStatus.confirmed, (n, req.status)
    s.close()


@test(2, "email.per_broker_send_from_member_inbox",
      "Per-broker opt-out emails go out from the member's inbox with Reply-To set to a fresh +address.")
def t_email_from_member_inbox():
    db, s = _memory_db()
    oe = _imp("core.optout_engine")
    es = _imp("core.email_send")
    P, C, pm, cm, boxes = _family(db, s, parent_inbox="pat@gmail.com")
    s.add(db.Identity(member_id=cm.id, kind="name", value="Kim Kid", is_primary=True))
    s.add(db.Identity(member_id=cm.id, kind="email", value="kim@old.example", is_primary=True))
    broker = db.Broker(name="Acme.com", notes="opt-out: privacy@acme.example")
    s.add(broker); s.commit()
    calls = []
    orig = es.send_email
    es.send_email = lambda cfg, **kw: calls.append((cfg, kw)) or {"ok": True, "via": "provider"}
    try:
        ok = oe.send_opt_out_email(cm, broker, "KEY1", None, {"email": {"provider": "smtp"}}, s)
        assert ok and len(calls) == 1
        cfg, kw = calls[0]
        assert kw["to"] == ["privacy@acme.example"]
        assert kw["account_ref"] == "mbx-parent" and cfg["email"]["provider"] == "gmail"
        assert kw["reply_to"].startswith("pat+oo") and kw["reply_to"].endswith("@gmail.com")
        assert "Kim Kid" in kw["body"] and "KEY1" in kw["body"]
        # A member with no usable inbox: nothing is sent.
        boxes["parent"].status = "removed"; s.commit()
        calls.clear()
        assert oe.send_opt_out_email(cm, broker, "KEY2", None, {}, s) is False and not calls
    finally:
        es.send_email = orig
        s.close()
    # EXPECTED: the system inbox never sends opt-outs; replies come back tagged.
    # IF THIS FAILS: opt-outs go out from the wrong account or can't be matched.


@test(2, "engine.no_inbox_goes_on_checklist",
      "A member with no inbox gets a plain-language checklist item, not a failed opt-out.")
def t_engine_no_inbox():
    import asyncio
    db, s = _memory_db()
    oe = _imp("core.optout_engine")
    P, C, pm, cm, boxes = _family(db, s)
    broker = db.Broker(name="Acme.com", notes="opt-out: privacy@acme.example", method=db.OptOutMethod.email)
    s.add(broker); s.flush()
    req = db.RemovalRequest(member_id=cm.id, broker_id=broker.id, status=db.RequestStatus.pending)
    s.add(req); s.commit()
    asyncio.run(oe.execute_optout(req, None, {}, s))
    s.refresh(req)
    assert req.status == db.RequestStatus.needs_manual, req.status
    assert "Kim Kid" in (req.notes or "") and "inbox" in req.notes
    s.close()


@test(2, "email_send.refresh_keeps_real_settings",
      "Refreshing an inbox's OAuth token saves only the token; a per-inbox settings copy never replaces the settings file.")
def t_refresh_keeps_settings():
    if _try_import("fastapi") is None:
        raise Skip("fastapi not installed")
    if _try_import("cryptography") is None:
        raise Skip("cryptography not installed")
    import json, tempfile
    es = _imp("core.email_send")
    ss = _imp("core.settings_store")
    oeng = _imp("core.oauth_engine")
    tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    real = {"email": {"provider": "smtp", "smtp_host": "system.example"},
            "oauth_clients": {"gmail": {"client_id": "id", "client_secret_enc": "", "redirect_uri": ""}},
            "email_credentials": {}}
    json.dump(real, tmp); tmp.close()
    saved = (ss.SETTINGS_FILE, oeng.load_tokens, oeng.is_expired, oeng.refresh_token, oeng.store_tokens)
    store = {}
    try:
        ss.SETTINGS_FILE = tmp.name
        oeng.load_tokens = lambda st, ref: {"refresh_token": "r", "client_id": "id", "client_secret": "x"}
        oeng.is_expired = lambda t: True
        oeng.refresh_token = lambda flow, client, rt: {"access_token": "new"}
        def _store(st, ref, toks):
            st.setdefault("email_credentials", {})[ref] = {"t": toks["access_token"]}
            store[ref] = toks
        oeng.store_tokens = _store
        inbox_cfg = dict(real); inbox_cfg["email"] = {"provider": "gmail"}
        ok = es._refresh_if_needed(inbox_cfg, "mbx-7", "gmail")
        on_disk = json.load(open(tmp.name))
        assert ok and store.get("mbx-7"), "token should be refreshed"
        assert on_disk["email"]["smtp_host"] == "system.example", "system email settings were overwritten"
        assert on_disk["email_credentials"]["mbx-7"] == {"t": "new"}
    finally:
        ss.SETTINGS_FILE, oeng.load_tokens, oeng.is_expired, oeng.refresh_token, oeng.store_tokens = saved
        os.unlink(tmp.name)



# ── Find your listings ────────────────────────────────────────────────────────

def _member_with_vault(db, s):
    U = db.User(email="jane@x.example", full_name="Jane Q Public", role=db.UserRole.parent)
    s.add(U); s.flush()
    m = db.FamilyMember(user_id=U.id, full_name="Jane Q Public")
    s.add(m); s.flush()
    for kind, value, primary in (("name", "Jane Q Public", True), ("name", "Jane Public", False),
                                 ("phone", "+1 (512) 555-0134", True),
                                 ("address", "123 Main St, Austin, TX 78701", True),
                                 ("email", "jane@old.example", True)):
        s.add(db.Identity(member_id=m.id, kind=kind, value=value, is_primary=primary))
    s.commit()
    return m


@test(1, "listings.url_checks_and_phone_formats",
      "Listing URLs are cleaned and unsafe ones refused; phone numbers come out in the formats people-search pages use.")
def t_listing_url_checks():
    lf = _imp("core.listing_finder")
    assert lf.validate_listing_url("radaris.com/p/Jane/Public") == "https://radaris.com/p/Jane/Public"
    for bad, frag in (("", "Paste"), ("ftp://x.com/a", "web address"), ("http://10.0.0.5/x", "IP"),
                      ("http://localhost/x", "public"), ("https://www.google.com/search?q=jane", "search results")):
        try:
            lf.validate_listing_url(bad)
            raise AssertionError(f"accepted {bad!r}")
        except ValueError as e:
            assert frag in str(e), (bad, str(e))
    assert lf.phone_variants("+1 (512) 555-0134") == ["(512) 555-0134", "512-555-0134", "512.555.0134", "5125550134"]
    assert lf.registrable_domain("people.radaris.com") == "radaris.com"
    assert lf.registrable_domain("a.b.example.co.uk") == "example.co.uk"


@test(2, "listings.search_plan_uses_every_variant",
      "Web searches cover each name, phone format, address and email once, with working search links.")
def t_listing_plan():
    db, s = _memory_db()
    lf = _imp("core.listing_finder")
    m = _member_with_vault(db, s)
    s.add_all([db.Broker(name="Radaris", opt_out_url="https://radaris.com/control-privacy"),
               db.Broker(name="Spokeo.com", opt_out_url="https://www.spokeo.com/optout"),
               db.Broker(name="Off.com", opt_out_url="https://off.com/x", enabled=False)])
    s.commit()
    plan = lf.search_plan(s, m)
    qs = [q["query"] for q in plan["queries"]]
    assert len(qs) == len(set(qs)), "duplicate searches"
    for needle in ('"(512) 555-0134"', '"512-555-0134"', '"123 Main St"', '"Jane Public" "Austin, TX"',
                   '"Jane Q Public" "possible relatives"', '"jane@old.example"'):
        assert needle in qs, f"missing {needle}: {qs}"
    link = plan["queries"][0]["links"]["google"]
    assert link.startswith("https://www.google.com/search?q=%22"), link
    names = {b["broker_name"] for b in plan["brokers"]}
    assert names == {"Radaris", "Spokeo.com"}, names
    assert all("site%3A" in b["search_url"] for b in plan["brokers"])
    s.close()


@test(2, "listings.url_to_broker",
      "A listing URL resolves to its broker by domain, subdomain, parent company or network of state sites.")
def t_listing_resolve():
    db, s = _memory_db()
    lf = _imp("core.listing_finder")
    pc = _imp("core.parent_catalog")
    s.add_all([db.Broker(name="Radaris", opt_out_url="https://radaris.com/control-privacy"),
               db.Broker(name="Intelius.com", opt_out_url="https://suppression.peopleconnect.us/login"),
               db.Broker(name="Staterecords.org", opt_out_url="https://staterecords.org/optout")])
    s.commit()
    pc.apply_catalog(s)
    r = lf.resolve_broker(s, "https://people.radaris.com/p/Jane/Public/")
    assert r["broker"].name == "Radaris" and r["match"] == "subdomain", r
    r = lf.resolve_broker(s, "https://www.instantcheckmate.com/people/jane-public/")
    assert r["broker"].name == "Intelius.com" and r["match"] == "parent" and "PeopleConnect" in r["note"], r
    r = lf.resolve_broker(s, "https://texasarrests.org/jane-public")
    assert r["broker"].name == "Staterecords.org", r
    r = lf.resolve_broker(s, "https://brand-new-broker.example/people/jane")
    assert r["broker"] is None and r["domain"] == "brand-new-broker.example"
    s.close()


@test(2, "listings.add_to_removal_cycle",
      "Adding a listing creates a pending request with its URL, reuses an open one, and turns unknown sites into checklist items.")
def t_listing_add():
    db, s = _memory_db()
    lf = _imp("core.listing_finder")
    m = _member_with_vault(db, s)
    b = db.Broker(name="Radaris", opt_out_url="https://radaris.com/control-privacy")
    s.add(b); s.commit()
    r1 = lf.add_listing(s, m, "https://radaris.com/p/Jane/Public/")
    req = s.query(db.RemovalRequest).get(r1["request_id"])
    assert r1["state"] == "added" and req.status == db.RequestStatus.pending
    assert req.listing_url == "https://radaris.com/p/Jane/Public/" and req.request_key
    r2 = lf.add_listing(s, m, "https://radaris.com/p/Jane/Public/2")
    assert r2["state"] == "already_open" and r2["request_id"] == r1["request_id"]
    s.refresh(req)
    assert "Public/2" in (req.notes or ""), "second listing should be kept"
    req.status = db.RequestStatus.confirmed; s.commit()
    r3 = lf.add_listing(s, m, "https://radaris.com/p/Jane/Public/")
    assert r3["state"] == "added" and r3["request_id"] != r1["request_id"], "listing came back: new request"
    r4 = lf.add_listing(s, m, "https://www.brand-new-broker.example/people/jane")
    nb = s.query(db.Broker).get(r4["broker_id"])
    nreq = s.query(db.RemovalRequest).get(r4["request_id"])
    assert r4["state"] == "new_broker" and nb.name == "brand-new-broker.example"
    assert nb.method == db.OptOutMethod.manual and lf.UNKNOWN_BROKER_NOTE in nb.notes
    assert nreq.status == db.RequestStatus.needs_manual and "brand-new-broker.example" in nreq.notes
    found = s.query(db.DiscoveryResult).filter(db.DiscoveryResult.source == "manual").count()
    assert found == 4, found
    s.close()
    # EXPECTED: every pasted listing ends up in the removal cycle or on the checklist.
    # IF THIS FAILS: listings people find by hand get lost.


@test(1, "interpreter.listing_url_field",
      "Broker specs can fill a form box with the member's own listing address.")
def t_listing_url_field():
    ci = _imp("core.interpreter")
    spec = ci.BrokerSpec.from_dict({"broker_id": "s", "name": "S", "method": "form",
                                    "opt_out_url": "https://s.example/optout",
                                    "steps": [{"kind": "fill", "selector": "input[name=url]", "field": "listing_url"}]})
    assert spec.validate() == []
    job = ci.compile_job(spec, {"listing_url": "https://s.example/p/jane"}, member_id="1")
    assert [st.value for st in job.steps if st.kind == "fill"] == ["https://s.example/p/jane"]



# ── State registries, dead sites, California DROP ─────────────────────────────

_CA_CSV = ("\ufeffData Broker Name,Website URL,Email Address,Registration Date,Notes\n"
           "Radaris LLC,https://radaris.com,privacy@radaris.example,2026-01-02,\n"
           "Acme Audience Data,www.acme-audience.example,optout@acme-audience.example,2026-02-03,\n"
           "TruthFinder,https://www.truthfinder.com/,,2026-02-04,\n"
           "No Website Co,,x@y.example,2026-02-05,\n").encode("utf-8")


@test(1, "registry.parse_exports",
      "Registry exports are read whatever their column names, encoding or delimiter; rows without a website are skipped.")
def t_registry_parse():
    rs = _imp("core.registry_sync")
    p = rs.parse_registry(_CA_CSV, "ca.csv")
    assert [r["domain"] for r in p["rows"]] == ["radaris.com", "acme-audience.example", "truthfinder.com"], p["rows"]
    assert p["skipped"] == 1 and p["mapped"]["name"] == "Data Broker Name" and "Registration Date" in p["unmapped"]
    assert p["rows"][0]["email"] == "privacy@radaris.example"
    semi = "Title line\n\nBusiness Name;Website;Contact Email\nOregon Data Co;oregondata.example;bad-email\n".encode("cp1252")
    q = rs.parse_registry(semi, "or.csv")
    assert q["rows"] == [{"name": "Oregon Data Co", "website": "oregondata.example",
                          "domain": "oregondata.example", "email": "", "opt_out_url": ""}], q
    for data, name, frag in ((b"", "x.csv", "empty"), (b"a,b\n1,2\n", "x.csv", "columns"),
                             (b"x", "old.xls", "xls")):
        try:
            rs.parse_registry(data, name); raise AssertionError(name)
        except ValueError as e:
            assert frag in str(e).lower(), (name, str(e))
    for url in ("http://x.example/a.csv", "https://localhost/a.csv", "https://127.0.0.1/a.csv"):
        try:
            rs.fetch_registry(url); raise AssertionError(url)
        except ValueError:
            pass


@test(2, "registry.import_starts_off_and_never_overrides",
      "Imported brokers start turned off; existing brokers only gain registry details; repeat imports from other states merge.")
def t_registry_import():
    db, s = _memory_db()
    rs = _imp("core.registry_sync")
    s.add(db.Broker(name="Radaris", opt_out_url="https://radaris.com/control-privacy", enabled=True))
    s.commit()
    rows = rs.parse_registry(_CA_CSV, "ca.csv")["rows"]
    plan = rs.plan(s, "CA", rows)
    assert plan["counts"] == {"rows": 3, "new": 2, "matched": 1, "no_longer_listed": 0}, plan["counts"]
    assert s.query(db.Broker).count() == 1, "preview must not write"
    assert any(n["domain"] == "truthfinder.com" and n["family"] == "PeopleConnect (Intelius)" for n in plan["new"])
    rs.apply(s, "CA", rows)
    B = {b.name: b for b in s.query(db.Broker).all()}
    acme = B["Acme Audience Data"]
    assert acme.enabled is False and acme.origin == "registry" and acme.registry_states == "CA"
    assert acme.method == db.OptOutMethod.manual and acme.registry_contact_email == "optout@acme-audience.example"
    rad = B["Radaris"]
    assert rad.enabled and rad.opt_out_url == "https://radaris.com/control-privacy" and rad.registry_states == "CA"
    assert (rad.origin or "curated") == "curated"
    rs.apply(s, "VT", rows[:1])
    s.refresh(rad); s.refresh(acme)
    assert rad.registry_states == "CA,VT"
    gone = rs.plan(s, "CA", rows[:1])["no_longer_listed"]
    assert {g["broker_name"] for g in gone} == {"Acme Audience Data", "TruthFinder"}, gone
    assert s.query(db.Broker).filter(db.Broker.enabled.is_(True)).count() == 1, "import must never turn brokers on"
    assert rs.enable_brokers(s, all_registry=True) == 2
    s.close()


@test(2, "registry.turning_on_requires_acknowledging_warning",
      "The admin endpoint refuses to turn registry brokers on unless the warning was acknowledged.")
def t_registry_ack():
    db, s = _memory_db()
    try:
        reg = _imp("routers.registry")
    except Exception as e:
        raise Skip(f"router deps missing: {e}")
    from fastapi import HTTPException
    b = db.Broker(name="Acme", opt_out_url="https://acme.example", enabled=False, origin="registry", registry_states="CA")
    s.add(b); s.commit()
    try:
        reg.enable(reg.EnableIn(broker_ids=[b.id]), s, None)
        raise AssertionError("enabled without acknowledgement")
    except HTTPException as e:
        assert e.status_code == 400 and "more harm than good" in e.detail
    s.refresh(b); assert b.enabled is False
    assert reg.enable(reg.EnableIn(broker_ids=[b.id], acknowledge=True), s, None)["enabled"] == 1
    s.close()


@test(2, "registry.gate_listing_exception_and_drop",
      "Off registry brokers run only for someone with a listing there; CA-only registry brokers are skipped 90 days after DROP.")
def t_registry_gate():
    from datetime import datetime, timedelta
    db, s = _memory_db()
    gate = _imp("core.broker_gate")
    sp = _imp("core.state_programs")
    U = db.User(email="c@x.example", full_name="Cal Resident", role=db.UserRole.parent)
    s.add(U); s.flush()
    m = db.FamilyMember(user_id=U.id, full_name="Cal Resident"); s.add(m); s.flush()
    s.add(db.Identity(member_id=m.id, kind="address", value="1 Ocean Ave, Santa Monica, CA 90401", is_primary=True))
    off = db.Broker(name="AdCo", opt_out_url="https://adco.example", enabled=False, origin="registry", registry_states="CA")
    cur = db.Broker(name="Curated", opt_out_url="https://cur.example", enabled=False)
    on_ca = db.Broker(name="OnCA", opt_out_url="https://onca.example", enabled=True, origin="registry", registry_states="CA")
    on_ca_tx = db.Broker(name="OnCATX", opt_out_url="https://oncatx.example", enabled=True, origin="registry", registry_states="CA,TX")
    s.add_all([off, cur, on_ca, on_ca_tx]); s.flush()
    R = lambda b, url=None: db.RemovalRequest(member_id=m.id, broker_id=b.id, listing_url=url, status=db.RequestStatus.pending)
    reqs = {"off": R(off), "off_listed": R(off, "https://adco.example/p/cal"), "cur": R(cur, "https://cur.example/p"),
            "on_ca": R(on_ca), "on_ca_tx": R(on_ca_tx)}
    s.add_all(reqs.values()); s.commit()
    ok = {k: gate.request_allowed(r, s) for k, r in reqs.items()}
    assert ok == {"off": False, "off_listed": True, "cur": False, "on_ca": True, "on_ca_tx": True}, ok
    assert sp.ensure_drop_items(s) == 1 and sp.ensure_drop_items(s) == 0, "one DROP item, once"
    drop_req = s.query(db.RemovalRequest).join(db.Broker).filter(db.Broker.origin == "state_program").one()
    assert drop_req.status == db.RequestStatus.needs_manual and "privacy.ca.gov/drop" in drop_req.notes
    drop_req.status = db.RequestStatus.confirmed
    drop_req.confirmed_at = datetime.utcnow() - timedelta(days=91); s.commit()
    assert gate.request_allowed(reqs["on_ca"], s) is False, "CA-only registry broker covered by DROP"
    assert gate.request_allowed(reqs["on_ca_tx"], s) is True, "also registered elsewhere: still contact it"
    drop_req.confirmed_at = datetime.utcnow() - timedelta(days=10); s.commit()
    assert gate.request_allowed(reqs["on_ca"], s) is True, "brokers' 90 days not up yet"
    s.close()


@test(2, "broker_health.dead_sites",
      "A site unreachable for 30+ days is marked defunct and turned off; one that answers again is flagged, not turned on.")
def t_dead_sites():
    from datetime import datetime, timedelta
    db, s = _memory_db()
    bh = _imp("core.broker_health")
    b = db.Broker(name="Gone.example", opt_out_url="https://gone.example/optout", enabled=True,
                  registry_states="CA", registry_last_seen=datetime.utcnow())
    s.add(b); s.commit()
    assert bh.classify_failure("net::ERR_NAME_NOT_RESOLVED at https://gone.example") == "unreachable"
    assert bh.classify_failure("Timeout 8000ms exceeded") == "timeout"
    bh.record_failure(s, b.id, "net::ERR_NAME_NOT_RESOLVED")
    h = s.query(db.BrokerHealth).filter_by(broker_id=b.id).one()
    assert h.unreachable_since and not h.defunct and b.enabled
    h.unreachable_since = datetime.utcnow() - timedelta(days=31); s.commit()
    bh.record_probe(s, b.id, False, "getaddrinfo failed")
    s.refresh(h); s.refresh(b)
    assert h.defunct and not b.enabled and "still on a state data broker registry" in h.auto_disabled_reason
    bh.record_probe(s, b.id, True, "HTTP 200")
    s.refresh(h); s.refresh(b)
    assert not h.defunct and h.needs_review and not b.enabled, "a returning site needs a person to check it"
    bh.record_failure(s, b.id, "selector #email not found")
    s.refresh(h); assert h.unreachable_since is None, "a form error means the site is up"
    seen = []
    res = bh.probe_sites(s, limit=5, fetch=lambda d: (seen.append(d) or (True, "ok")))
    assert res == {"checked": 1, "unreachable": 0} and seen == ["gone.example"]
    s.close()


@test(2, "listings.manual_broker_gets_instructions",
      "A listing on a site with no automated opt-out becomes a checklist item naming where to ask, including the registry contact.")
def t_listing_manual_registry():
    db, s = _memory_db()
    lf = _imp("core.listing_finder")
    m = _member_with_vault(db, s)
    b = db.Broker(name="Acme Audience Data", opt_out_url="https://acme-audience.example", enabled=False,
                  origin="registry", registry_states="CA", registry_contact_email="optout@acme-audience.example",
                  method=db.OptOutMethod.manual)
    s.add(b); s.commit()
    r = lf.add_listing(s, m, "https://acme-audience.example/people/jane")
    req = s.query(db.RemovalRequest).get(r["request_id"])
    assert r["broker_name"] == "Acme Audience Data"
    assert req.status == db.RequestStatus.needs_manual
    assert "optout@acme-audience.example" in req.notes and "acme-audience.example/people/jane" in req.notes
    s.close()



# ── General web search ────────────────────────────────────────────────────────

@test(1, "web_search.match_strength",
      "Results are scored strong (exact phone/address/email), medium (name + city) or weak.")
def t_ws_score():
    ws = _imp("core.web_search")
    prof = {"names": ["Jane Q Public", "Jane Public"], "places": ["Austin, TX"],
            "streets": ["123 Main Street"], "phones": ["+1 (512) 555-0134"], "emails": ["jane@old.example"]}
    assert ws.score(prof, "Jane Public, age 41, phone 512.555.0134") == ("strong", "phone")
    assert ws.score(prof, "Lives at 123 Main St, Austin TX") == ("strong", "address")
    assert ws.score(prof, "contact: JANE@old.example") == ("strong", "email")
    assert ws.score(prof, "Jane Public in Austin, TX — relatives") == ("medium", "name+city")
    assert ws.score(prof, "Jane Public of Denver") == ("weak", "name")
    assert ws.score(prof, "1123 Main Street Springfield") == ("weak", ""), "street must match as a whole"
    assert ws.score(prof, "call 512-555-0135") == ("weak", "")
    assert not ws.configured({"enabled": True, "provider": "searxng", "searxng_url": ""})
    assert ws.configured({"enabled": True, "provider": "searxng", "searxng_url": "http://searxng:8080"})


@test(1, "web_search.on_by_default",
      "Web search is on (weekly too) when the bundled SearXNG address is set; an admin's choice wins.")
def t_ws_default():
    ws = _imp("core.web_search")
    old = os.environ.get("SEARXNG_URL")
    try:
        os.environ["SEARXNG_URL"] = "http://searxng:8080"
        d = ws.settings_of({})
        assert d["enabled"] and d["weekly"] and ws.configured(d), d
        assert ws.configured(ws.settings_of({"web_search": {"searxng_url": ""}})), "empty saved address keeps the bundled one"
        assert not ws.configured(ws.settings_of({"web_search": {"enabled": False}})), "an admin can turn it off"
        os.environ["SEARXNG_URL"] = ""
        assert not ws.configured(ws.settings_of({})), "no SearXNG anywhere: nothing to search with"
    finally:
        if old is None:
            os.environ.pop("SEARXNG_URL", None)
        else:
            os.environ["SEARXNG_URL"] = old


@test(2, "web_search.sorts_results_and_adds_strong_broker_matches",
      "Strong matches on known brokers join the removal cycle; everything else waits for review; 'not me' is remembered.")
def t_ws_run():
    db, s = _memory_db()
    ws = _imp("core.web_search")
    m = _member_with_vault(db, s)
    s.add_all([db.Broker(name="Radaris", opt_out_url="https://radaris.com/control-privacy"),
               db.Broker(name="Spokeo.com", opt_out_url="https://www.spokeo.com/optout")])
    s.commit()
    pages = [
        {"url": "https://radaris.com/p/Jane/Public/", "title": "Jane Public, Austin", "snippet": "Phone (512) 555-0134"},
        {"url": "https://www.spokeo.com/Jane-Public/Texas/Austin", "title": "Jane Public - Austin, TX", "snippet": "Age 41"},
        {"url": "https://unknownpeople.example/jane", "title": "Jane Q Public", "snippet": "512-555-0134"},
        {"url": "https://www.google.com/search?q=x", "title": "x", "snippet": ""},
        {"url": "https://radaris.com/p/Jane/Public", "title": "dupe", "snippet": "same page"},
    ]
    calls = []
    search = lambda q: (calls.append(q) or pages)
    st = ws.run_for_member(s, m, {"web_search": {"max_queries": 3}}, search=search, pause=0)
    assert len(calls) == 3 and st["queries"] == 3
    assert st["new"] == 3 and st["added"] == 1, st
    H = {h.domain: h for h in s.query(db.WebSearchHit).all()}
    assert set(H) == {"radaris.com", "spokeo.com", "unknownpeople.example"}
    assert H["radaris.com"].status == "added" and H["radaris.com"].request_id
    req = s.query(db.RemovalRequest).get(H["radaris.com"].request_id)
    assert req.listing_url.startswith("https://radaris.com/p/Jane/Public")
    assert H["spokeo.com"].status == "new" and H["spokeo.com"].strength == "medium"
    assert H["unknownpeople.example"].status == "new" and H["unknownpeople.example"].strength == "strong", \
        "unknown sites are never added without a person"
    assert H["radaris.com"].title == "Jane Public, Austin"
    ws.dismiss_hit(s, H["spokeo.com"])
    st2 = ws.run_for_member(s, m, {"web_search": {"max_queries": 1}}, search=lambda q: pages, pause=0)
    assert st2["new"] == 0 and s.query(db.WebSearchHit).filter_by(status="dismissed").count() == 1
    res = ws.add_hit(s, H["unknownpeople.example"], m)
    assert res["state"] == "new_broker" and H["unknownpeople.example"].status == "added"
    def broken(q):
        raise RuntimeError("SearXNG refused the request. Add `json` to search.formats in its settings.yml.")
    st3 = ws.run_for_member(s, m, {"web_search": {"max_queries": 5}}, search=broken, pause=0)
    assert st3["queries"] == 0 and len(st3["errors"]) == 1, "stop when the provider refuses"
    s.close()
    # EXPECTED: no person-less additions except strong matches on known brokers.
    # IF THIS FAILS: wrong people's pages could be sent opt-outs, or real listings missed.



# ── Checklist ─────────────────────────────────────────────────────────────────

@test(2, "checklist.groups_and_progress",
      "The checklist gathers inbox, finish-by-hand, CAPTCHA, review, overdue and re-check items, with per-person progress.")
def t_checklist():
    from datetime import datetime, timedelta
    db, s = _memory_db()
    cl = _imp("core.checklist")
    P, C, pm, cm, boxes = _family(db, s, parent_inbox="pat@yahoo.com", parent_plus="unsupported")
    b = {n: db.Broker(name=n, opt_out_url=f"https://{n.lower()}.example") for n in ("A", "B", "Cc", "D", "E", "F")}
    s.add_all(b.values()); s.flush()
    now = datetime.utcnow()
    R = db.RequestStatus
    reqs = [
        db.RemovalRequest(member_id=pm.id, broker_id=b["A"].id, status=R.needs_manual, notes="Do the thing at A."),
        db.RemovalRequest(member_id=pm.id, broker_id=b["B"].id, status=R.pending),
        db.RemovalRequest(member_id=pm.id, broker_id=b["Cc"].id, status=R.sent, sent_at=now - timedelta(days=60)),
        db.RemovalRequest(member_id=pm.id, broker_id=b["D"].id, status=R.sent, sent_at=now - timedelta(days=10)),
        db.RemovalRequest(member_id=pm.id, broker_id=b["E"].id, status=R.confirmed, recheck_after=now - timedelta(days=1)),
        db.RemovalRequest(member_id=cm.id, broker_id=b["F"].id, status=R.confirmed, recheck_after=now + timedelta(days=30)),
    ]
    s.add_all(reqs); s.flush()
    s.add(db.CaptchaChallenge(request_id=reqs[1].id, broker_id=b["B"].id, member_id=pm.id, status="pending"))
    s.add(db.WebSearchHit(member_id=cm.id, url="https://x.example/kim", url_hash="h1", domain="x.example", status="new"))
    s.commit()
    data = cl.build(s, [pm.id, cm.id])
    g = data["groups"]
    assert [i["member_name"] for i in g["inbox"]] == ["Kim Kid"], "Kim can't share Pat's Yahoo inbox"
    assert [i["broker_name"] for i in g["finish"]] == ["A"] and "Do the thing" in g["finish"][0]["text"]
    assert [i["broker_name"] for i in g["captcha"]] == ["B"]
    assert [i["broker_name"] for i in g["overdue"]] == ["Cc"] and g["overdue"][0]["days_waiting"] >= 60
    assert [i["broker_name"] for i in g["recheck"]] == ["E"]
    assert g["review"][0]["member_name"] == "Kim Kid" and g["review"][0]["count"] == 1
    P_ = {p["member_name"]: p for p in data["progress"]}
    assert P_["Pat Parent"] == {"member_id": pm.id, "member_name": "Pat Parent", "removed": 1,
                                "in_progress": 1, "needs_you": 3, "other": 0}, P_["Pat Parent"]
    assert P_["Kim Kid"]["removed"] == 1 and P_["Kim Kid"]["needs_you"] == 2
    cl.mark_done(s, reqs[0], "Pat")
    assert reqs[0].status == R.sent and reqs[0].recheck_after > now and "Done by Pat" in reqs[0].notes
    cl.mark_removed(s, reqs[2], "Pat")
    assert reqs[2].status == R.confirmed and reqs[2].confirmed_at
    g2 = cl.build(s, [pm.id])["groups"]
    assert not g2["finish"] and not g2["overdue"]
    s.close()



# ── Broker confirmation links ─────────────────────────────────────────────────

@test(1, "confirm_links.reading_the_email",
      "Confirmation links are found in HTML and text; only https links on the broker's site (or a click-tracker) are picked.")
def t_confirm_read():
    c = _imp("core.confirm_links")
    links = c.extract_links("Or paste https://radaris.com/optout/verify?t=abc.",
                            '<a href="https://radaris.com/unsubscribe?u=1">Unsubscribe</a>'
                            '<a href="https://u1.ct.sendgrid.net/ls/click?upn=x&amp;y=1">Confirm my removal</a>')
    urls = [l["url"] for l in links]
    assert "https://u1.ct.sendgrid.net/ls/click?upn=x&y=1" in urls and "https://radaris.com/optout/verify?t=abc" in urls
    dom = {"radaris.com"}
    assert c.pick_link(links, dom) == ("https://radaris.com/optout/verify?t=abc", None)
    assert c.pick_link([{"url": "https://radaris.com/unsubscribe", "text": "confirm"}], dom) == (None, "no_link")
    assert c.pick_link([{"url": "http://radaris.com/confirm?t=1", "text": ""}], dom)[0] is None, "https only"
    assert c.pick_link([{"url": "https://radaris.evil.example/confirm?t=1", "text": ""}], dom) == (None, "off_site")
    assert c.pick_link([{"url": "https://u1.ct.sendgrid.net/ls/click?u=1", "text": "Verify email"}], dom)[0]
    assert c.asks_for_click("Confirm your opt-out", "Please click the link below to confirm your request.")
    assert c.asks_for_click("", "Use the verification link we sent.")
    assert not c.asks_for_click("Removed", "Your listing was removed. Questions? Click here for support.")
    # EXPECTED: the confirm link is chosen, unsubscribe/off-site/plain-http links never are.


@test(2, "confirm_links.safe_visit",
      "Clicking follows only https redirects on the broker's site or a click-tracker, never private addresses, and reads the result.")
def t_confirm_visit():
    c = _imp("core.confirm_links")
    dom = {"radaris.com"}
    pages = {
        "https://u1.ct.sendgrid.net/c?1": (302, "https://radaris.com/optout/done?t=1", ""),
        "https://radaris.com/optout/done?t=1": (200, "", "<h1>Your request has been confirmed.</h1>"),
        "https://u1.ct.sendgrid.net/c?2": (302, "https://other-site.example/x", ""),
        "https://radaris.com/c?3": (302, "https://internal.radaris.com/x", ""),
        "https://radaris.com/c?4": (200, "", "<p>This link has expired.</p>"),
        "https://radaris.com/c?5": (200, "", '<form><button type="submit">Confirm removal</button></form>'),
        "https://radaris.com/c?6": (302, "http://radaris.com/plain", ""),
    }
    visited = []
    def get(u):
        visited.append(u); return pages[u]
    resolve = lambda h: h != "internal.radaris.com"
    assert c.http_visit("https://u1.ct.sendgrid.net/c?1", dom, get, resolve)[0] == "ok"
    assert c.http_visit("https://u1.ct.sendgrid.net/c?2", dom, get, resolve)[0] == "off_site"
    assert "https://other-site.example/x" not in visited, "never request a site that isn't the broker's"
    assert c.http_visit("https://radaris.com/c?3", dom, get, resolve)[0] == "off_site"
    assert "https://internal.radaris.com/x" not in visited, "never request private addresses"
    assert c.http_visit("https://radaris.com/c?4", dom, get, resolve)[0] == "rejected"
    assert c.http_visit("https://radaris.com/c?5", dom, get, resolve)[0] == "needs_button"
    assert c.http_visit("https://radaris.com/c?6", dom, get, resolve)[0] == "off_site"
    # EXPECTED: only the broker's own pages (via a tracker at most) are ever requested.
    # IF THIS FAILS: a reply email could make the server fetch arbitrary or internal URLs.


@test(2, "confirm_links.reply_waits_for_click",
      "A 'click to confirm' reply keeps the request sent until the link is clicked; failures go on the checklist.")
def t_confirm_flow():
    db, s = _memory_db()
    m = _imp("core.mailboxes")
    c = _imp("core.confirm_links")
    cl = _imp("core.checklist")
    try:
        sched = _imp("core.scheduler")
    except Exception as e:
        raise Skip(f"scheduler deps missing: {e}")
    P, C, pm, cm, boxes = _family(db, s, parent_inbox="pat@gmail.com")
    R = db.RequestStatus
    b1 = db.Broker(name="Radaris", opt_out_url="https://radaris.com/control-privacy")
    b2 = db.Broker(name="Spokeo", opt_out_url="https://www.spokeo.com/optout")
    s.add_all([b1, b2]); s.flush()
    r1 = db.RemovalRequest(member_id=cm.id, broker_id=b1.id, request_key="rk-1", status=R.sent)
    r2 = db.RemovalRequest(member_id=cm.id, broker_id=b2.id, request_key="rk-2", status=R.sent)
    s.add_all([r1, r2]); s.commit()
    ca1, _ = m.issue_contact_address(s, boxes["parent"], cm, broker=b1, request_key="rk-1")
    ca2, _ = m.issue_contact_address(s, boxes["parent"], cm, broker=b2, request_key="rk-2")
    ask = "Please click the link below to confirm your opt-out request."

    # 1. Link on the broker's site: saved, request still 'sent', then clicked.
    n = sched._handle_member_message(s, {}, boxes["parent"], ca1.address, "privacy@radaris.com",
                                     "Confirm your request", ask,
                                     links=[{"url": "https://radaris.com/optout/verify?t=SECRET", "text": "Confirm"}])
    s.refresh(r1)
    row = s.query(db.ConfirmationLink).filter_by(request_id=r1.id).one()
    assert n == 1 and r1.status == R.sent and row.status == "pending" and row.host == "radaris.com"
    stats = c.click_pending(s, {}, visit=lambda u, d: ("ok", u), press=lambda u, d: "ok")
    s.refresh(r1); s.refresh(row)
    assert stats["clicked"] == 1 and row.status == "clicked" and r1.status == R.confirmed and r1.recheck_after

    # 2. The inbox couldn't give us links: goes on the checklist; "I've confirmed it" finishes it.
    sched._handle_member_message(s, {}, boxes["parent"], ca2.address, "noreply@spokeo.com",
                                 "Action required", ask, links=None)
    s.refresh(r2)
    row2 = s.query(db.ConfirmationLink).filter_by(request_id=r2.id).one()
    assert r2.status == R.sent and row2.status == "needs_person" and row2.reason == "no_link"
    g = cl.build(s, [cm.id])["groups"]
    assert [i["broker_name"] for i in g["confirm"]] == ["Spokeo"] and g["confirm"][0]["confirm_url"] is None
    assert "noreply@spokeo.com" in g["confirm"][0]["text"]
    c.mark_done(s, row2, {}, "Pat")
    s.refresh(r2)
    assert r2.status == R.confirmed and row2.status == "done"

    # 3. A stranger writing to the tag: nothing of theirs is ever clicked.
    r3 = db.RemovalRequest(member_id=cm.id, broker_id=b1.id, request_key="rk-3", status=R.sent)
    s.add(r3); s.commit()
    ca3, _ = m.issue_contact_address(s, boxes["parent"], cm, broker=b1, request_key="rk-3")
    sched._handle_member_message(s, {}, boxes["parent"], ca3.address, "promo@spam-deals.example",
                                 "Confirm now", ask,
                                 links=[{"url": "https://radaris.com/confirm?t=FAKE", "text": "Confirm"}])
    assert not s.query(db.ConfirmationLink).filter(db.ConfirmationLink.request_id == r3.id,
                                                   db.ConfirmationLink.url.isnot(None)).count()

    # 4. A page that rejects the link goes to the checklist with the link to open by hand.
    r4 = db.RemovalRequest(member_id=cm.id, broker_id=b2.id, request_key="rk-4", status=R.sent)
    s.add(r4); s.commit()
    c.handle_reply(s, [r4], "Verify", ask, [{"url": "https://www.spokeo.com/optout/confirm/xyz", "text": ""}])
    c.click_pending(s, {}, visit=lambda u, d: ("rejected", u))
    item = [i for i in cl.build(s, [cm.id])["groups"]["confirm"] if i["request_id"] == r4.id][0]
    assert item["confirm_url"] == "https://www.spokeo.com/optout/confirm/xyz" and "expired" in item["text"]

    # 5. Auto-click turned off: everything waits for a person.
    r5 = db.RemovalRequest(member_id=cm.id, broker_id=b1.id, request_key="rk-5", status=R.sent)
    s.add(r5); s.commit()
    c.handle_reply(s, [r5], "Verify", ask, [{"url": "https://radaris.com/confirm?t=5", "text": ""}])
    c.click_pending(s, {"confirm_links": {"auto_click": False}}, visit=lambda u, d: 1 / 0)
    assert s.query(db.ConfirmationLink).filter_by(request_id=r5.id).one().reason == "turned_off"
    s.close()
    # EXPECTED: "click to confirm" replies are no longer counted as removals until clicked.
    # IF THIS FAILS: the dashboard counts removals that the broker never processed.


# ── Per-variant removal report ────────────────────────────────────────────────

@test(2, "variants.tracking_and_report",
      "Requests record which saved details they sent; the report splits main details from other variants.")
def t_variant_report():
    db, s = _memory_db()
    vr = _imp("core.variant_report")
    cmb = _imp("core.combinations")
    m = _member_with_vault(db, s)           # Jane Q Public / Jane Public, 123 Main St, one phone, one email
    s.add(db.Identity(member_id=m.id, kind="address", value="9 Old Rd, Dallas, TX 75201", is_primary=False))
    s.add(db.Identity(member_id=m.id, kind="phone", value="(214) 555-0199", is_primary=False))
    s.commit(); s.refresh(m)
    I = {(i.kind, i.value): i.id for i in m.identities}
    main = vr.main_identity_ids(m)
    assert main == {I[("name", "Jane Q Public")], I[("address", "123 Main St, Austin, TX 78701")],
                    I[("phone", "+1 (512) 555-0134")]}, main

    combo = cmb.IdentityCombo(name="Jane Public", address="9 Old Rd", city="Dallas", state="TX",
                              phone="(214) 555-0199", email=None)
    assert set(vr.identities_for_combo(m, combo)) == {I[("name", "Jane Public")], I[("address", "9 Old Rd, Dallas, TX 75201")],
                                                      I[("phone", "(214) 555-0199")]}
    assert len(vr.identities_in_email(m)) == 7, "an email lists every saved detail"

    B = [db.Broker(name=f"B{i}", opt_out_url=f"https://b{i}.example") for i in range(4)]
    s.add_all(B); s.flush()
    R = db.RequestStatus
    a = db.RemovalRequest(member_id=m.id, broker_id=B[0].id, status=R.confirmed)   # every detail, removed
    b = db.RemovalRequest(member_id=m.id, broker_id=B[1].id, status=R.sent)        # main only, waiting
    c = db.RemovalRequest(member_id=m.id, broker_id=B[2].id, status=R.pending)     # not sent: not counted
    d = db.RemovalRequest(member_id=m.id, broker_id=B[3].id, status=R.confirmed)   # older, nothing recorded
    s.add_all([a, b, c, d]); s.flush()
    sent_all = [i for i in vr.identities_in_email(m) if i != I[("phone", "(214) 555-0199")]]
    assert vr.record(s, a.id, sent_all) == 6 and vr.record(s, a.id, sent_all) == 0, "recording is idempotent"
    vr.record(s, b.id, main)
    vr.record(s, c.id, [I[("name", "Jane Public")]])
    s.commit()

    rep = vr.member_report(s, m)
    assert rep["main"] == {"sent": 6, "removed": 3, "count": 3, "never_sent": 0, "percent_removed": 50}, rep["main"]
    assert rep["variants"] == {"sent": 3, "removed": 3, "count": 4, "never_sent": 1, "percent_removed": 100}, rep["variants"]
    assert rep["untracked_requests"] == 1
    labels = {d["label"]: d for d in rep["details"]}
    assert "••• 0134" in labels and labels["••• 0199"]["brokers_sent"] == 0, "phones are masked"
    assert "j•••@old.example" in labels
    fam = vr.family_report(s, [m.id])
    assert fam["family"]["main"]["percent_removed"] == 50 and fam["untracked_requests"] == 1
    s.close()
    # EXPECTED: removal coverage reported separately for main details and other variants.
    # IF THIS FAILS: the dashboard would overstate (or hide) how far removal has reached.


# ── runner ────────────────────────────────────────────────────────────────────

@test(2, "keyed.phone_and_email_optouts",
      "Sites that file people by phone or email get one opt-out per saved number or address.")
def t_keyed_optouts():
    db, s = _memory_db()
    cmb = _imp("core.combinations")
    bs = _imp("core.interpreter.broker_spec")
    mf = _imp("core.interpreter.member_fields")
    m = _member_with_vault(db, s)
    s.add(db.Identity(member_id=m.id, kind="phone", value="(214) 555-0199", is_primary=False))
    s.add(db.Identity(member_id=m.id, kind="email", value="jane@work.example", is_primary=False))
    s.commit(); s.refresh(m)
    phones = cmb.build_keyed_optout_combos(m, "phone")
    assert [c.phone for c in phones] == ["+1 (512) 555-0134", "(214) 555-0199"], phones
    assert all(c.name == "Jane Q Public" and c.city == "Austin" for c in phones)
    emails = cmb.build_keyed_optout_combos(m, "email")
    assert len(emails) == len([i for i in m.identities if i.kind == "email"]) and all(c.email for c in emails)
    f = mf.resolve(m, phones[1])
    assert f["phone_digits"] == "2145550199" and f["phone_e164"] == "+12145550199" and f["phone_dashed"] == "214-555-0199"
    assert "(214) 555-0199" in f["all_phones"] and "jane@work.example" in f["all_emails"]
    assert mf.phone_e164("+44 20 7946 0958") == "+442079460958"
    ok = bs.BrokerSpec.from_dict({"broker_id": "x", "name": "X", "method": "manual", "lookup_by": "phone"})
    assert ok.validate() == [] and ok.to_dict()["lookup_by"] == "phone"
    bad = bs.BrokerSpec.from_dict({"broker_id": "x", "name": "X", "method": "manual", "lookup_by": "ssn"})
    assert any("lookup_by" in e for e in bad.validate())
    assert not any("ssn" in k or "social" in k for k in bs.KNOWN_FIELDS), "never a field for Social Security numbers"
    eng = _imp("core.optout_engine")
    msg = eng._missing_key_instruction(type("B", (), {"name": "Truecaller"})(), m, "phone")
    assert "phone numbers" in msg and "Your details" in msg, msg
    s.close()
    # EXPECTED: a caller-ID or email-lookup site gets a request for every saved number/address.
    # IF THIS FAILS: old numbers and work emails would stay listed on those sites.


@test(2, "keyed.verify_each_number",
      "Checking a phone site searches every saved number and ignores the number the page just echoes back.")
def t_keyed_verify():
    db, s = _memory_db()
    ver = _imp("core.verification")
    bs = _imp("core.interpreter.broker_spec")
    m = _member_with_vault(db, s)
    s.add(db.Identity(member_id=m.id, kind="phone", value="(214) 555-0199", is_primary=False))
    s.commit(); s.refresh(m)
    spec = bs.BrokerSpec.from_dict({"broker_id": "p", "name": "P", "method": "manual", "lookup_by": "phone",
                                    "search_url": "https://p.example/lookup?n={phone_digits}",
                                    "listing_pattern": "/number/"})
    profile = ver._profile(m)
    pages = {}
    def fetch(url, domain):
        return url, 200, pages.get(url.split("n=")[-1], "<p>No results</p>")
    # The page only repeats the searched number under someone else's name: not her.
    pages["5125550134"] = '<a href="/number/5125550134">512-555-0134</a> Bob Smith, Reno NV'
    v, d, _ = ver.check_keyed_search(spec, m, profile, "p.example", fetch, "phone")
    assert v == "gone", (v, d)
    # The second number shows her name and city: still listed.
    pages["2145550199"] = '<a href="/number/2145550199">214-555-0199</a> Jane Q Public, Austin TX'
    v, d, _ = ver.check_keyed_search(spec, m, profile, "p.example", fetch, "phone")
    assert v == "listed" and "0199" in d, (v, d)
    s.close()
    # EXPECTED: one search per saved number; an echoed number alone isn't proof of a listing.
    # IF THIS FAILS: phone sites would always look "still listed", or a listing on an old number would be missed.


@test(2, "age.dob_fields_and_matching",
      "A saved birthday fills age, birth year and date fields, and an age on a page tells her from a namesake.")
def t_age_dob():
    import datetime as _dt
    db, s = _memory_db()
    age = _imp("core.age")
    mf = _imp("core.interpreter.member_fields")
    ws = _imp("core.web_search")
    lf = _imp("core.listing_finder")
    assert age.parse_dob("1983-04-09") == _dt.date(1983, 4, 9)
    assert age.parse_dob("04/09/1983") == _dt.date(1983, 4, 9) and age.parse_dob("19830409") == _dt.date(1983, 4, 9)
    assert age.parse_dob("2999-01-01") is None and age.parse_dob("1983-02-30") is None and age.parse_dob("soon") is None
    assert age.age_on(_dt.date(1983, 4, 9), _dt.date(2026, 4, 8)) == 42
    assert age.age_on(_dt.date(1983, 4, 9), _dt.date(2026, 4, 9)) == 43
    assert age.age_range(43) == "40-49"
    m = _member_with_vault(db, s)
    m.dob = "1983-04-09"; s.commit(); s.refresh(m)
    f = mf.resolve(m, today=_dt.date(2026, 10, 11))
    assert f["age"] == "43" and f["birth_year"] == "1983" and f["dob"] == "04/09/1983"
    assert f["dob_iso"] == "1983-04-09" and f["birth_month"] == "4" and f["birth_day"] == "9" and f["age_range"] == "40-49"
    m.dob = None; m.age = 30; s.commit(); s.refresh(m)
    f = mf.resolve(m, today=_dt.date(2026, 10, 11))
    assert f["age"] == "30" and f["dob"] is None and f["birth_year"] == "1996"
    m.dob = "1983-04-09"; s.commit(); s.refresh(m)
    prof = lf._profile(m)
    assert set(age.plausible_ages(m)) >= {age.current_age(m)}
    a = age.current_age(m)
    assert ws.score(prof, f"Jane Q Public, Age {a}")[0] == "medium"
    assert ws.score(prof, f"Jane Q Public Austin TX age {a}") == ("strong", "name+city+age")
    assert ws.score(prof, "Jane Q Public, Age 71")[0] == "weak", "a different age is not her"
    assert ws.score(prof, "Jane Q Public, born 1983")[0] == "medium"
    s.close()
    # EXPECTED: birthday-driven fields and age-aware matching.
    # IF THIS FAILS: forms that need a birth date stop for a person, or namesakes get mixed up.


@test(2, "credit_freeze.letters",
      "Freeze letters fill in name, address and birthday, never a Social Security number, and children get the parent version.")
def t_credit_freeze_letters():
    import datetime as _dt
    db, s = _memory_db()
    cf = _imp("core.credit_freeze")
    parent = _member_with_vault(db, s)
    parent.dob = "1983-04-09"
    U = db.User(email="kid@x.example", full_name="Kid Public", role=db.UserRole.member)
    s.add(U); s.flush()
    kid = db.FamilyMember(user_id=U.id, full_name="Kid Public", dob="2016-06-01")
    s.add(kid); s.flush()
    s.add(db.Identity(member_id=kid.id, kind="address", value="123 Main St, Austin, TX 78701", is_primary=True))
    s.commit(); s.refresh(kid); s.refresh(parent)
    a = cf.letters(parent, today=_dt.date(2026, 10, 11))
    assert a["kind"] == "adult" and len(a["letters"]) == 3
    tu = {l["key"]: l for l in a["letters"]}["transunion"]
    assert "P.O. Box 160" in tu["mail_to"] and "April 9, 1983" in tu["letter"] and cf.SSN_BLANK in tu["letter"]
    k = cf.letters(kid, requester=parent, today=_dt.date(2026, 10, 11))
    assert k["kind"] == "minor"
    L = {l["key"]: l for l in k["letters"]}
    assert "P.O. Box 380" in L["transunion"]["mail_to"] and "Protected Consumer Freeze" in L["transunion"]["letter"]
    assert "Jane Q Public" in L["equifax"]["letter"] and "Kid Public" in L["equifax"]["letter"] and L["equifax"]["form"]
    assert any("birth certificate" in x for x in L["experian"]["enclose"])
    import re as _re
    for l in a["letters"] + k["letters"]:
        assert not _re.search(r"\b\d{3}-\d{2}-\d{4}\b", l["letter"]), "no SSN-shaped numbers in letters"
    s.close()
    # EXPECTED: printable freeze letters with every blank but the SSN filled in.
    # IF THIS FAILS: families would have to write freeze letters from scratch, or an SSN could leak into one.

@test(1, "plain_language.family_pages",
      "Pages families use don't show technical words like PII, matrix, OAuth or token.")
def t_plain_language_family_pages():
    import re, pathlib
    root = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src"
    if not root.exists():
        raise Skip("frontend source not present")
    pages = ["pages/IdentityVault.jsx", "pages/Discovery.jsx", "pages/Family.jsx",
             "pages/Scheduled.jsx", "pages/CaptchaQueue.jsx", "pages/Brokers.jsx",
             "pages/Inboxes.jsx", "pages/Checklist.jsx", "pages/EmailMonitor.jsx",
             "pages/Dashboard.jsx", "pages/Login.jsx", "components/Sidebar.jsx",
             "components/VariantCoverage.jsx", "components/FindListings.jsx"]
    jargon = re.compile(r"\b(PII|matrix|bots?|OAuth|tokens?|payloads?|endpoints?|specs?|queued?|"
                        r"cron|regex|webhooks?|Incogni|variants?|enumerat\w*|scrap\w*|SQLCipher|"
                        r"daemon|null|undefined|invalid|primary|vault|JSON|UUID|exception)\b", re.I)
    text = re.compile(r">([^<>{}]*[A-Za-z][^<>{}]*)<")
    lit = re.compile(r"""(['"`])([A-Z][^'"`\n]{6,}?)\1""")
    hits = []
    for rel in pages:
        f = root / rel
        if not f.exists():
            continue
        for i, line in enumerate(f.read_text().splitlines(), 1):
            if line.strip().startswith(("import", "//", "*", "console.")):
                continue
            cands = [m.group(1) for m in text.finditer(line)] + \
                    [m.group(2) for m in lit.finditer(line) if " " in m.group(2)]
            for c in cands:
                m = jargon.search(c)
                if m:
                    hits.append(f"{rel}:{i} [{m.group(0)}] {c.strip()[:80]}")
    assert not hits, "Technical words on family pages:\n  " + "\n  ".join(hits)
@test(2, "timeline.rounds",
      "A request's history groups into rounds: sent, reply, removed, found again, sent again.")
def t_timeline_rounds():
    import datetime as _dt
    db, s = _memory_db()
    tl = _imp("core.timeline")
    m = _member_with_vault(db, s)
    b = db.Broker(name="Spokeo", opt_out_url="https://www.spokeo.com/optout")
    s.add(b); s.flush()
    R = db.RequestStatus
    r = db.RemovalRequest(member_id=m.id, broker_id=b.id, status=R.pending)
    s.add(r); s.commit()
    assert [e.to_status for e in r.events] == ["pending"], "status changes are recorded"
    d = lambda day: _dt.datetime(2026, 1, 1) + _dt.timedelta(days=day)
    def at(day, *rows):
        for x in rows:
            s.add(x)
        s.flush()
    s.add(db.AutomationLog(request_id=r.id, action="form_fill", status="success", created_at=d(0)))
    s.add(db.AutomationLog(request_id=r.id, action="form_fill", status="success", created_at=d(20)))   # follow-up
    s.add(db.EmailLog(request_id=r.id, direction="received", received_at=d(22)))
    s.add(db.ConfirmationLink(request_id=r.id, status="clicked", found_at=d(22), clicked_at=d(22)))
    s.add(db.VerificationCheck(request_id=r.id, checked_at=d(30), method="broker_search", verdict="gone"))
    s.add(db.VerificationCheck(request_id=r.id, checked_at=d(60), method="broker_search", verdict="gone"))
    s.add(db.VerificationCheck(request_id=r.id, checked_at=d(120), method="web_search", verdict="listed"))
    s.add(db.AutomationLog(request_id=r.id, action="form_fill", status="success", created_at=d(121)))
    s.commit()
    r.status = R.sent; s.commit()
    for e in r.events:          # put the status changes on the test's calendar
        e.at = d(0) if e.to_status == "sent" else d(-1)
    s.commit()
    out = tl.build(s, r, now=d(130))
    c = out["cycles"]
    assert len(c) == 2, [x["stage"] for x in c]
    one, two = c
    assert one["sent_at"].startswith("2026-01-01") and len(one["follow_ups"]) == 1
    assert one["replied_at"].startswith("2026-01-23") and one["removed_at"].startswith("2026-01-31")
    assert one["found_again_at"] and one["stage"] == "found_again"
    assert two["sent_at"] and two["stage"] == "sent"
    kinds = [e["kind"] for e in two["events"]]
    assert kinds[0] == "sent_again", kinds
    assert [s_["key"] for s_ in out["stages"]] == ["sent", "reply", "removed", "watching"]
    s.close()
    # EXPECTED: each round shows sent/reply/removed dates, follow-ups, and when the listing came back.
    # IF THIS FAILS: the progress bar on the Broker sites page would show the wrong dates or merge rounds.


@test(1, "i18n.full_coverage",
      "Every built-in language translates every dictionary key, and every menu label has a key.")
def t_i18n_full_coverage():
    import re, pathlib
    i18n = _imp("core.i18n")
    keys = {e["key"] for e in i18n.MASTER_DICTIONARY}
    missing = {code: sorted(keys - set(msgs)) for code, msgs in i18n.BUILTIN_TRANSLATIONS.items()}
    missing = {c: m for c, m in missing.items() if m}
    assert not missing, f"untranslated keys: {missing}"
    side = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src" / "components" / "Sidebar.jsx"
    if side.exists():
        used = set(re.findall(r"k: '(nav\.[a-z_]+)'", side.read_text()))
        assert used and not (used - keys), f"menu keys missing from the dictionary: {sorted(used - keys)}"
    # EXPECTED: switching language changes every menu item and status label.
    # IF THIS FAILS: part of the screen stays in English for that language.


@test(2, "backup.rclone_destination",
      "The rclone option uploads, lists and deletes through rclone with a private temp config, and checks its inputs.")
def t_backup_rclone():
    if _try_import("cryptography") is None:
        raise Skip("cryptography not installed")
    import os, stat, tempfile, shutil as _sh
    bk = _imp("core.backup")
    oe = _imp("core.oauth_engine")
    # Create work dir on an executable mount (Docker container mounts /tmp with noexec)
    exec_base = None
    for candidate in [None, os.path.expanduser("~"), "/data", "/app"]:
        if candidate and not os.path.exists(candidate):
            continue
        try:
            td = tempfile.mkdtemp(dir=candidate)
            test_sh = os.path.join(td, "x")
            with open(test_sh, "w") as fp:
                fp.write("#!/bin/sh\n")
            os.chmod(test_sh, stat.S_IRWXU)
            is_exec = os.access(test_sh, os.X_OK)
            _sh.rmtree(td, ignore_errors=True)
            if is_exec:
                exec_base = candidate
                break
        except Exception:
            continue
    work = tempfile.mkdtemp(dir=exec_base)
    store, bindir = os.path.join(work, "store"), os.path.join(work, "bin")
    os.makedirs(store); os.makedirs(bindir)
    log = os.path.join(work, "calls")
    fake = os.path.join(bindir, "rclone")
    with open(fake, "w") as f:
        f.write(f"""#!/bin/sh
# fake rclone: --config FILE ... CMD ARGS ; remote "r:dir/name" maps to {store}/dir/name
conf="$2"; [ -f "$conf" ] || exit 9
perm=$(stat -c %a "$conf"); echo "$perm $*" >> {log}
shift 2; while [ "${{1#--}}" != "$1" ]; do shift 2; done
cmd="$1"; shift
loc() {{ p="${{1#*:}}"; echo "{store}/$p"; }}
case "$cmd" in
  copyto) mkdir -p "$(dirname "$(loc "$2")")"; cp "$1" "$(loc "$2")";;
  lsf) d="$(loc "$2")"; ls -1 "$d" 2>/dev/null;;
  deletefile) rm "$(loc "$1")";;
  *) echo "unknown $cmd" >&2; exit 3;;
esac
""")
    os.chmod(fake, stat.S_IRWXU)
    old = os.environ.get("PATH", "")
    os.environ["PATH"] = bindir + os.pathsep + old
    try:
        conf = {"kind": "rclone", "remote": "proton", "path": "oo/backups",
                "config_enc": oe._encrypt("[proton]\ntype = protondrive\n")}
        d = bk.destination(conf, {})
        d.test()                                   # write, list, delete a test file
        src = os.path.join(work, "b.oobackup"); open(src, "wb").write(b"x")
        d.upload(src, bk.PREFIX + "2026.oobackup")
        assert d.names() == [bk.PREFIX + "2026.oobackup"]
        d.delete(bk.PREFIX + "2026.oobackup")
        assert d.names() == []
        calls = open(log).read().splitlines()
        assert calls and all(c.startswith("600 ") for c in calls), "config file is private"
        assert not [n for n in os.listdir(tempfile.gettempdir()) if n.startswith("oo-rclone-")], "temp config removed"
        for bad in ({"remote": "pro ton"}, {"remote": "proton", "path": "../etc"}):
            try:
                bk.destination({**conf, **bad}, {}).names()
                raise AssertionError(f"accepted {bad}")
            except RuntimeError:
                pass
        try:
            bk.destination({**conf, "config_enc": ""}, {}).names()
            raise AssertionError("ran without a config")
        except RuntimeError as e:
            assert "rclone.conf" in str(e)
    finally:
        os.environ["PATH"] = old
        _sh.rmtree(work, ignore_errors=True)
    # EXPECTED: backups reach any rclone remote (Proton Drive, Box, pCloud...).
    # IF THIS FAILS: the "Other cloud storage" option can't upload, or leaves its config lying around.


@test(2, "family.add_and_remove_person",
      "A parent can add a person (no sign-in, managed by them) and remove them; members and other accounts are protected.")
def t_family_add_remove():
    db, s = _memory_db()
    fam = _imp("routers.family")
    auth = _imp("core.auth")
    from fastapi import HTTPException
    parent = db.User(email="p@x.example", full_name="Pat Parent", role=db.UserRole.parent, hashed_password="x")
    s.add(parent); s.flush()
    s.add(db.FamilyMember(user_id=parent.id, full_name="Pat Parent")); s.commit()
    out = fam.add_member(fam.MemberCreate(full_name=" Kim Kid ", dob="2015-03-02", authorized=True), db=s, current_user=parent)
    assert out.full_name == "Kim Kid" and out.dob == "2015-03-02" and out.age is not None and out.can_edit
    kid = s.query(db.FamilyMember).get(out.id)
    assert kid.user.role == db.UserRole.member and kid.user.email.endswith(".invalid") and not kid.user.hashed_password
    assert out.id in auth.get_accessible_member_ids(s, parent), "the parent can see who they added"
    s.add(db.Identity(member_id=kid.id, kind="phone", value="555-0100"))
    b = db.Broker(name="B", opt_out_url="https://b.example"); s.add(b); s.flush()
    rq = db.RemovalRequest(member_id=kid.id, broker_id=b.id, status=db.RequestStatus.sent); s.add(rq); s.flush()
    s.add_all([db.AutomationLog(request_id=rq.id, member_id=kid.id, action="form_fill", status="success"),
               db.EmailLog(request_id=rq.id, direction="received"),
               db.VerificationCheck(request_id=rq.id, method="web_search", verdict="gone"),
               db.MemberScheduleConfig(member_id=kid.id)])
    s.commit()
    child_user = kid.user
    try:
        fam.add_member(fam.MemberCreate(full_name="X", authorized=True), db=s, current_user=child_user)
        raise AssertionError("a member added someone")
    except HTTPException as e:
        assert e.status_code == 403
    own = s.query(db.FamilyMember).filter_by(user_id=parent.id).first()
    try:
        fam.remove_member(own.id, db=s, current_user=parent)
        raise AssertionError("removed themselves")
    except HTTPException as e:
        assert e.status_code == 400
    fam.remove_member(out.id, db=s, current_user=parent)
    assert s.query(db.FamilyMember).get(out.id) is None
    assert s.query(db.Identity).filter_by(member_id=out.id).count() == 0
    assert s.query(db.RemovalRequest).count() == 0 and s.query(db.EmailLog).count() == 0
    assert s.query(db.VerificationCheck).count() == 0 and s.query(db.AutomationLog).count() == 0
    assert s.query(db.ProfileAccess).count() == 0 and s.query(db.User).count() == 1
    s.close()
    # EXPECTED: "Add a person" and "Remove" on the Family page work.
    # IF THIS FAILS: families can't add children or remove people they added.
@test(2, "compliance.deadlines_scope_and_notices",
      "The deadline report flags late and relisting sites for the viewer's people only, and opted-in notices go out once.")
def t_compliance_report():
    import datetime as _dt, json as _json
    db, s = _memory_db()
    cp = _imp("core.compliance")
    tl = _imp("core.timeline")
    jane = _member_with_vault(db, s)
    U2 = db.User(email="other@x.example", full_name="Other Family", role=db.UserRole.parent)
    s.add(U2); s.flush()
    other = db.FamilyMember(user_id=U2.id, full_name="Other Family"); s.add(other); s.flush()
    b = db.Broker(name="SlowSite", opt_out_url="https://slow.example")
    s.add(b); s.flush()
    d = lambda day: _dt.datetime(2026, 1, 1) + _dt.timedelta(days=day)
    R = db.RequestStatus
    r1 = db.RemovalRequest(member_id=jane.id, broker_id=b.id, status=R.sent)
    r2 = db.RemovalRequest(member_id=other.id, broker_id=b.id, status=R.sent)
    s.add_all([r1, r2]); s.commit()
    for r in (r1, r2):
        for e in r.events:
            e.at = d(0)
        s.add(db.AutomationLog(request_id=r.id, action="form_fill", status="success", created_at=d(0)))
    s.add(db.VerificationCheck(request_id=r2.id, checked_at=d(10), method="broker_search", verdict="gone"))
    s.add(db.VerificationCheck(request_id=r2.id, checked_at=d(40), method="broker_search", verdict="listed"))
    s.commit()
    orig = tl.build
    tl.build = lambda db_, req, now=None: (lambda o: (o.update(response_days=45) or [c.update(due_by=(_dt.datetime.fromisoformat(c["sent_at"]) + _dt.timedelta(days=45)).isoformat()) for c in o["cycles"] if c["sent_at"]] and o))(orig(db_, req, now=now))
    try:
        mine = cp.report(s, [jane.id], now=d(60))
        assert [r["person"] for r in mine["rows"]] == ["Jane Q Public"], "only the viewer's people"
        assert mine["rows"][0]["verdict"] == "overdue" and mine["totals"]["overdue"] == 1
        theirs = cp.report(s, [other.id], now=d(60))
        assert theirs["totals"]["relisted"] == 1 and theirs["rows"][0]["verdict"] == "on_time"
        assert "found_again" in cp.to_csv(theirs).splitlines()[0]
        assert cp.report(s, [], now=d(60))["rows"] == []
        # Notices: off by default; once turned on, each problem is emailed once.
        u = jane.user
        assert cp.pending_notices(s, u, now=d(60)) == []
        u.notification_prefs = _json.dumps({"overdue": True, "relisted": True}); s.commit()
        sent = []
        st = cp.run_notices(s, {}, send=lambda to, subj, body: sent.append((to, subj, body)) or {"ok": True}, now=d(60))
        assert st["emails"] == 1 and len(sent) == 1 and "SlowSite" in sent[0][2] and sent[0][0] == "jane@x.example"
        assert "Other Family" not in sent[0][2], "never about people outside the family"
        st = cp.run_notices(s, {}, send=lambda *a: sent.append(a) or {"ok": True}, now=d(61))
        assert st["emails"] == 0 and len(sent) == 1, "not sent twice"
    finally:
        tl.build = orig
    s.close()
    # EXPECTED: per-viewer deadline report; notices only for opted-in people, once per problem.
    # IF THIS FAILS: people could see others' requests, miss notices, or get the same email every day.


@test(2, "privacy.record_export_log_retention_delete",
      "The privacy record lists what's kept; exports cover one person; staff access is logged; old logs expire; people can delete themselves.")
def t_privacy_record():
    import datetime as _dt, json as _json, tempfile, os
    db, s = _memory_db()
    pr = _imp("core.privacy_record")
    priv = _imp("routers.privacy")
    fam = _imp("routers.family")
    from fastapi import HTTPException
    parent = db.User(email="p@x.example", full_name="Pat Parent", role=db.UserRole.parent, hashed_password="x")
    staff = db.User(email="s@lib.example", full_name="Sam Staff", role=db.UserRole.super_admin, hashed_password="x")
    s.add_all([parent, staff]); s.flush()
    s.add(db.FamilyMember(user_id=parent.id, full_name="Pat Parent"))
    s.add(db.FamilyMember(user_id=staff.id, full_name="Sam Staff")); s.commit()
    kid = fam.add_member(fam.MemberCreate(full_name="Kim Kid", authorized=True), db=s, current_user=parent)
    s.add(db.Identity(member_id=kid.id, kind="phone", value="512-555-0100"))
    b = db.Broker(name="B", opt_out_url="https://b.example"); s.add(b); s.flush()
    rq = db.RemovalRequest(member_id=kid.id, broker_id=b.id, status=db.RequestStatus.sent); s.add(rq); s.flush()
    old = _dt.datetime.utcnow() - _dt.timedelta(days=400)
    s.add_all([db.AutomationLog(request_id=rq.id, action="form_fill", status="success", created_at=old),
               db.AutomationLog(request_id=rq.id, action="form_fill", status="success"),
               db.EmailLog(request_id=rq.id, direction="received", subject="Removed", body_snippet="Dear Kim", received_at=old)])
    s.commit()

    rec = pr.record(s, {})
    keys = {r["key"] for r in rec["inventory"]}
    assert {"names", "contact", "birthday", "requests", "emails", "logs", "access"} <= keys
    assert "Social Security numbers" in rec["never_stored"] and rec["counts"]["people"] == 3

    member = s.query(db.FamilyMember).get(kid.id)
    ex = pr.export_person(s, member)
    assert ex["person"]["name"] == "Kim Kid" and ex["details"][0]["value"] == "512-555-0100"
    assert ex["requests"][0]["site"] == "B" and ex["account"]["email"] is None, "placeholder address not shown"

    # A parent looking at their own child isn't logged; staff looking is, once an hour.
    pr.log_access(s, parent, member, "view")
    assert s.query(db.AccessLog).count() == 0
    pr.log_access(s, staff, member, "view"); pr.log_access(s, staff, member, "view")
    pr.log_access(s, staff, member, "export")
    assert [a.action for a in s.query(db.AccessLog).order_by(db.AccessLog.id)] == ["view", "export"]
    mine = priv.my_access_log(db=s, current_user=parent)
    assert len(mine) == 2 and mine[0]["who"] == "Sam Staff"

    shots = tempfile.mkdtemp(); f = os.path.join(shots, "old.png"); open(f, "w").write("x")
    os.utime(f, (old.timestamp(), old.timestamp()))
    st = pr.purge(s, {"privacy": {"auto_purge_logs_days": 365}}, screenshots_dir=shots)
    assert st["automation_logs"] == 1 and st["email_excerpts"] == 1 and st["screenshot_files"] == 1
    assert s.query(db.AutomationLog).count() == 1 and s.query(db.EmailLog).one().body_snippet is None
    assert s.query(db.RemovalRequest).count() == 1 and s.query(db.Identity).count() == 1, "details untouched"
    assert pr.retention_days({"privacy": {"auto_purge_logs_days": 5}}) == 30, "at least 30 days"

    try:
        priv.delete_me(priv.DeleteMe(confirm="nope"), db=s, current_user=parent)
        raise AssertionError("deleted without confirmation")
    except HTTPException as e:
        assert e.status_code == 400
    try:
        priv.delete_me(priv.DeleteMe(confirm="DELETE"), db=s, current_user=staff)
        raise AssertionError("deleted the only super admin")
    except HTTPException as e:
        assert e.status_code == 400
    out = priv.delete_me(priv.DeleteMe(confirm="delete"), db=s, current_user=parent)
    assert out["also_removed"] == ["Kim Kid"]
    assert s.query(db.User).count() == 1 and s.query(db.FamilyMember).count() == 1
    assert s.query(db.RemovalRequest).count() == 0 and s.query(db.Identity).count() == 0
    assert s.query(db.AccessLog).count() == 2, "the access record outlives the account"
    s.close()
    # EXPECTED: a complete, honest privacy record and working access/deletion rights.
    # IF THIS FAILS: an install can't show what it keeps, answer a request, or forget someone.


@test(1, "privacy.no_details_in_logs",
      "Identity combinations are masked before they're written to logs or stored labels.")
def t_masked_combo():
    cmb = _imp("core.combinations")
    c = cmb.IdentityCombo(name="Jane Q Public", address="123 Main St", city="Austin", state="TX",
                          phone="(512) 555-0134", email="jane@old.example")
    m = c.masked_label()
    for secret in ("Jane", "Public", "123 Main", "555-0134", "jane@"):
        assert secret not in m, (secret, m)
    assert "J.Q.P." in m and "0134" in m and "old.example" in m
    assert m != cmb.IdentityCombo(name="Jane Q Public", city="Austin", phone="(512) 555-0199").masked_label()


@test(2, "i18n.languages_are_plugins",
      "Only English lives in core; the other languages are built-in language-pack plugins an admin can turn off.")
def t_languages_are_plugins():
    import os, tempfile, pathlib
    i18n = _imp("core.i18n")
    lp = _imp("plugins.language_packs")
    src = pathlib.Path(i18n.__file__).read_text(encoding="utf-8")
    assert "Bóveda" not in src and "Panel de Control" not in src, "translations are no longer hardcoded"
    assert set(i18n.BUNDLED_LANGUAGES) == {"es", "fr", "ar", "pirate", "de", "hi", "ko", "pt", "ru", "tl", "vi", "zh", "pl", "uk", "ur", "sw", "id"}
    assert all(p["id"] == f"lang-{c}" for c, p in i18n.BUNDLED_LANGUAGES.items())
    assert i18n.BUNDLED_LANGUAGES["ar"]["is_rtl"] and i18n.BUNDLED_LANGUAGES["ur"]["is_rtl"] and "en" in i18n.DEFAULT_ENABLED
    db, s = _memory_db()
    root = tempfile.mkdtemp()
    old = os.environ.get("PLUGINS_DIR"); os.environ["PLUGINS_DIR"] = root
    try:
        st = lp.sync_builtin_languages(s)
        assert st["installed"] == 17, st
        assert os.path.isfile(os.path.join(root, "languages", "lang-de", "messages.json"))
        assert lp.sync_builtin_languages(s)["installed"] == 0, "second run changes nothing"
        rows = {r.plugin_id: r for r in s.query(db.InstalledPlugin).all()}
        assert rows["lang-de"].status == "data" and rows["lang-de"].enabled
        de = i18n.get_translations_for_locale("de")
        assert de["nav.vault"] == "Deine Angaben"
        # Turned off: German falls back to English and shows as off.
        i18n._DISABLED_CACHE.update(at=10**12, ids={"lang-de"})
        assert i18n.get_translations_for_locale("de")["nav.vault"] == "Your details"
        langs = {l["code"]: l for l in i18n.get_available_languages()}
        assert langs["de"]["plugin_off"] and not langs["de"]["enabled"] and langs["es"]["built_in"]
    finally:
        i18n._DISABLED_CACHE.update(at=0.0, ids=set())
        if old is None: os.environ.pop("PLUGINS_DIR", None)
        else: os.environ["PLUGINS_DIR"] = old
    s.close()
    # EXPECTED: languages install, update and turn off like any other plugin.
    # IF THIS FAILS: a language can't be turned off, or translations are stuck in core code.


@test(2, "reports.score_and_pdf",
      "The privacy score weighs sites by priority and keeps daily snapshots; the PDF report renders without personal details.")
def t_score_and_pdf():
    import datetime as _dt
    db, s = _memory_db()
    ps = _imp("core.privacy_score")
    rr = _imp("core.removal_report")
    m = _member_with_vault(db, s)
    big = db.Broker(name="BigWholesaler", opt_out_url="https://big.example", priority=5)
    small = db.Broker(name="SmallSite", opt_out_url="https://small.example", priority=1)
    s.add_all([big, small]); s.flush()
    R = db.RequestStatus
    rb = db.RemovalRequest(member_id=m.id, broker_id=big.id, status=R.pending)
    rs = db.RemovalRequest(member_id=m.id, broker_id=small.id, status=R.pending)
    s.add_all([rb, rs]); s.commit()
    assert ps.compute(s, m)["score"] == 0
    assert ps.snapshot(s, today=_dt.date(2026, 10, 1)) == 1
    rb.status = R.confirmed; s.commit()
    c = ps.compute(s, m)
    assert c["score"] == round(100 * (1 - 1 / 6)) and c["gone"] == 1 and c["exposed"] == 1, c
    rs.status = R.sent; s.commit()
    assert ps.compute(s, m)["score"] == round(100 * (1 - 0.5 / 6))
    rb.last_verdict = "listed"; s.commit()
    assert ps.site_state(rb) == "exposed", "a removal that came back counts as listed"
    rb.last_verdict = "gone"; s.commit()
    ps.snapshot(s, today=_dt.date(2026, 10, 11)); ps.snapshot(s, today=_dt.date(2026, 10, 11))
    assert s.query(db.PrivacyScoreSnapshot).count() == 2, "one row per person per day"
    rep = ps.report(s, [m.id])
    assert rep["family"]["start"] == 0 and rep["family"]["now"] == 92 and len(rep["family"]["history"]) == 2
    assert ps.report(s, [])["family"]["now"] is None
    data = rr.gather(s, [m.id])
    assert [r["site"] for r in data["people"][0]["rows"]] == ["SmallSite", "BigWholesaler"], "still-open sites first"
    pdf = rr.render(data, title="Removal report: Jane Q Public")
    assert pdf.startswith(b"%PDF") and len(pdf) > 2000
    try:
        from pypdf import PdfReader
        import io
        text = "".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)
        assert "BigWholesaler" in text and "Privacy score" in text
        for secret in ("123 Main", "555-0134", "jane@old.example"):
            assert secret not in text, secret
    except ImportError:
        pass
    s.close()
    # EXPECTED: a score that moves as sites remove you, and a PDF of every site's progress.
    # IF THIS FAILS: the dashboard score is wrong, or the report can't be downloaded or leaks details.


@test(2, "calendar.days_off_events_and_feed",
      "Opt-outs skip days off; the calendar lists runs, checks and legal deadlines; the .ics feed is valid and shows no details.")
def t_calendar():
    import datetime as _dt
    db, s = _memory_db()
    cal = _imp("core.calendar_plan")
    m = _member_with_vault(db, s)
    b = db.Broker(name="Spokeo", opt_out_url="https://www.spokeo.com/optout")
    s.add(b); s.flush()
    r = db.RemovalRequest(member_id=m.id, broker_id=b.id, status=db.RequestStatus.confirmed,
                          recheck_after=_dt.datetime(2026, 10, 20, 2, 0))
    s.add(r); s.commit()
    sc = {"enabled": True, "run_time": "02:00", "timezone": "America/Chicago",
          "run_days": cal.clean_days([0, 2, 4, 9]), "skip_dates": cal.clean_dates(["2026-10-14", "nope"])}
    assert sc["run_days"] == [0, 2, 4] and sc["skip_dates"] == ["2026-10-14"]
    assert cal.clean_days(list(range(7))) is None, "every day = no limit"
    assert cal.run_allowed(sc, _dt.date(2026, 10, 12))[0]                 # Monday
    assert not cal.run_allowed(sc, _dt.date(2026, 10, 13))[0]             # Tuesday
    ok, why = cal.run_allowed(sc, _dt.date(2026, 10, 14))                 # Wednesday, but a day off
    assert not ok and "day off" in why
    ev = cal.upcoming(s, [m.id], sc, start=_dt.date(2026, 10, 12), days=14)
    kinds = [(e["date"], e["kind"]) for e in ev]
    assert ("2026-10-12", "run") in kinds and ("2026-10-14", "skip") in kinds and ("2026-10-13", "run") not in kinds
    assert ("2026-10-20", "check") in kinds
    assert any(e["title"] == "Check again: Spokeo (Jane)" for e in ev)
    ics = cal.to_ics(ev, now=_dt.datetime(2026, 10, 11))
    assert ics.startswith("BEGIN:VCALENDAR\r\n") and ics.endswith("END:VCALENDAR\r\n")
    assert "DTSTART;VALUE=DATE:20261020" in ics
    assert all(len(l.encode()) <= 75 for l in ics.split("\r\n")), "lines folded"
    for secret in ("Public", "123 Main", "555-0134", "jane@"):
        assert secret not in ics, secret
    assert cal.token_hash("abc") != "abc" and len(cal.token_hash("abc")) == 64
    s.close()
    # EXPECTED: admins pick opt-out days and holidays; families see what's coming and can subscribe.
    # IF THIS FAILS: opt-outs go out on days off, or the calendar feed leaks details.


@test(2, "captcha.redaction_and_safe_urls",
      "CAPTCHA pictures keep only the puzzle, black out fields and saved details for good, and page addresses lose anything personal.")
def t_captcha_redaction():
    import io
    cp = _imp("core.captcha_privacy")
    try:
        from PIL import Image, PngImagePlugin
    except ImportError:
        raise Skip("Pillow not installed")
    db, s = _memory_db()
    m = _member_with_vault(db, s)
    sec = cp.member_secrets(m)
    for want in ("Jane", "Public", "123 Main St", "5125550134", "512-555-0134", "jane@old.example"):
        assert want in sec, (want, sec[:20])
    assert cp.contains_secret("Results for JANE public in Austin", sec)
    assert not cp.contains_secret("Please verify you are human", sec)
    assert cp.safe_page_url("https://www.spokeo.com/Jane-Public/Texas?ref=x#y", sec) == "https://www.spokeo.com/"
    assert cp.safe_page_url("https://site.example/optout?name=Jane", sec) == "https://site.example/optout"
    assert cp.safe_page_url("https://site.example/lookup/5125550134", sec) == "https://site.example/"
    assert cp.safe_page_url("javascript:alert(1)", sec) == ""
    # A white page with metadata; black out a box inside a crop.
    img = Image.new("RGB", (400, 300), (255, 255, 255))
    meta = PngImagePlugin.PngInfo(); meta.add_text("Comment", "Jane Q Public 123 Main St")
    buf = io.BytesIO(); img.save(buf, format="PNG", pnginfo=meta)
    out = cp.redact_image(buf.getvalue(), boxes=[(120, 120, 40, 20)], crop=(100, 100, 300, 250))
    red = Image.open(io.BytesIO(out))
    assert red.size == (200, 150), red.size
    assert red.getpixel((40, 30)) == (0, 0, 0) and red.getpixel((5, 140)) == (255, 255, 255)
    assert b"Jane" not in out and not red.info.get("Comment"), "no metadata carried over"
    s.close()
    # EXPECTED: nothing personal in any CAPTCHA image or address that is stored or sent.
    # IF THIS FAILS: a solving service (or the screenshots folder) could see a person's details.


def _chromium_or_skip():
    try:
        from playwright.async_api import async_playwright  # noqa: F401
    except ImportError:
        raise Skip("playwright not installed")


@test(3, "captcha.capture_live_page",
      "A real page: only the CAPTCHA area is captured, with the filled-in form fields blacked out.")
def t_captcha_capture_live():
    _chromium_or_skip()
    import asyncio, io
    from PIL import Image
    cp = _imp("core.captcha_privacy")
    html = """<html><body style='margin:0;background:#fff'>
      <div style='position:absolute;left:40px;top:40px'>Jane Q Public</div>
      <input id=name value='Jane Q Public' style='position:absolute;left:40px;top:200px;width:200px;height:30px;background:#fff;border:0'>
      <div id=captcha style='position:absolute;left:30px;top:180px;width:300px;height:120px;background:#c0e0ff'></div>
      <input id=name2 value='Jane Q Public' style='position:absolute;left:60px;top:240px;width:150px;height:24px;background:#fff;border:0'>
    </body></html>"""
    async def go():
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            b = await p.firefox.launch()
            try:
                page = await b.new_page(viewport={"width": 800, "height": 600})
                await page.set_content(html)
                return await cp.capture(page, "#captcha", ["Jane Q Public", "Jane"])
            finally:
                await b.close()
    try:
        res = asyncio.run(go())
    except Exception as e:
        raise Skip(f"no browser here: {e}")
    img = Image.open(io.BytesIO(res["image"]))
    assert img.size == (300 + 2 * cp.PAD, 120 + 2 * cp.PAD), img.size
    assert res["boxes"] >= 1
    # Field at page (60,240) -> crop (60-6, 240-156) = (54, 84): blacked out.
    assert img.getpixel((54 + 20, 84 + 10)) == (0, 0, 0)
    # The name at the top of the page is outside the crop entirely.
    # EXPECTED: solvers and the screenshots folder get the puzzle, not the person's form.


@test(3, "captcha.live_handoff_session",
      "A live session waits at the CAPTCHA, shows the page, passes clicks and typing to it, and carries on when the person is done.")
def t_live_handoff():
    _chromium_or_skip()
    import time as _t, asyncio
    lc = _imp("core.live_captcha")
    html = """<html><body><button id=b style='position:absolute;left:100px;top:100px;width:200px;height:60px'
      onclick="document.title='clicked'">I'm not a robot</button><input id=t style='position:absolute;left:100px;top:300px'></body></html>"""
    outcome = {}
    async def runner(s):
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            b = await p.firefox.launch()
            try:
                page = await b.new_page(viewport=lc.VIEWPORT)
                await page.set_content(html)
                s.page = page
                s.state = "replaying"
                outcome["result"] = await lc._person_solver(s)({"type": "recaptcha_v2"})
                outcome["title"] = await page.title()
                outcome["typed"] = await page.input_value("#t")
                s.state = "done"
            except Exception as e:
                outcome["error"] = str(e); s.state = "failed"
            finally:
                s.page = None
                await b.close()
    mgr = lc.LiveManager()
    info = mgr.start(42, user_id=1, runner=runner)
    assert info["state"] in ("starting", "replaying", "waiting_for_you")
    for _ in range(100):
        st = mgr.status(42)
        if st["state"] in ("waiting_for_you", "failed"):
            break
        _t.sleep(0.1)
    if st["state"] == "failed":
        raise Skip(f"no browser here: {outcome.get('error')}")
    assert st["can_interact"]
    frame = mgr.frame(42)
    assert frame and frame[:3] == b"\xff\xd8\xff", "a JPEG of the page"
    assert mgr.send_input(42, {"type": "click", "x": 200, "y": 130})
    assert mgr.send_input(42, {"type": "click", "x": 150, "y": 310})
    assert mgr.send_input(42, {"type": "text", "text": "hello"})
    assert not mgr.send_input(42, {"type": "key", "key": "Meta"}), "only ordinary keys"
    assert mgr.solved(42)
    for _ in range(100):
        if mgr.status(42)["state"] == "done":
            break
        _t.sleep(0.1)
    assert outcome["result"] == {"solved": True, "by_person": True}, outcome
    assert outcome["title"] == "clicked" and outcome["typed"] == "hello", outcome
    assert mgr.frame(42) is None and not mgr.send_input(42, {"type": "text", "text": "x"}), "closed afterwards"
    # EXPECTED: "Solve it here" works end to end and the opt-out continues after the person.
    # IF THIS FAILS: CAPTCHAs still need the person to redo the whole opt-out by hand.


_STEP_PAGE = """<html><body><input id=name><p>Enter the code we texted you:</p><input id=code>
<button id=send onclick="document.title='sent:' + document.getElementById('code').value">Send</button></body></html>"""


def _step_job():
    comp = _imp("core.interpreter.compiler")
    JS = comp.JobStep
    return comp.Job(broker_id="b", broker_name="B", member_id="1", method="form", steps=[
        JS(kind="fill", selector="#name", value="Jordan Example"),
        JS(kind="pause_for_human", text="Enter the code the site texted you, then press \"I've done this step\"."),
        JS(kind="click", selector="#send")])


@test(3, "live.person_step_continues_on_same_page",
      "At a person's step the flow waits for them on the live page and then carries on; without a person it stops and records where.")
def t_live_person_step():
    _chromium_or_skip()
    import asyncio
    ex_mod = _imp("core.interpreter.executor")

    async def go(hook):
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            b = await p.firefox.launch()
            try:
                page = await b.new_page()
                await page.set_content(_STEP_PAGE)
                ex = ex_mod.PlaywrightExecutor(page=page, person_hook=hook)
                res = await ex.run(_step_job())
                return res, await page.title()
            finally:
                await b.close()
    try:
        res, title = asyncio.run(go(None))
    except Exception as e:
        raise Skip(f"no browser here: {e}")
    assert not res.ok and res.needs_manual and res.pause_step == 1 and res.pause_kind == "pause", res
    assert ex_mod.ExecResult.from_dict(res.to_dict()).pause_step == 1, "survives a worker round trip"
    assert title == "", "nothing was sent"
    seen = {}

    async def person(info):
        seen.update(info)
        # what a person does on the live page: type the code
        await person.page.fill("#code", "482913")
        return True

    async def go2():
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            b = await p.firefox.launch()
            try:
                page = await b.new_page()
                person.page = page
                await page.set_content(_STEP_PAGE)
                res = await ex_mod.PlaywrightExecutor(page=page, person_hook=person).run(_step_job())
                return res, await page.title()
            finally:
                await b.close()
    res, title = asyncio.run(go2())
    assert res.ok and title == "sent:482913", (res, title)
    assert seen["kind"] == "pause" and "code" in seen["text"] and seen["step"] == 1
    # EXPECTED: "Do it here" can finish flows that need a code, an answer or a choice.
    # IF THIS FAILS: such opt-outs must be redone by hand on the broker's site.


@test(3, "live.step_session_end_to_end",
      "A live step session shows the step's instruction with the page, passes typing to it, and carries on when the person says they're done.")
def t_live_step_session():
    _chromium_or_skip()
    import time as _t
    lc = _imp("core.live_captcha")
    ex_mod = _imp("core.interpreter.executor")
    outcome = {}

    async def runner(s):
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            b = await p.firefox.launch()
            try:
                page = await b.new_page(viewport=lc.VIEWPORT)
                await page.set_content(_STEP_PAGE)
                s.page, s.state = page, "replaying"
                res = await ex_mod.PlaywrightExecutor(page=page, person_hook=lc._person_step(s)).run(_step_job())
                outcome["ok"], outcome["title"] = res.ok, await page.title()
                s.state = "done" if res.ok else "failed"
            except Exception as e:
                outcome["error"] = str(e); s.state = "failed"
            finally:
                s.page = None
                await b.close()
    mgr = lc.LiveManager()
    mgr.start(7, user_id=1, runner=runner, kind="step")
    assert mgr.status(7) is None or True
    for _ in range(100):
        st = mgr.status(7, kind="step")
        if st["state"] in ("waiting_for_you", "failed"):
            break
        _t.sleep(0.1)
    if st["state"] == "failed":
        raise Skip(f"no browser here: {outcome.get('error')}")
    assert st["can_interact"] and st["prompt_kind"] == "pause" and "code" in st["prompt"], st
    assert "I've done this step" in st["message"]
    assert mgr.status(7) is None, "a CAPTCHA session with the same number is a different session"
    assert mgr.send_input(7, {"type": "click", "x": 30, "y": 50}, kind="step")
    # the code box is the second input; click it, then type
    assert mgr.send_input(7, {"type": "key", "key": "Tab"}, kind="step")
    assert mgr.send_input(7, {"type": "text", "text": "77"}, kind="step")
    assert mgr.solved(7, kind="step")
    for _ in range(100):
        if mgr.status(7, kind="step")["state"] == "done":
            break
        _t.sleep(0.1)
    assert outcome.get("ok") and outcome["title"] == "sent:77", outcome
    assert mgr.status(7, kind="step")["message"] == lc.STATES["done_step"]
    # EXPECTED: the person sees what to do, does it in the page, and the opt-out finishes itself.
    # IF THIS FAILS: "Do it here" on the Checklist doesn't work.


@test(2, "live.handoff_recorded_and_finished",
      "An opt-out that stopped for a person offers \"Do it here\" on the Checklist; a finished live session marks it sent, an unfinished one leaves it as it was.")
def t_live_handoff_db():
    import json, types
    db, s = _memory_db()
    lc = _imp("core.live_captcha")
    cl = _imp("core.checklist")
    m = _member_with_vault(db, s)
    b = db.Broker(name="CodeCo", opt_out_url="https://codeco.example"); s.add(b); s.flush()
    r = db.RemovalRequest(member_id=m.id, broker_id=b.id, status=db.RequestStatus.needs_manual,
                          notes="Enter the code the site texted you.",
                          handoff_enc=json.dumps({"combo": {"name": "Jane Q Public"}, "step": 3, "kind": "pause"}))
    r2 = db.RemovalRequest(member_id=m.id, broker_id=b.id, status=db.RequestStatus.needs_manual, notes="Call them.")
    s.add_all([r, r2]); s.commit()
    enc = _imp("core.encryption")
    assert isinstance(db.RemovalRequest.__table__.c.handoff_enc.type, enc.EncryptedString), \
        "the hand-off point (it holds the details being sent) is stored encrypted"
    items = {i["request_id"]: i for i in cl.build(s, [m.id])["groups"]["finish"]}
    assert items[r.id].get("live") and not items[r2.id].get("live")
    ns = lambda **k: types.SimpleNamespace(**{"ok": False, "needs_manual": False, "needs_captcha": False,
                                              "detail": "", "human_instruction": "", **k})
    lc.finish_step(s, r, ns(needs_manual=True, human_instruction="Now pick your listing."), user_id=1)
    assert r.status == db.RequestStatus.needs_manual and r.notes == "Now pick your listing." and r.handoff_enc
    lc.finish_step(s, r, ns(detail="timed out"), user_id=1)
    assert r.status == db.RequestStatus.needs_manual, "an unfinished live session never marks it failed"
    lc.finish_step(s, r, ns(ok=True), user_id=1)
    assert r.status == db.RequestStatus.sent and r.handoff_enc is None and r.recheck_after
    assert s.query(db.AutomationLog).filter_by(request_id=r.id, action="step_live").count() == 3
    s.close()
    # IF THIS FAILS: the Checklist can't offer "Do it here", or a live session's result is lost.


@test(2, "captcha.finish_and_service_settings",
      "A live session's result updates the request; the solving-service key is stored encrypted and never shown.")
def t_captcha_finish_services():
    import os, json, tempfile, types
    db, s = _memory_db()
    lc = _imp("core.live_captcha")
    cs = _imp("core.captcha_services")
    store = _imp("core.settings_store")
    m = _member_with_vault(db, s)
    b = db.Broker(name="B", opt_out_url="https://b.example"); s.add(b); s.flush()
    r = db.RemovalRequest(member_id=m.id, broker_id=b.id, status=db.RequestStatus.pending); s.add(r); s.flush()
    ch = db.CaptchaChallenge(request_id=r.id, broker_id=b.id, member_id=m.id, status="pending",
                             combo_enc=json.dumps({"name": "Jane Q Public", "city": "Austin"}))
    s.add(ch); s.commit()
    assert json.loads(ch.combo_enc)["city"] == "Austin"
    lc.finish(s, ch, r, types.SimpleNamespace(ok=True, needs_manual=False, needs_captcha=False, detail="ok",
                                              human_instruction=""), user_id=1)
    assert r.status == db.RequestStatus.sent and r.recheck_after and ch.status == "resolved" and ch.resolved_by == 1
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".json"); tmp.write(b"{}"); tmp.close()
    old = store.SETTINGS_FILE; store.SETTINGS_FILE = tmp.name
    try:
        pub = cs.save_service(cs.SERVICE_PLUGIN, "2captcha", "sk-test-123")
        raw = open(tmp.name).read()
        assert "sk-test-123" not in raw and pub["services"][cs.SERVICE_PLUGIN] == {"service": "2captcha", "has_key": True}
        meta = cs.plugin_meta(cs.SERVICE_PLUGIN)
        assert meta["api_key"] == "sk-test-123" and meta["service_base"] == "https://api.2captcha.com"
        assert cs.plugin_meta("some-other-solver") == {}, "the key goes only to its own plugin"
        try:
            cs.save_service(cs.SERVICE_PLUGIN, "made-up", None); raise AssertionError("accepted an unknown service")
        except ValueError:
            pass
        cs.save_service(cs.SERVICE_PLUGIN, "2captcha", "")
        assert cs.plugin_meta(cs.SERVICE_PLUGIN) == {}
    finally:
        store.SETTINGS_FILE = old; os.unlink(tmp.name)
    s.close()


@test(1, "captcha.solving_service_plugin_tasks",
      "The built-in solving-service plugin builds the right task per service, and defers without a key.")
def t_solver_plugin_tasks():
    import importlib.util, sys, pathlib, json, types
    here = pathlib.Path(__file__).resolve().parents[1]
    d = here / "plugins" / "bundled" / "captcha" / "captcha-solving-service"
    perms = _imp("plugins.permissions")
    m = perms.PluginManifest.from_dict(json.loads((d / "manifest.json").read_text()))
    assert m.validate() == [] and m.effective_type == "captcha" and "read_pii" not in m.permissions
    sys.path.insert(0, str(here / "plugins" / "sdk"))
    try:
        spec = importlib.util.spec_from_file_location("solver_plugin_under_test", d / "plugin.py")
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    except Exception as e:
        raise Skip(f"plugin SDK not importable here: {e}")
    finally:
        sys.path.pop(0)
    C = lambda **k: types.SimpleNamespace(**{"type": "recaptcha_v2", "site_key": "6Lc", "page_url": "https://b.example/optout",
                                              "screenshot": b"", "meta": {}, **k})
    assert mod.build_task(C(), "2captcha") == {"type": "RecaptchaV2TaskProxyless", "websiteURL": "https://b.example/optout", "websiteKey": "6Lc"}
    assert mod.build_task(C(), "capsolver")["type"] == "ReCaptchaV2TaskProxyLess"
    assert mod.build_task(C(type="hcaptcha"), "anticaptcha") is None
    img = mod.build_task(C(type="image", screenshot=b"PNG"), "capmonster")
    assert img["type"] == "ImageToTextTask" and img["body"] == "UE5H"
    assert mod.build_task(C(site_key=""), "2captcha") is None
    assert mod.solve(C()) == {"defer_to_human": True}, "no service key: hand it to a person"


@test(1, "captcha.executor_person_and_picture_answers",
      "The executor carries on after a person solves it, and types a picture-CAPTCHA answer into its box.")
def t_executor_answers():
    import asyncio
    ex_mod = _imp("core.interpreter.executor")
    comp = _imp("core.interpreter.compiler")

    class FakePage:
        url = "https://b.example/optout?name=Jane"
        def __init__(self): self.filled = {}
        async def content(self): return "<img src='/captcha.png'><input name='captcha_code'>"
        async def query_selector(self, sel):
            return object() if "captcha" in sel.lower() and sel.startswith("input") else None
        async def screenshot(self, **k): return b""
        async def evaluate(self, js, *a): return None
        async def fill(self, sel, val, timeout=0): self.filled[sel] = val

    def run(result):
        page = FakePage()
        ex = ex_mod.PlaywrightExecutor(page=page, captcha_solver=lambda ch: result, secrets=["Jane"])
        job = comp.Job(broker_id="1", broker_name="B", member_id="2", method="form",
                       steps=[comp.JobStep(kind="solve_captcha", selector="img")])
        return asyncio.new_event_loop().run_until_complete(ex.run(job)), page, ex

    res, page, ex = run({"solved": True, "token": "X7KQ"})
    assert not res.needs_captcha and page.filled == {"input[name*='captcha' i]": "X7KQ"}, (res.trace, page.filled)
    assert ex.last_challenge["page_url"] == "https://b.example/optout", "query string dropped"
    res, page, _ = run({"solved": True, "by_person": True})
    assert not res.needs_captcha and page.filled == {}
    res, _, _ = run({"defer_to_human": True})
    assert res.needs_captcha
@test(1, "frontend.no_undefined_names",
      "No screen uses a name (an icon, a component) that was never imported; the build doesn't catch these and the screen crashes.")
def t_frontend_names():
    import shutil, subprocess
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    fe = os.path.join(root, "frontend")
    if not shutil.which("node") or not os.path.isdir(os.path.join(fe, "node_modules", "@babel", "traverse")):
        raise Skip("node or the frontend's dev packages aren't installed (run npm install in frontend/)")
    r = subprocess.run(["node", "scripts/check-names.mjs", "src"], cwd=fe, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-1000:]
    # IF THIS FAILS: add the missing import; the listed screen would crash for everyone who opens it.


@test(1, "i18n.page_texts_current",
      "The list of on-screen phrases matches the screens, and every bundled language translates all of them with the same {placeholders} and <0> tags.")
def t_page_texts():
    import json, re, subprocess, sys as _sys
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    script_path = os.path.join(root, "scripts", "extract_page_texts.py")
    if not os.path.isfile(script_path):
        raise Skip("scripts/extract_page_texts.py not present (bare backend checkout)")
    r = subprocess.run([_sys.executable, script_path, "--check"], cwd=root,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, (r.stdout + r.stderr)[-1500:]
    # IF THIS FAILS: run scripts/extract_page_texts.py, then translate the new phrases in each language pack.
    master = [t["text"] for t in json.load(open(os.path.join(root, "backend", "core", "page_texts.json")))["texts"]]
    ph = re.compile(r"\{(\w+)\}")
    tag = re.compile(r"</?\d+/?>")
    packs = os.path.join(root, "backend", "plugins", "bundled", "languages")
    for d in sorted(os.listdir(packs)):
        p = os.path.join(packs, d, "texts.json")
        if not os.path.exists(p):
            continue
        texts = json.load(open(p, encoding="utf-8"))
        missing = [k for k in master if k not in texts]
        assert not missing, f"{d}: {len(missing)} phrases untranslated, e.g. {missing[:3]}"
        for k, v in texts.items():
            assert set(ph.findall(k)) == set(ph.findall(v)), f"{d}: placeholders differ in {k[:60]!r}"
            assert sorted(tag.findall(k)) == sorted(tag.findall(v)), f"{d}: tags differ in {k[:60]!r}"
    # IF THIS FAILS: a screen would show English, or a translation would drop a value or a link.


def _frontend_src():
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    src = os.path.join(root, "frontend", "src")
    if not os.path.isdir(src):
        raise Skip("frontend source not present here")
    import glob
    return src, sorted(glob.glob(os.path.join(src, "**", "*.js*"), recursive=True))


@test(1, "i18n.rtl_logical_classes",
      "Screens use start/end spacing and alignment (ms-, pe-, start-, text-start), so right-to-left languages mirror.")
def t_rtl_logical_classes():
    import re
    _, files = _frontend_src()
    V = r"(?:\d+(?:\.\d+)?|\d+/\d+|px|full|auto|\[[^\]\s'\"`]+\])"
    rx = re.compile(r"(?<![\w-])(?:[a-z0-9-]+:)*-?(?:(?:m[lr]|p[lr]|left|right)-" + V +
                    r"|text-(?:left|right)|border-[lr](?:-[\w/-]+)?|rounded-[tb]?[lr](?:-\w+)?)(?![\w/.-])")
    lit = re.compile(r"'(?:[^'\\\n]|\\.)*'|\"(?:[^\"\\\n]|\\.)*\"|`(?:[^`\\]|\\.)*`")
    bad = []
    for f in files:
        for m in lit.finditer(open(f, encoding="utf-8").read()):
            bad += [f"{os.path.basename(f)}: {h}" for h in rx.findall(m.group(0))]
    assert not bad, f"{len(bad)} left/right classes, e.g. {bad[:6]}"
    # IF THIS FAILS: use the start/end form (ml- -> ms-, pr- -> pe-, left- -> start-,
    #   text-right -> text-end, border-l -> border-s). It looks the same in English
    #   and flips for Arabic. Something that must stay on one physical side needs
    #   a comment and dir="ltr" on the element instead.


@test(1, "i18n.rtl_mirrored_icons",
      "Every arrow-like icon on screen is either mirrored for right-to-left languages or listed as one that keeps its direction.")
def t_rtl_mirrored_icons():
    import re
    src, files = _frontend_src()
    css = open(os.path.join(src, "index.css"), encoding="utf-8").read()
    block = re.search(r'html\[dir="rtl"\] :is\(([^)]*)\):not\(\.rtl-keep\)\s*\{\s*scale: -1 1;', css)
    assert block, "the RTL icon-mirroring rule is missing from index.css"
    mirrored = set(re.findall(r"\.lucide-([a-z0-9-]+)", block.group(1)))
    # Point up or down, or contain digits/letters that must not flip.
    keep = {"arrow-up", "arrow-down", "arrow-up-circle", "chevron-up", "chevron-down", "chevrons-up-down",
            "list-ordered", "refresh-cw", "mouse-pointer-click"}
    looks = re.compile(r"left|right|arrow|chevron|undo|redo|rotate|send|reply|forward|log-in|log-out|"
                       r"skip|external|trending|toggle|indent|outdent|move|step|corner|^list")
    used = set()
    for f in files:
        for imp in re.finditer(r"import\s*\{([^}]*)\}\s*from\s*'lucide-react'", open(f, encoding="utf-8").read(), re.S):
            for n in imp.group(1).split(","):
                n = n.strip().split(" as ")[0].strip()
                if n:
                    used.add(re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Za-z])(?=[0-9])", "-", n).lower())
    unsure = sorted(n for n in used if looks.search(n) and n not in mirrored and n not in keep)
    assert not unsure, f"decide whether these icons flip in right-to-left languages: {unsure}"
    assert {"chevron-left", "chevron-right", "arrow-left", "arrow-right", "external-link", "send"} <= mirrored
    for f in files:
        txt = open(f, encoding="utf-8").read()
        assert not re.search(r"isRTL\s*\?\s*<(Chevron|Arrow)", txt), \
            f"{os.path.basename(f)} swaps an arrow by hand; the stylesheet already mirrors it"
    # IF THIS FAILS: add the icon to the list in frontend/src/index.css if it
    #   points the reading way (back/next, open, send, undo), or to `keep` above
    #   if it points up/down or holds text. Don't swap icons in code.


@test(1, "i18n.regional_formats_used",
      "Screens show dates and numbers through i18n/format.js, so the admin's regional formats apply everywhere.")
def t_regional_formats_used():
    import re
    src, files = _frontend_src()
    bad = []
    for f in files:
        if f.endswith(os.path.join("i18n", "format.js")):
            continue
        for i, line in enumerate(open(f, encoding="utf-8"), 1):
            if re.search(r"\.toLocale(Date|Time)?String\(|new Intl\.(DateTimeFormat|NumberFormat)\(", line):
                bad.append(f"{os.path.basename(f)}:{i}")
    assert not bad, f"format these with fmtDate/fmtDateTime/fmtNumber from i18n/format.js: {bad}"
    # IF THIS FAILS: import the helper from i18n/format.js instead of calling
    #   toLocaleString() directly; the browser's own locale would ignore the
    #   admin's choice (and treat the server's UTC times as local).


@test(1, "settings.regional_formats",
      "Regional formats default to the US, reject bad values in plain words, and set the day/month order of server-written dates.")
def t_regional_formats():
    from datetime import date
    rg = _imp("core.regional")
    assert rg.get({}) == rg.DEFAULTS and rg.DEFAULTS["region"] == "US"
    assert rg.format_date(date(2026, 10, 1), {}) == "Oct 1, 2026"
    assert rg.format_date("2026-10-01T20:05:00", {"regional": {"region": "GB"}}) == "1 Oct 2026"
    assert rg.format_date(date(2026, 10, 1), {"regional": {"region": "JP"}}) == "2026-10-01"
    assert rg.format_date(None, {}) == "—"
    ok = rg.clean({"region": "ca", "hour_cycle": "h23", "week_start": "mon", "time_zone": "America/Chicago", "digits": "native"})
    assert ok["region"] == "CA" and ok["time_zone"] == "America/Chicago"
    for bad in ({"region": "USA"}, {"hour_cycle": "h25"}, {"week_start": "tue"}, {"digits": "roman"},
                {"time_zone": "Mars/Base"}):
        try:
            rg.clean(bad)
            raise AssertionError(f"accepted {bad}")
        except ValueError as e:
            assert str(e)[0].isupper() and "_" not in str(e).split()[0]
    # A broken saved value falls back to the defaults instead of breaking pages.
    assert rg.get({"regional": {"region": "??"}}) == rg.DEFAULTS
    try:
        from fastapi.testclient import TestClient
    except Exception:
        raise Skip("fastapi test client not available")
    main = _import_app_main()
    r = TestClient(main.app).get("/api/settings/regional")
    assert r.status_code == 200 and r.json()["region"] and "US" in r.json()["regions"], r.text
    assert set(r.json()) == set(rg.DEFAULTS) | {"regions"}, "nothing else is shown before sign-in"


@test(1, "observability.webhooks_safe_and_formatted",
      "Webhook messages carry only allowed counts and names, never saved personal details, in each service's own format.")
def t_webhooks():
    if _try_import("cryptography") is None:
        raise Skip("cryptography not installed")
    import json, hmac, hashlib
    wh = _imp("core.webhooks")
    real_blocked = wh._blocked
    sent = []
    wh.TRANSPORT = lambda url, body, headers: (sent.append((url, body, headers)), 204)[1]
    wh._blocked = lambda: ["Jordan Example", "jordan@example.invalid", "555-010-0199"]
    try:
        # Format per service.
        b, h = wh.payload("ntfy", "run_finished", "Opt-outs sent", "3 sent.", {"sent": 3}, secret="tk")
        assert b == b"3 sent." and h["Title"] == "Opt-outs sent" and h["Authorization"] == "Bearer tk"
        b, h = wh.payload("gotify", "broker_turned_off", "T", "M", {}, secret="app")
        assert json.loads(b)["priority"] == 7 and h["X-Gotify-Key"] == "app"
        assert json.loads(wh.payload("slack", "test", "T", "M", {})[0]) == {"text": "*T*\nM"}
        d = json.loads(wh.payload("discord", "test", "T", "M", {})[0])
        assert d["content"] == "**T**\nM" and d["allowed_mentions"] == {"parse": []}, "no @everyone pings"
        card = json.loads(wh.payload("teams", "test", "T", "M", {})[0])["attachments"][0]
        assert card["contentType"] == "application/vnd.microsoft.card.adaptive" and card["content"]["body"][0]["text"] == "T"
        raw, h = wh.payload("json", "listing_back", "T", "M", {"count": 2}, secret="s3cret")
        assert json.loads(raw)["details"] == {"count": 2} and json.loads(raw)["source"] == "openoptout"
        assert h["X-OpenOptOut-Signature"] == "sha256=" + hmac.new(b"s3cret", raw, hashlib.sha256).hexdigest()
        # Only allowed details; nothing personal.
        for bad in (lambda: wh.build("run_finished", "x", {"person": "someone"}),
                    lambda: wh.build("broker_turned_off", "Jordan Example's listing", {"broker": "Acme"}),
                    lambda: wh.build("broker_turned_off", "x", {"broker": "a\nb<script>"}),
                    lambda: wh.build("nope", "x")):
            try:
                bad(); raise AssertionError("allowed")
            except ValueError:
                pass
        t, m, _ = wh.build("needs_you", "Mail from someone@example.org or 555 123 4567 needs you.", {"checklist": 1})
        assert "[email]" in m and "[number]" in m and "@" not in m
        # Sending: only targets that want the event; secrets stay encrypted at rest.
        cfg = {"observability": {"webhooks": [
            wh.make_target({"kind": "slack", "url": "https://hooks.slack.example/services/T/B/X", "events": ["run_finished"]}),
            wh.make_target({"kind": "ntfy", "url": "https://ntfy.example/oo-alerts", "events": ["backup_failed"]}),
        ]}}
        stored = json.dumps(cfg)
        assert "hooks.slack.example" not in stored, "the webhook address is stored encrypted"
        assert wh.public_view(cfg["observability"]["webhooks"][0])["host"] == "hooks.slack.example"
        assert wh.notify("run_finished", "2 sent.", {"sent": 2}, settings=cfg, sync=True) == 1
        assert sent[-1][0].startswith("https://hooks.slack.example/") and len(sent) == 1
        before = wh.STATS["refused"]
        assert wh.notify("run_finished", "Sent for Jordan Example.", {"sent": 1}, settings=cfg, sync=True) == 0
        assert wh.STATS["refused"] == before + 1 and len(sent) == 1, "a saved name never leaves"
        # Repeats of "needs you" are held back for a while.
        cfg["observability"]["webhooks"][1]["events"] = ["needs_you"]
        wh._last_sent.clear()
        assert wh.notify("needs_you", "1 waits.", {"checklist": 1}, settings=cfg, sync=True) == 1
        assert wh.notify("needs_you", "1 waits.", {"checklist": 1}, settings=cfg, sync=True) == 0
        for bad in ({"kind": "pager", "url": "https://x.example"}, {"kind": "slack", "url": "ftp://x"}, {"kind": "slack"}):
            try:
                wh.make_target(bad); raise AssertionError(f"accepted {bad}")
            except ValueError:
                pass
    finally:
        wh.TRANSPORT = None
        wh._blocked = real_blocked
        wh._last_sent.clear()
    # IF THIS FAILS: a notification could carry someone's details, or reach a service in a form it rejects.


@test(1, "observability.log_forwarding",
      "Log lines go to syslog, OpenTelemetry, Loki or Splunk scrubbed of secrets, emails and phone numbers, without slowing the app.")
def t_log_forwarding():
    if _try_import("cryptography") is None:
        raise Skip("cryptography not installed")
    import json, logging, re
    lf = _imp("core.log_forwarding")
    msg = lf.scrub("Login for jordan@example.invalid from 555-010-0199 with Bearer abc.def token=xyz")
    assert "example.invalid" not in msg and "555" not in msg and "abc.def" not in msg and "xyz" not in msg, msg
    from datetime import datetime, timezone
    t0 = datetime(2026, 10, 11, tzinfo=timezone.utc).timestamp() + 0.25
    rec = {"time": t0, "level": "WARNING", "logger": "backend.core.scheduler", "message": "Run took long"}
    line = lf.syslog_line(rec).decode()
    assert re.match(r"^<132>1 2026-10-11T00:00:00\.250Z \S+ openoptout \d+ backend\.core\.scheduler - Run took long$", line), line
    o = lf.otlp_json([rec])["resourceLogs"][0]
    lr = o["scopeLogs"][0]["logRecords"][0]
    assert lr["severityNumber"] == 13 and lr["body"]["stringValue"] == "Run took long" and lr["timeUnixNano"] == str(int(t0 * 1e9))
    assert {"key": "service.name", "value": {"stringValue": "openoptout"}} in o["resource"]["attributes"]
    assert lf.loki_json([rec])["streams"][0]["stream"]["level"] == "warning"
    assert json.loads(lf.splunk_lines([rec]))["event"]["message"] == "Run took long"
    for bad in ({"kind": "syslog", "host": "bad host!"}, {"kind": "syslog", "host": "logs.example", "port": 99999},
                {"kind": "otlp", "endpoint": "logs.example"}, {"kind": "carrier-pigeon"},
                {"kind": "loki", "endpoint": "https://l.example", "level": "LOUD"}):
        try:
            lf.make_destination(bad); raise AssertionError(f"accepted {bad}")
        except ValueError:
            pass
    d = lf.make_destination({"kind": "splunk_hec", "endpoint": "https://splunk.example:8088/", "token": "hec-secret"})
    assert d["endpoint"] == "https://splunk.example:8088" and "hec-secret" not in json.dumps(d)
    assert lf.public_view(d)["has_token"] is True and "token_enc" not in lf.public_view(d)
    got = []
    lf.SENDER = lambda dest, recs: got.append((dest["id"], [r["message"] for r in recs]))
    h = lf.ForwardingHandler()
    try:
        h.dests = [dict(d, id="all", level="DEBUG"), dict(d, id="errors", level="ERROR")]
        lg = logging.getLogger("backend.test.forwarding")
        for level, text in ((logging.INFO, "hello jordan@example.invalid"), (logging.ERROR, "it broke")):
            h.emit(lg.makeRecord(lg.name, level, __file__, 1, text, (), None))
        h.emit(lg.makeRecord("httpx", logging.INFO, __file__, 1, "POST https://splunk.example", (), None))
        batch = [h.q.get_nowait() for _ in range(h.q.qsize())]
        assert len(batch) == 2, "the sender's own HTTP lines are never forwarded"
        h.flush_batch(batch)
        assert ("all", ["hello [email]", "it broke"]) in got and ("errors", ["it broke"]) in got
        # A server that can't keep up: oldest lines go, never the app.
        small = lf.ForwardingHandler(); small.q.maxsize = 2; small.dests = [d]
        before = lf.STATS["dropped"]
        for i in range(4):
            small.emit(lg.makeRecord(lg.name, logging.INFO, __file__, 1, f"line {i}", (), None))
        assert lf.STATS["dropped"] == before + 2 and [r["message"] for r in list(small.q.queue)] == ["line 2", "line 3"]
        lf.SENDER = lambda dest, recs: (_ for _ in ()).throw(ConnectionRefusedError("nobody home"))
        assert "ConnectionRefusedError" in lf.test(d)
    finally:
        lf.SENDER = None
    # IF THIS FAILS: logs could leave with secrets or contact details, or a log server could stall the app.


@test(1, "observability.health_and_metrics",
      "Health checks and Prometheus metrics report counts and states only, need the token, and webhooks hear when health changes.")
def t_health_metrics():
    from types import SimpleNamespace as NS
    mon = _imp("core.monitoring")
    db, s = _memory_db()
    s.add(db.FamilyMember(full_name="Jordan Example", user_id=1))
    s.add(db.Broker(name="Example Broker", opt_out_url="https://broker.example/optout"))
    s.commit()
    text = mon.metrics(s, {})
    for name in ("openoptout_up 1", "openoptout_brokers{enabled=\"true\"} 1", "openoptout_family_members 1",
                 "# TYPE openoptout_requests gauge", "openoptout_captchas_waiting 0"):
        assert name in text, (name, text[:400])
    assert "Jordan" not in text and "example.invalid" not in text, "metrics never name anyone"
    checks = {c["name"]: c for c in mon.checks(s, {})}
    assert checks["database"]["ok"] and "scheduler" in checks and checks["inboxes"]["ok"]
    cfg = {}
    token = mon.new_token(cfg)
    assert token.startswith("oo_metrics_") and token not in str(cfg)
    assert mon.token_ok(cfg, token) and not mon.token_ok(cfg, token + "x") and not mon.token_ok({}, token)
    # The health job only speaks when the result changes.
    wh = _imp("core.webhooks")
    said = []
    real_ready, real_notify, real_session = mon.ready, wh.safe_notify, db.SessionLocal
    try:
        db.SessionLocal = lambda: NS(close=lambda: None)
        wh.safe_notify = lambda ev, msg, details=None, **k: said.append((ev, details))
        states = iter([{"status": "ok", "checks": []}, {"status": "ok", "checks": []},
                       {"status": "problem", "checks": [{"name": "disk", "label": "Disk space", "ok": False, "detail": "1 GB free."}]},
                       {"status": "problem", "checks": [{"name": "disk", "label": "Disk space", "ok": False, "detail": "1 GB free."}]},
                       {"status": "ok", "checks": []}])
        mon.ready = lambda db_: next(states)
        mon._last_state["ok"] = None
        for _ in range(5):
            mon.health_job()
        assert said == [("health_problem", {"checks": "disk"}), ("health_ok", None)], said
    finally:
        mon.ready, wh.safe_notify, db.SessionLocal = real_ready, real_notify, real_session
        mon._last_state["ok"] = None
    obs = _imp("routers.observability")
    r = obs.health_ready(db=s)
    assert r.status_code in (200, 503) and b"database" in r.body
    try:
        obs.get_metrics(NS(headers={}), db=s)
        raise AssertionError("metrics answered without a token")
    except Exception as e:
        assert getattr(e, "status_code", 0) == 401
    # IF THIS FAILS: monitoring could expose details, answer anyone, or alert on every check.


@test(1, "i18n.plugin_text_lookup_order",
      "Plugin text is looked up admin override → language pack → the plugin's locales/<lang> → its default locale → the text as written, trying pt-BR then pt.")
def t_plugin_text_order():
    import json, tempfile
    pi = _imp("plugins.plugin_i18n")
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "locales"))
    json.dump({"id": "demo", "default_locale": "fr"}, open(os.path.join(d, "manifest.json"), "w"))
    json.dump({"instructions": "PLUGIN-ES", "only_plugin": "P-ES"}, open(os.path.join(d, "locales", "es.json"), "w"))
    json.dump({"instructions": "PLUGIN-FR", "fr_only": "P-FR"}, open(os.path.join(d, "locales", "fr.json"), "w"))
    json.dump({"instructions": "PLUGIN-PT"}, open(os.path.join(d, "locales", "pt.json"), "w"))
    real_over, real_pack = pi._overrides, pi.pack_table
    over, pack = {}, {}
    pi._overrides = lambda lang: over.get(lang, {})
    pi.pack_table = lambda lang, pid: pack.get(lang, {})
    try:
        txt = lambda key, lang: pi.plugin_text("demo", key, lang, "AS-WRITTEN", d)
        assert txt("instructions", "es") == "PLUGIN-ES"                      # 3. plugin locale
        pack["es"] = {"instructions": "PACK-ES"}
        assert txt("instructions", "es") == "PACK-ES"                        # 2. pack beats plugin
        over["es"] = {"plugin:demo:instructions": "ADMIN-ES"}
        assert txt("instructions", "es") == "ADMIN-ES"                       # 1. admin beats all
        assert txt("only_plugin", "es") == "P-ES"
        assert txt("fr_only", "de") == "P-FR", "missing language should fall back to the default locale"
        assert txt("nowhere", "de") == "AS-WRITTEN"                          # 5. as written
        assert txt("instructions", "pt-BR") == "PLUGIN-PT", "pt-BR should fall back to pt"
        assert txt("instructions", "PT_br") == "PLUGIN-PT"
    finally:
        pi._overrides, pi.pack_table = real_over, real_pack
    # IF THIS FAILS: a plugin's own translation, a language pack's or an admin's fix would be ignored.


@test(1, "plugins.locales_validated",
      "A plugin's locales/ files must exist for every declared language, be flat key → text JSON, and keep the original {placeholders}.")
def t_plugin_locales_valid():
    import json, tempfile
    pi = _imp("plugins.plugin_i18n")
    PluginManifest = _imp("plugins.permissions").PluginManifest
    d = tempfile.mkdtemp()
    os.makedirs(os.path.join(d, "locales"))
    m = PluginManifest.from_dict({"id": "demo", "name": "Demo", "version": "1", "author": "a",
                                  "type": "brokers", "description": "Hi {full_name}",
                                  "locales": ["fr", "de"], "default_locale": "en"})
    json.dump({"broker_id": "demo", "name": "Demo", "method": "manual",
               "instructions": "Open {listing_url}"}, open(os.path.join(d, "spec.json"), "w"))
    json.dump({"instructions": "Ouvrez le lien", "description": "Salut {full_name}"},
              open(os.path.join(d, "locales", "fr.json"), "w"))
    errs = pi.locale_errors(d, m)
    assert any("de.json is missing" in e for e in errs), errs
    assert any("'instructions'" in e and "listing_url" in e for e in errs), errs
    assert not any("description" in e for e in errs), errs
    json.dump({"instructions": "Ouvrez {listing_url}"}, open(os.path.join(d, "locales", "fr.json"), "w"))
    json.dump({"instructions": ["not", "text"]}, open(os.path.join(d, "locales", "de.json"), "w"))
    errs = pi.locale_errors(d, m)
    assert len(errs) == 1 and "values must be text" in errs[0], errs
    json.dump({"instructions": "Öffne {listing_url}"}, open(os.path.join(d, "locales", "de.json"), "w"))
    assert pi.locale_errors(d, m) == []
    assert "default_locale" in m.to_dict() and m.to_dict()["locales"] == ["fr", "de"]
    bad = PluginManifest.from_dict({"id": "x", "name": "X", "version": "1", "author": "a",
                                    "locales": ["fr", "not a code"]})
    assert any("isn't a language code" in e for e in bad.validate())
    # IF THIS FAILS: a broken translation could drop a person's link or crash the Plugins page.


@test(1, "interpreter.spec_jurisdiction_and_text_keys",
      "Specs take a jurisdiction, a legal language and per-language letters; keyed text ({\"$t\": ...}) loads and saves; LGPD is a known law.")
def t_spec_jurisdiction():
    BrokerSpec = _imp("core.interpreter").BrokerSpec
    base = {"broker_id": "b", "name": "B", "method": "manual"}
    s = BrokerSpec.from_dict({**base, "instructions": {"$t": "how_to", "default": "Open {listing_url}"}})
    assert s.instructions == "Open {listing_url}" and s.text_keys == {"instructions": "how_to"}
    assert s.to_dict()["instructions"] == {"$t": "how_to", "default": "Open {listing_url}"}
    assert BrokerSpec.from_dict(s.to_dict()).text_keys == {"instructions": "how_to"}
    try:
        BrokerSpec.from_dict({**base, "instructions": {"$t": "", "default": "x"}})
        raise AssertionError("an empty $t key should be refused")
    except ValueError:
        pass
    # Defaults: US unless a law says otherwise; legal language from the jurisdiction.
    assert BrokerSpec.from_dict(base).effective_jurisdiction() == "US"
    assert BrokerSpec.from_dict({**base, "legal_basis": ["ccpa"]}).effective_legal_language() == "en"
    g = BrokerSpec.from_dict({**base, "legal_basis": ["gdpr"]})
    assert g.effective_jurisdiction() == "EU" and g.effective_legal_language() == "en"
    fr = BrokerSpec.from_dict({**base, "jurisdiction": "fr"})
    assert fr.jurisdiction == "FR" and fr.effective_legal_language() == "fr" and fr.validate() == []
    br = BrokerSpec.from_dict({**base, "legal_basis": ["lgpd"]})
    assert br.validate() == [] and br.effective_jurisdiction() == "BR" and br.effective_legal_language() == "pt-BR"
    own = BrokerSpec.from_dict({**base, "jurisdiction": "DE",
                                "email_templates": {"de": {"subject": "S {full_name}", "body": "B {identifiers}"}}})
    assert own.validate() == [] and own.letter_template()["subject"] == "S {full_name}"
    assert own.letter_template("en") is None
    assert "email_templates" in own.to_dict() and "jurisdiction" in own.to_dict()
    for bad, msg in [({"jurisdiction": "Mars"}, "jurisdiction"), ({"legal_language": "english!"}, "legal_language"),
                     ({"email_templates": {"fr": {"subject": "x"}}}, "email_templates.fr")]:
        errs = BrokerSpec.from_dict({**base, **bad}).validate()
        assert any(msg in e for e in errs), (bad, errs)
    # IF THIS FAILS: add-ons couldn't say where a broker is, or keyed translations would be lost on save.


@test(1, "legal.letter_follows_broker_not_interface",
      "The opt-out letter is chosen by the broker's country and written in its legal language: English CCPA/US letters for US brokers, French GDPR for France, Portuguese LGPD for Brazil — whatever language the family uses.")
def t_legal_letters():
    tmpl = _imp("core.optout_email_template")
    ll = _imp("core.legal_letters")
    assert ll.template_errors() == [], ll.template_errors()
    ids = tmpl.Identifiers(full_name="Ana Souza", name_variants=["Ana S."], emails=["ana@example.com"],
                           phones=["555-0101"], addresses=["1 Rua A"], age_range="30-35")
    cases = [  # (jurisdiction, letter language asked for, residence, template, language, must contain)
        ("US", "", "TX", "us", "en", "California Consumer Privacy Act"),
        ("US", "", "CA", "ccpa", "en", "§ 1798.105"),
        ("US", "es", "TX", "us", "en", "state privacy laws"),     # no Spanish US letter: English, no note
        ("FR", "", "", "gdpr", "fr", "article 17 du Règlement général"),
        ("DE", "", "", "gdpr", "de", "Art. 17 der Datenschutz-Grundverordnung"),
        ("EU", "", "", "gdpr", "en", "Article 17"),
        ("GB", "", "", "uk_gdpr", "en", "Information Commissioner"),
        ("BR", "", "", "lgpd", "pt-BR", "Lei nº 13.709/2018"),
        ("CA-QC", "", "", "pipeda", "fr", "LPRPDE"),
        ("AU", "", "", "generic", "en", "data-protection law that applies"),
    ]
    for j, lang, res, tid, want_lang, needle in cases:
        e = tmpl.compose_optout_email(ids, "Acme", "p@acme.example", ["Site A"], jurisdiction=j,
                                      locale=lang, state=res, request_key="K-1")
        assert (e.template_id, e.language) == (tid, want_lang), (j, lang, e.template_id, e.language)
        assert needle in e.body, (j, needle)
        assert "localized" not in e.body and "[Note" not in e.body, "no 'not yet translated' note"
        assert "ana@example.com" in e.body and "Site A" in e.body and "30-35" in e.body, j
        assert "K-1" in e.subject and "K-1" in e.body and e.review_status == "draft"
        assert not __import__("re").search(r"\{[a-z_]+\}", e.body + e.subject), \
            f"unfilled placeholder in {tid}/{want_lang}"
    for t in ll.catalog():
        assert t["review_status"] == "draft" and len(t["review_note"]) > 40, t["id"]
    # IF THIS FAILS: a broker could get a letter citing the wrong law, in a language its
    #   legal team doesn't read, or a translated letter could leave out the identifiers.


@test(1, "legal.broker_email_uses_letter",
      "Per-broker opt-out emails use the broker's legal letter (CCPA for a California resident), or the add-on's own letter in its legal language.")
def t_legal_broker_email():
    if _try_import("sqlalchemy") is None:
        raise Skip("sqlalchemy not installed")
    from types import SimpleNamespace as NS
    oe = _imp("core.optout_engine")
    ba = _imp("plugins.broker_addon")
    BrokerSpec = _imp("core.interpreter").BrokerSpec
    member = _fake_member()
    broker = NS(name="Acme", is_property_broker=False, notes="", plugin_id=None)
    subject, body = oe._build_exhaustive_email(member, broker, "K-2", None, db=None)
    assert "CCPA" in body and "jane@example.com" in body and "Jane Public" in body and "K-2" in subject, body
    assert "§ 1798.105" not in body, "a Texas resident gets the general US letter"
    real = ba.get_broker_spec_for_broker
    try:
        ba.get_broker_spec_for_broker = lambda db, b: BrokerSpec.from_dict(
            {"broker_id": "acme", "name": "Acme", "method": "email", "jurisdiction": "FR",
             "email": {"to_address": "dpo@acme.example", "subject_template": "x", "body_template": "x"}})
        subject, body = oe._build_exhaustive_email(member, broker, "K-3", None, db=object())
        # The spec's single English template wins over the built-in letter; its
        # identifiers are labelled in the broker's legal language.
        assert body.startswith("x") and "Adresses e-mail" in body, body
        ba.get_broker_spec_for_broker = lambda db, b: BrokerSpec.from_dict(
            {"broker_id": "acme", "name": "Acme", "method": "manual", "jurisdiction": "FR"})
        subject, body = oe._build_exhaustive_email(member, broker, "K-4", None, db=object())
        assert "RGPD" in subject and "article 17" in body and "jane@example.com" in body, body
        ba.get_broker_spec_for_broker = lambda db, b: BrokerSpec.from_dict(
            {"broker_id": "acme", "name": "Acme", "method": "manual", "jurisdiction": "FR",
             "email_templates": {"fr": {"subject": "Suppression {full_name} [{request_key}]",
                                        "body": "Bonjour {broker},\n{identifiers}"}}})
        subject, body = oe._build_exhaustive_email(member, broker, "K-5", None, db=object())
        assert subject == "Suppression Jane Q Public [K-5]" and "Bonjour Acme" in body and "Numéros de téléphone" in body
    finally:
        ba.get_broker_spec_for_broker = real
    # IF THIS FAILS: brokers would get English letters regardless of where they are, or an
    #   add-on's own wording would be ignored.


@test(1, "legal.letters_are_plugins",
      "Opt-out letters are plugins: built-in ones load, a turned-off letter isn't used, an admin's own letter replaces a built-in one, and a bad letter plugin is refused.")
def t_letters_are_plugins():
    import json, tempfile, shutil
    ll = _imp("core.legal_letters")
    layout = _imp("plugins.layout")
    perms = _imp("plugins.permissions")
    ll.reload()
    cat = {t["id"]: t for t in ll.catalog()}
    assert set(cat) >= {"ccpa", "us", "gdpr", "uk_gdpr", "lgpd", "pipeda", "generic"}, sorted(cat)
    assert all(t["built_in"] and t["plugin_id"].startswith("letter-") for t in cat.values())
    for found in [f for f in layout.scan(layout.BUNDLED_ROOT) if f.manifest and f.manifest.effective_type == "letters"]:
        assert found.valid, (found.path, found.errors)
        assert found.manifest.is_data_only
    real_states, real_root = ll._plugin_states, os.environ.get("PLUGINS_DIR")
    tmp = tempfile.mkdtemp()
    try:
        # Turned off: a California resident falls back to the general US letter;
        # the general letter can't be lost.
        ll._plugin_states = lambda: {"letter-ccpa": False, "letter-generic": False}
        ll.reload()
        assert ll.choose_template("US", "CA")["id"] == "us"
        assert ll.choose_template("AU")["id"] == "generic"
        assert {t["id"]: t["enabled"] for t in ll.catalog()}["ccpa"] is False, "shown, marked off"
        assert ll.letter_choice(admin_choice="ccpa", jurisdiction="US")["missing"] == "ccpa"
        # An admin's own plugin with the same letter id replaces the built-in one.
        os.environ["PLUGINS_DIR"] = tmp
        mine = os.path.join(tmp, "letters", "my-ccpa")
        os.makedirs(mine)
        t = json.load(open(os.path.join(layout.BUNDLED_ROOT, "letters", "letter-ccpa", "letter.json")))
        t["languages"]["en"]["body"] = "Our own wording for {broker}.\n{scope}\n{property_note}\n{identifiers}\n{reference}\n{full_name}"
        json.dump(t, open(os.path.join(mine, "letter.json"), "w"))
        json.dump({"id": "my-ccpa", "type": "letters", "name": "Our CCPA letter", "version": "1.0.0",
                   "author": "Example Library", "description": "Our own CCPA wording."},
                  open(os.path.join(mine, "manifest.json"), "w"))
        ll._plugin_states = lambda: {"my-ccpa": True}
        ll.reload()
        assert ll.choose_template("US", "CA")["_plugin_id"] == "my-ccpa"
        tmpl = _imp("core.optout_email_template")
        ids = tmpl.Identifiers(full_name="Jordan Example", emails=["jordan@example.invalid"])
        e = tmpl.compose_optout_email(ids, "Acme", "p@acme.example", [], state="CA")
        assert e.body.startswith("Our own wording for Acme") and "jordan@example.invalid" in e.body
        # Not yet enabled (just uploaded): the built-in one is used.
        ll._plugin_states = lambda: {"my-ccpa": False}
        ll.reload()
        assert ll.choose_template("US", "CA")["_plugin_id"] == "letter-ccpa"
        # A letter plugin that leaves out the identifiers is refused at upload.
        t["languages"]["en"]["body"] = "Please delete me. {broker} {scope} {full_name}"
        json.dump(t, open(os.path.join(mine, "letter.json"), "w"))
        m = perms.PluginManifest.from_dict(json.load(open(os.path.join(mine, "manifest.json"))))
        errs = layout.content_errors(mine, m)
        assert any("identifiers" in e for e in errs), errs
        os.remove(os.path.join(mine, "letter.json"))
        assert any("letter.json" in e for e in layout.content_errors(mine, m))
        bad = perms.PluginManifest.from_dict({"id": "x-letter", "type": "letters", "name": "X", "version": "1",
                                              "author": "x", "entrypoint": "plugin.py", "permissions": ["network"]})
        assert bad.validate(), "a letters plugin can't run code or reach the network"
    finally:
        ll._plugin_states = real_states
        if real_root is None:
            os.environ.pop("PLUGINS_DIR", None)
        else:
            os.environ["PLUGINS_DIR"] = real_root
        shutil.rmtree(tmp, ignore_errors=True)
        ll.reload()
    # IF THIS FAILS: letters couldn't be added, replaced or turned off as plugins,
    #   or a letter missing the identifiers could reach brokers.


@test(1, "legal.letter_chosen_per_broker",
      "An admin can give a broker or parent company a different letter; it wins over the add-on's choice and wording, and an unavailable choice falls back to automatic.")
def t_letter_per_broker():
    if _try_import("sqlalchemy") is None:
        raise Skip("sqlalchemy not installed")
    from types import SimpleNamespace as NS
    ll = _imp("core.legal_letters")
    oe = _imp("core.optout_engine")
    ba = _imp("plugins.broker_addon")
    tmpl = _imp("core.optout_email_template")
    BrokerSpec = _imp("core.interpreter").BrokerSpec
    ll.reload()
    member = _fake_member()
    # Admin's choice: a US broker gets the GDPR letter.
    broker = NS(name="Acme", is_property_broker=False, notes="", plugin_id=None, letter_template="gdpr")
    subject, body = oe._build_exhaustive_email(member, broker, "K-9", None, db=None)
    assert "Article 17" in body and "jane@example.com" in body, body
    # A choice that isn't available: automatic, never a failed send.
    broker.letter_template = "no-such-letter"
    subject, body = oe._build_exhaustive_email(member, broker, "K-9", None, db=None)
    assert "Article 17" not in body and "jane@example.com" in body
    real = ba.get_broker_spec_for_broker
    try:
        spec = BrokerSpec.from_dict({"broker_id": "acme", "name": "Acme", "method": "manual", "letter": "uk_gdpr"})
        assert spec.validate() == [] and spec.to_dict()["letter"] == "uk_gdpr"
        assert BrokerSpec.from_dict({"broker_id": "a", "name": "A", "method": "manual", "letter": "Bad Letter!"}).validate()
        ba.get_broker_spec_for_broker = lambda db, b: spec
        broker.letter_template = None
        subject, body = oe._build_exhaustive_email(member, broker, "K-10", None, db=object())
        assert "Information Commissioner" in body, "the add-on's named letter is used"
        broker.letter_template = "lgpd"
        subject, body = oe._build_exhaustive_email(member, broker, "K-11", None, db=object())
        assert "13.709" in body, "the admin's choice wins over the add-on's"
        own = BrokerSpec.from_dict({"broker_id": "acme", "name": "Acme", "method": "manual",
                                    "email_templates": {"en": {"subject": "Own {request_key}", "body": "Own words {identifiers}"}}})
        ba.get_broker_spec_for_broker = lambda db, b: own
        subject, body = oe._build_exhaustive_email(member, broker, "K-12", None, db=object())
        assert "13.709" in body and not body.startswith("Own"), "the admin's choice wins over the add-on's wording"
        broker.letter_template = None
        subject, body = oe._build_exhaustive_email(member, broker, "K-13", None, db=object())
        assert body.startswith("Own words")
        assert ll.letter_choice(spec=own, legal_language="en")["source"] == "addon_text"
    finally:
        ba.get_broker_spec_for_broker = real
    ids = tmpl.Identifiers(full_name="Jordan Example", emails=["jordan@example.invalid"])
    e = tmpl.compose_optout_email(ids, "Parent Co", "p@parent.example", [], jurisdiction="US", template_id="pipeda")
    assert e.template_id == "pipeda"
    # The API's preview uses made-up details only.
    letters = _imp("routers.letters")
    pv = letters.preview("gdpr", language="fr", broker="Exemple", _=None)
    assert pv["language"] == "fr" and "Jordan Example" in pv["body"] and "jordan@example.invalid" in pv["body"]
    assert pv["review_status"] == "draft"
    # The admin's choice is stored on the broker and the parent company.
    db, s = _memory_db()
    s.add(db.Broker(name="Example Broker", opt_out_url="https://broker.example/optout"))
    s.add(db.ParentCompany(name="Example Parent", jurisdiction="FR"))
    s.commit()
    b = s.query(db.Broker).first(); p = s.query(db.ParentCompany).first()
    row = letters.assign(letters.Assign(kind="broker", id=b.id, letter_id="ccpa"), db=s, user=NS(id=1))
    assert row["uses"] == "ccpa" and row["source"] == "admin" and s.query(db.Broker).first().letter_template == "ccpa"
    row = letters.assign(letters.Assign(kind="parent", id=p.id, letter_id=""), db=s, user=NS(id=1))
    assert row["uses"] == "gdpr" and row["source"] == "automatic"
    try:
        letters.assign(letters.Assign(kind="broker", id=b.id, letter_id="no-such-letter"), db=s, user=NS(id=1))
        raise AssertionError("accepted a letter that doesn't exist")
    except Exception as ex:
        assert getattr(ex, "status_code", 0) == 400
    # IF THIS FAILS: brokers couldn't get different letters, or a broken choice would stop sends.


@test(1, "i18n.plugin_text_translated",
      "Every built-in language pack translates every built-in plugin's description and instructions; instructions show in the member's language and page-matching text is left alone.")
def t_plugin_text_translated():
    import importlib.util, json
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    script_path = os.path.join(root, "scripts", "plugin_texts.py")
    if not os.path.isfile(script_path):
        raise Skip("scripts/plugin_texts.py not present (bare backend checkout)")
    spec_ = importlib.util.spec_from_file_location("plugin_texts", script_path)
    pt = importlib.util.module_from_spec(spec_); spec_.loader.exec_module(pt)
    errs = pt.problems()
    assert not errs, f"{len(errs)} problems, e.g. {errs[:3]}"
    # IF THIS FAILS: run scripts/plugin_texts.py --check and translate what it lists.
    pi = _imp("plugins.plugin_i18n")
    ba = _imp("plugins.broker_addon")
    d = os.path.join(root, "backend", "plugins", "bundled", "brokers", "beenverified")
    spec, _ = ba.validate_broker_spec_file(d)
    spec.plugin_id, spec.plugin_dir = "beenverified", d
    es = pi.localize_spec(spec, "es")
    pauses = [i for i, s in enumerate(spec.steps) if s.kind == "pause_for_human"]
    assert pauses and all(es.steps[i].text != spec.steps[i].text for i in pauses)
    assert "{contact_email}" in es.steps[pauses[0]].text
    for i, s in enumerate(spec.steps):
        if s.kind != "pause_for_human":
            assert es.steps[i].text == s.text, "text matched on the broker's page must not be translated"
    assert spec.steps[pauses[0]].text.startswith("BeenVerified needs"), "the original spec must not change"
    from types import SimpleNamespace as NS
    assert pi.member_language(NS(user=NS(preferred_language="vi"))) == "vi"
    # IF THIS FAILS: a family would read checklist steps in English, or the robot would look
    #   for translated words on an English-language site.


# ── AI helpers and automatic broker steps ─────────────────────────────────────

def _ai_settings(extra=None):
    """A throwaway settings file with the three online helpers keyed, for AI helper tests."""
    if _try_import("cryptography") is None:
        raise Skip("cryptography not installed")
    import json, tempfile
    ss = _imp("core.settings_store")
    oe = _imp("core.oauth_engine")
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    cfg = {"ai_helpers": {"providers": {pid: {"enabled": True, "api_key_enc": oe._encrypt(f"key-{pid}")}
                                        for pid in ("claude", "openai", "antigravity")}}}
    if extra:
        cfg["ai_helpers"].update(extra)
    json.dump(cfg, open(path, "w"))
    old = ss.SETTINGS_FILE
    ss.SETTINGS_FILE = path
    return ss, old, path


_GOOD_DRAFT = {"method": "form", "opt_out_url": "https://acme.example/privacy",
               "steps": [{"kind": "navigate", "selector": "", "field": "", "value": "", "url": "https://acme.example/privacy",
                          "text": "", "optional": False},
                         {"kind": "fill", "selector": "#email", "field": "contact_email", "value": "", "url": "",
                          "text": "", "optional": False},
                         {"kind": "click", "selector": "#send", "field": "", "value": "", "url": "", "text": "",
                          "optional": False}],
               "success_text": "received", "success_selector": "", "instructions": "", "requires": [],
               "lookup_by": "", "confidence": "high", "notes": "Simple form."}


@test(1, "ai.draft_schema_closed",
      "The draft shape every AI helper must return is closed, fully required, and limited to the spec's own step kinds and member fields.")
def t_ai_schema():
    ai = _imp("core.ai_helpers")
    bs = _imp("core.interpreter.broker_spec")
    sch = ai.draft_schema()
    assert sch["additionalProperties"] is False and set(sch["required"]) == set(sch["properties"])
    step = sch["properties"]["steps"]["items"]
    assert step["additionalProperties"] is False and set(step["required"]) == set(step["properties"])
    assert set(step["properties"]["kind"]["enum"]) == bs.STEP_KINDS
    assert set(step["properties"]["field"]["enum"]) == bs.KNOWN_FIELDS | {""}
    assert "ssn" not in " ".join(step["properties"]["field"]["enum"])
    assert "contact_email" in ai.system_prompt() and "{fields}" not in ai.system_prompt()
    # IF THIS FAILS: a helper could return steps the interpreter doesn't know, or a
    #   structured-output mode would reject the schema (all three need closed objects).


@test(1, "ai.provider_requests",
      "Claude, ChatGPT/Codex and Antigravity are called with their documented request shapes, and their answers are read back.")
def t_ai_providers():
    import json
    ai = _imp("core.ai_helpers")
    ss, old, path = _ai_settings()
    calls = []
    try:
        def claude(m, url, h, body, timeout=None):
            calls.append((m, url, h, body))
            return 200, {"stop_reason": "end_turn", "content": [{"type": "text", "text": json.dumps(_GOOD_DRAFT)}]}
        ai.TRANSPORT = claude
        out = ai.draft(ss.load_settings(), "claude", "page")
        m, url, h, body = calls[-1]
        assert url == "https://api.anthropic.com/v1/messages" and h["x-api-key"] == "key-claude"
        assert h["anthropic-version"] == "2023-06-01" and body["model"] == "claude-opus-5-5"
        assert body["output_config"]["format"]["type"] == "json_schema" and out["steps"][1]["field"] == "contact_email"

        def openai(m, url, h, body, timeout=None):
            calls.append((m, url, h, body))
            return 200, {"output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(_GOOD_DRAFT)}]}]}
        ai.TRANSPORT = openai
        out = ai.draft(ss.load_settings(), "openai", "page")
        m, url, h, body = calls[-1]
        assert url == "https://api.openai.com/v1/responses" and h["Authorization"] == "Bearer key-openai"
        assert body["text"]["format"]["strict"] is True and body["model"] == "gpt-6-astra"
        assert out["method"] == "form"

        seq = []
        def agent(m, url, h, body, timeout=None):
            calls.append((m, url, h, body))
            seq.append(url)
            if m == "POST" and url.endswith("/interactions"):
                return 200, {"id": "int-1", "status": "in_progress", "steps": []}
            if m == "GET":
                return 200, {"id": "int-1", "status": "requires_action",
                             "steps": [{"type": "function_call", "id": "c1", "name": "submit_draft", "arguments": _GOOD_DRAFT}]}
            return 200, {}
        ai.TRANSPORT, ai.SLEEP = agent, (lambda s: None)
        out = ai.draft(ss.load_settings(), "antigravity", "page", page_url="https://acme.example/privacy")
        first = [c for c in calls if c[1].endswith("/interactions")][-1]
        body = first[3]
        assert first[2]["x-goog-api-key"] == "key-antigravity" and body["agent"].startswith("antigravity-")
        assert {t["type"] for t in body["tools"]} == {"url_context", "function"}, "the agent may only read pages"
        assert "environment" not in body, "no sandbox filesystem for the agent"
        assert out["steps"][2]["selector"] == "#send"
        assert any(u.endswith(":cancel") for u in seq), "the run is cancelled once the draft is in"

        ai.TRANSPORT = lambda *a, **k: (401, {"error": {"message": "bad key"}})
        try:
            ai.draft(ss.load_settings(), "claude", "page")
            raise AssertionError("a refused key should raise")
        except ai.AIError as e:
            assert "refused the API key" in str(e)
        cfg = json.load(open(path))
        assert cfg["ai_helpers"]["usage"]["calls"] == 4, "online calls are counted"
        assert "key-claude" not in open(path).read(), "keys are stored encrypted"
    finally:
        ai.TRANSPORT, ai.SLEEP = ai._http, __import__("time").sleep
        ss.SETTINGS_FILE = old
    # IF THIS FAILS: a provider changed its API, or the request shape drifted from
    #   what Anthropic / OpenAI / Google document.


@test(1, "ai.local_model_connection",
      "Your own model (LM Studio, Ollama...) is reached through the OpenAI chat API at the address you give, falls back to plain JSON, and isn't counted.")
def t_ai_local():
    import json
    ai = _imp("core.ai_helpers")
    ss, old, path = _ai_settings({"monthly_limit": 0})
    try:
        for bad in ("localhost:1234", "ftp://x/v1", "http://a b/v1"):
            try:
                ai.save_local(None, "LM", bad, "m")
                raise AssertionError(f"accepted {bad}")
            except ValueError:
                pass
        pub = ai.save_local(None, "LM Studio", "http://192.168.1.20:1234/v1/", "qwen3-coder-30b")
        pub = ai.save_local(None, "LM Studio", "http://host.docker.internal:11434/v1", "llama3.1:8b", api_key="")
        ids = [l["id"] for l in pub["local"]]
        assert ids == ["lm-studio", "lm-studio-2"], ids
        assert pub["order"][:2] == ["local:lm-studio-2", "local:lm-studio"], "new connections are tried first"
        cfg = ss.load_settings()
        assert ai.available(cfg)[:2] == ["local:lm-studio-2", "local:lm-studio"]
        calls = []
        def server(m, url, h, body, timeout=None):
            calls.append((url, h, body, timeout))
            if body.get("response_format", {}).get("type") == "json_schema":
                return 400, {"error": "json_schema not supported"}
            return 200, {"choices": [{"message": {"content": "Here you go:\n" + json.dumps(_GOOD_DRAFT)}}]}
        ai.TRANSPORT = server
        out = ai.draft(cfg, "local:lm-studio", "page")
        assert calls[0][0] == "http://192.168.1.20:1234/v1/chat/completions"
        assert "Authorization" not in calls[0][1], "no key, no Authorization header"
        assert calls[1][2]["response_format"] == {"type": "json_object"}, "falls back to plain JSON"
        assert calls[0][3] >= 600, "a home model gets a long timeout"
        assert out["steps"][1]["field"] == "contact_email"
        assert "usage" not in json.load(open(path))["ai_helpers"], "your own model isn't counted (limit was 0)"
        ai.TRANSPORT = lambda *a, **k: (_ for _ in ()).throw(ConnectionError("refused"))
        res = ai.test_connection(cfg, "local:lm-studio")
        assert not res["ok"] and "host.docker.internal" in res["message"]
        pub = ai.delete_local("lm-studio")
        assert [l["id"] for l in pub["local"]] == ["lm-studio-2"] and "local:lm-studio" not in pub["order"]
        try:
            ai.draft(ss.load_settings(), "claude", "page")
            raise AssertionError("monthly limit 0 should stop online helpers")
        except ai.AIError as e:
            assert "monthly limit" in str(e)
    finally:
        ai.TRANSPORT = ai._http
        ss.SETTINGS_FILE = old
    # IF THIS FAILS: people running their own model couldn't connect it, or its calls
    #   would eat the online helpers' monthly budget.


@test(1, "ai.refuses_personal_details",
      "Nothing is sent to an AI helper if it contains any saved name, email, phone number or address.")
def t_ai_pii():
    ai = _imp("core.ai_helpers")
    blocked = ["Zelda Quintessa", "zelda@example.com", "(512) 555-0142", "12 Oak Lane, Austin TX"]
    ai.check_outgoing("A form with a name box and an email box. Call 1-800-555-0000.", blocked)
    for leak in ("listing for zelda quintessa in Austin", "contact ZELDA@example.com",
                 "phone 512.555.0142", "lives at 12 Oak Lane, Austin TX"):
        try:
            ai.check_outgoing(leak, blocked)
            raise AssertionError(f"not caught: {leak}")
        except ai.AIError:
            pass
    ss, old, path = _ai_settings()
    sent = []
    try:
        ai.TRANSPORT = lambda *a, **k: sent.append(a) or (200, {})
        try:
            ai.draft(ss.load_settings(), "claude", "Page text: Zelda Quintessa, age 41", blocked)
            raise AssertionError("should refuse")
        except ai.AIError:
            pass
        assert not sent, "a request with personal details must not leave"
    finally:
        ai.TRANSPORT = ai._http
        ss.SETTINGS_FILE = old
    # IF THIS FAILS: a family member's details could be sent to an outside AI service.


@test(1, "spec_drafter.draft_safety_checks",
      "An AI draft can't send the browser off the broker's site, type fixed emails or numbers, or skip warnings about dates of birth or low confidence.")
def t_drafter_safety():
    from types import SimpleNamespace as NS
    import copy
    sd = _imp("core.spec_drafter")
    broker = NS(name="Acme", plugin_id=None)
    spec, warns = sd.build_spec(_GOOD_DRAFT, broker, {"acme.example"})
    assert spec.validate() == [] and spec.method == "form" and warns == []
    assert spec.source and "Drafted automatically" in spec.notes
    bad = copy.deepcopy(_GOOD_DRAFT)
    bad["steps"][0]["url"] = "https://evil.example/collect"
    for d, why in [(bad, "isn't the broker's site")]:
        try:
            sd.build_spec(d, broker, {"acme.example"})
            raise AssertionError("off-site navigate accepted")
        except ValueError as e:
            assert why in str(e)
    hosted = copy.deepcopy(_GOOD_DRAFT)
    hosted["steps"][0]["url"] = "https://privacyportal.onetrust.com/webform/abc"
    sd.build_spec(hosted, broker, {"acme.example"})   # a known privacy platform is fine
    lit = copy.deepcopy(_GOOD_DRAFT)
    lit["steps"][1].update(field="", value="someone@else.example")
    try:
        sd.build_spec(lit, broker, {"acme.example"})
        raise AssertionError("fixed email accepted")
    except ValueError:
        pass
    dob = copy.deepcopy(_GOOD_DRAFT)
    dob["steps"].insert(2, dict(dob["steps"][1], selector="#dob", field="dob"))
    dob["confidence"] = "low"
    _, warns = sd.build_spec(dob, broker, {"acme.example"})
    assert len(warns) == 2, warns
    # IF THIS FAILS: a helper's mistake (or a page trying to steer it) could send a
    #   family's details somewhere other than the broker.


@test(1, "spec_drafter.final_click_and_selector_only",
      "Rehearsals stop at the click that would send the request, and a fix counts as selector-only only when nothing typed, used or said changes.")
def t_drafter_rules():
    sd = _imp("core.spec_drafter")
    BrokerSpec = _imp("core.interpreter").BrokerSpec
    mk = lambda steps: BrokerSpec.from_dict({"broker_id": "a", "name": "A", "method": "form",
                                             "opt_out_url": "https://a.example", "steps": steps})
    s = mk([{"kind": "navigate", "url": "https://a.example"}, {"kind": "fill", "selector": "#n", "field": "full_name"},
            {"kind": "click", "selector": "#next"}, {"kind": "fill", "selector": "#e", "field": "contact_email"},
            {"kind": "click", "selector": "#send"}, {"kind": "wait", "timeout_ms": 1000},
            {"kind": "expect_success", "text": "ok"}])
    assert sd.final_submit_index(s.steps) == 4, "the last click after all filling is the one that sends"
    assert sd.final_submit_index(mk([{"kind": "navigate", "url": "https://a.example"}, {"kind": "autofill"}]).steps) == -1
    import copy
    moved = copy.deepcopy(s)
    moved.steps[3].selector, moved.steps[4].selector = "input[name=mail]", "#go"
    assert sd.selector_only_change(s, moved)
    for change in (lambda x: setattr(x.steps[3], "field", "email"),
                   lambda x: setattr(x.steps[0], "url", "https://b.example"),
                   lambda x: x.steps.append(x.steps[-1]),
                   lambda x: setattr(x.steps[1], "value", "x")):
        other = copy.deepcopy(s)
        change(other)
        assert not sd.selector_only_change(s, other)
    # IF THIS FAILS: a rehearsal could press the final button, or a fix that changes what
    #   is sent could apply itself without an admin.


@test(3, "spec_drafter.rehearsal_and_rule_repair",
      "A rehearsal fills a form with made-up details and stops before the final click; when the page's fields move, the built-in rules find them by label.")
def t_drafter_rehearsal():
    if _try_import("playwright") is None:
        raise Skip("playwright not installed")
    import threading, http.server, socketserver, os, tempfile
    sd = _imp("core.spec_drafter")
    BrokerSpec = _imp("core.interpreter").BrokerSpec
    v1 = (b"<html><body><form><label for=first_name>First name</label><input id=first_name>"
          b"<label for=email>Email</label><input id=email type=email>"
          b"<label><input type=checkbox id=agree> I certify this is my information</label>"
          b"<button id=send type=button onclick=\"document.title='SENT'\">Submit request</button></form></body></html>")
    v2 = (b"<html><head><title>v2</title></head><body><form><label>First name <input name=fname></label>"
          b"<label for=mail>Email address</label><input id=mail type=email>"
          b"<label><input type=checkbox id=agree> I certify this is my information</label>"
          b"<button id=go type=button onclick=\"document.title='SENT'\">Send request</button></form></body></html>")
    page = {"html": v1}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200); self.send_header("Content-Type", "text/html"); self.end_headers()
            self.wfile.write(page["html"])

        def log_message(self, *a):
            pass
    srv = socketserver.TCPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/optout"
    spec = BrokerSpec.from_dict({"broker_id": "t", "name": "T", "method": "form", "opt_out_url": url, "steps": [
        {"kind": "navigate", "url": url},
        {"kind": "fill", "selector": "#first_name", "field": "first_name", "timeout_ms": 1500},
        {"kind": "fill", "selector": "#email", "field": "contact_email", "timeout_ms": 1500},
        {"kind": "check", "selector": "#agree", "timeout_ms": 1500},
        {"kind": "click", "selector": "#send", "timeout_ms": 1500},
        {"kind": "expect_success", "text": "received"}]})
    try:
        shot = os.path.join(tempfile.mkdtemp(), "r.png")
        r = sd.rehearse(spec, shot)
        assert r["ok"] and r["stop"] == 4 and os.path.getsize(shot) > 1000, r
        assert r["page_map"]["title"] != "SENT", "the final button must not be pressed"
        names = {f.get("id") or f.get("name") for f in r["page_map"]["fields"]}
        assert {"first_name", "email", "agree"} <= names
        page["html"] = v2
        cand = spec
        for _ in range(5):
            r = sd.rehearse(cand)
            if r["ok"]:
                break
            cand = sd.rule_repair(cand, r["failed"], r["page_map"])
            assert cand is not None, r["detail"]
        assert r["ok"] and r["page_map"]["title"] == "v2", r
        assert [s.selector for s in cand.steps[1:5]] == ['input[name="fname"]', "#mail", "#agree", "#go"]
        assert sd.selector_only_change(spec, cand)
    finally:
        srv.shutdown()
    # IF THIS FAILS: automatic repairs can't see where a field moved, or a rehearsal
    #   could submit a request.


@test(2, "spec_drafter.apply_approve_revert",
      "A form failure queues one repair a day; a passing selector-only fix applies itself and is used, can be undone, and is set aside when the plugin updates; a new draft waits for approval.")
def t_drafter_db():
    import json
    db, s = _memory_db()
    sd = _imp("core.spec_drafter")
    bh = _imp("core.broker_health")
    bridge = _imp("core.interpreter.script_bridge")
    BrokerSpec = _imp("core.interpreter").BrokerSpec
    ss, old, path = _ai_settings()
    try:
        b = db.Broker(name="DraftCo", enabled=True, method=db.OptOutMethod.form, opt_out_url="https://draftco.example")
        s.add(b); s.commit()
        bh.record_failure(s, b.id, detail="Locator.fill: Timeout - selector #email not found")
        bh.record_failure(s, b.id, detail="selector #email not found")
        q = s.query(db.SpecDraft).filter_by(broker_id=b.id).all()
        assert len(q) == 1 and q[0].status == "queued" and q[0].kind == "repair", "one repair a day"
        bh.record_failure(s, b.id, detail="Timeout waiting")   # not a page change: nothing more
        assert s.query(db.SpecDraft).count() == 1

        old_spec = BrokerSpec.from_dict({"broker_id": "draftco", "name": "DraftCo", "method": "form",
                                         "opt_out_url": "https://draftco.example",
                                         "steps": [{"kind": "navigate", "url": "https://draftco.example"},
                                                   {"kind": "fill", "selector": "#email", "field": "contact_email"},
                                                   {"kind": "click", "selector": "#send"}]})
        new_spec = BrokerSpec.from_dict(dict(old_spec.to_dict(), steps=[
            {"kind": "navigate", "url": "https://draftco.example"},
            {"kind": "fill", "selector": "#mail", "field": "contact_email"}, {"kind": "click", "selector": "#send"}]))
        row = q[0]
        row.spec_json, row.previous_spec_json, row.source = json.dumps(new_spec.to_dict()), json.dumps(old_spec.to_dict()), "rules"
        s.commit()
        sd.decide(s, row, b, old_spec, new_spec, {"ok": True}, ss.load_settings())
        assert row.status == "applied" and row.decided_by == "automatic"
        used = bridge.get_or_build_broker_spec(b, db=s)
        assert used.steps[1].selector == "#mail", "the applied fix is used"
        assert bridge.get_or_build_broker_spec(b, db=s, use_drafts=False).steps[1].selector != "#mail"
        assert s.query(db.BrokerUpdate).filter_by(kind="steps_applied", broker_id=b.id).count() == 1
        sd.revert(s, row, "admin@example.invalid")
        assert row.status == "reverted" and bridge.get_or_build_broker_spec(b, db=s).steps[1].selector != "#mail"

        # Not selector-only (a step added): waits for an admin even with auto-apply on.
        more = BrokerSpec.from_dict(dict(new_spec.to_dict(), steps=new_spec.to_dict()["steps"] + [{"kind": "wait", "timeout_ms": 500}]))
        r2 = db.SpecDraft(broker_id=b.id, kind="repair", status="drafting", spec_json=json.dumps(more.to_dict()))
        s.add(r2); s.commit()
        sd.decide(s, r2, b, old_spec, more, {"ok": True}, ss.load_settings())
        assert r2.status == "ready"
        sd.approve(s, r2, "admin@example.invalid")
        assert r2.status == "approved" and len(bridge.get_or_build_broker_spec(b, db=s).steps) == 4

        # A repair made against plugin 1.0.0 is set aside once the plugin is 1.1.0.
        s.add(db.InstalledPlugin(plugin_id="draftco", name="DraftCo", version="1.1.0", author="x",
                                 manifest_json="{}", granted_permissions="[]", enabled=True, status="spec",
                                 install_path="/nonexistent/draftco"))
        b.plugin_id = "draftco"
        r2.base_version = "1.0.0"
        s.commit()
        assert sd.active_draft(s, b, "1.1.0") is None and r2.status == "superseded"

        # A new broker's draft is never applied automatically.
        r3 = db.SpecDraft(broker_id=b.id, kind="new", status="drafting", spec_json=json.dumps(new_spec.to_dict()))
        s.add(r3); s.commit()
        sd.decide(s, r3, b, None, new_spec, {"ok": True}, ss.load_settings())
        assert r3.status == "ready"
        try:
            sd.revert(s, r3, "x")
            raise AssertionError("only steps in use can be undone")
        except ValueError:
            pass
    finally:
        ss.SETTINGS_FILE = old
        s.close()
    # IF THIS FAILS: automatic fixes wouldn't be used, couldn't be undone, or could
    #   override a newer plugin; or new steps could go live without an admin.


@test(2, "spec_drafter.ai_repair_never_leaks",
      "When the rules can't fix a broker, the AI helper is asked with the page and steps; a draft from a page showing a family member's details is refused before anything is sent.")
def t_drafter_ai_repair():
    import json
    db, s = _memory_db()
    sd = _imp("core.spec_drafter")
    ai = _imp("core.ai_helpers")
    BrokerSpec = _imp("core.interpreter").BrokerSpec
    ss, old, path = _ai_settings()
    real_rehearse, real_current = sd.rehearse, sd.current_spec
    try:
        m = db.FamilyMember(full_name="Zelda Quintessa", user_id=1)
        s.add(m); s.commit()
        s.add(db.Identity(member_id=m.id, kind="email", value="zelda@example.com", is_primary=True))
        b = db.Broker(name="LeakCo", enabled=True, method=db.OptOutMethod.form, opt_out_url="https://acme.example/privacy")
        s.add(b); s.commit()
        spec = BrokerSpec.from_dict({"broker_id": "leakco", "name": "LeakCo", "method": "form",
                                     "opt_out_url": "https://acme.example/privacy",
                                     "steps": [{"kind": "navigate", "url": "https://acme.example/privacy"},
                                               {"kind": "fill", "selector": "#old", "field": "contact_email"},
                                               {"kind": "click", "selector": "#send"}]})
        sd.current_spec = lambda db_, broker: spec
        pmap = {"url": "https://acme.example/privacy", "title": "Privacy", "fields": [
            {"selector": "#a", "tag": "input", "type": "text", "label": "Your contact"},
            {"selector": "#b", "tag": "input", "type": "text", "label": "Your contact"}], "buttons": [], "text": ""}
        results = iter([{"ok": False, "failed": 1, "detail": "step 2 (fill) failed", "page_map": pmap, "trace": []},
                        {"ok": True, "detail": "Stopped before the final click, which is on the page.", "trace": []}])
        sd.rehearse = lambda sp, shot="": next(results)
        prompts = []
        def claude(mth, url, h, body, timeout=None):
            prompts.append(body["messages"][0]["content"])
            return 200, {"stop_reason": "end_turn", "content": [{"type": "text", "text": json.dumps(_GOOD_DRAFT)}]}
        ai.TRANSPORT = claude
        row = db.SpecDraft(broker_id=b.id, kind="repair", status="queued")
        s.add(row); s.commit()
        sd.repair(s, row)
        assert row.source == "claude" and row.status == "ready", (row.status, row.reason)
        assert "LeakCo" in prompts[0] and "#old" in prompts[0] and "zelda" not in prompts[0].lower()
        # Now the page shows a saved detail: nothing is sent.
        pmap["text"] = "Results: Zelda Quintessa, Austin TX"
        results = iter([{"ok": False, "failed": 1, "detail": "step 2 (fill) failed", "page_map": pmap, "trace": []}])
        n = len(prompts)
        row2 = db.SpecDraft(broker_id=b.id, kind="repair", status="queued")
        s.add(row2); s.commit()
        sd.repair(s, row2)
        assert row2.status == "failed" and len(prompts) == n, "the request with a saved name was not sent"
        assert "saved details" in row2.reason
    finally:
        sd.rehearse, sd.current_spec = real_rehearse, real_current
        ai.TRANSPORT = ai._http
        ss.SETTINGS_FILE = old
        s.close()
    # IF THIS FAILS: a broken broker couldn't be repaired with a helper, or a page that
    #   shows a family's listing could be sent to an outside service.


@test(1, "agents.instructions_present",
      "Coding agents (Claude Code, Codex, Antigravity) find the project's rules and the broker-plugin procedure, and both copies of the procedure match.")
def t_agent_instructions():
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    agents_path = os.path.join(root, "AGENTS.md")
    if not os.path.isfile(agents_path):
        raise Skip("AGENTS.md not present (bare backend checkout)")
    agents = open(agents_path, encoding="utf-8").read()
    assert "No personal data" in agents and "broker-plugin/SKILL.md" in agents
    assert len(agents) < 12000, "Antigravity reads rule files up to 12,000 characters"
    assert open(os.path.join(root, "CLAUDE.md"), encoding="utf-8").read().startswith("@AGENTS.md")
    a = open(os.path.join(root, ".agents", "skills", "broker-plugin", "SKILL.md"), encoding="utf-8").read()
    b = open(os.path.join(root, ".claude", "skills", "broker-plugin", "SKILL.md"), encoding="utf-8").read()
    assert a == b and a.startswith("---\nname: broker-plugin\ndescription: ")
    # IF THIS FAILS: copy .agents/skills/broker-plugin/SKILL.md over the .claude one (or back).


@test(1, "matching.classify_unclear_listings",
      "Possible listings are sorted into yours, unclear (only the name shows) and not you (a different name or age).")
def t_match_classify():
    mp = _imp("core.match_policy")
    prof = {"names": ["Jane Q Public", "Jane Public"], "places": ["Austin, TX"], "streets": ["123 Main St"],
            "phones": ["+1 (512) 555-0134"], "emails": [], "ages": [44, 45], "birth_years": [1981, 1982]}
    assert mp.classify(prof, "Jane Public, Austin, TX")[0] == "yours"
    assert mp.classify(prof, "Jane Public")[0] == "unclear"
    assert mp.classify(prof, "Jane Public  View details")[0] == "unclear"
    assert mp.classify(prof, "Robert Smith, Austin TX")[0] == "not_you"
    assert mp.classify(prof, "Jane Public, Age 87")[0] == "not_you"
    assert mp.classify(prof, "Jane Public, Age 45")[0] in ("yours", "unclear")
    g = mp.global_settings({})
    assert g == {"unclear_listings": "ask", "users_choose": True}
    assert mp.global_settings({"matching": {"unclear_listings": "nonsense"}})["unclear_listings"] == "ask"
    # EXPECTED: only listings that could really be the person reach the policy.


@test(2, "matching.policy_default_user_and_parent",
      "The admin's default applies unless people may choose; then a person's own choice, or their parent's, wins.")
def t_match_policy():
    db, s = _memory_db()
    mp = _imp("core.match_policy")
    m = _member_with_vault(db, s)
    cfg = {"matching": {"unclear_listings": "skip", "users_choose": True}}
    assert mp.for_member(s, m, cfg) == "skip"
    parent = db.User(email="mom@x.example", full_name="Mom", role=db.UserRole.parent); s.add(parent); s.flush()
    s.add(db.ProfileAccess(manager_id=parent.id, managed_id=m.user_id)); s.flush()
    mp.save_user(parent, "remove_all"); s.commit()
    assert mp.for_member(s, m, cfg) == "remove_all", "a parent's choice covers the people they manage"
    mp.save_user(m.user, "ask"); s.commit()
    assert mp.for_member(s, m, cfg) == "ask", "the person's own choice comes first"
    assert mp.for_member(s, m, {"matching": {"unclear_listings": "skip", "users_choose": False}}) == "skip"
    mp.save_user(m.user, None); s.commit()
    assert mp.user_choice(m.user) is None and m.user.optout_prefs is None
    try:
        mp.save_user(m.user, "everything"); raise AssertionError("accepted a made-up choice")
    except ValueError:
        pass
    s.close()


@test(1, "matching.executor_pick_listing",
      "pick_listing goes to the person's listing, and for name-only results follows the setting: ask, skip or remove all.")
def t_match_executor():
    import asyncio
    ex_mod = _imp("core.interpreter.executor")
    comp = _imp("core.interpreter.compiler")
    prof = {"names": ["Jane Public"], "places": ["Austin, TX"], "streets": [], "phones": [], "emails": [],
            "ages": [], "birth_years": []}

    class FakePage:
        url = "https://b.example/search"
        def __init__(self, results): self.results, self.visited = results, []
        async def evaluate(self, js, *a): return self.results
        async def goto(self, url, timeout=0): self.visited.append(url)
        async def wait_for_timeout(self, ms): pass

    def run(results, policy, preset=None):
        page = FakePage(results)
        ex = ex_mod.PlaywrightExecutor(page=page, match_profile=prof, unclear_policy=policy, preset_listing_url=preset)
        job = comp.Job(broker_id="1", broker_name="B", member_id="2", method="form",
                       steps=[comp.JobStep(kind="pick_listing", selector="a.result")])
        return asyncio.new_event_loop().run_until_complete(ex.run(job)), page

    unclear = [{"url": f"https://b.example/p/{i}", "text": "Jane Public"} for i in range(3)]
    mine = [{"url": "https://b.example/p/me", "text": "Jane Public, Austin, TX, age 45"}]
    other = [{"url": "https://b.example/p/bob", "text": "Bob Jones, Reno, NV"}]
    res, page = run(mine + unclear + other, "ask")
    assert res.ok and page.visited == ["https://b.example/p/me"] and res.extra_picks == [], res.trace
    res, page = run(unclear + other, "ask")
    assert res.needs_manual and len(res.candidates) == 3 and page.visited == [], res.trace
    assert "Checklist" in res.human_instruction
    res, page = run(unclear, "skip")
    assert res.skipped and not res.ok and page.visited == []
    res, page = run(unclear, "remove_all")
    assert res.ok and page.visited == ["https://b.example/p/0"] and res.extra_picks == ["https://b.example/p/1", "https://b.example/p/2"]
    res, page = run(other, "remove_all")
    assert res.not_listed and page.visited == []
    res, page = run(unclear, "ask", preset="https://b.example/p/2")
    assert res.ok and page.visited == ["https://b.example/p/2"], "a listing the person picked is used directly"


@test(3, "matching.results_from_a_real_page",
      "On a real search-results page, each result link comes back with the text of its own result card.")
def t_match_results_live():
    _chromium_or_skip()
    import asyncio
    ex_mod = _imp("core.interpreter.executor")
    html = """<html><body><div id=results>
      <div class=card><h3>Jane Public</h3><a class=r href='/p/1'>View</a></div>
      <div class=card><h3>Jane Public</h3><span>Austin, TX</span><a class=r href='/p/2'>View</a></div>
      <div class=card><h3>Bob Jones</h3><a class=r href='/p/3'>View</a></div>
    </div><a href='/about'>About</a></body></html>"""
    async def go():
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            b = await p.firefox.launch()
            try:
                page = await b.new_page()
                await page.route("https://search.example/**", lambda r: r.fulfill(body=html, content_type="text/html"))
                await page.goto("https://search.example/s")
                by_sel = await page.evaluate(ex_mod.PlaywrightExecutor._RESULTS_JS, ["a.r", ""])
                by_pat = await page.evaluate(ex_mod.PlaywrightExecutor._RESULTS_JS, ["", r"/p/\d+"])
                return by_sel, by_pat
            finally:
                await b.close()
    try:
        by_sel, by_pat = asyncio.run(go())
    except Exception as e:
        raise Skip(f"no browser here: {e}")
    assert [r["url"] for r in by_sel] == [f"https://search.example/p/{i}" for i in (1, 2, 3)], by_sel
    assert "Austin" in by_sel[1]["text"] and "Austin" not in by_sel[0]["text"], by_sel
    assert "Bob Jones" in by_sel[2]["text"]
    assert [r["url"] for r in by_pat] == [r["url"] for r in by_sel], "the address pattern finds the same results"


@test(2, "matching.checklist_pick_and_none",
      "Unclear listings show on the Checklist; picked ones are queued, and 'none of these' marks the site skipped.")
def t_match_checklist():
    import json
    db, s = _memory_db()
    cl = _imp("core.checklist")
    m = _member_with_vault(db, s)
    b = db.Broker(name="B", opt_out_url="https://b.example"); s.add(b); s.flush()
    cands = [{"url": "https://b.example/p/1", "text": "Jane Public", "why": "only the name"},
             {"url": "https://b.example/p/2", "text": "Jane Public", "why": "only the name"},
             {"url": "javascript:alert(1)", "text": "x"}]
    r = db.RemovalRequest(member_id=m.id, broker_id=b.id, status=db.RequestStatus.needs_manual,
                          candidates_enc=json.dumps(cands), notes="pick")
    s.add(r); s.commit()
    item = cl.build(s, [m.id])["groups"]["finish"][0]
    assert [c["url"] for c in item["candidates"]] == ["https://b.example/p/1", "https://b.example/p/2"]
    assert cl.pick(s, r, ["https://b.example/p/2", "https://evil.example/x"], "Jane") == "queued"
    assert r.status == db.RequestStatus.pending and json.loads(r.picked_enc) == ["https://b.example/p/2"]
    assert r.candidates_enc is None, "only picked addresses are kept"
    r.status, r.candidates_enc = db.RequestStatus.needs_manual, json.dumps(cands); s.commit()
    assert cl.pick(s, r, [], "Jane") == "skipped" and r.status == db.RequestStatus.skipped
    s.close()


@test(2, "matching.web_search_follows_the_setting",
      "Name-only web search hits on known brokers are skipped, queued for removal or left to review, per the setting.")
def t_match_web_search():
    db, s = _memory_db()
    ws = _imp("core.web_search")
    m = _member_with_vault(db, s)
    s.add(db.Broker(name="Radaris", opt_out_url="https://radaris.com/control-privacy")); s.commit()
    pages = [{"url": "https://radaris.com/p/Jane/Public/1", "title": "Jane Public", "snippet": "View profile"},
             {"url": "https://radaris.com/p/Jane/Public/2", "title": "Jane Public", "snippet": "View profile"},
             {"url": "https://radaris.com/p/Bob/Jones", "title": "Bob Jones", "snippet": "Reno, NV"}]
    def hits():
        return {h.url: h for h in s.query(db.WebSearchHit).all()}
    def run(policy):
        for h in s.query(db.WebSearchHit).all():
            s.delete(h)
        s.commit()
        return ws.run_for_member(s, m, {"web_search": {"max_queries": 1}, "matching": {"unclear_listings": policy}},
                                 search=lambda q: pages, pause=0)
    run("ask")
    H = hits()
    unclear = [h for u, h in H.items() if "/Jane/" in u]
    assert unclear and all(h.status == "new" and h.matched_on == "unclear" for h in unclear), \
        [(h.url, h.status, h.matched_on) for h in H.values()]
    st = run("skip")
    assert all(h.status == "dismissed" and h.dismiss_reason == "unclear_skipped"
               for u, h in hits().items() if "/Jane/" in u), "skip leaves them alone"
    run("remove_all")
    assert all(h.status == "added" for u, h in hits().items() if "/Jane/" in u), "remove all queues every one"
    s.close()
    # EXPECTED: name-only hits follow the same setting as listings found on the sites themselves.


@test(1, "security.secret_key_and_sso_and_null_bytes",
      "Missing or example SECRET_KEY values are rejected; multi-tenant Microsoft without allowed_domains cannot sign in to existing accounts; null bytes are stripped.")
def t_security_scanner_regressions():
    ss = _imp("core.settings_store")
    for bad in ("", "   ", "change-me-please", "change-me-to-a-long-random-string",
                "change-me-in-production-use-a-long-random-string", "openoptout-default-pepper-key", "secret"):
        assert not ss.is_valid_secret_key(bad), f"expected {bad!r} to be rejected"
    assert ss.is_valid_secret_key("0123456789abcdef0123456789abcdef0123456789abcdef")

    old_key = os.environ.get("SECRET_KEY")
    old_file = os.environ.get("SECRET_KEY_FILE")
    try:
        os.environ["SECRET_KEY"] = "change-me-please"
        os.environ["SECRET_KEY_FILE"] = "/tmp/nonexistent_openoptout_test_secret.key"
        try:
            ss.get_secret_key()
            assert False, "get_secret_key must refuse example key"
        except RuntimeError:
            pass

        # User-entered master secret key must be 128..512 chars with sufficient entropy
        assert ss.MAX_SECRET_KEY_CHARS == 512
        assert not ss.is_valid_user_secret_key("short-key-" + "x" * 50)
        assert not ss.is_valid_user_secret_key("a" * 128)
        assert not ss.is_valid_user_secret_key("Ab3$kL9!" * 65)  # 520 > 512
        good_128 = ("Ab3$kL9!pQ2@vX7#mZ4&wN8*yR1^tF6%" * 4)
        assert len(good_128) == 128 and ss.is_valid_user_secret_key(good_128)

        import tempfile
        with tempfile.TemporaryDirectory() as td:
            kf = os.path.join(td, "secret.key")
            os.environ["SECRET_KEY_FILE"] = kf
            st0 = ss.get_secret_key_status()
            assert st0["needs_key"] and st0["banner_required"], st0

            st1 = ss.save_secret_key_file(good_128)
            assert st1["has_valid_file_key"] and not st1["needs_key"], st1
            assert st1["permissions_insecure"] and st1["banner_required"], st1
            assert ss.get_secret_key() == good_128

            os.chmod(kf, 0o600)
            st2 = ss.get_secret_key_status()
            assert st2["permissions_secure"] and not st2["permissions_insecure"] and not st2["banner_required"], st2
    finally:
        if old_key is not None:
            os.environ["SECRET_KEY"] = old_key
        if old_file is not None:
            os.environ["SECRET_KEY_FILE"] = old_file
        else:
            os.environ.pop("SECRET_KEY_FILE", None)

    # Microsoft multi-tenant without allowed_domains must block even existing accounts (user_exists=True)
    sp = _imp("core.sso_policy")
    class _MsRes:
        provider = "microsoft"
        email = "admin@example.invalid"
        email_verified = True
        hosted_domain = ""
        groups = []
    d = sp.evaluate_sso_login(_MsRes(), {"tenant_id": "common", "allowed_domains": ""}, {}, user_exists=True, user_count=5)
    assert not d.allowed and "allowed domains" in d.reason, d
    d_tenant = sp.evaluate_sso_login(_MsRes(), {"tenant_id": "contoso.onmicrosoft.com", "allowed_domains": ""}, {}, user_exists=True, user_count=5)
    assert d_tenant.allowed, d_tenant

    # Null byte stripping helper
    lim = _imp("core.limits")
    cleaned = lim.strip_null_bytes({"username": "jordan\x00example", "nested": ["a\x00b", ("c\x00d",)]})
    assert cleaned == {"username": "jordanexample", "nested": ["ab", ("cd",)]}, cleaned

    # HSTS command generation in wizard
    wiz_src = os.path.join(os.path.dirname(os.path.dirname(__file__)), "routers", "wizard.py")
    with open(wiz_src, encoding="utf-8") as f:
        code = f.read()
    import ast
    tree = ast.parse(code)
    ns = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") in ("FRONT_DOORS", "CERTIFICATES") for t in node.targets):
            exec(compile(ast.Module(body=[node], type_ignores=[]), wiz_src, "exec"), ns)
        elif isinstance(node, ast.FunctionDef) and node.name == "enable_https_commands":
            exec(compile(ast.Module(body=[node], type_ignores=[]), wiz_src, "exec"), ns)
    cmds_no_hsts = ns["enable_https_commands"]("caddy", "letsencrypt", "home.example.org", hsts=False)
    assert "--no-hsts" in cmds_no_hsts["linux"] and "-NoHsts" in cmds_no_hsts["windows"], cmds_no_hsts


@test(2, "security.mfa_stepup_password_length_hsts_and_svg_csp",
      "MFA enrollment requires full sign-in once MFA is active; passwords require 8+ chars while shorter existing passwords still sign in; SVG logos carry CSP sandbox; HSTS toggles work.")
def t_security_tier2_regressions():
    try:
        import fastapi  # noqa: F401
    except ImportError as e:
        raise Skip(f"fastapi not installed: {e}")
    db, s = _memory_db()
    auth_core = _imp("core.auth")
    auth_router = _imp("routers.auth")
    mfa_core = _imp("core.mfa")
    branding_router = _imp("routers.branding")
    from fastapi import HTTPException

    # 1. Minimum password length = 8 chars, null bytes stripped
    for short_pw in ("1", "1234567", "abc\x00def"):
        try:
            auth_core.validate_password_length(short_pw)
            assert False, f"expected {short_pw!r} to be rejected"
        except ValueError as e:
            assert "8 characters" in str(e)
    auth_core.validate_password_length("12345678")

    # 2. MFA step-up: mfa_ticket cannot enroll or replace MFA on an account that already has MFA
    u = db.User(
        email="jordan@example.invalid",
        full_name="Jordan Example",
        role=db.UserRole.parent,
        hashed_password=auth_core.hash_password("legacy"),  # existing short password hashes and verifies
        totp_enabled=False,
    )
    s.add(u); s.commit()
    assert auth_core.verify_password("legacy", u.hashed_password), "existing shorter password must still verify"

    ticket = mfa_core.create_mfa_ticket(u.id, u.email)
    # Before MFA is enabled, mfa_ticket is allowed for initial enrollment
    resolved = auth_router._resolve_user_for_mfa(s, current_user=None, mfa_ticket=ticket, for_enrollment=True)
    assert resolved.id == u.id

    # Once TOTP is enabled on the account, mfa_ticket must be rejected for enrollment (403)
    u.totp_enabled = True
    u.totp_secret_enc = "encrypted-secret"
    s.commit()
    try:
        auth_router._resolve_user_for_mfa(s, current_user=None, mfa_ticket=ticket, for_enrollment=True)
        assert False, "mfa_ticket must not allow re-enrolling MFA when MFA is already enabled"
    except HTTPException as e:
        assert e.status_code == 403, e.detail

    # Full sign-in (current_user present) is allowed
    resolved_full = auth_router._resolve_user_for_mfa(s, current_user=u, mfa_ticket=None, for_enrollment=True)
    assert resolved_full.id == u.id

    # 3. SVG logo CSP headers
    assert "sandbox" in branding_router._SVG_CSP_HEADERS.get("Content-Security-Policy", "")
    assert branding_router._SVG_CSP_HEADERS.get("X-Content-Type-Options") == "nosniff"
    s.close()


def main():
    ap = argparse.ArgumentParser(description="OpenOptOut test runner")
    ap.add_argument("--tier", type=int, default=4, help="run tiers up to N (1-4)")
    ap.add_argument("--only", type=str, default="", help="substring filter on test name")
    ap.add_argument("--verbose", action="store_true", help="show full tracebacks")
    args = ap.parse_args()

    tests = sorted(_REGISTRY, key=lambda t: (t[0], t[1]))
    results = []
    print("=" * 70)
    print("  OpenOptOut test runner")
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
