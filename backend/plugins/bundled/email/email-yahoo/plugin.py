"""
Yahoo Mail email-provider plugin (OAuth only).

Yahoo no longer offers a proprietary Mail REST API to third parties: access
is through standard IMAP and SMTP, signed in with an OAuth 2.0 access token
(SASL OAUTHBEARER, RFC 7628; XOAUTH2 where a server only offers that). See
https://senders.yahooinc.com/developer/documentation/ . There is no
app-password mode: the person signs in with Yahoo, and OpenOptOut never sees
or stores their password.

  send   SMTP over TLS (smtp.mail.yahoo.com:465), authenticated with the token
  list   IMAP over TLS (imap.mail.yahoo.com:993), authenticated with the token.
         With include_links, the bodies of matching messages are read with
         BODY.PEEK (so they stay unread for the person) and only their http(s)
         links and a short plain-text snippet leave this plugin; that is how
         broker confirmation links are found and clicked.

The token comes from the host (plugin.get_email_credentials), already
refreshed if it had expired. The mailbox address the token belongs to is
needed to sign in over IMAP/SMTP; the host passes it as account_address
(list) and meta["account_address"] (send). It is never a recipient.

Trusted-class posture: the HOST controls the recipient list; this plugin
sends ONLY to the host-supplied to/cc and returns sent_to so the host can
verify. It never hardcodes a destination.

Yahoo's mail scopes (mail-r, mail-w) need Yahoo's approval for each OAuth
client ("Request developer access"); until a client is approved, sign-in
works but mail access is refused.
"""

import base64
import imaplib
import smtplib
import email as email_mod
from email.mime.text import MIMEText
from email.utils import parsedate_to_datetime

from openoptout_sdk import Plugin, manifest, wants_links, links_from_mime

plugin = Plugin(manifest(
    id="email-yahoo", name="Yahoo Mail",
    version="2.0.0", author="OpenOptOut",
    permissions=["email_provider", "read_pii", "network", "settings_read"],
    hooks=["email_provider"],
    methods=["settings.get", "log", "email.get_credentials"],
    outbound_domains=["smtp.mail.yahoo.com", "imap.mail.yahoo.com"],
    timeout_seconds=30,
))

plugin.email_provider(info={
    "provider_key": "yahoo",
    "display_name": "Yahoo Mail",
    "auth_type": "oauth",
    "can_send": True,
    "can_receive": True,
    # See the matching comment in email-gmail/plugin.py.
    "oauth_auth_url": "https://api.login.yahoo.com/oauth2/request_auth",
    "oauth_token_url": "https://api.login.yahoo.com/oauth2/get_token",
    "oauth_use_pkce": True,
    "oauth_scopes": "mail-r mail-w",
    "notes": "Sign in with Yahoo (OAuth). Mail is sent and read over Yahoo's IMAP and SMTP with "
             "the sign-in token; no app password. The OAuth client needs Yahoo's approval for "
             "mail access.",
})

SMTP_HOST, SMTP_PORT = "smtp.mail.yahoo.com", 465
IMAP_HOST, IMAP_PORT = "imap.mail.yahoo.com", 993


def _token(account_ref):
    creds = plugin.get_email_credentials(account_ref)
    if not creds or not creds.get("access_token"):
        raise RuntimeError("This Yahoo inbox isn't signed in. Connect it again from Email inboxes.")
    return creds["access_token"]


def oauthbearer(user: str, token: str, host: str, port: int) -> str:
    """SASL OAUTHBEARER initial response (RFC 7628)."""
    return f"n,a={user},\x01host={host}\x01port={port}\x01auth=Bearer {token}\x01\x01"


def xoauth2(user: str, token: str) -> str:
    """SASL XOAUTH2 initial response, for servers that only offer that."""
    return f"user={user}\x01auth=Bearer {token}\x01\x01"


def _need_address(addr: str) -> str:
    addr = (addr or "").strip()
    if "@" not in addr:
        raise RuntimeError("OpenOptOut didn't say which Yahoo address this is; update OpenOptOut.")
    return addr


# SEND

def _smtp_login(s, user: str, token: str) -> None:
    s.ehlo()
    mechs = (s.esmtp_features.get("auth", "") or "").upper().split()
    if "OAUTHBEARER" in mechs or not mechs:
        s.auth("OAUTHBEARER", lambda challenge=None: oauthbearer(user, token, SMTP_HOST, SMTP_PORT),
               initial_response_ok=True)
    elif "XOAUTH2" in mechs:
        s.auth("XOAUTH2", lambda challenge=None: xoauth2(user, token), initial_response_ok=True)
    else:
        raise RuntimeError("Yahoo's mail server didn't offer token sign-in.")


