"""
Host-side OAuth engine for email providers.

The hybrid design: an email-provider PLUGIN describes its OAuth flow (auth URL,
token URL, scopes, PKCE) via EmailProviderInfo. The HOST — this module — executes
that flow: it holds the operator-registered client_id/client_secret, runs the
redirect/consent/token-exchange, and stores the resulting tokens ENCRYPTED. The
sensitive material (client secret, access/refresh tokens) NEVER passes through
the sandboxed plugin. At send time the host hands the plugin only a live access
token (via settings.get("email_credentials:{account_ref}")).

Why the split: making a plugin a "trusted class" to SEND an opt-out is very
different from trusting sandboxed third-party code to hold the OAuth client
secret and mint mailbox-access tokens (a stolen refresh token = standing access
to someone's entire inbox). So the provider's OAuth *knowledge* lives in the
plugin (declarative, extensible), but the *secrets and execution* stay in the host.

This module is pure logic (URL building, token exchange, encrypted storage) and
is unit-testable without a browser. The actual redirect happens in the router
that calls begin_authorization() / complete_authorization().
"""

import base64
import hashlib
import json
import os
import secrets
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Optional


# ── Encryption (same scheme as settings) ──────────────────────────────────────

def _fernet():
    from cryptography.fernet import Fernet
    from .settings_store import get_secret_key
    raw = get_secret_key()
    padded = (raw * 4)[:32].encode()
    return Fernet(base64.urlsafe_b64encode(padded))


def _encrypt(s: str) -> str:
    return _fernet().encrypt(s.encode()).decode() if s else ""


def _decrypt(s: str) -> str:
    try:
        return _fernet().decrypt(s.encode()).decode()
    except Exception:
        return ""


# ── Flow description (from the plugin) + operator client credentials ──────────

@dataclass
class OAuthFlowDesc:
    """What the plugin declares about its OAuth flow (no secrets here)."""
    provider_key: str
    auth_url: str
    token_url: str
    scopes: str
    use_pkce: bool = False
    extra_params: str = ""     # "k=v&k=v"


@dataclass
class OAuthClient:
    """Operator-registered client credentials (held by the HOST, encrypted).
    The client_secret NEVER leaves the host / never goes to a plugin."""
    client_id: str
    client_secret: str
    redirect_uri: str


@dataclass
class PendingAuth:
    """Transient state for an in-progress authorization (host-side only)."""
    state: str
    account_ref: str
    provider_key: str
    code_verifier: str = ""     # for PKCE
    created_at: float = field(default_factory=time.time)


# ── PKCE helpers ──────────────────────────────────────────────────────────────

def _pkce_pair():
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(40)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


# ── Begin: build the authorization URL the operator is redirected to ──────────

def begin_authorization(flow: "OAuthFlowDesc", client: "OAuthClient",
                        account_ref: str) -> tuple[str, "PendingAuth"]:
    """
    Build the consent URL. Returns (auth_url, pending) — the caller redirects the
    operator to auth_url and stashes `pending` (keyed by its state) to correlate
    the callback. No secrets are in the URL (only client_id, which is not secret).
    """
    state = secrets.token_urlsafe(24)
    params = {
        "client_id": client.client_id,
        "redirect_uri": client.redirect_uri,
        "response_type": "code",
        "scope": flow.scopes,
        "state": state,
        "access_type": "offline",     # ask for a refresh token (Google)
        "prompt": "consent",
    }
    pending = PendingAuth(state=state, account_ref=account_ref,
                          provider_key=flow.provider_key)
    if flow.use_pkce:
        verifier, challenge = _pkce_pair()
        pending.code_verifier = verifier
        params["code_challenge"] = challenge
        params["code_challenge_method"] = "S256"
    # Provider-specific extras (e.g. Microsoft tenant).
    for kv in (flow.extra_params or "").split("&"):
        if "=" in kv:
            k, v = kv.split("=", 1)
            params[k] = v
    url = flow.auth_url + "?" + urllib.parse.urlencode(params)
    return url, pending


# ── Complete: exchange the code for tokens, store them encrypted ──────────────

def exchange_code(flow: "OAuthFlowDesc", client: "OAuthClient",
                  pending: "PendingAuth", code: str, http_post=None) -> dict:
    """
    Exchange the authorization code for tokens. `http_post` is injected for
    testability; defaults to httpx. Returns the token dict (access_token,
    refresh_token, expiry). Raises on failure.
    """
    data = {
        "client_id": client.client_id,
        "client_secret": client.client_secret,   # HOST-only secret
        "code": code,
        "redirect_uri": client.redirect_uri,
        "grant_type": "authorization_code",
    }
    if pending.code_verifier:
        data["code_verifier"] = pending.code_verifier
    resp = (http_post or _default_post)(flow.token_url, data)
    if resp.get("error"):
        raise RuntimeError(f"token exchange failed: {resp.get('error')}: "
                           f"{resp.get('error_description', '')}")
    return _normalize_tokens(resp, flow, client)


def refresh_token(flow: "OAuthFlowDesc", client: "OAuthClient",
                  refresh: str, http_post=None) -> dict:
    """Refresh an access token using the stored refresh token."""
    data = {
        "client_id": client.client_id,
        "client_secret": client.client_secret,
        "refresh_token": refresh,
        "grant_type": "refresh_token",
    }
    resp = (http_post or _default_post)(flow.token_url, data)
    if resp.get("error"):
        raise RuntimeError(f"token refresh failed: {resp.get('error')}")
    toks = _normalize_tokens(resp, flow, client)
    # Providers often don't return a new refresh token on refresh; keep the old.
    if not toks.get("refresh_token"):
        toks["refresh_token"] = refresh
    return toks


def _normalize_tokens(resp: dict, flow, client) -> dict:
    now = int(time.time())
    return {
        "access_token": resp.get("access_token", ""),
        "refresh_token": resp.get("refresh_token", ""),
        "expires_at": now + int(resp.get("expires_in", 3600)),
        "scopes": flow.scopes,
        "client_id": client.client_id,
        "client_secret": client.client_secret,   # stored ENCRYPTED (see store_tokens)
        "provider_key": flow.provider_key,
    }


def _default_post(url: str, data: dict) -> dict:
    import httpx
    r = httpx.post(url, data=data, headers={"Accept": "application/json"}, timeout=25)
    try:
        return r.json()
    except Exception:
        return {"error": f"http {r.status_code}", "error_description": r.text[:200]}


# ── Storage: tokens encrypted at email_credentials:{account_ref} ──────────────

def store_tokens(settings: dict, account_ref: str, tokens: dict) -> dict:
    """
    Store the token bundle ENCRYPTED in the settings dict under
    email_credentials:{account_ref}. The plugin later reads the DECRYPTED bundle
    at send time via the host's settings accessor (which decrypts for it). The
    raw secrets are never written in plaintext.
    """
    creds = settings.setdefault("email_credentials", {})
    creds[account_ref] = _encrypt(json.dumps(tokens))
    return settings


def load_tokens(settings: dict, account_ref: str) -> Optional[dict]:
    enc = (settings.get("email_credentials") or {}).get(account_ref)
    if not enc:
        return None
    raw = _decrypt(enc)
    return json.loads(raw) if raw else None


def is_expired(tokens: dict, skew: int = 120) -> bool:
    return int(tokens.get("expires_at", 0)) - skew <= int(time.time())
