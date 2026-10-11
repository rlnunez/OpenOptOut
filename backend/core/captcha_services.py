"""
Settings for automatic CAPTCHA solving.

Solving services (2Captcha, Anti-Captcha, CapSolver, CapMonster) are reached
through the built-in "CAPTCHA solving service" plugin. Its account key is kept
here, encrypted, and handed only to that plugin, only while it's solving
(plugins/manager.dispatch_solve_captcha meta_for). What the service receives
is limited by core/captcha_privacy.py: a site key and a cleaned page address,
or a cropped, blacked-out picture of the puzzle, plus a job number.

settings["captcha"] = {
    "services": {plugin_id: {"service": "2captcha", "api_key_enc": "..."}}
}
Solving is on when the plugin is turned on (Plugins page) and has a key.
"""
from __future__ import annotations

from typing import Optional

SERVICES = {
    "2captcha":   {"label": "2Captcha",     "base": "https://api.2captcha.com"},
    "anticaptcha": {"label": "Anti-Captcha", "base": "https://api.anti-captcha.com"},
    "capsolver":  {"label": "CapSolver",    "base": "https://api.capsolver.com"},
    "capmonster": {"label": "CapMonster Cloud", "base": "https://api.capmonster.cloud"},
}
SERVICE_PLUGIN = "captcha-solving-service"


def settings_of(cfg: dict) -> dict:
    c = (cfg or {}).get("captcha") or {}
    return {"services": c.get("services") or {}}


def public(cfg: dict) -> dict:
    """What the admin page may show: never the key itself."""
    s = settings_of(cfg)
    return {"services": {pid: {"service": v.get("service"), "has_key": bool(v.get("api_key_enc"))}
                         for pid, v in s["services"].items()},
            "choices": {k: v["label"] for k, v in SERVICES.items()}}


def plugin_meta(plugin_id: str) -> dict:
    """Extras for one solver plugin's request: its own service and key, nothing else."""
    from .settings_store import load_settings
    s = settings_of(load_settings())
    conf = s["services"].get(plugin_id) or {}
    if not conf.get("api_key_enc") or conf.get("service") not in SERVICES:
        return {}
    from .oauth_engine import _decrypt
    return {"service": conf["service"], "api_key": _decrypt(conf["api_key_enc"]),
            "service_base": SERVICES[conf["service"]]["base"]}


def save_service(plugin_id: str, service: str, api_key: Optional[str]) -> dict:
    """Set the service and (when given) a new key for one solver plugin. An empty key clears it."""
    import json as _json
    from .settings_store import load_settings, SETTINGS_FILE
    from .oauth_engine import _encrypt
    if service not in SERVICES:
        raise ValueError("Choose one of the listed services.")
    cfg = load_settings()
    svc = cfg.setdefault("captcha", {}).setdefault("services", {}).setdefault(plugin_id, {})
    svc["service"] = service
    if api_key is not None:
        if api_key.strip():
            svc["api_key_enc"] = _encrypt(api_key.strip())
        else:
            svc.pop("api_key_enc", None)
    with open(SETTINGS_FILE, "w") as f:
        _json.dump(cfg, f, indent=2)
    return public(cfg)
