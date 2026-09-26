"""
Proxy management for the automation engine.

IP masking is the single most impactful bot-evasion measure — brokers track
and block primarily by IP. This module routes Playwright browser contexts
through proxies, supporting:

  - Single proxy (one IP for everything)
  - Rotating pool (different proxy/IP per broker)
  - Provider presets (Bright Data, Oxylabs, Smartproxy/Decodo, IPRoyal) + generic

SECURITY MODEL (same as db_connection.py):
  Non-secret config (mode, provider, host, port) may live in settings.
  SECRET material (usernames, passwords) is resolved ONLY from environment
  variables or mounted files controlled by the operator — never stored in
  the app database or settings, never logged.

LEGITIMACY NOTE:
  Submitting opt-out requests is lawful. Use reputable proxy providers that
  source residential IPs from *consented* networks. Avoid providers known to
  use malware-sourced IPs. This module is provider-agnostic by design.

Playwright accepts proxies per browser context:
  context = await browser.new_context(proxy={
      "server": "http://host:port",
      "username": "...",
      "password": "...",
  })
"""

import os
import random
import logging
from typing import Optional
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class ProxyProfile:
    """A resolved proxy ready to hand to Playwright."""
    server:   str                 # e.g. "http://gate.provider.com:7000"
    username: Optional[str] = None
    password: Optional[str] = None
    label:    str = ""            # for logging (never includes credentials)

    def to_playwright(self) -> dict:
        p = {"server": self.server}
        if self.username:
            p["username"] = self.username
        if self.password:
            p["password"] = self.password
        return p


# ── Provider presets ──────────────────────────────────────────────────────────
# Presets encode the connection endpoint format for major residential proxy
# providers. The operator supplies credentials via env/files; these just make
# the host/port easy to fill in correctly.

PROXY_PRESETS = {
    "generic": {
        "label": "Generic / custom proxy",
        "scheme": "http",
        "note": "Works with any HTTP/HTTPS/SOCKS5 proxy. Enter host and port; supply credentials via environment variables.",
        "default_port": 8080,
    },
    "brightdata": {
        "label": "Bright Data",
        "scheme": "http",
        "host_hint": "brd.superproxy.io",
        "default_port": 22225,
        "note": "Bright Data residential proxies. Username format: brd-customer-<id>-zone-<zone>. Rotating IPs are automatic per request on their gateway. Supply BRIGHTDATA_USER / BRIGHTDATA_PASS via env.",
        "env_user": "BRIGHTDATA_USER",
        "env_pass": "BRIGHTDATA_PASS",
    },
    "oxylabs": {
        "label": "Oxylabs",
        "scheme": "http",
        "host_hint": "pr.oxylabs.io",
        "default_port": 7777,
        "note": "Oxylabs residential proxies. Username format: customer-<user>-cc-<country>. Supply OXYLABS_USER / OXYLABS_PASS via env.",
        "env_user": "OXYLABS_USER",
        "env_pass": "OXYLABS_PASS",
    },
    "smartproxy": {
        "label": "Smartproxy / Decodo",
        "scheme": "http",
        "host_hint": "gate.smartproxy.com",
        "default_port": 7000,
        "note": "Smartproxy (now Decodo) residential proxies. Endpoint gate.smartproxy.com:7000 rotates IP per request; use :10000+ for sticky sessions. Supply SMARTPROXY_USER / SMARTPROXY_PASS via env.",
        "env_user": "SMARTPROXY_USER",
        "env_pass": "SMARTPROXY_PASS",
    },
    "iproyal": {
        "label": "IPRoyal",
        "scheme": "http",
        "host_hint": "geo.iproyal.com",
        "default_port": 12321,
        "note": "IPRoyal royal residential proxies. Supports sticky sessions via username suffix. Supply IPROYAL_USER / IPROYAL_PASS via env.",
        "env_user": "IPROYAL_USER",
        "env_pass": "IPROYAL_PASS",
    },
}


# ── Secret resolution (env / mounted files only) ──────────────────────────────

def _resolve_secret(env_var: Optional[str], file_path: Optional[str]) -> Optional[str]:
    """
    Resolve a proxy credential from an environment variable or a mounted file.
    Never logs the value. Returns None if neither is available.
    """
    if env_var and os.getenv(env_var):
        return os.getenv(env_var)
    if file_path and os.path.exists(file_path):
        try:
            with open(file_path, "r") as f:
                return f.read().strip()
        except Exception as e:
            log.error(f"Could not read proxy secret file {file_path}: {e}")
    return None


