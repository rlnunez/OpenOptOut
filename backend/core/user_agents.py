"""
User-agent rotation for the automation engine.

A static user agent across thousands of form submissions is an easy
fingerprint for bot detection. This module provides a pool of current,
realistic UA strings and pairs each with a consistent viewport/platform
so the browser context is internally coherent.

IMPORTANT — honest limitations:
  UA rotation is ONE layer of evasion. Sophisticated bot detection also
  fingerprints TLS handshakes, canvas rendering, WebGL, timing patterns,
  and mouse movement. UA rotation combined with human-like delays and
  viewport variation raises the bar but does not defeat advanced systems.
  It is most effective against simple UA-based blocking.

Admins can extend the pool with custom UA strings via settings.
"""

import random
from typing import Optional

# ── Built-in pool of current, real user agents (updated for 2024) ─────────────
# Each entry pairs a UA with a matching platform and a plausible viewport.

BUILTIN_AGENTS = [
    # ── Chrome on Windows ──
    {
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "platform": "Windows", "viewport": {"width": 1920, "height": 1080},
    },
    {
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "platform": "Windows", "viewport": {"width": 1536, "height": 864},
    },
    {
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "platform": "Windows", "viewport": {"width": 1366, "height": 768},
    },
    # ── Chrome on macOS ──
    {
        "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "platform": "macOS", "viewport": {"width": 1440, "height": 900},
    },
    {
        "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "platform": "macOS", "viewport": {"width": 1512, "height": 982},
    },
    # ── Firefox on Windows ──
    {
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
        "platform": "Windows", "viewport": {"width": 1920, "height": 1080},
    },
    {
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
        "platform": "Windows", "viewport": {"width": 1366, "height": 768},
    },
    # ── Firefox on macOS ──
    {
        "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:125.0) Gecko/20100101 Firefox/125.0",
        "platform": "macOS", "viewport": {"width": 1440, "height": 900},
    },
    {
        "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:124.0) Gecko/20100101 Firefox/124.0",
        "platform": "macOS", "viewport": {"width": 1680, "height": 1050},
    },
    # ── Safari on macOS ──
    {
        "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
        "platform": "macOS", "viewport": {"width": 1440, "height": 900},
    },
    {
        "ua": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
        "platform": "macOS", "viewport": {"width": 1512, "height": 982},
    },
    # ── Edge on Windows ──
    {
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
        "platform": "Windows", "viewport": {"width": 1920, "height": 1080},
    },
    {
        "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
        "platform": "Windows", "viewport": {"width": 1536, "height": 864},
    },
    # ── Chrome on Linux ──
    {
        "ua": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "platform": "Linux", "viewport": {"width": 1920, "height": 1080},
    },
]


def get_random_agent(custom_uas: Optional[list] = None) -> dict:
    """
    Return a random user-agent profile: {ua, platform, viewport}.

    If custom_uas (a list of UA strings) is provided, they're mixed into
    the pool. Custom UAs get a generic desktop viewport since we can't
    reliably infer platform from an arbitrary string.
    """
    pool = list(BUILTIN_AGENTS)

    if custom_uas:
        for ua in custom_uas:
            if ua and ua.strip():
                pool.append({
                    "ua": ua.strip(),
                    "platform": _guess_platform(ua),
                    "viewport": random.choice([
                        {"width": 1920, "height": 1080},
                        {"width": 1366, "height": 768},
                        {"width": 1440, "height": 900},
                    ]),
                })

    return random.choice(pool)


def _guess_platform(ua: str) -> str:
    ua_lower = ua.lower()
    if "windows" in ua_lower:   return "Windows"
    if "macintosh" in ua_lower or "mac os" in ua_lower: return "macOS"
    if "linux" in ua_lower:     return "Linux"
    if "android" in ua_lower:   return "Linux"
    if "iphone" in ua_lower or "ipad" in ua_lower: return "iOS"
    return "Windows"


def get_custom_uas_from_settings() -> list:
    """Load admin-defined custom UA strings from settings."""
    try:
        from .settings_store import load_settings
        s = load_settings()
        return s.get("automation", {}).get("custom_user_agents", [])
    except Exception:
        return []


def rotation_enabled() -> bool:
    """Check whether UA rotation is enabled (default: True)."""
    try:
        from .settings_store import load_settings
        s = load_settings()
        return s.get("automation", {}).get("rotate_user_agents", True)
    except Exception:
        return True
