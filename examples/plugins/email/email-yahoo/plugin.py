"""
Yahoo Mail email-provider plugin — DUAL-MODE reference.

Yahoo supports BOTH OAuth 2.0 and app-passwords over standard SMTP/IMAP. This
plugin implements BOTH in one file and picks the mode from the stored
credentials, so it serves three teaching purposes:

  1. A working Yahoo provider (either transport).
  2. A template for a HYBRID provider (supports OAuth AND app-password) — useful
     for any provider where both are possible.
  3. A reference for how the plain SMTP/IMAP path works (the same pattern used by
     Apple/iCloud and self-hosted mail), shown side-by-side with the OAuth path.

Mode selection (from settings.get("email_credentials:{account_ref}")):
  - {"access_token": ...}  -> OAUTH mode  (preferred; more secure — token, not password)
  - {"username": ..., "app_password": ...} -> SMTP/IMAP mode (fallback)
If both are present, OAuth is preferred (matches the project's OAuth-first stance).

Trusted-class posture (both modes): the HOST controls the recipient list; this
plugin sends ONLY to the host-supplied to/cc and returns sent_to so the host can
verify. It never hardcodes a destination in either path.

OAuth mode uses `requests` (report an error if absent). SMTP/IMAP mode uses only
the Python stdlib (smtplib, imaplib).
"""

import json
import base64
import smtplib
import imaplib
import email as email_mod
from email.mime.text import MIMEText
from email.utils import parsedate_to_datetime

from openoptout_sdk import Plugin, manifest

plugin = Plugin(manifest(
    id="email-yahoo", name="Yahoo Mail Email Provider (dual-mode reference)",
    version="1.1.0", author="OpenOptOut",
    permissions=["email_provider", "read_pii", "network", "settings_read"],
    hooks=["email_provider"],
    methods=["settings.get", "log"],
    outbound_domains=["smtp.mail.yahoo.com", "imap.mail.yahoo.com",
                      "api.login.yahoo.com", "api.mail.yahoo.com"],
    timeout_seconds=30,
))

plugin.email_provider(info={
    "provider_key": "yahoo",
    "display_name": "Yahoo Mail",
    "auth_type": "oauth_or_app_password",
    "can_send": True,
    "can_receive": True,
    # See the matching comment in email-gmail/plugin.py.
    "oauth_auth_url": "https://api.login.yahoo.com/oauth2/request_auth",
    "oauth_token_url": "https://api.login.yahoo.com/oauth2/get_token",
    "oauth_use_pkce": False,
    "oauth_scopes": "mail-w",
    "notes": "Supports OAuth (preferred) or an app-password over SMTP/IMAP. The "
             "mode is chosen from the stored credentials. A template for hybrid "
             "providers and for the plain SMTP/IMAP pattern.",
})

SMTP_HOST = "smtp.mail.yahoo.com"
SMTP_PORT = 587
IMAP_HOST = "imap.mail.yahoo.com"


def _load_creds(account_ref):
    creds = plugin.get_email_credentials(account_ref)
    if not creds:
        raise RuntimeError(f"no stored Yahoo credentials for account '{account_ref}'")
    return creds


def _mode(creds):
    """OAuth-first: prefer a token if present, else fall back to app-password.
    In THIS app, only the OAuth path is actually reachable today —
    email_credentials only ever holds OAuth tokens (see
    plugin.get_email_credentials); username/app_password here is a template
    for a hybrid provider plugin that stores its own credential shape via
    plugin.settings (non-secret bits) plus its own storage.set (secret bits),
    rather than something this reference plugin currently wires up itself."""
    if creds.get("access_token"):
        return "oauth"
    if creds.get("username") and creds.get("app_password"):
        return "app_password"
    raise RuntimeError("Yahoo credentials need either an access_token (OAuth) or "
                       "username + app_password (SMTP/IMAP)")


def _requests():
    try:
        import requests
        return requests
    except ImportError:
        raise RuntimeError("Yahoo OAuth mode needs 'requests' installed in the deployment.")


# SEND

@plugin.email_send
def send(req):
    to = list(req.get("to", []))
    cc = list(req.get("cc", []))
    if not to:
        return {"ok": False, "error": "no recipient provided by host"}
    try:
        creds = _load_creds(req.get("account_ref", "default"))
        mode = _mode(creds)
    except Exception as e:
        return {"ok": False, "error": str(e) or type(e).__name__}
    if mode == "oauth":
        return _send_oauth(creds, to, cc, req)
    return _send_smtp(creds, to, cc, req)