# ── Config loading ────────────────────────────────────────────────────────────

def _proxy_config() -> dict:
    try:
        from .settings_store import load_settings
        return load_settings().get("proxy", {})
    except Exception:
        return {}


def proxy_enabled() -> bool:
    # Env override takes precedence, then settings
    env = os.getenv("PROXY_ENABLED")
    if env is not None:
        return env.lower() in ("1", "true", "yes")
    return _proxy_config().get("enabled", False)


def _resolve_single_proxy(cfg: dict) -> Optional[ProxyProfile]:
    """
    Build a single ProxyProfile from config.

    Non-secret (from settings or env): provider, host, port, scheme.
    Secret (env/files only): username, password.
    """
    provider = cfg.get("provider", "generic")
    preset   = PROXY_PRESETS.get(provider, PROXY_PRESETS["generic"])

    scheme = cfg.get("scheme") or preset.get("scheme", "http")
    host   = os.getenv("PROXY_HOST") or cfg.get("host") or preset.get("host_hint")
    port   = os.getenv("PROXY_PORT") or cfg.get("port") or preset.get("default_port")

    if not host or not port:
        log.warning("Proxy enabled but no host/port configured")
        return None

    # Credentials: prefer provider-specific env vars from the preset,
    # then generic PROXY_USER / PROXY_PASS, then mounted files.
    user = None
    password = None

    if preset.get("env_user"):
        user     = _resolve_secret(preset["env_user"], None)
        password = _resolve_secret(preset["env_pass"], None)

    if not user:
        user = _resolve_secret("PROXY_USER", os.getenv("PROXY_USER_FILE"))
    if not password:
        password = _resolve_secret("PROXY_PASS", os.getenv("PROXY_PASS_FILE"))

    server = f"{scheme}://{host}:{port}"
    return ProxyProfile(
        server=server, username=user, password=password,
        label=f"{provider}:{host}:{port}",
    )


def _resolve_pool() -> list[ProxyProfile]:
    """
    Build a list of ProxyProfiles for rotation.

    The pool is defined as a newline- or comma-separated list in the
    PROXY_POOL env var or a mounted file (PROXY_POOL_FILE). Each entry is
    a full proxy URL, optionally with inline credentials:
        http://user:pass@host:port
        http://host:port           (credentials from PROXY_USER/PROXY_PASS)

    Keeping the pool in env/files (not settings) keeps credentials out of
    the app database.
    """
    raw = os.getenv("PROXY_POOL")
    pool_file = os.getenv("PROXY_POOL_FILE")
    if not raw and pool_file and os.path.exists(pool_file):
        try:
            with open(pool_file) as f:
                raw = f.read()
        except Exception as e:
            log.error(f"Could not read PROXY_POOL_FILE: {e}")
            return []

    if not raw:
        return []

    # Split on newlines or commas
    entries = [e.strip() for e in raw.replace(",", "\n").splitlines() if e.strip()]
    shared_user = _resolve_secret("PROXY_USER", os.getenv("PROXY_USER_FILE"))
    shared_pass = _resolve_secret("PROXY_PASS", os.getenv("PROXY_PASS_FILE"))

    profiles = []
    for entry in entries:
        profiles.append(_parse_proxy_url(entry, shared_user, shared_pass))
    log.info(f"Loaded proxy pool: {len(profiles)} proxies")
    return profiles


def _parse_proxy_url(url: str, shared_user, shared_pass) -> ProxyProfile:
    """Parse a proxy URL that may contain inline credentials."""
    from urllib.parse import urlparse
    if "://" not in url:
        url = "http://" + url
    parsed = urlparse(url)
    user = parsed.username or shared_user
    password = parsed.password or shared_pass
    server = f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"
    # Label without credentials
    return ProxyProfile(server=server, username=user, password=password,
                        label=f"{parsed.hostname}:{parsed.port}")


# ── Public API ────────────────────────────────────────────────────────────────

# Cache the pool so we don't re-read files on every call
_pool_cache: Optional[list] = None


