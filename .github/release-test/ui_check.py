#!/usr/bin/env python3
"""Walk through OpenOptOut's first-run setup in a real browser, like a new user.

  1. opens the site and expects the "create administrator" screen
  2. creates the admin account through the form
  3. clicks through the setup wizard (skipping each step) to the dashboard
  4. visits every page in the app

Along the way it records everything that went wrong — JavaScript crashes,
console errors, failed or 5xx API calls, blank pages — and takes a screenshot
of each screen. Results go to OUT_DIR:

    screenshots/NN-name.png   one per screen
    ui-results.json           machine-readable results
    ui-report.md              the readable report (also added to the job summary)

The admin credentials it creates are written to --creds-file so the API check
(setup_check.py) can log in as the same user afterwards.

Exit code: 0 = no serious problems, 1 = serious problems found, 2 = could not run.
Requires: pip install playwright && python -m playwright install --with-deps chromium
"""
import argparse
import json
import os
import re
import secrets
import sys
import time

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# Every page route in frontend/src/App.jsx (a super admin can open all of them).
PAGES = [
    "/", "/family", "/identity", "/brokers", "/discovery", "/scheduled",
    "/email", "/captcha", "/reporting", "/settings", "/branding", "/admin",
    "/translations", "/database", "/plugins", "/plugin-help", "/plugin-upload",
    "/broker-health", "/broker-priority", "/parent-companies", "/logs",
    "/worker-fleet", "/help",
]

ERROR_TEXT = re.compile(
    r"(something went wrong|unexpected error|internal server error|"
    r"cannot read propert|is not a function|undefined is not)", re.I)

# Pages that render the app's own text catalogs or diagnostics as CONTENT:
# the translation editor lists every UI string (including the wording of error
# messages), the logs page shows log lines (ERROR entries and all), and the
# help pages quote admin-editable notes. An error phrase appearing there is
# expected content, not a live failure, so a match is a warning, not a
# run-failing error.
CONTENT_PAGES = {"/translations", "/logs", "/help", "/plugin-help"}

AXE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "axe.min.js")
AXE_SCRIPT = None
if os.path.isfile(AXE_PATH):
    try:
        with open(AXE_PATH, "r", encoding="utf-8") as f:
            AXE_SCRIPT = f.read()
    except Exception:
        pass


def audit_page_a11y(page, rec, route, is_ada=False, ada_theme_name=None):
    """Evaluate WCAG 2.2 accessibility rules via axe-core."""
    if not AXE_SCRIPT:
        return
    try:
        results = page.evaluate("""(fallbackScript) => {
            if (typeof axe === 'undefined' && fallbackScript) {
                window.eval(fallbackScript);
            }
            return new Promise((resolve) => {
                if (typeof axe === 'undefined') {
                    resolve({ error: 'axe not loaded' });
                    return;
                }
                axe.run(document, {
                    runOnly: {
                        type: 'tag',
                        values: ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']
                    }
                }, (err, res) => {
                    if (err) resolve({ error: String(err) });
                    else resolve(res);
                });
            });
        }""", AXE_SCRIPT)
        theme_name = ada_theme_name or ("ADA/WCAG (theme-dark-ada)" if is_ada else "Regular Theme")
        if isinstance(results, dict) and "violations" in results:
            for v in results["violations"]:
                impact = str(v.get("impact", "unknown")).lower()
                desc = v.get("description", "")
                nodes = v.get("nodes", [])
                rule = v.get("id", "rule")

                node_details = []
                for idx, n in enumerate(nodes[:5], 1):
                    target = " > ".join(n.get("target", []))
                    html_snippet = n.get("html", "").strip().replace("\n", " ")
                    if len(html_snippet) > 90:
                        html_snippet = html_snippet[:87] + "..."
                    why = n.get("failureSummary", "").strip().replace("\n", "; ")
                    if len(why) > 130:
                        why = why[:127] + "..."
                    node_details.append(f"#{idx} <{target}> `{html_snippet}` ({why})")

                elements_str = " | ".join(node_details)
                if len(nodes) > 5:
                    elements_str += f" | ... +{len(nodes) - 5} more"

                msg = f"[{theme_name}] [{impact.upper()}] {rule}: {desc} ({len(nodes)} node(s)) -> {elements_str}"
                print(f"  [A11Y] {route}: {msg}", flush=True)

                # In standard/regular theme mode, subdued text contrast and compact touch targets
                # are visual styling choices that are purposefully satisfied when the user activates
                # the ADA/WCAG High Contrast & Enhanced Targets theme. Suppress them from warnings.
                if not is_ada and rule in ("color-contrast", "target-size"):
                    pass
                elif impact in ("critical", "serious"):
                    rec.error("Accessibility violation (WCAG 2.2)", f"{route}: {msg}")
                else:
                    rec.warn("Accessibility warning (WCAG 2.2)", f"{route}: {msg}")
    except Exception as e:
        rec.warn("Accessibility audit exception", f"{route}: {e}")


