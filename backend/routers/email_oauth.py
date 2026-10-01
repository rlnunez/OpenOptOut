"""
Email OAuth connect flow (host-side execution).

Endpoints the operator uses to connect an OAuth email account (Gmail, Outlook,
Yahoo, or any provider whose plugin describes an OAuth flow):

  POST /api/email-oauth/client   — store the operator's registered client_id +
                                    client_secret for a provider (encrypted).
  POST /api/email-oauth/begin    — start authorization; returns the consent URL
                                    to redirect the operator to.
  GET  /api/email-oauth/callback — provider redirects here with ?code&state; the
                                    host exchanges the code for tokens and stores
                                    them encrypted. The plugin never sees secrets.

The plugin describes the flow (auth/token URLs, scopes) via EmailProviderInfo;
this router asks the running plugin for that description, then the host executes
it with the operator's client credentials. See core/oauth_engine.py.
"""

import html
import json
import os
import time
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from ..models.database import get_db, User
from ..core.auth import get_current_user
from ..core.settings_store import load_settings, SETTINGS_FILE
from ..core import oauth_engine as oe

router = APIRouter(prefix="/api/email-oauth", tags=["email-oauth"])

# In-memory pending-auth store (state -> PendingAuth). Short-lived; fine for a
# single-process host. A multi-process deployment would move this to the DB.
_PENDING: dict = {}


def _admin(user: User):
    from ..core.access import has_permission, PERMISSIONS
    if not has_permission(user, "email.manage"):
        raise HTTPException(403, f"This needs the '{PERMISSIONS['email.manage']['label']}' permission")


def _save(data: dict):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def _provider_flow(provider_key: str) -> oe.OAuthFlowDesc:
    """
    Ask the running email-provider plugin to describe its OAuth flow. Falls back
    to built-in descriptions for the bundled providers if the plugin isn't
    queryable (e.g. not running). The plugin DESCRIBES; the host executes.
    """
    # Try the live plugin first.
    try:
        from ..plugins import get_manager
        mgr = get_manager()
        if mgr:
            info = mgr.dispatch_email_provider_info(provider_key)  # returns dict or None
            # Require BOTH URLs to be present and non-empty before trusting this
            # over the builtin fallback below — a plugin (bundled or, someday,
            # third-party) that declares auth_type: oauth without actually
            # filling in oauth_auth_url/oauth_token_url would otherwise hand
            # back an OAuthFlowDesc with an empty token_url, and the request
            # library's own error for that ("Request URL is missing an
            # 'http://' or 'https://' protocol") gives no hint that the real
            # problem is upstream in the plugin's own self-description, not
            # in the connect/refresh code trying to use it. Falling through
            # here instead means a plugin with incomplete info degrades to
            # the same behavior as a plugin that isn't running at all, rather
            # than actively breaking a provider the host has a good built-in
            # answer for anyway.
            if (info and info.get("auth_type") == "oauth"
                    and info.get("oauth_auth_url") and info.get("oauth_token_url")):
                return oe.OAuthFlowDesc(
                    provider_key=provider_key,
                    auth_url=info.get("oauth_auth_url", ""),
                    token_url=info.get("oauth_token_url", ""),
                    scopes=info.get("oauth_scopes", ""),
                    use_pkce=bool(info.get("oauth_use_pkce", False)),
                    extra_params=info.get("oauth_extra_params", ""),
                )
    except Exception:
        pass
    # Built-in fallbacks for the bundled providers.
    builtins = {
        "gmail": oe.OAuthFlowDesc(
            "gmail",
            "https://accounts.google.com/o/oauth2/v2/auth",
            "https://oauth2.googleapis.com/token",
            "https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/gmail.readonly",
            use_pkce=True),
        "outlook": oe.OAuthFlowDesc(
            "outlook",
            "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
            "https://login.microsoftonline.com/common/oauth2/v2.0/token",
            "https://graph.microsoft.com/Mail.Send https://graph.microsoft.com/Mail.Read offline_access",
            use_pkce=True),
        "yahoo": oe.OAuthFlowDesc(
            "yahoo",
            "https://api.login.yahoo.com/oauth2/request_auth",
            "https://api.login.yahoo.com/oauth2/get_token",
            "mail-w", use_pkce=False),
    }
    flow = builtins.get(provider_key)
    if not flow:
        raise HTTPException(400, f"No OAuth flow available for provider '{provider_key}' "
                                 "(the plugin must describe one, or it's app-password only)")
    return flow