def get_proxy_for_context() -> Optional[dict]:
    """
    Return a Playwright-ready proxy dict for a new browser context, or None
    if proxying is disabled/unconfigured.

    Respects the configured mode:
      - "single": always the same proxy
      - "pool":   a random proxy from the rotating pool (different IP per call)
    """
    global _pool_cache

    if not proxy_enabled():
        return None

    cfg  = _proxy_config()
    mode = cfg.get("mode", "single")

    if mode == "pool":
        if _pool_cache is None:
            _pool_cache = _resolve_pool()
        if not _pool_cache:
            log.warning("Proxy mode=pool but pool is empty — check PROXY_POOL / PROXY_POOL_FILE")
            # Fall back to single if a single proxy is also configured
            single = _resolve_single_proxy(cfg)
            return single.to_playwright() if single else None
        chosen = random.choice(_pool_cache)
        log.debug(f"Proxy (pool): {chosen.label}")
        return chosen.to_playwright()

    # single
    single = _resolve_single_proxy(cfg)
    if not single:
        return None
    log.debug(f"Proxy (single): {single.label}")
    return single.to_playwright()


def clear_pool_cache():
    """Call after settings/env changes to force a pool reload."""
    global _pool_cache
    _pool_cache = None


def get_proxy_status() -> dict:
    """
    Report proxy configuration status WITHOUT exposing credentials.
    Used by the admin UI.
    """
    cfg     = _proxy_config()
    enabled = proxy_enabled()
    mode    = cfg.get("mode", "single")
    provider = cfg.get("provider", "generic")
    preset  = PROXY_PRESETS.get(provider, {})

    # Detect whether credentials are resolvable (without revealing them)
    cred_user = None
    cred_pass = None
    if preset.get("env_user"):
        cred_user = bool(os.getenv(preset["env_user"]))
        cred_pass = bool(os.getenv(preset["env_pass"]))
    if not cred_user:
        cred_user = bool(os.getenv("PROXY_USER") or (os.getenv("PROXY_USER_FILE") and os.path.exists(os.getenv("PROXY_USER_FILE", ""))))
    if not cred_pass:
        cred_pass = bool(os.getenv("PROXY_PASS") or (os.getenv("PROXY_PASS_FILE") and os.path.exists(os.getenv("PROXY_PASS_FILE", ""))))

    pool_size = 0
    if mode == "pool":
        pool_size = len(_resolve_pool())

    host = os.getenv("PROXY_HOST") or cfg.get("host") or preset.get("host_hint")
    port = os.getenv("PROXY_PORT") or cfg.get("port") or preset.get("default_port")

    return {
        "enabled":       enabled,
        "mode":          mode,
        "provider":      provider,
        "host":          host,
        "port":          port,
        "creds_user_set": bool(cred_user),
        "creds_pass_set": bool(cred_pass),
        "pool_size":     pool_size,
        "pool_env_set":  bool(os.getenv("PROXY_POOL") or os.getenv("PROXY_POOL_FILE")),
    }


async def test_proxy(playwright) -> dict:
    """
    Test the configured proxy by fetching an IP-echo service through it.
    Returns the exit IP so the admin can confirm masking works.
    Never returns credentials.
    """
    proxy = get_proxy_for_context()
    if not proxy:
        return {"ok": False, "error": "Proxy not enabled or not configured"}

    browser = None
    try:
        browser = await playwright.firefox.launch(headless=True)
        context = await browser.new_context(proxy=proxy)
        page = await context.new_page()
        # Use a neutral IP-echo endpoint
        await page.goto("https://api.ipify.org?format=json", timeout=20000)
        content = await page.content()
        import re, json as _json
        match = re.search(r'\{.*\}', content)
        exit_ip = None
        if match:
            try:
                exit_ip = _json.loads(match.group(0)).get("ip")
            except Exception:
                pass
        await context.close()
        return {"ok": True, "exit_ip": exit_ip,
                "message": f"Traffic is exiting via {exit_ip}" if exit_ip else "Connected through proxy"}
    except Exception as e:
        err = str(e)
        # Sanitize — never echo credentials
        for marker in ("password", "@"):
            if marker in err:
                err = "Proxy connection failed (check host, port, and credentials)"
                break
        return {"ok": False, "error": err}
    finally:
        if browser:
            await browser.close()