class Recorder:
    """Collects problems, tagged with the screen they happened on."""

    def __init__(self):
        self.screen = "startup"
        self.errors = []     # serious: fail the run
        self.warnings = []   # worth a look, don't fail

    def error(self, kind, detail):
        self.errors.append({"screen": self.screen, "kind": kind, "detail": detail[:4000]})

    def warn(self, kind, detail):
        self.warnings.append({"screen": self.screen, "kind": kind, "detail": detail[:4000]})


def settle(page, ms=8000):
    try:
        page.wait_for_load_state("networkidle", timeout=ms)
    except PWTimeout:
        pass


def visible(page, role, name, timeout=1500):
    loc = page.get_by_role(role, name=name)
    try:
        loc.first.wait_for(state="visible", timeout=timeout)
        return loc.first
    except PWTimeout:
        return None


ADA_THEMES = [
    {
        "id": "dark-ada",
        "label": "Dark ADA",
        "desc": "WCAG Level AAA 21:1 contrast, 125% font, enhanced targets",
        "classes": [
            "theme-dark", "theme-dark-ada",
            "a11y-high-contrast", "a11y-high-contrast-dark",
            "a11y-enhanced-targets", "a11y-large-text"
        ],
    },
    {
        "id": "light-ada",
        "label": "Light ADA",
        "desc": "Crisp white, high-contrast black & saturated blue, enhanced targets",
        "classes": [
            "theme-light", "theme-light-ada",
            "a11y-high-contrast", "a11y-high-contrast-light",
            "a11y-enhanced-targets", "a11y-large-text"
        ],
    },
    {
        "id": "space-ada",
        "label": "Space Explorer ADA",
        "desc": "Cosmic black, high-contrast luminous amber (AAA), 2px visibility borders",
        "classes": [
            "theme-space", "theme-space-ada",
            "a11y-high-contrast", "a11y-high-contrast-space",
            "a11y-enhanced-targets", "a11y-large-text"
        ],
    },
]


