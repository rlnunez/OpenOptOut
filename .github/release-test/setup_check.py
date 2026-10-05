#!/usr/bin/env python3
"""Check a running OpenOptOut install through its API, the way a new user would use it.

Phases:
  fresh           (default) for a brand-new install:
                  health + version · first-run state · admin account (reuses the
                  one ui_check.py created, or creates one) · setup wizard ·
                  Identity Vault save/read-back · every simple GET endpoint
  before-upgrade  same as fresh, then saves what it created to --state-file
  after-upgrade   after upgrading: logs in with the saved account and checks the
                  saved Identity Vault data is still there and readable, then the
                  GET sweep again

Writes setup-results.json and setup-report.md to --out-dir.
Exit code: 0 = all good, 1 = problems found, 2 = could not run at all.
Standard library only. Uses only obviously fake example data.
"""
import argparse
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# Fake identity data used to test the encrypted Identity Vault round trip.
# example.com / 555-01xx / "ZZ 00000" are reserved for examples and reach no one.
VAULT_SAMPLE = [
    ("name", "Release Test Person"),
    ("email", "release-test-person@example.com"),
    ("phone", "555-0100"),
    ("address", "123 Example Street, Springfield, ZZ 00000"),
]

# GET endpoints that are slow on purpose, stream forever, or reach the internet.
SKIP_GET_SUBSTRINGS = ("stream", "/events", "/sse", "/download", "/export")


