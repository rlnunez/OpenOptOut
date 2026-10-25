"""
W3C Global Privacy Control (GPC) Implementation.

Global Privacy Control (GPC) is a standardized mechanism (W3C Privacy Community
Group specification) allowing consumers to signal their privacy preferences,
specifically the universal opt-out of personal data sale, sharing, and targeted
advertising across online data brokers and platforms.

Under California Consumer Privacy Act / CPRA (11 CCR § 7025) and Colorado Privacy
Act (4 CCR 904-3 Rule 5.06), data brokers and covered businesses are legally
required to recognize and honor GPC signals as valid consumer opt-out requests.

This module provides:
1. HTTP header constants (Sec-GPC: 1, DNT: 1) for outbound requests.
2. Context header injection for Playwright and API clients.
3. DOM init scripts setting `navigator.globalPrivacyControl = true`.
4. Well-known resource generator for `/.well-known/gpc.json`.
"""

import logging
from typing import Optional, Dict, Any

log = logging.getLogger("core.gpc")

# W3C GPC standard header and value
GPC_HEADER = "Sec-GPC"
GPC_VALUE = "1"

# Legacy Do Not Track header for paired compatibility
DNT_HEADER = "DNT"
DNT_VALUE = "1"

# Extra HTTP headers dict to merge into network requests
GPC_EXTRA_HEADERS: Dict[str, str] = {
    GPC_HEADER: GPC_VALUE,
    DNT_HEADER: DNT_VALUE,
}

# Standard DOM script setting navigator.globalPrivacyControl = true
# Defined as non-writable, non-configurable, enumerable to reflect user agent state
GPC_DOM_SCRIPT = (
    "try {"
    "  if (typeof navigator !== 'undefined') {"
    "    Object.defineProperty(navigator, 'globalPrivacyControl', {"
    "      value: true,"
    "      writable: false,"
    "      configurable: false,"
    "      enumerable: true"
    "    });"
    "  }"
    "} catch (e) {}"
)


def apply_gpc_headers(ctx_args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Ensure ctx_args includes Sec-GPC: 1 and DNT: 1 in extra_http_headers.
    Creates or updates the 'extra_http_headers' key safely.
    """
    args = dict(ctx_args or {})
    headers = dict(args.get("extra_http_headers") or {})
    headers[GPC_HEADER] = GPC_VALUE
    headers[DNT_HEADER] = DNT_VALUE
    args["extra_http_headers"] = headers
    return args


async def apply_gpc_to_context(context: Any) -> None:
    """
    Inject the GPC DOM property initialization script into a Playwright browser context.
    Ensures navigator.globalPrivacyControl is true on every frame and page.
    """
    if context is None:
        return
    try:
        add_init_script = getattr(context, "add_init_script", None)
        if callable(add_init_script):
            await add_init_script(GPC_DOM_SCRIPT)
    except Exception as e:
        log.debug("Failed to apply GPC init script to context: %s", e)


def gpc_well_known_document() -> Dict[str, Any]:
    """
    Return the standard W3C GPC well-known document content for /.well-known/gpc.json.
    Per W3C GPC specification section 4 (The Well-Known Resource).
    """
    return {
        "gpc": True,
        "lastUpdate": "2026-10-24",
    }