def _send_oauth(creds, to, cc, req):
    """OAuth path: Yahoo Mail API. Host supplies + host verifies recipients."""
    try:
        requests = _requests()
    except Exception as e:
        return {"ok": False, "error": str(e) or type(e).__name__}
    token = creds.get("access_token")
    msg = MIMEText(req.get("body", ""), "plain")
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = req.get("subject", "")
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    try:
        r = requests.post(
            "https://api.mail.yahoo.com/ws/v3/mailboxes/@.messages",
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json"},
            data=json.dumps({"raw": raw}), timeout=25)
        if r.status_code in (200, 201, 202):
            plugin.log.info(f"Yahoo (OAuth) sent to {to}")
            return {"ok": True, "message_id": r.headers.get("x-request-id", ""),
                    "sent_to": to + cc}
        return {"ok": False, "error": f"Yahoo API {r.status_code}: {r.text[:200]}"}
    except Exception as e:
        return {"ok": False, "error": f"Yahoo OAuth send failed: {str(e) or type(e).__name__}"}


def _send_smtp(creds, to, cc, req):
    """SMTP/app-password path (also the generic IMAP/SMTP reference)."""
    user = creds["username"]
    pw = creds["app_password"]
    msg = MIMEText(req.get("body", ""), "plain")
    msg["From"] = user
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = req.get("subject", "")
    recipients = to + cc
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=25) as s:
            s.starttls()
            s.login(user, pw)
            s.sendmail(user, recipients, msg.as_string())
        plugin.log.info(f"Yahoo (SMTP) sent to {to}")
        return {"ok": True, "message_id": "", "sent_to": recipients}
    except Exception as e:
        return {"ok": False, "error": f"Yahoo SMTP send failed: {str(e) or type(e).__name__}"}


# LIST (read confirmations)

@plugin.email_list
def list_messages(req):
    try:
        creds = _load_creds(req.get("account_ref", "default"))
        mode = _mode(creds)
    except Exception as e:
        return {"ok": False, "error": str(e) or type(e).__name__}
    if mode == "oauth":
        return _list_oauth(creds, req)
    return _list_imap(creds, req)


def _list_oauth(creds, req):
    try:
        requests = _requests()
    except Exception as e:
        return {"ok": False, "error": str(e) or type(e).__name__}
    token = creds.get("access_token")
    top = int(req.get("max_results", 20)) or 20
    try:
        r = requests.get(
            f"https://api.mail.yahoo.com/ws/v3/mailboxes/@.messages?count={top}",
            headers={"Authorization": f"Bearer {token}"}, timeout=25)
        if r.status_code != 200:
            return {"ok": False, "error": f"Yahoo API {r.status_code}: {r.text[:200]}"}
        out = []
        for m in r.json().get("messages", []):
            out.append({
                "message_id": m.get("id", ""),
                "from": (m.get("from", {}) or {}).get("email", ""),
                "subject": m.get("subject", ""),
                "snippet": m.get("snippet", ""),
                "received_ts": int(m.get("receivedDate", 0)),
            })
        return {"ok": True, "messages": out}
    except Exception as e:
        return {"ok": False, "error": f"Yahoo OAuth list failed: {str(e) or type(e).__name__}"}


def _list_imap(creds, req):
    user = creds["username"]
    pw = creds["app_password"]
    max_results = int(req.get("max_results", 20)) or 20
    try:
        M = imaplib.IMAP4_SSL(IMAP_HOST)
        M.login(user, pw)
        M.select("INBOX")
        typ, data = M.search(None, "ALL")
        ids = data[0].split()[-max_results:] if data and data[0] else []
        out = []
        for i in reversed(ids):
            typ, msg_data = M.fetch(i, "(RFC822.HEADER)")
            if not msg_data or not msg_data[0]:
                continue
            hdr = email_mod.message_from_bytes(msg_data[0][1])
            ts = 0
            try:
                ts = int(parsedate_to_datetime(hdr.get("Date")).timestamp())
            except Exception:
                pass
            out.append({
                "message_id": (hdr.get("Message-ID") or i.decode()).strip("<>"),
                "from": hdr.get("From", ""),
                "subject": hdr.get("Subject", ""),
                "snippet": "",
                "received_ts": ts,
            })
        M.logout()
        return {"ok": True, "messages": out}
    except Exception as e:
        return {"ok": False, "error": f"Yahoo IMAP list failed: {str(e) or type(e).__name__}"}


if __name__ == "__main__":
    plugin.run()