class Checker:
    def __init__(self, base):
        self.base = base.rstrip("/")
        self.token = None
        self.steps = []      # {"name", "ok", "note"}
        self.errors = []     # {"where", "detail"}
        self.warnings = []

    # ── HTTP ────────────────────────────────────────────────────────────────
    def call(self, method, path, body=None, form=None, timeout=30):
        headers = {}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        elif form is not None:
            data = urllib.parse.urlencode(form).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                return r.status, _json(raw)
        except urllib.error.HTTPError as e:
            return e.code, _json(e.read())

    def step(self, name, ok, note=""):
        self.steps.append({"name": name, "ok": bool(ok), "note": str(note)[:300]})
        print(f"{'PASS' if ok else 'FAIL'}  {name}  {note}")
        if not ok:
            self.errors.append({"where": name, "detail": str(note)[:500]})
        return ok

    # ── checks ──────────────────────────────────────────────────────────────
    def wait_healthy(self, seconds):
        deadline = time.time() + seconds
        last = ""
        while time.time() < deadline:
            try:
                status, body = self.call("GET", "/api/health", timeout=5)
                if status == 200:
                    return body
                last = f"HTTP {status}"
            except Exception as e:  # noqa: BLE001
                last = str(e)
            time.sleep(3)
        raise RuntimeError(f"API not healthy after {seconds}s ({last})")

    def check_version(self, health, expect):
        got = str(health.get("version", ""))
        if not expect:
            return self.step("Version reported", True, got)
        want = expect.lstrip("vV")
        return self.step("Version matches the release tag", got.lstrip("vV") == want,
                         f"API reports {got!r}, release tag is {expect!r}")

    def login_or_register(self, creds_file):
        creds = None
        if creds_file and os.path.exists(creds_file):
            with open(creds_file) as f:
                creds = json.load(f)
        status, body = self.call("GET", "/api/auth/needs-setup")
        needs = isinstance(body, dict) and body.get("needs_setup")

        if needs:
            # Nobody has registered yet (e.g. the browser check didn't get that far)
            creds = {"email": f"release-test-{secrets.token_hex(3)}@example.com",
                     "password": secrets.token_urlsafe(18)}
            status, body = self.call("POST", "/api/auth/register", {
                "email": creds["email"], "password": creds["password"],
                "full_name": "Release Test Admin"})
            if not self.step("Create the first (administrator) account via API",
                             status == 201, f"HTTP {status} {short(body)}"):
                return None
            if creds_file:
                with open(creds_file, "w") as f:
                    json.dump(creds, f)
        elif not creds:
            self.step("Log in", False, "an account already exists but no credentials were saved")
            return None

        status, body = self.call("POST", "/api/auth/token",
                                 form={"username": creds["email"], "password": creds["password"]})
        if not self.step("Log in with the administrator account", status == 200,
                         f"HTTP {status}" + ("" if status == 200 else f" {short(body)}")):
            return None
        self.token = body["access_token"]
        status, me = self.call("GET", "/api/auth/me")
        self.step("Account is a super admin", status == 200 and me.get("role") == "super_admin",
                  f"role={me.get('role') if isinstance(me, dict) else me}")
        status, body = self.call("GET", "/api/auth/needs-setup")
        self.step("First-run screen is gone once an admin exists",
                  status == 200 and body.get("needs_setup") is False, short(body))
        return creds

    def finish_wizard(self):
        status, state = self.call("GET", "/api/wizard/state")
        if not self.step("Read setup wizard state", status == 200, f"HTTP {status} {short(state)}"):
            return
        if state.get("completed"):
            return self.step("Setup wizard completed", True, "already finished (in the browser)")
        for s in ("database", "email", "deployment", "branding"):
            if s not in (state.get("steps") or {}):
                st, b = self.call("POST", "/api/wizard/skip", {"step": s})
                self.step(f"Wizard: skip '{s}' step", st == 200, f"HTTP {st} {short(b)}")
        st, b = self.call("POST", "/api/wizard/complete")
        self.step("Wizard: finish", st == 200, f"HTTP {st} {short(b)}")
        st, state = self.call("GET", "/api/wizard/state")
        self.step("Setup wizard completed", st == 200 and state.get("completed"), short(state))

    def first_member_id(self):
        status, members = self.call("GET", "/api/family")
        if not self.step("List family members", status == 200 and isinstance(members, list) and members,
                         f"HTTP {status} {short(members)}"):
            return None
        return members[0]["id"]

    def vault_write(self, member_id):
        created = []
        for kind, value in VAULT_SAMPLE:
            st, b = self.call("POST", f"/api/identity/{member_id}",
                              {"kind": kind, "value": value, "is_primary": False})
            ok = st == 201 and isinstance(b, dict) and b.get("value") == value
            self.step(f"Identity Vault: save {kind}", ok, f"HTTP {st} {short(b)}")
            if ok:
                created.append({"id": b["id"], "kind": kind, "value": value})
        return created

    def vault_verify(self, member_id, expected, label):
        st, rows = self.call("GET", f"/api/identity/{member_id}")
        if not self.step(f"Identity Vault: read back ({label})", st == 200 and isinstance(rows, list),
                         f"HTTP {st} {short(rows)}"):
            return
        by_id = {r["id"]: r for r in rows}
        missing = [e for e in expected if e["id"] not in by_id]
        changed = [e for e in expected if e["id"] in by_id and by_id[e["id"]]["value"] != e["value"]]
        self.step(f"Identity Vault: all {len(expected)} entries present and unchanged ({label})",
                  not missing and not changed and expected,
                  ("" if expected else "nothing to compare; ")
                  + (f"missing ids {[e['id'] for e in missing]}; " if missing else "")
                  + (f"changed: {[(e['kind'], by_id[e['id']]['value']) for e in changed]}" if changed else ""))

    def get_sweep(self, schema_url):
        """Call every GET endpoint that needs no ID. A 5xx is a bug; slow ones are warnings."""
        # nginx only forwards /api/*, so the schema is fetched from the API port directly.
        try:
            with urllib.request.urlopen(schema_url, timeout=30) as r:
                schema = _json(r.read())
        except Exception as e:  # noqa: BLE001
            schema = str(e)
        if not isinstance(schema, dict) or "paths" not in schema:
            self.step("Fetch API schema", False, f"{schema_url}: {short(schema)}")
            return
        paths = [p for p, ops in schema.get("paths", {}).items()
                 if "get" in ops and "{" not in p
                 and not any(s in p for s in SKIP_GET_SUBSTRINGS)]
        fails = []
        for p in sorted(paths):
            try:
                code, body = self.call("GET", p, timeout=20)
            except Exception as e:  # noqa: BLE001 — timeouts etc.
                self.warnings.append({"where": f"GET {p}", "detail": f"no response: {e}"})
                continue
            if code >= 500:
                fails.append(f"{code} GET {p} {short(body, 120)}")
                self.errors.append({"where": f"GET {p}", "detail": f"HTTP {code} {short(body, 300)}"})
            elif code >= 400 and code not in (401, 403, 404):
                self.warnings.append({"where": f"GET {p}", "detail": f"HTTP {code} {short(body, 200)}"})
        self.steps.append({"name": f"Every simple GET endpoint answers without a server error ({len(paths)} checked)",
                           "ok": not fails, "note": "; ".join(fails)[:300]})
        print(f"{'PASS' if not fails else 'FAIL'}  GET sweep: {len(paths)} endpoints, {len(fails)} server errors")


