"""
Outlook / Microsoft 365 email-provider plugin (reference).

Implements email_provider via Microsoft Graph using OAuth 2.0. Same trusted-class
posture as the Gmail plugin: host controls recipients, plugin never hardcodes a
destination, host inspects for hidden recipients.

Credentials: the host performs the OAuth flow (Azure app registration) and stores
the token; the plugin reads it via settings and calls Graph with the access token.

Dependency: uses `requests` for the Graph REST calls (no heavy SDK needed). If
absent, reports an error rather than crashing.
"""

import json

from openoptout_sdk import Plugin, manifest

plugin = Plugin(manifest(
    id="email-outlook", name="Outlook / Microsoft 365 Email Provider", version="1.0.0",
    author="OpenOptOut",
    permissions=["email_provider", "read_pii", "network", "settings_read"],
    hooks=["email_provider"],
    methods=["settings.get", "log"],
    outbound_domains=["graph.microsoft.com", "login.microsoftonline.com"],
    timeout_seconds=30,
))

plugin.email_provider(info={
    "provider_key": "outlook",
    "display_name": "Outlook / Microsoft 365",
    "auth_type": "oauth",
    "can_send": True,
    "can_receive": True,
    # See the matching comment in email-gmail/plugin.py — without these, the
    # host's connect/refresh flow silently depends on whether this plugin
    # happens to be running or not at the time, which is exactly the kind of
    # thing that works in early testing and breaks later.
    "oauth_auth_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
    "oauth_token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
    "oauth_use_pkce": True,
    "oauth_scopes": "https://graph.microsoft.com/Mail.Send "
                    "https://graph.microsoft.com/Mail.Read offline_access",
    "notes": "Uses Microsoft Graph. Host performs OAuth (Azure app) and stores the "
             "token; this plugin reads it via settings.",
})

_GRAPH = "https://graph.microsoft.com/v1.0"


def _access_token(account_ref):
    creds = plugin.get_email_credentials(account_ref)
    if not creds:
        raise RuntimeError(f"no stored Outlook credentials for account '{account_ref}'")
    return creds["access_token"]


def _requests():
    try:
        import requests
        return requests
    except ImportError:
        raise RuntimeError("Outlook provider needs 'requests' installed in the deployment.")


@plugin.email_send
def send(req):
    to = list(req.get("to", []))
    cc = list(req.get("cc", []))
    if not to:
        return {"ok": False, "error": "no recipient provided by host"}
    try:
        requests = _requests()
        token = _access_token(req.get("account_ref", "default"))
    except Exception as e:
        return {"ok": False, "error": str(e) or type(e).__name__}

    # Recipients come ONLY from the host-supplied lists.
    message = {
        "message": {
            "subject": req.get("subject", ""),
            "body": {"contentType": "Text", "content": req.get("body", "")},
            "toRecipients": [{"emailAddress": {"address": a}} for a in to],
            "ccRecipients": [{"emailAddress": {"address": a}} for a in cc],
        },
        "saveToSentItems": True,
    }
    try:
        r = requests.post(f"{_GRAPH}/me/sendMail",
                          headers={"Authorization": f"Bearer {token}",
                                   "Content-Type": "application/json"},
                          data=json.dumps(message), timeout=25)
        if r.status_code in (200, 202):
            plugin.log.info(f"Outlook sent to {to}")
            return {"ok": True, "message_id": r.headers.get("request-id", ""),
                    "sent_to": to + cc}
        return {"ok": False, "error": f"Graph sendMail {r.status_code}: {r.text[:200]}"}
    except Exception as e:
        return {"ok": False, "error": f"Outlook send failed: {str(e) or type(e).__name__}"}


@plugin.email_list
def list_messages(req):
    try:
        requests = _requests()
        token = _access_token(req.get("account_ref", "default"))
    except Exception as e:
        return {"ok": False, "error": str(e) or type(e).__name__}

    top = int(req.get("max_results", 20)) or 20
    try:
        r = requests.get(
            f"{_GRAPH}/me/messages?$top={top}"
            f"&$select=id,from,subject,bodyPreview,receivedDateTime",
            headers={"Authorization": f"Bearer {token}"}, timeout=25)
        if r.status_code != 200:
            return {"ok": False, "error": f"Graph messages {r.status_code}: {r.text[:200]}"}
        out = []
        for m in r.json().get("value", []):
            frm = (m.get("from", {}) or {}).get("emailAddress", {}).get("address", "")
            import datetime
            ts = 0
            try:
                ts = int(datetime.datetime.fromisoformat(
                    m.get("receivedDateTime", "").replace("Z", "+00:00")).timestamp())
            except Exception:
                pass
            out.append({"message_id": m.get("id", ""), "from": frm,
                        "subject": m.get("subject", ""),
                        "snippet": m.get("bodyPreview", ""), "received_ts": ts})
        return {"ok": True, "messages": out}
    except Exception as e:
        return {"ok": False, "error": f"Outlook list failed: {str(e) or type(e).__name__}"}


if __name__ == "__main__":
    plugin.run()
