"""
Gmail email-provider plugin (reference implementation).

Implements the email_provider hook: sends opt-out emails and lists confirmation
emails through the Gmail API using OAuth 2.0. This is a REFERENCE for how an
email-provider plugin is structured; the three real Google API touch points are
clearly marked.

Security posture (email-provider trusted class):
  - Declares read_pii + network (sending member identifiers to Gmail is its job).
  - The HOST controls the recipient list — this plugin sends ONLY to the `to`/`cc`
    it is given in the request, and returns `sent_to` so the host can verify no
    hidden recipient was added. It never hardcodes a destination.
  - The host statically inspects this plugin for hidden/hardcoded To/Cc/Bcc
    before trusting it.

Credentials: the plugin does NOT run the interactive OAuth consent. The host
performs the OAuth dance (during setup), stores the tokens, and refreshes them
when needed — the plugin calls plugin.get_email_credentials(account_ref) for
just the current access token right before sending. It never sees the refresh
token or the OAuth client secret; both stay host-side.

Dependencies: needs `google-auth` and `google-api-python-client` present in the
deployment. If they're missing, the plugin reports an error rather than crashing,
so the host can surface "install these to use Gmail."
"""

import base64
from email.mime.text import MIMEText

from privacyshield_sdk import Plugin, manifest

plugin = Plugin(manifest(
    id="email-gmail", name="Gmail Email Provider", version="1.0.0",
    author="PrivacyShield",
    permissions=["email_provider", "read_pii", "network", "settings_read"],
    hooks=["email_provider"],
    methods=["settings.get", "log"],
    outbound_domains=["gmail.googleapis.com", "oauth2.googleapis.com"],
    timeout_seconds=30,
))


# ---- provider info ----
plugin.email_provider(info={
    "provider_key": "gmail",
    "display_name": "Gmail / Google Workspace",
    "auth_type": "oauth",
    "can_send": True,
    "can_receive": True,
    # These are what the host actually uses to build the connect URL and to
    # refresh a token later — leaving them out here doesn't mean "no OAuth",
    # it means the host silently falls back to its own hardcoded copy (see
    # routers/email_oauth.py's _provider_flow) whenever this plugin ISN'T
    # currently running, and gets an EMPTY url from here (info.get(...) with
    # no default) the moment it IS running — which is exactly what an empty,
    # working-then-broken-once-the-plugin-launches "Request URL is missing an
    # 'http://' or 'https://' protocol" refresh failure looks like. This
    # plugin's own self-description should be the correct, authoritative
    # copy regardless of whether the host ever needed its own fallback.
    "oauth_auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
    "oauth_token_url": "https://oauth2.googleapis.com/token",
    "oauth_use_pkce": True,
    "oauth_scopes": "https://www.googleapis.com/auth/gmail.send "
                    "https://www.googleapis.com/auth/gmail.readonly",
    "notes": "Uses the Gmail API. The host performs OAuth and stores the refresh "
             "token; this plugin reads it via settings and sends/reads mail.",
})


def _gmail_service(account_ref):
    """
    Build an authenticated Gmail API client from the stored OAuth credentials for
    `account_ref`. Raises RuntimeError with a clear message if the Google
    libraries aren't installed or credentials are missing.
    """
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        raise RuntimeError(
            "Gmail provider needs 'google-auth' and 'google-api-python-client' "
            "installed in the deployment.")

    creds_dict = plugin.get_email_credentials(account_ref)
    if not creds_dict:
        raise RuntimeError(f"no stored Gmail credentials for account '{account_ref}'")
    # Just the access token — the host already refreshed it before dispatching
    # this send (see core/email_send.py's _refresh_if_needed), so the plugin
    # never needs the refresh token or the OAuth client secret at all, both of
    # which are more sensitive than a token this app already scopes narrowly
    # and can revoke. A static (non-refreshing) Credentials object is exactly
    # what a single API call needs.
    creds = Credentials(token=creds_dict["access_token"])
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


@plugin.email_send
def send(req):
    """
    Send one email. req = {account_ref, to[], cc[], subject, body, meta}.
    Sends ONLY to the given recipients; returns sent_to so the host can verify.
    """
    to = list(req.get("to", []))
    cc = list(req.get("cc", []))
    if not to:
        return {"ok": False, "error": "no recipient provided by host"}
    try:
        svc = _gmail_service(req.get("account_ref", "default"))
    except Exception as e:
        return {"ok": False, "error": str(e) or type(e).__name__}

    msg = MIMEText(req.get("body", ""), "plain")
    msg["To"] = ", ".join(to)          # host-supplied recipients ONLY
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = req.get("subject", "")
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

    try:
        sent = svc.users().messages().send(userId="me", body={"raw": raw}).execute()
        plugin.log.info(f"Gmail sent message {sent.get('id')} to {to}")
        return {"ok": True, "message_id": sent.get("id", ""), "sent_to": to + cc}
    except Exception as e:
        return {"ok": False, "error": f"Gmail send failed: {str(e) or type(e).__name__}"}


@plugin.email_list
def list_messages(req):
    """
    List recent inbound messages for confirmation matching.
    req = {account_ref, max_results, since_ts}.
    """
    try:
        svc = _gmail_service(req.get("account_ref", "default"))
    except Exception as e:
        return {"ok": False, "error": str(e) or type(e).__name__}

    max_results = int(req.get("max_results", 20)) or 20
    since_ts = int(req.get("since_ts", 0))
    query = f"after:{since_ts}" if since_ts else ""

    try:
        listing = svc.users().messages().list(
            userId="me", maxResults=max_results, q=query).execute()
        out = []
        for m in listing.get("messages", []):
            full = svc.users().messages().get(
                userId="me", id=m["id"], format="metadata",
                metadataHeaders=["From", "Subject", "Date"]).execute()
            headers = {h["name"]: h["value"]
                       for h in full.get("payload", {}).get("headers", [])}
            out.append({
                "message_id": m["id"],
                "from": headers.get("From", ""),
                "subject": headers.get("Subject", ""),
                "snippet": full.get("snippet", ""),
                "received_ts": int(int(full.get("internalDate", "0")) / 1000),
            })
        return {"ok": True, "messages": out}
    except Exception as e:
        return {"ok": False, "error": f"Gmail list failed: {str(e) or type(e).__name__}"}


if __name__ == "__main__":
    plugin.run()
