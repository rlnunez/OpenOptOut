"""
Certificate monitor — one daily check for every certificate sign-in depends on.

  LDAP (LDAPS/StartTLS)  live server certificate. These usually auto-renew, so a
                          certificate close to expiry means renewal has FAILED.
  SIP2 over TLS           same, for the library ILS.
  SAML IdP signing cert   read from the stored IdP metadata. These do NOT
                          auto-update here: when the IdP switches to a new signing
                          certificate, sign-in breaks until an admin uploads the
                          new metadata. Warned from 30 days out. If the metadata
                          already contains a later-expiring certificate (a planned
                          rollover), there's nothing to do and no warning.

Alerts appear on the super-admin dashboard, and super admins are emailed once
per milestone (30/14/7/3/1 days, and on expiry) — never a daily repeat.

State (last results + which reminders were sent) lives in its own small JSON file
next to the settings file, so the daily job never races with admins saving
settings.
"""

import base64
import datetime
import json
import logging
import os

log = logging.getLogger(__name__)

SAML_WARN_DAYS = 30
REMINDER_DAYS = (30, 14, 7, 3, 1)
ALERT_LEVELS = ("warning", "expired", "error")
_MD = "urn:oasis:names:tc:SAML:2.0:metadata"
_DS = "http://www.w3.org/2000/09/xmldsig#"


# ── state file ────────────────────────────────────────────────────────────────

def _state_path() -> str:
    from .settings_store import SETTINGS_FILE
    return os.path.join(os.path.dirname(os.path.abspath(SETTINGS_FILE)), "cert_monitor.json")


def load_state() -> dict:
    try:
        with open(_state_path()) as f:
            return json.load(f)
    except Exception:
        return {"results": {}, "notified": {}}


def _save_state(state: dict):
    path = _state_path()
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, path)


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# ── SAML signing certificates ─────────────────────────────────────────────────

def saml_signing_certs(metadata_xml: str, idp_entity_id: str = "") -> list:
    """Signing certificates for the IdP in the metadata (use="signing" or no use)."""
    from defusedxml.ElementTree import fromstring      # safe XML parsing (no XXE)
    from cryptography import x509
    from .auth_providers import _cert_info
    root = fromstring(metadata_xml.encode() if isinstance(metadata_xml, str) else metadata_xml)
    entities = [root] if root.tag == f"{{{_MD}}}EntityDescriptor" else \
        root.findall(f".//{{{_MD}}}EntityDescriptor")
    certs = []
    for ent in entities:
        if idp_entity_id and ent.get("entityID") != idp_entity_id:
            continue
        for idp in ent.findall(f"{{{_MD}}}IDPSSODescriptor"):
            for kd in idp.findall(f"{{{_MD}}}KeyDescriptor"):
                if kd.get("use") not in (None, "signing"):
                    continue
                for el in kd.findall(f".//{{{_DS}}}X509Certificate"):
                    b64 = "".join((el.text or "").split())
                    try:
                        c = x509.load_der_x509_certificate(base64.b64decode(b64))
                        certs.append(_cert_info(c))
                    except Exception:
                        continue
    return certs


def saml_cert_status(saml_cfg: dict) -> dict:
    now = _now()
    xml = (saml_cfg.get("idp_metadata_xml") or "").strip()
    if not xml:
        return {"level": "none", "checked_at": now, "message": "No IdP metadata configured."}
    try:
        certs = saml_signing_certs(xml, (saml_cfg.get("idp_entity_id") or "").strip())
    except Exception as e:
        return {"level": "error", "checked_at": now,
                "message": f"Could not read the IdP metadata ({e}). Re-upload it in the SAML settings."}
    if not certs:
        return {"level": "error", "checked_at": now,
                "message": "The IdP metadata contains no signing certificate. Re-upload it."}
    newest = max(certs, key=lambda c: c["days_left"])   # a rollover cert covers the old one
    days, date = newest["days_left"], newest["not_after"][:10]
    base = {"checked_at": now, "days_left": days, "not_after": newest["not_after"],
            "issuer": newest["issuer"], "subject": newest["subject"], "cert_count": len(certs)}
    if days < 0:
        return {**base, "level": "expired",
                "message": (f"Your SAML identity provider's signing certificate expired on {date}. "
                            "If SAML sign-in is failing, download the IdP's new metadata and "
                            "upload it in the SAML settings.")}
    if days <= SAML_WARN_DAYS:
        return {**base, "level": "warning",
                "message": (f"Your SAML identity provider's signing certificate expires on {date} "
                            f"({days} days). Around then the IdP will switch to a new certificate, "
                            "and SAML sign-in will fail until you upload the IdP's new metadata in "
                            "the SAML settings. (If your metadata was set from a URL, just re-save.)")}
    return {**base, "level": "ok",
            "message": f"Signing certificate valid until {date} ({days} days)."}


# ── run all checks ────────────────────────────────────────────────────────────