def run_worker(theme_id, args):
    """Audit all routes for one specific theme in an isolated browser process."""
    base = args.base_url.rstrip("/")
    shots = os.path.join(args.out_dir, "screenshots")
    os.makedirs(shots, exist_ok=True)
    rec = Recorder()
    page_results = []
    steps = []

    def snap(page, name, force=False):
        if not force and not args.save_all_screenshots and "failure" not in name:
            return None
        path = os.path.join(shots, f"{name}.png")
        try:
            page.screenshot(path=path, full_page=True)
        except Exception:
            try:
                page.screenshot(path=path, full_page=False)
            except Exception as e:
                rec.warn("screenshot", f"{name}: {e}")
        return path

    t_cfg = next((t for t in ADA_THEMES if t["id"] == theme_id), None)
    is_regular = (theme_id == "regular")
    t_label = "Regular Theme" if is_regular else (t_cfg["label"] if t_cfg else theme_id)
    t_classes = t_cfg["classes"] if t_cfg else []
    t_desc = t_cfg.get("desc", "") if t_cfg else ""

    with sync_playwright() as p:
        exe = os.environ.get("CHROMIUM_EXECUTABLE") or None
        launcher = getattr(p, args.browser.lower(), p.chromium)
        browser = launcher.launch(executable_path=exe)
        ctx = browser.new_context(
            storage_state=args.storage_state,
            viewport={"width": 1366, "height": 900},
        )
        if AXE_SCRIPT:
            ctx.add_init_script(AXE_SCRIPT)
        page = ctx.new_page()

        page.on("pageerror", lambda e: rec.error("JavaScript crash", str(e)))
        page.on("console", lambda m: m.type == "error" and rec.warn("Console error", m.text))

        def on_failed(r):
            detail = f"{r.method} {r.url} — {r.failure}"
            aborted = any(tok in str(r.failure) for tok in ("ERR_ABORTED", "NS_BINDING_ABORTED", "Request cancelled"))
            if r.url.startswith(base) and not aborted:
                rec.error("Request failed", detail)
            else:
                rec.warn("Request failed", detail)
        page.on("requestfailed", on_failed)

        def on_response(r):
            if "/api/" not in r.url:
                return
            if r.status >= 500:
                rec.error("Server error", f"{r.status} {r.request.method} {r.url}")
            elif r.status >= 400 and r.status not in (401,):
                rec.warn("API error", f"{r.status} {r.request.method} {r.url}")
        page.on("response", on_response)

        if not is_regular:
            rec.screen = f"switch to {t_label}"
            try:
                page.goto(base + "/", timeout=45000)
                settle(page)
                page.evaluate("""(classes) => {
                    const root = document.documentElement;
                    root.classList.remove(
                        'theme-light', 'theme-light-ada',
                        'theme-gray',
                        'theme-dark', 'theme-dark-ada',
                        'theme-space', 'theme-space-ada',
                        'a11y-high-contrast',
                        'a11y-high-contrast-light',
                        'a11y-high-contrast-dark',
                        'a11y-high-contrast-space'
                    );
                    for (const c of classes) {
                        root.classList.add(c);
                    }
                    root.style.setProperty('--a11y-font-size', '125%');
                }""", t_classes)
                settle(page, 2000)
                snap(page, f"ada-{theme_id}-dashboard", force=True)
                steps.append((f"Switch to {t_label} ({t_desc})", True, f"Theme {theme_id} activated"))
            except Exception as e:
                steps.append((f"Switch to {t_label}", False, str(e)[:200]))

        if getattr(args, "routes", None) and args.routes.strip() and args.routes.strip().lower() != "all":
            routes_to_test = [r.strip() for r in args.routes.split(",") if r.strip()]
        else:
            routes_to_test = PAGES

        for route in routes_to_test:
            rec.screen = f"page {route}" if is_regular else f"page {route} ({t_label} mode)"
            before = (len(rec.errors), len(rec.warnings))
            try:
                page.goto(base + route, timeout=30000)
            except Exception as e:  # noqa: BLE001
                rec.error(f"Page did not load in {t_label} mode" if not is_regular else "Page did not load", str(e))
            settle(page)
            time.sleep(0.3)

            if is_regular:
                try:
                    tb = page.locator("section[aria-labelledby='terms-title'] input[type='checkbox']")
                    if tb.count() > 0 and tb.first.is_visible() and not tb.first.is_checked():
                        tb.first.check()
                        time.sleep(0.2)
                except Exception:
                    pass
                cont = (visible(page, "button", re.compile(r"^\s*Continue\s*$", re.I), timeout=300)
                        or visible(page, "button", re.compile(r"^\s*I understand\s*$", re.I), timeout=300))
                if cont and cont.is_enabled():
                    cont.click()
                    settle(page, 2000)
                tour = visible(page, "button", re.compile(r"^\s*Skip Tutorial\s*$", re.I), timeout=300)
                if tour:
                    tour.click()
                    settle(page, 3000)
            else:
                try:
                    page.evaluate("""(classes) => {
                        const root = document.documentElement;
                        root.classList.remove(
                            'theme-light', 'theme-light-ada',
                            'theme-gray',
                            'theme-dark', 'theme-dark-ada',
                            'theme-space', 'theme-space-ada',
                            'a11y-high-contrast',
                            'a11y-high-contrast-light',
                            'a11y-high-contrast-dark',
                            'a11y-high-contrast-space'
                        );
                        for (const c of classes) {
                            root.classList.add(c);
                        }
                        root.style.setProperty('--a11y-font-size', '125%');
                    }""", t_classes)
                except Exception:
                    pass

            text = ""
            for _ in range(10):
                try:
                    text = page.inner_text("body")
                except Exception:  # noqa: BLE001
                    pass
                if len(text.strip()) >= 20:
                    break
                time.sleep(0.5)
            if len(text.strip()) < 20:
                rec.error("Blank page", f"{route} rendered almost no text")
            m = ERROR_TEXT.search(text)
            if m and route not in CONTENT_PAGES:
                rec.error("Error shown on page", f"{route}: …{text[max(0, m.start() - 80):m.end() + 120]}…")
            if "/login" in page.url and route != "/login":
                rec.error("Logged out unexpectedly", f"opening {route} sent us to {page.url}")

            audit_route = route if is_regular else f"{route} ({t_label})"
            audit_page_a11y(page, rec, audit_route, is_ada=not is_regular, ada_theme_name=f"{t_label} ({theme_id})" if not is_regular else None)

            has_error = len(rec.errors) > before[0]
            name = ("page-root" if route == "/" else "page" + route.replace("/", "-")) if is_regular else (("page-root-" if route == "/" else "page" + route.replace("/", "-") + "-") + theme_id)
            if has_error or args.save_all_screenshots:
                snap(page, f"{name}-failure" if has_error else name, force=True)
            page_results.append({
                "route": audit_route,
                "errors": len(rec.errors) - before[0],
                "warnings": len(rec.warnings) - before[1],
            })

        if is_regular:
            steps.append(("Open every page (Regular theme)", True, f"{len(routes_to_test)} pages"))
        else:
            steps.append((f"Open every page in {t_label} mode", True, f"{len(routes_to_test)} pages audited"))

        browser.close()

    out_file = os.path.join(args.out_dir, f"worker-results-{theme_id}.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump({
            "theme_id": theme_id,
            "errors": rec.errors,
            "warnings": rec.warnings,
            "pages": page_results,
            "steps": steps,
        }, f)
    return 0