@plugin.email_send
def send(req):
    to = list(req.get("to", []))
    cc = list(req.get("cc", []))
    if not to:
        return {"ok": False, "error": "no recipient provided by host"}
    meta = req.get("meta") or {}
    try:
        token = _token(req.get("account_ref", "default"))
        user = _need_address(meta.get("account_address", ""))
    except Exception as e:
        return {"ok": False, "error": str(e) or type(e).__name__}
    msg = MIMEText(req.get("body", ""), "plain")
    msg["From"] = user
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = req.get("subject", "")
    if meta.get("reply_to"):
        msg["Reply-To"] = meta["reply_to"]     # host-supplied; not a recipient
    recipients = to + cc
    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=25) as s:
            _smtp_login(s, user, token)
            s.sendmail(user, recipients, msg.as_string())
        plugin.log.info(f"Yahoo sent to {len(recipients)} recipient(s)")
        return {"ok": True, "message_id": msg.get("Message-ID", "") or "", "sent_to": recipients}
    except smtplib.SMTPAuthenticationError:
        return {"ok": False, "error": "Yahoo refused the sign-in token. If this OAuth client hasn't been "
                                      "approved for mail by Yahoo yet, mail access is refused."}
    except Exception as e:
        return {"ok": False, "error": f"Yahoo send failed: {str(e) or type(e).__name__}"}


# LIST (read confirmations)

def _plain_snippet(raw: bytes, n: int = 400) -> str:
    msg = email_mod.message_from_bytes(raw)
    for part in (msg.walk() if msg.is_multipart() else [msg]):
        if part.get_content_type() == "text/plain":
            try:
                return " ".join(part.get_payload(decode=True).decode(
                    part.get_content_charset() or "utf-8", "replace").split())[:n]
            except Exception:
                return ""
    return ""


def _imap_login(M, user: str, token: str) -> None:
    caps = [c.decode().upper() if isinstance(c, bytes) else str(c).upper() for c in (M.capabilities or ())]
    if "AUTH=OAUTHBEARER" in caps or not any(c.startswith("AUTH=") for c in caps):
        M.authenticate("OAUTHBEARER", lambda _: oauthbearer(user, token, IMAP_HOST, IMAP_PORT).encode())
    elif "AUTH=XOAUTH2" in caps:
        M.authenticate("XOAUTH2", lambda _: xoauth2(user, token).encode())
    else:
        raise RuntimeError("Yahoo's mail server didn't offer token sign-in.")


def _imap(host=IMAP_HOST, port=IMAP_PORT):
    """Replaced in tests."""
    return imaplib.IMAP4_SSL(host, port, timeout=25)


@plugin.email_list
def list_messages(req):
    try:
        token = _token(req.get("account_ref", "default"))
        user = _need_address(req.get("account_address", ""))
    except Exception as e:
        return {"ok": False, "error": str(e) or type(e).__name__}
    max_results = int(req.get("max_results", 20) or 20)
    since_ts = int(req.get("since_ts", 0) or 0)
    try:
        M = _imap()
        _imap_login(M, user, token)
        M.select("INBOX", readonly=True)
        typ, data = M.search(None, "ALL")
        ids = data[0].split()[-max_results:] if data and data[0] else []
        out = []
        for i in reversed(ids):
            typ, msg_data = M.fetch(i, "(BODY.PEEK[HEADER])")
            if not msg_data or not msg_data[0] or not isinstance(msg_data[0], tuple):
                continue
            hdr = email_mod.message_from_bytes(msg_data[0][1])
            ts = 0
            try:
                ts = int(parsedate_to_datetime(hdr.get("Date")).timestamp())
            except Exception:
                pass
            if since_ts and ts and ts < since_ts:
                continue
            to_h = ", ".join(filter(None, [hdr.get("To", ""), hdr.get("Delivered-To", "")]))
            item = {
                "message_id": (hdr.get("Message-ID") or i.decode()).strip().strip("<>"),
                "from": hdr.get("From", ""),
                "to": to_h,
                "subject": hdr.get("Subject", ""),
                "snippet": "",
                "received_ts": ts,
            }
            if wants_links(req, to_h):
                # BODY.PEEK leaves the message unread for the person; only the
                # links and a short snippet leave this plugin.
                typ, full = M.fetch(i, "(BODY.PEEK[])")
                if full and full[0] and isinstance(full[0], tuple):
                    item["links"] = links_from_mime(full[0][1])
                    item["snippet"] = _plain_snippet(full[0][1])
            out.append(item)
        try:
            M.logout()
        except Exception:
            pass
        return {"ok": True, "messages": out, "links_supported": True}
    except imaplib.IMAP4.error as e:
        if "AUTHENTICATE" in str(e).upper() or "AUTH" in str(e).upper():
            return {"ok": False, "error": "Yahoo refused the sign-in token. If this OAuth client hasn't been "
                                          "approved for mail by Yahoo yet, mail access is refused."}
        return {"ok": False, "error": f"Yahoo read failed: {e}"}
    except Exception as e:
        return {"ok": False, "error": f"Yahoo read failed: {str(e) or type(e).__name__}"}


if __name__ == "__main__":
    plugin.run()
