"""
Generic SMTP / IMAP email-provider plugin.

Server-AGNOSTIC: nothing is hardcoded to a specific provider. The SMTP/IMAP host,
port, TLS mode, and credentials all come from the stored account settings. Use it
for:
  - self-hosted / on-premises mail servers (an institution's own mail),
  - any provider that offers plain SMTP/IMAP but has no dedicated plugin,
  - a fallback when the OAuth-based providers don't fit.

This is the "bring your own server" reference — the operator points it at whatever
mail server they run.

Stored credentials (settings.get("email_credentials:{account_ref}")) — a JSON
object with:
  {
    "smtp_host": "mail.example.org", "smtp_port": 587,
    "imap_host": "mail.example.org", "imap_port": 993,
    "username": "...", "password": "...",
    "tls": "starttls"        # "starttls" | "ssl" | "none"
  }
imap_host/imap_port are optional (receive is skipped if absent).

Trusted-class posture: the HOST controls recipients — this plugin sends ONLY to
the host-supplied to/cc and returns sent_to for verification. It never hardcodes
a destination. Stdlib only (smtplib, imaplib), so no extra dependencies.

Note on the sandbox allowlist: because the destination server is operator-defined
and unknown at authoring time, this plugin's manifest declares outbound_domains
["*"] with a note; the HOST binds the actual allowed host to the configured
smtp_host/imap_host at enable time rather than trusting a wildcard blindly.
"""

import json
import smtplib
import imaplib
import ssl
import email as email_mod
from email.mime.text import MIMEText
from email.utils import parsedate_to_datetime

from openoptout_sdk import Plugin, manifest

plugin = Plugin(manifest(
    id="email-smtp", name="Generic SMTP / IMAP Email Provider", version="1.0.0",
    author="OpenOptOut",
    permissions=["email_provider", "read_pii", "network", "settings_read"],
    hooks=["email_provider"],
    methods=["settings.get", "log"],
    outbound_domains=["*"],   # operator-defined host; bound by the host at enable time
    timeout_seconds=30,
))

plugin.email_provider(info={
    "provider_key": "smtp",
    "display_name": "Generic SMTP / IMAP (self-hosted / on-prem)",
    "auth_type": "smtp",
    "can_send": True,
    "can_receive": True,
    "oauth_scopes": "",
    "notes": "Server-agnostic. Configure smtp_host/imap_host, port, TLS mode, and "
             "credentials in the account settings. Works with self-hosted and "
             "on-premises mail servers.",
})


def _cfg(account_ref):
    raw = plugin.settings.get(f"email_credentials:{account_ref}")
    if not raw:
        raise RuntimeError(f"no stored SMTP settings for account '{account_ref}'")
    c = json.loads(raw)
    if not c.get("smtp_host") or not c.get("username"):
        raise RuntimeError("SMTP settings need at least smtp_host and username")
    return c


@plugin.email_send
def send(req):
    to = list(req.get("to", []))
    cc = list(req.get("cc", []))
    if not to:
        return {"ok": False, "error": "no recipient provided by host"}
    try:
        c = _cfg(req.get("account_ref", "default"))
    except Exception as e:
        return {"ok": False, "error": str(e) or type(e).__name__}

    host = c["smtp_host"]
    port = int(c.get("smtp_port", 587))
    user = c["username"]
    pw = c.get("password", "")
    tls = (c.get("tls", "starttls") or "starttls").lower()

    msg = MIMEText(req.get("body", ""), "plain")
    msg["From"] = c.get("from_address", user)
    msg["To"] = ", ".join(to)      # host-supplied only
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = req.get("subject", "")
    recipients = to + cc           # explicit list = host-supplied only

    try:
        if tls == "ssl":
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, timeout=25, context=ctx) as s:
                if pw:
                    s.login(user, pw)
                s.sendmail(msg["From"], recipients, msg.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=25) as s:
                if tls == "starttls":
                    s.starttls(context=ssl.create_default_context())
                if pw:
                    s.login(user, pw)
                s.sendmail(msg["From"], recipients, msg.as_string())
        plugin.log.info(f"SMTP sent to {to} via {host}")
        return {"ok": True, "message_id": "", "sent_to": recipients}
    except Exception as e:
        return {"ok": False, "error": f"SMTP send failed ({host}:{port}): {str(e) or type(e).__name__}"}


@plugin.email_list
def list_messages(req):
    try:
        c = _cfg(req.get("account_ref", "default"))
    except Exception as e:
        return {"ok": False, "error": str(e) or type(e).__name__}

    imap_host = c.get("imap_host")
    if not imap_host:
        return {"ok": True, "messages": []}   # send-only account; nothing to read
    imap_port = int(c.get("imap_port", 993))
    user = c["username"]
    pw = c.get("password", "")
    max_results = int(req.get("max_results", 20)) or 20

    try:
        M = imaplib.IMAP4_SSL(imap_host, imap_port)
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
        return {"ok": False, "error": f"IMAP list failed ({imap_host}:{imap_port}): {str(e) or type(e).__name__}"}


if __name__ == "__main__":
    plugin.run()