def _json(raw):
    try:
        return json.loads(raw or b"null")
    except ValueError:
        return raw.decode(errors="replace")[:500]


def short(obj, n=200):
    s = obj if isinstance(obj, str) else json.dumps(obj, default=str)
    return s if len(s) <= n else s[:n] + "…"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost")
    ap.add_argument("--phase", choices=["fresh", "before-upgrade", "after-upgrade"], default="fresh")
    ap.add_argument("--expect-version", default="", help="release tag the API should report")
    ap.add_argument("--creds-file", required=True)
    ap.add_argument("--state-file", help="before/after-upgrade: where to save/load created data")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--wait-seconds", type=int, default=420)
    ap.add_argument("--schema-url", default="http://localhost:8010/openapi.json",
                    help="OpenAPI schema (default: the API port docker-compose.yml publishes on 127.0.0.1)")
    args = ap.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)

    c = Checker(args.base_url)
    try:
        health = c.wait_healthy(args.wait_seconds)
        c.step("API is up (through the web server)", True, short(health))
    except RuntimeError as e:
        c.step("API is up (through the web server)", False, str(e))
        return write(args, c)
    c.check_version(health, args.expect_version)

    if not c.login_or_register(args.creds_file):
        return write(args, c)

    if args.phase in ("fresh", "before-upgrade"):
        c.finish_wizard()
        member = c.first_member_id()
        if member:
            created = c.vault_write(member)
            c.vault_verify(member, created, "same version")
            if args.phase == "before-upgrade" and args.state_file:
                with open(args.state_file, "w") as f:
                    json.dump({"member_id": member, "identities": created}, f)
    else:  # after-upgrade
        st, state = c.call("GET", "/api/wizard/state")
        c.step("Setup wizard still marked complete after upgrade",
               st == 200 and state.get("completed"), short(state))
        saved = {}
        if args.state_file and os.path.exists(args.state_file):
            with open(args.state_file) as f:
                saved = json.load(f)
        if saved.get("member_id"):
            c.vault_verify(saved["member_id"], saved.get("identities", []), "after upgrade")
        else:
            c.step("Identity Vault data from before the upgrade", False, "no saved state to compare")

    c.get_sweep(args.schema_url)
    return write(args, c)


def write(args, c):
    ok = all(s["ok"] for s in c.steps) and not c.errors
    with open(os.path.join(args.out_dir, f"setup-results-{args.phase}.json"), "w") as f:
        json.dump({"ok": ok, "phase": args.phase, "steps": c.steps,
                   "errors": c.errors, "warnings": c.warnings}, f, indent=2)
    title = {"fresh": "API setup check",
             "before-upgrade": "API check — previous release (before upgrade)",
             "after-upgrade": "API check — after upgrading"}[args.phase]
    md = [f"### {title}", ""]
    for s in c.steps:
        md.append(f"- {'✅' if s['ok'] else '❌'} {s['name']}"
                  + (f" — `{s['note'][:160]}`" if s["note"] and not s["ok"] else ""))
    extra = [e for e in c.errors if e["where"].startswith("GET ")]
    if extra:
        md += ["", f"**Server errors from the GET sweep ({len(extra)}):**", "",
               "| Endpoint | Response |", "|---|---|"]
        md += [f"| `{e['where']}` | {e['detail'][:200].replace('|', '¦')} |" for e in extra[:40]]
    if c.warnings:
        md += ["", f"<details><summary>⚠️ {len(c.warnings)} warning(s)</summary>", "",
               "| Where | Details |", "|---|---|"]
        md += [f"| `{w['where']}` | {w['detail'][:200].replace('|', '¦')} |" for w in c.warnings[:60]]
        md += ["", "</details>"]
    md.append("")
    with open(os.path.join(args.out_dir, f"setup-report-{args.phase}.md"), "w") as f:
        f.write("\n".join(md))
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001
        print(f"::error::API setup check could not run: {e}")
        sys.exit(2)