def _checks() -> dict:
    """Run every applicable check. Returns {source: status}."""
    from .settings_store import load_settings
    from .auth_providers import ldap_cert_status, sip2_cert_status
    ap = load_settings().get("auth_providers", {}) or {}
    out = {}
    ldap = ap.get("ldap", {}) or {}
    if ldap.get("enabled"):
        out["ldap"] = ldap_cert_status(ldap)
    sip2 = ap.get("sip2", {}) or {}
    if sip2.get("enabled") and sip2.get("use_tls"):
        out["sip2"] = sip2_cert_status(sip2)
    saml = ap.get("saml", {}) or {}
    if saml.get("enabled"):
        out["saml"] = saml_cert_status(saml)
    https = https_cert_status()
    if https is not None:
        out["https"] = https
    return out


def https_cert_status():
    """
    OpenOptOut's own certificate (Caddy or Traefik front door), or None if HTTPS isn't on.
    Let's Encrypt stopped emailing expiry warnings in 2025, so this is what
    catches a failed automatic renewal.
      letsencrypt          full verification (also catches a leftover staging cert)
      staging/acme/custom  dates only: the API container deliberately doesn't get
                           deploy/certs (it can hold the site's private key)
      cloudflare-tunnel    Cloudflare's edge holds the certificate; not checked
      none                 front door with no certificate; nothing to check
      internal             Caddy's private CA renews itself; not checked (Caddy-only — the Traefik front door refuses this mode)
    """
    from .auth_providers import tls_peer_cert_status
    mode = os.getenv("HTTPS_MODE", "").strip()
    domain = os.getenv("DOMAIN", "").split(",")[0].strip()
    if not mode or mode == "none" or not domain:
        # 'none' = a front door with no certificate yet: nothing to check, and the plain-HTTP warning elsewhere already covers it.
        return None
    if mode == "cloudflare-tunnel":
        return {"level": "none", "checked_at": _now(),
                "message": "Cloudflare issues and renews this certificate at its edge "
                           "(Cloudflare Tunnel). Nothing to check on this server."}
    if mode == "internal":
        return {"level": "none", "checked_at": _now(),
                "message": "Caddy's internal CA issues and renews this certificate itself."}
    host = os.getenv("HTTPS_CHECK_HOST", "caddy").strip() or "caddy"
    port = int(os.getenv("HTTPS_CHECK_PORT", "443") or 443)
    st = tls_peer_cert_status(host, port, timeout=10, service="HTTPS front door",
                              server_name=domain, verify=(mode == "letsencrypt"))
    if mode == "letsencrypt-staging" and st.get("level") == "ok":
        st["message"] += " (Staging certificate: browsers won't trust it. Switch to letsencrypt.)"
    return st


LABELS = {"ldap": "LDAP directory", "sip2": "Library ILS (SIP2)", "saml": "SAML identity provider",
          "https": "OpenOptOut HTTPS"}


def alerts(state: dict = None) -> list:
    """Current alerts for the dashboard (warning / expired / error only)."""
    state = state or load_state()
    return [{"source": k, "label": LABELS.get(k, k), **v}
            for k, v in (state.get("results") or {}).items()
            if v.get("level") in ALERT_LEVELS]


def _reminder_key(source: str, status: dict):
    """Which milestone this status falls in; None = no email due. The key embeds
    the certificate's expiry date, so a replaced certificate starts fresh."""
    level = status.get("level")
    cert_id = status.get("not_after", "")[:10]
    if level == "expired":
        return f"{source}:{cert_id}:expired"
    if level == "error":
        return f"{source}:error:{status.get('message', '')[:60]}"
    if level == "warning":
        days = status.get("days_left", 0)
        passed = [m for m in REMINDER_DAYS if days <= m]
        if passed:
            return f"{source}:{cert_id}:{min(passed)}d"
    return None


def run_cert_checks(send_email=True, db=None) -> dict:
    """Run all checks, store results, and email super admins for new milestones."""
    state = load_state()
    results = _checks()
    state["results"] = results
    state["checked_at"] = _now()
    notified = state.setdefault("notified", {})
    due = []
    for source, st in results.items():
        key = _reminder_key(source, st)
        if key and key not in notified:
            due.append((key, source, st))
    sent = []
    if send_email and due:
        from .admin_notify import send_admin_email
        for key, source, st in due:
            subject = f"[OpenOptOut] {LABELS.get(source, source)} certificate: action needed"
            body = (f"{st.get('message', '')}\n\n"
                    f"Source: {LABELS.get(source, source)}\n"
                    f"Checked: {st.get('checked_at', '')}\n\n"
                    "This reminder was sent to all OpenOptOut super administrators. "
                    "You'll get one reminder per milestone (30, 14, 7, 3, and 1 day, and on "
                    "expiry), not a daily repeat.")
            result = send_admin_email(subject, body, db=db)
            if result.get("sent"):
                notified[key] = _now()
                sent.append(key)
            else:
                log.warning("Certificate reminder not emailed (%s): %s", key, result.get("error"))
    _save_state(state)
    for source, st in results.items():
        if st.get("level") in ALERT_LEVELS:
            log.warning("Certificate check [%s]: %s", source, st.get("message"))
    return {"results": results, "emailed": sent}
