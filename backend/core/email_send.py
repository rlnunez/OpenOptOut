"""
Unified email send.

One function the opt-out engine calls to send an email, regardless of transport.
It routes to whichever email provider is configured:

  - If an email PROVIDER plugin is configured (Gmail/Outlook/Yahoo/custom), send
    through it via the plugin manager. Before sending, if the account's OAuth
    token is expired, REFRESH it host-side and store the new token — so sends
    don't fail on a stale token. The host supplies the recipient list and the
    manager enforces it (a provider can't add a hidden recipient at runtime).

  - Otherwise, fall back to direct SMTP using the configured account (the
    existing behavior), so deployments without a provider plugin still work.

This keeps the opt-out engine transport-agnostic: it says "send this," and this
module figures out how.
"""

import json
import logging
import os
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

log = logging.getLogger(__name__)


def _refresh_if_needed(settings: dict, account_ref: str, provider_key: str):
    """
    If the stored OAuth token for account_ref is expired, refresh it host-side
    and persist the new token. Returns True if a usable token exists after this.
    App-password / SMTP accounts have no token to refresh — returns True (nothing
    to do). Never raises.
    """
    try:
        from . import oauth_engine as oe
        toks = oe.load_tokens(settings, account_ref)
        if not toks or not toks.get("refresh_token"):
            return True  # nothing to refresh (app-password or not-yet-connected)
        if not oe.is_expired(toks):
            return True
        # Rebuild the flow description + client to refresh.
        from ..routers.email_oauth import _provider_flow, _client  # reuse resolution
        flow = _provider_flow(provider_key or toks.get("provider_key", ""))
        client = oe.OAuthClient(
            client_id=toks.get("client_id", ""),
            client_secret=toks.get("client_secret", ""),
            redirect_uri="",
        )
        new = oe.refresh_token(flow, client, toks["refresh_token"])
        oe.store_tokens(settings, account_ref, new)
        # Persist the refreshed token.
        from .settings_store import SETTINGS_FILE
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=2)
        # nosemgrep: python-logger-credential-disclosure -- logs account label, not token secret
        log.info("Refreshed OAuth token for account '%s'", account_ref)
        return True
    except Exception as e:
        # nosemgrep: python-logger-credential-disclosure -- logs account label, not token secret
        log.error("token refresh failed for '%s': %s", account_ref, e)
        return False


def send_email(cfg: dict, to: list, cc: list, subject: str, body: str,
               account_ref: str = "default", from_address: str = "") -> dict:
    """
    Send an email via the configured provider, or SMTP fallback.
    Returns {"ok": bool, "via": "provider"|"smtp", "error": str, "sent_to": [...]}.
    """
    email_cfg = cfg.get("email", {})
    provider = email_cfg.get("provider", "")
    provider_note = ""   # why the provider path didn't work, if it didn't — carried
                         # into the SMTP fallback's error so "not configured" isn't
                         # the only thing anyone ever sees when a provider WAS set.

    # ── Provider-plugin path ──────────────────────────────────────────────────
    # A provider is a plugin one unless it's the generic 'smtp' pseudo-provider
    # (which the wizard uses to mean "use SMTP settings directly").
    if provider and provider != "smtp":
        try:
            from ..plugins import get_manager
            mgr = get_manager()
            result = None
            if mgr:
                # Refresh the token first if it's an OAuth account and expired.
                _refresh_if_needed(cfg, account_ref, provider)
                result = mgr.dispatch_email_send(
                    provider_key=provider, account_ref=account_ref,
                    to=to, cc=cc, subject=subject, body=body, meta={})
            if result is None:
                # No plugin running for this provider yet — either the plugin
                # system is off, or the matching plugin was never installed
                # (connecting OAuth tokens and having a running provider
                # plugin are two separate things; see provider_plugins.py).
                # If it's one of the providers this app ships a plugin for,
                # provision it now and retry ONCE rather than silently
                # falling back to SMTP, which was never configured for an
                # OAuth account and would just fail with a confusing error.
                from .provider_plugins import ensure_provider_plugin, has_bundled_plugin
                if not has_bundled_plugin(provider):
                    provider_note = (f"provider '{provider}' is set, but no plugin is running for it "
                                     "and this app doesn't ship a built-in one for it (only "
                                     "gmail/outlook/yahoo are bundled) — install one under "
                                     "Settings -> Plugins.")
                elif ensure_provider_plugin(provider):
                    mgr = get_manager()
                    if mgr:
                        _refresh_if_needed(cfg, account_ref, provider)
                        result = mgr.dispatch_email_send(
                            provider_key=provider, account_ref=account_ref,
                            to=to, cc=cc, subject=subject, body=body, meta={})
                    if result is None:
                        provider_note = (f"provider '{provider}''s plugin was installed and enabled, "
                                         "but still didn't produce a result — check the API "
                                         "container's logs for a plugin launch/crash error.")
                else:
                    provider_note = (f"provider '{provider}' is set, and this app ships a plugin for it, "
                                     "but auto-installing/enabling/launching it failed — check the "
                                     "API container's logs (search for 'provider_plugins' or "
                                     "'Auto-provisioning failed') for the specific reason.")
            if result is not None:
                result["via"] = "provider"
                return result
            log.warning("provider '%s' configured but no matching plugin could be run (%s); "
                        "falling back to SMTP", provider, provider_note)
        except Exception as e:
            provider_note = f"provider '{provider}' send raised an exception: {e}"
            log.error("provider send failed (%s); trying SMTP fallback: %s", provider, e)

    # ── Direct SMTP fallback ──────────────────────────────────────────────────
    return _smtp_send(cfg, to, cc, subject, body, from_address, provider_note)


def _smtp_send(cfg: dict, to: list, cc: list, subject: str, body: str,
               from_address: str = "", provider_note: str = "") -> dict:
    email_cfg = cfg.get("email", {})
    host = email_cfg.get("smtp_host")
    port = int(email_cfg.get("smtp_port", 587))
    # The wizard writes smtp_username; the Settings page writes smtp_user for
    # the same field (see the same fallback in routers/settings.py's GET) —
    # read both so SMTP set up from either UI actually works, not just
    # whichever one happens to match this exact key.
    user = email_cfg.get("smtp_username") or email_cfg.get("smtp_user")
    tls = (email_cfg.get("smtp_tls", "starttls") or "starttls")
    frm = from_address or email_cfg.get("from_address") or email_cfg.get("from_email") or user
    if not host or not user:
        msg = "SMTP not configured"
        if provider_note:
            msg = f"{provider_note} SMTP fallback also isn't configured (no smtp_host/username set)."
        return {"ok": False, "via": "smtp", "error": msg, "sent_to": []}

    # Decrypt the SMTP password (stored encrypted).
    pw = ""
    try:
        from . import oauth_engine as oe
        pw = oe._decrypt(email_cfg.get("smtp_password_enc", ""))
    except Exception:
        pw = ""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = frm
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg.attach(MIMEText(body, "plain"))
    recipients = list(to) + list(cc)

    try:
        ctx = ssl.create_default_context()
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        if tls == "ssl":
            with smtplib.SMTP_SSL(host, port, timeout=25,
                                  context=ctx) as s:
                if pw:
                    s.login(user, pw)
                s.sendmail(frm, recipients, msg.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=25) as s:
                if tls == "starttls":
                    s.starttls(context=ctx)
                if pw:
                    s.login(user, pw)
                s.sendmail(frm, recipients, msg.as_string())
        return {"ok": True, "via": "smtp", "error": "", "sent_to": recipients}
    except Exception as e:
        return {"ok": False, "via": "smtp", "error": str(e), "sent_to": []}