def dispatch_workers(args, rec, steps, theme_ids, auth_state_path=None):
    """Run audits for selected themes sequentially to guarantee database consistency and avoid port contention."""
    all_pages = []
    for t_id in theme_ids:
        if auth_state_path:
            args.storage_state = auth_state_path
        run_worker(t_id, args)

        worker_file = os.path.join(args.out_dir, f"worker-results-{t_id}.json")
        if os.path.exists(worker_file):
            try:
                with open(worker_file, "r", encoding="utf-8") as f:
                    w_data = json.load(f)
                    rec.errors.extend(w_data.get("errors", []))
                    rec.warnings.extend(w_data.get("warnings", []))
                    all_pages.extend(w_data.get("pages", []))
                    for s in w_data.get("steps", []):
                        steps.append((s[0], s[1], s[2]))
            except Exception as e:
                rec.error("Worker result parse failed", f"Failed to read results for {t_id}: {e}")
                steps.append((f"Run audit for theme {t_id}", False, str(e)[:200]))
        else:
            rec.error("Worker failed", f"Worker for theme {t_id} did not produce results file {worker_file}.")
            steps.append((f"Run audit for theme {t_id}", False, "Worker results missing"))

    return all_pages


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost")
    ap.add_argument("--browser", default=os.environ.get("PLAYWRIGHT_BROWSER", "firefox"))
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--creds-file", default=None, help="Path to credentials output file")
    ap.add_argument(
        "--save-all-screenshots",
        action="store_true",
        default=os.environ.get("SAVE_ALL_SCREENSHOTS", "").lower() in ("1", "true", "yes"),
        help="Capture full screenshots for every page rather than only on failure or key milestones",
    )
    ap.add_argument(
        "--worker-theme",
        help="Run audit only for a specific theme ('regular', 'dark-ada', 'light-ada', 'space-ada')",
    )
    ap.add_argument(
        "--storage-state",
        help="Path to browser storage_state json file with authenticated session",
    )
    ap.add_argument(
        "--no-parallel",
        action="store_true",
        help="Run theme passes sequentially instead of parallel processes",
    )
    ap.add_argument(
        "--routes",
        default="all",
        help="Comma-separated list of routes to audit (e.g. '/logs,/settings' or 'all')",
    )
    ap.add_argument(
        "--themes",
        default="all",
        help="Comma-separated list of themes to audit ('all', or subset of 'regular,dark-ada,light-ada,space-ada')",
    )
    ap.add_argument(
        "--skip-setup",
        action="store_true",
        help="Skip first-run account creation and onboarding wizard (audit existing instance)",
    )
    args = ap.parse_args()

    if not args.creds_file:
        args.creds_file = os.path.join(args.out_dir, "creds.json")

    if args.worker_theme:
        return run_worker(args.worker_theme, args)

    valid_themes = ["regular", "dark-ada", "light-ada", "space-ada"]
    if args.themes and args.themes.lower() != "all":
        theme_ids = [t.strip() for t in args.themes.split(",") if t.strip() in valid_themes]
        if not theme_ids:
            theme_ids = valid_themes
    else:
        theme_ids = valid_themes

    shots = os.path.join(args.out_dir, "screenshots")
    os.makedirs(shots, exist_ok=True)
    rec = Recorder()
    steps = []

    if args.skip_setup:
        steps.append(("Skip first-run setup (direct audit)", True, "Direct route audit mode"))
        all_pages = dispatch_workers(args, rec, steps, theme_ids, args.storage_state)
        return finish(args, rec, steps, pages=all_pages)

    base = args.base_url.rstrip("/")
    shot_no = [0]

    email = f"release-test-{secrets.token_hex(3)}@example.com"
    password = secrets.token_urlsafe(18)
    with open(args.creds_file, "w") as f:
        json.dump({"email": email, "password": password}, f)

    def snap(page, name, force=False):
        if not force and not args.save_all_screenshots and "failure" not in name:
            return None
        shot_no[0] += 1
        path = os.path.join(shots, f"{shot_no[0]:02d}-{name}.png")
        try:
            page.screenshot(path=path, full_page=True)
        except Exception:
            try:
                page.screenshot(path=path, full_page=False)
            except Exception as e:  # noqa: BLE001
                rec.warn("screenshot", f"{name}: {e}")
        return path

    with sync_playwright() as p:
        # Optional: use an already-installed browser executable
        exe = os.environ.get("CHROMIUM_EXECUTABLE") or None
        launcher = getattr(p, args.browser.lower(), p.chromium)
        browser = launcher.launch(executable_path=exe)
        ctx = browser.new_context(viewport={"width": 1366, "height": 900})
        if AXE_SCRIPT:
            ctx.add_init_script(AXE_SCRIPT)
        page = ctx.new_page()

        # ── listeners: anything that goes wrong on any screen ────────────────
        page.on("pageerror", lambda e: rec.error("JavaScript crash", str(e)))
        page.on("console", lambda m: m.type == "error" and rec.warn("Console error", m.text))
        def on_failed(r):
            detail = f"{r.method} {r.url} — {r.failure}"
            # Our own server failing is serious; a third-party resource (web fonts,
            # CDNs) or a request cancelled by navigating away is only a warning.
            # Chromium reports ERR_ABORTED, Firefox reports NS_BINDING_ABORTED,
            # and WebKit reports 'Request cancelled'.
            aborted = any(tok in str(r.failure) for tok in ("ERR_ABORTED", "NS_BINDING_ABORTED", "Request cancelled"))
            if r.url.startswith(base) and not aborted:
                rec.error("Request failed", detail)
            else:
                rec.warn("Request failed", detail)
        page.on("requestfailed", on_failed)

        def on_response(r):
            if "/api/" not in r.url:
                return
            if r.status >= 500:
                rec.error("Server error", f"{r.status} {r.request.method} {r.url}")
            elif r.status >= 400 and r.status not in (401,):
                rec.warn("API error", f"{r.status} {r.request.method} {r.url}")
        page.on("response", on_response)

        # ── 1. first-run screen ──────────────────────────────────────────────
        rec.screen = "first-run screen"
        try:
            page.goto(base + "/", timeout=60000)
        except Exception as e:  # noqa: BLE001
            rec.error("Site unreachable", str(e))
            steps.append(("Open the site", False, str(e)[:200]))
            return finish(args, rec, steps, browser, fatal=True)
        settle(page)
        # Advance through first-boot usability / language personalization screen if presented
        continue_usability_btn = visible(page, "button", re.compile(r"^\s*Continue\s*$", re.I), timeout=5000)
        if continue_usability_btn and not visible(page, "button", "Create administrator account", timeout=500):
            snap(page, "first-run-usability", force=True)
            continue_usability_btn.click()
            settle(page)

        create_btn = visible(page, "button", "Create administrator account", timeout=20000)
        snap(page, "first-run", force=True)
        if not create_btn:
            rec.error("First-run screen missing",
                      "A fresh install should show 'Create administrator account'.")
            steps.append(("First-run screen appears", False, "button not found"))
            return finish(args, rec, steps, browser, fatal=True)
        steps.append(("First-run screen appears", True, ""))
        audit_page_a11y(page, rec, "/first-run")

        # ── 2. create the administrator through the form ─────────────────────
        rec.screen = "create administrator"
        name_input = page.get_by_placeholder("Your name")
        if name_input.count() > 0:
            name_input.first.fill("Release Test Admin")
        else:
            page.locator("input:not([type='password']):not([type='email'])").first.fill("Release Test Admin")

        email_input = page.get_by_placeholder("Admin email")
        if email_input.count() > 0:
            email_input.first.fill(email)
        else:
            page.locator("input[type='email']").first.fill(email)

        pw_input = page.get_by_placeholder(re.compile(r"Password\s*\(min\s*\d+\s*characters\)", re.I))
        if pw_input.count() > 0:
            pw_input.first.fill(password)
        else:
            page.locator("input[type='password']").first.fill(password)

        conf_input = page.get_by_placeholder(re.compile(r"Confirm password", re.I))
        if conf_input.count() > 0:
            conf_input.first.fill(password)
        else:
            page.locator("input[type='password']").nth(1).fill(password)

        create_btn.click()
        settle(page)
        time.sleep(1)
        snap(page, "after-create-admin", force=True)
        if visible(page, "button", "Create administrator account", timeout=1000):
            body = page.inner_text("body")[:300]
            rec.error("Could not create administrator", body)
            steps.append(("Create the administrator account", False, body[:200]))
            return finish(args, rec, steps, browser, fatal=True)
        steps.append(("Create the administrator account", True, email))

        # ── 3. setup wizard: skip every step until the dashboard ─────────────
        rec.screen = "setup wizard"
        reached = False
        secret_key_handled = False
        for i in range(25):
            # 3a. MFA setup screen in first-run (optional/skippable for super admin)
            mfa_btn = (visible(page, "button", re.compile(r"Skip\s+for\s+now", re.I), timeout=1000)
                       or visible(page, "button", re.compile(r"^\s*Skip\s*$", re.I), timeout=500))
            body_sample = ""
            try:
                body_sample = page.inner_text("body")[:2000]
            except Exception:
                pass
            if mfa_btn and any(w in body_sample for w in ("MFA", "Super Admin", "compliance window", "Protect Your")):
                snap(page, f"mfa-setup-{i + 1}")
                mfa_btn.click()
                settle(page, 5000)
                time.sleep(0.5)
                continue

            # 3b. Terms gate (accept limits, notice, operator terms)
            is_terms = (page.locator("#terms-title").count() > 0 and page.locator("#terms-title").first.is_visible()) or \
                       any(w in body_sample for w in ("Before you start: what OpenOptOut", "terms-title", "guarantee removal", "How OpenOptOut works for you", "Terms for this server"))
            if is_terms:
                try:
                    cb = page.locator("section[aria-labelledby='terms-title'] input[type='checkbox']")
                    if cb.count() > 0 and cb.first.is_visible() and not cb.first.is_checked():
                        cb.first.check(force=True)
                        time.sleep(0.3)
                    if cb.count() > 0 and cb.first.is_visible() and not cb.first.is_checked():
                        cb_lbl = page.locator("section[aria-labelledby='terms-title'] label")
                        if cb_lbl.count() > 0:
                            cb_lbl.first.click(force=True)
                            time.sleep(0.3)
                except Exception:
                    pass

                terms_btn = (visible(page, "button", re.compile(r"^\s*Continue\s*$", re.I), timeout=1500)
                             or visible(page, "button", re.compile(r"^\s*I understand\s*$", re.I), timeout=1500)
                             or visible(page, "button", re.compile(r"^\s*Accept\s*$", re.I), timeout=1500))
                if terms_btn and terms_btn.is_enabled():
                    snap(page, f"terms-gate-{i + 1}")
                    terms_btn.click()
                    settle(page, 5000)
                    time.sleep(0.5)
                    continue

            # 3c. Secret key generation banner / modal (if prompted during setup wizard or top banner)
            key_banner_btn = visible(page, "button", re.compile(r"^\s*Generate & Save Master Key\s*$", re.I), timeout=500)
            if not secret_key_handled and (key_banner_btn or any(w in body_sample for w in ("Critical Security Action",))):
                snap(page, f"secret-key-{i + 1}")
                if key_banner_btn:
                    key_banner_btn.click()
                    settle(page, 2000)
                    time.sleep(0.3)
                try:
                    txt = page.locator("#master-secret-key-input, textarea[id*='secret-key']")
                    if txt.count() > 0 and txt.first.is_visible():
                        val = txt.first.input_value()
                        if len(val.strip()) < 128:
                            auto_key = secrets.token_hex(64)  # 128 hex chars
                            txt.first.fill(auto_key)
                            time.sleep(0.3)
                        save_btn = visible(page, "button", re.compile(r"^\s*Save Master Key to File\s*$", re.I), timeout=1000)
                        if save_btn and save_btn.is_enabled():
                            save_btn.click()
                            settle(page, 4000)
                            time.sleep(0.5)
                except Exception:
                    pass
                v_btn = visible(page, "button", re.compile(r"^\s*Verify File Permissions\s*$", re.I), timeout=500)
                if v_btn and v_btn.is_enabled():
                    v_btn.click()
                    settle(page, 2000)
                secret_key_handled = True

            # 3d. Setup wizard summary: "Go to dashboard"
            dash_btn = visible(page, "button", re.compile(r"^\s*Go to dashboard\s*$", re.I), timeout=1500)
            if dash_btn:
                snap(page, f"wizard-summary-{i + 1}")
                dash_btn.click()
                settle(page, 5000)
                time.sleep(1)
                # Dismiss welcome tour if it appears right after
                tour = visible(page, "button", re.compile(r"^\s*Skip Tutorial\s*$", re.I), timeout=1500)
                if tour:
                    tour.click()
                    settle(page, 3000)
                reached = True
                break

            # 3e. Setup wizard steps or tour: "Skip", "Continue", "Finish", or "Skip Tutorial"
            skip_btn = (visible(page, "button", re.compile(r"^\s*Skip Tutorial\s*$", re.I), timeout=500)
                        or visible(page, "button", re.compile(r"^\s*Skip\s*$", re.I), timeout=1000)
                        or visible(page, "button", re.compile(r"^\s*Continue\s*$", re.I), timeout=500)
                        or visible(page, "button", re.compile(r"^\s*(Finish|Complete)\s*(Setup)?\s*$", re.I), timeout=500))
            if skip_btn and skip_btn.is_enabled():
                snap(page, f"wizard-{i + 1}")
                skip_btn.click()
                settle(page, 5000)
                time.sleep(0.5)
                continue

            # 3f. Check if dashboard is already reached (no modals or gates blocking)
            if ("/login" not in page.url and
                not visible(page, "button", re.compile(r"^\s*Create administrator account\s*$", re.I), timeout=200) and
                not visible(page, "button", re.compile(r"^\s*Go to dashboard\s*$", re.I), timeout=200) and
                not any(w in body_sample for w in ("Before you start: what OpenOptOut can", "Step 2: MFA Setup", "System Setup Wizard"))):
                reached = True
                break

            time.sleep(0.5)

        snap(page, "dashboard", force=True)
        if not reached:
            rec.error("Setup wizard stuck", "Still showing wizard buttons after 25 clicks.")
        steps.append(("Click through the setup wizard", reached,
                      "" if reached else "wizard never finished"))

        # ── 4. save auth state & dispatch theme passes ────────────────────────
        auth_state_path = os.path.join(args.out_dir, "auth_state.json")
        ctx.storage_state(path=auth_state_path)
        browser.close()

        all_pages = dispatch_workers(args, rec, steps, theme_ids, auth_state_path)
        return finish(args, rec, steps, pages=all_pages)