def _client(settings: dict, provider_key: str) -> oe.OAuthClient:
    store = (settings.get("oauth_clients") or {}).get(provider_key)
    if not store:
        raise HTTPException(400, f"No OAuth client registered for '{provider_key}'. "
                                 "Register the client_id/client_secret first.")
    return oe.OAuthClient(
        client_id=store.get("client_id", ""),
        client_secret=oe._decrypt(store.get("client_secret_enc", "")),
        redirect_uri=store.get("redirect_uri", ""),
    )


# ── Register the operator's OAuth client credentials ──────────────────────────

class ClientIn(BaseModel):
    provider_key: str
    client_id: str
    client_secret: str
    redirect_uri: str


@router.post("/client")
def set_client(body: ClientIn, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """Store the operator's registered OAuth client for a provider. The secret is
    encrypted and held HOST-side only — it is never given to any plugin."""
    _admin(user)
    s = load_settings()
    clients = s.setdefault("oauth_clients", {})
    clients[body.provider_key] = {
        "client_id": body.client_id.strip(),
        "client_secret_enc": oe._encrypt(body.client_secret),
        "redirect_uri": body.redirect_uri.strip(),
    }
    _save(s)
    return {"ok": True, "provider_key": body.provider_key}


# ── Begin authorization ───────────────────────────────────────────────────────

class BeginIn(BaseModel):
    provider_key: str
    account_ref: str = "default"


@router.post("/begin")
def begin(body: BeginIn, db: Session = Depends(get_db),
          user: User = Depends(get_current_user)):
    """Start the OAuth flow. Returns the consent URL to send the operator to."""
    _admin(user)
    s = load_settings()
    flow = _provider_flow(body.provider_key)
    client = _client(s, body.provider_key)
    if not flow.auth_url or not flow.token_url:
        raise HTTPException(400, "provider did not describe auth/token URLs")
    url, pending = oe.begin_authorization(flow, client, body.account_ref)
    _PENDING[pending.state] = pending
    return {"authorize_url": url, "state": pending.state}


# ── Callback: exchange code, store tokens ─────────────────────────────────────

@router.get("/callback", response_class=HTMLResponse)
def callback(code: Optional[str] = Query(None), state: Optional[str] = Query(None),
             error: Optional[str] = Query(None), db: Session = Depends(get_db)):
    """
    Provider redirects here after consent. The host exchanges the code for tokens
    (using the HOST-held client secret) and stores them encrypted. No auth
    dependency here because the provider (not the operator's browser session)
    initiates the redirect — the `state` parameter is the CSRF guard.
    """
    if error:
        safe_error = html.escape(error, quote=True)
        return HTMLResponse(f"<p>Authorization failed: {safe_error}</p>", status_code=400)
    if not code or not state or state not in _PENDING:
        return HTMLResponse("<p>Invalid or expired authorization state.</p>", status_code=400)

    pending = _PENDING.pop(state)
    s = load_settings()
    flow = _provider_flow(pending.provider_key)
    client = _client(s, pending.provider_key)
    try:
        tokens = oe.exchange_code(flow, client, pending, code)
    except Exception as e:
        safe_err = html.escape(str(e), quote=True)
        return HTMLResponse(f"<p>Token exchange failed: {safe_err}</p>", status_code=400)

    oe.store_tokens(s, pending.account_ref, tokens)
    # Keep settings["email"]["provider"] in sync with whichever account is
    # actually active — that field is what send_email() checks to decide
    # whether to even ATTEMPT the provider path at all. Without this, an
    # account connected from anywhere other than the setup wizard (e.g. the
    # Settings page's "Connect another account", added after the wizard was
    # the only place this got set) leaves provider empty, and every send
    # silently skips straight to SMTP — which was never configured — instead
    # of using the very account that just finished connecting.
    email = s.setdefault("email", {})
    active = email.get("active_account_ref") or "default"
    if pending.account_ref == active or not email.get("provider"):
        email["provider"] = pending.provider_key
    _save(s)
    return HTMLResponse(
        "<html><body style='font-family:sans-serif;background:#0f172a;color:#e2e8f0;"
        "padding:2rem'><h2>✓ Email account connected</h2>"
        "<p>You can close this window and return to OpenOptOut.</p></body></html>")


# ── Status ────────────────────────────────────────────────────────────────────

@router.get("/status")
def status(account_ref: str = Query("default"), db: Session = Depends(get_db),
           user: User = Depends(get_current_user)):
    """Whether an account is connected, and whether its token needs refresh."""
    _admin(user)
    s = load_settings()
    toks = oe.load_tokens(s, account_ref)
    if not toks:
        return {"connected": False}
    return {
        "connected": True,
        "provider_key": toks.get("provider_key", ""),
        "expired": oe.is_expired(toks),
        "scopes": toks.get("scopes", ""),
    }


# ── Multiple connected accounts (e.g. for testing) ─────────────────────────────
# Every connect goes through the SAME begin/callback flow above with a
# different account_ref — "default" isn't special except as the fallback
# active one. These endpoints just make the accounts that ends up producing
# visible and switchable, instead of only ever the one hardcoded account_ref
# the wizard happens to use.

def active_account_ref(settings: dict) -> str:
    """The account_ref actual shared/admin sends use — core/optout_engine.py
    reads this instead of hardcoding 'default', so switching here takes
    effect on the next send with no other changes needed."""
    return (settings.get("email", {}) or {}).get("active_account_ref") or "default"


@router.get("/accounts")
def list_accounts(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Every connected OAuth account (any account_ref with stored tokens), and
    which one is currently active for the shared/admin send path."""
    _admin(user)
    s = load_settings()
    active = active_account_ref(s)
    out = []
    for ref in (s.get("email_credentials") or {}).keys():
        toks = oe.load_tokens(s, ref)
        if not toks:
            continue
        out.append({
            "account_ref": ref,
            "provider_key": toks.get("provider_key", ""),
            "expired": oe.is_expired(toks),
            "active": ref == active,
        })
    out.sort(key=lambda a: (not a["active"], a["account_ref"]))
    return {"accounts": out, "active_account_ref": active}


@router.post("/accounts/{account_ref}/activate")
def activate_account(account_ref: str, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    """Make account_ref the one the shared/admin send path uses."""
    _admin(user)
    s = load_settings()
    toks = oe.load_tokens(s, account_ref)
    if not toks:
        raise HTTPException(404, f"No connected account '{account_ref}'")
    email = s.setdefault("email", {})
    email["active_account_ref"] = account_ref
    # Keep provider in sync with whichever account is now active — switching
    # to a different account (e.g. an Outlook one after a Gmail one) must
    # switch which plugin send_email() actually tries, not just which token
    # gets used once it gets there.
    email["provider"] = toks.get("provider_key") or email.get("provider")
    _save(s)
    return {"ok": True, "active_account_ref": account_ref, "provider": email["provider"]}


@router.delete("/accounts/{account_ref}", status_code=204)
def disconnect_account(account_ref: str, db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    """Forget a connected account's tokens. If it was the active one, falls
    back to whatever else is left connected (or plain "default" — meaningless
    once nothing is stored there — if nothing else is left)."""
    _admin(user)
    s = load_settings()
    creds = s.get("email_credentials") or {}
    if account_ref not in creds:
        raise HTTPException(404, f"No connected account '{account_ref}'")
    creds.pop(account_ref, None)
    s["email_credentials"] = creds
    email = s.setdefault("email", {})
    if email.get("active_account_ref", "default") == account_ref:
        email["active_account_ref"] = next(iter(creds.keys()), "default")
    _save(s)