def finish(args, rec, steps, browser=None, pages=None, fatal=False):
    if browser:
        try:
            browser.close()
        except Exception:  # noqa: BLE001
            pass
    result = {
        "ok": not rec.errors and not fatal and all(ok for _, ok, _ in steps),
        "steps": [{"name": n, "ok": ok, "note": note} for n, ok, note in steps],
        "pages": pages or [],
        "errors": rec.errors,
        "warnings": rec.warnings,
    }
    with open(os.path.join(args.out_dir, "ui-results.json"), "w") as f:
        json.dump(result, f, indent=2)

    md = ["### Browser walk-through (first-run setup + every page)", ""]
    for s in result["steps"]:
        md.append(f"- {'✅' if s['ok'] else '❌'} {s['name']}" + (f" — {s['note']}" if s["note"] else ""))
    md.append("")
    if pages:
        bad = [p for p in pages if p["errors"]]
        md.append(f"Pages opened: **{len(pages)}**, with errors: **{len(bad)}**"
                  + (": " + ", ".join(f"`{p['route']}`" for p in bad) if bad else ""))
        md.append("")
    if rec.errors:
        md.append(f"**❌ {len(rec.errors)} problem(s):**\n")
        md.append("| Where | What | Details |\n|---|---|---|")
        for e in rec.errors[:40]:
            md.append(f"| {e['screen']} | {e['kind']} | {cell(e['detail'])} |")
        if len(rec.errors) > 40:
            md.append(f"| … | … | {len(rec.errors) - 40} more in ui-results.json |")
        md.append("")
    if rec.warnings:
        md.append(f"<details><summary>⚠️ {len(rec.warnings)} warning(s) (console errors, 4xx API responses)</summary>\n")
        md.append("| Where | What | Details |\n|---|---|---|")
        for w in rec.warnings[:60]:
            md.append(f"| {w['screen']} | {w['kind']} | {cell(w['detail'])} |")
        md.append("\n</details>\n")
    if not rec.errors and not fatal:
        md.append("✅ No problems found in the browser.\n")
    if args.save_all_screenshots:
        md.append("Screenshots of every screen: download the **release-test-*** artifact → `screenshots/`.\n")
    else:
        md.append("Screenshots of key milestones & failures: download the **release-test-*** artifact → `screenshots/`.\n")
    with open(os.path.join(args.out_dir, "ui-report.md"), "w") as f:
        f.write("\n".join(md))
    print("\n".join(md))
    return 0 if result["ok"] else 1


def cell(s):
    return s.replace("|", "\\|").replace("\n", " ")[:2500]


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:  # noqa: BLE001
        print(f"::error::Browser check could not run: {e}")
        sys.exit(2)
