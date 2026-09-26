"""
SAML 2.0 service provider (SP) — general-purpose staff/employee sign-in.

Works with any standards-compliant SAML identity provider: a home-lab Keycloak or
Authentik, a university Shibboleth / InCommon IdP, Microsoft ADFS or Entra, Okta,
etc. The administrator uploads (or points at) the IdP's metadata; PrivacyShield
publishes its own SP metadata for the IdP to register.

Built on pysaml2 (maintained, uses the xmlsec1 tool for XML signatures) — no
hand-rolled XML crypto. Security properties:
  - A valid signature is REQUIRED on the response or the assertion; unsigned
    responses are rejected.
  - SP-initiated only: every response must answer an AuthnRequest we issued
    (InResponseTo). IdP-initiated/unsolicited responses are rejected.
  - Each AuthnRequest ID is single-use and expires after 10 minutes, so a
    captured response can't be replayed.
  - Audience, recipient, and validity windows are checked by pysaml2
    (60s clock-skew allowance).
  - The resulting identity goes through the SAME sign-in policy as every other
    provider (core/sso_policy.py): allowed domains, required groups (e.g. a
    university can require eduPersonAffiliation=staff), registration mode,
    and no auto-granted super admin.

Settings live at settings["auth_providers"]["saml"].
"""

import logging
import os
import time
from typing import Optional

log = logging.getLogger(__name__)

REQUEST_TTL = 600                    # seconds an AuthnRequest stays valid
_OUTSTANDING: dict = {}              # request_id -> issued_at (single-use)

# Common attribute names across IdPs (friendly names, OIDs, and Microsoft claim
# URIs). Admin-configured names are tried first.
EMAIL_ATTRS = ["mail", "email", "emailaddress",
               "urn:oid:0.9.2342.19200300.100.1.3",
               "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
               "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/upn"]
NAME_ATTRS = ["displayname", "cn", "name", "urn:oid:2.16.840.1.113730.3.1.241",
              "urn:oid:2.5.4.3",
              "http://schemas.microsoft.com/identity/claims/displayname",
              "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name"]
GROUP_ATTRS = ["groups", "memberof", "ismemberof", "edupersonaffiliation",
               "urn:oid:1.3.6.1.4.1.5923.1.1.1.1",       # eduPersonAffiliation
               "urn:oid:1.3.6.1.4.1.5923.1.5.1.1",       # isMemberOf
               "http://schemas.microsoft.com/ws/2008/06/identity/claims/groups",
               "http://schemas.microsoft.com/ws/2008/06/identity/claims/role"]


class SamlError(Exception):
    """A SAML sign-in that must be refused. The message is safe to show users."""


# ── URLs ──────────────────────────────────────────────────────────────────────

def public_base_url(cfg: dict, request_base: str = "") -> str:
    """The externally reachable base URL. Must match what the IdP registered, so
    an explicit setting wins over anything inferred from the request."""
    base = (cfg.get("sp_base_url") or os.getenv("PUBLIC_BASE_URL")
            or os.getenv("FRONTEND_URL") or request_base or "http://localhost")
    return base.rstrip("/")


def sp_urls(base: str) -> dict:
    return {
        "entity_id": f"{base}/api/auth/saml/metadata",
        "acs_url": f"{base}/api/auth/saml/acs",
        "metadata_url": f"{base}/api/auth/saml/metadata",
        "login_url": f"{base}/api/auth/saml/login",
    }


# ── pysaml2 configuration ─────────────────────────────────────────────────────

def build_config(cfg: dict, base: str, require_idp: bool = True):
    from saml2 import BINDING_HTTP_POST
    from saml2.config import SPConfig
    from saml2.sigver import get_xmlsec_binary

    urls = sp_urls(base)
    conf = {
        "entityid": urls["entity_id"],
        "xmlsec_binary": get_xmlsec_binary(["/usr/bin", "/usr/local/bin", "/opt/local/bin"]),
        "service": {"sp": {
            "endpoints": {"assertion_consumer_service": [(urls["acs_url"], BINDING_HTTP_POST)]},
            "allow_unsolicited": False,                  # SP-initiated only
            "authn_requests_signed": False,
            "want_response_signed": False,
            "want_assertions_signed": False,
            "want_assertions_or_response_signed": True,  # but ONE must be signed
        }},
        "accepted_time_diff": 60,
        "allow_unknown_attributes": True,
    }
    idp_xml = (cfg.get("idp_metadata_xml") or "").strip()
    if idp_xml:
        conf["metadata"] = {"inline": [idp_xml]}
    elif require_idp:
        raise SamlError("SAML is not configured: identity provider metadata is missing.")
    c = SPConfig()
    c.load(conf)
    return c


def _client(cfg: dict, base: str):
    from saml2.client import Saml2Client
    return Saml2Client(config=build_config(cfg, base))


def idp_entity_ids(cfg: dict, base: str) -> list:
    """Entity IDs of IdPs found in the configured metadata (validation helper)."""
    client = _client(cfg, base)
    return list(client.metadata.identity_providers())


def _pick_idp(client, cfg: dict) -> str:
    idps = list(client.metadata.identity_providers())
    wanted = (cfg.get("idp_entity_id") or "").strip()
    if wanted:
        if wanted not in idps:
            raise SamlError("Configured IdP entity ID was not found in the metadata.")
        return wanted
    if len(idps) == 1:
        return idps[0]
    raise SamlError("The metadata lists several identity providers; set which one to use.")


def sp_metadata_xml(cfg: dict, base: str) -> str:
    """SP metadata for the IdP administrator. Works before IdP metadata exists,
    since registering the SP at the IdP is usually the first step."""
    from saml2.metadata import entity_descriptor
    return str(entity_descriptor(build_config(cfg, base, require_idp=False)))


# ── Login flow ────────────────────────────────────────────────────────────────

def _prune():
    now = time.time()
    for rid in [r for r, t in _OUTSTANDING.items() if now - t > REQUEST_TTL]:
        _OUTSTANDING.pop(rid, None)


def begin_login(cfg: dict, base: str) -> str:
    """Create an AuthnRequest and return the IdP redirect URL."""
    from saml2 import BINDING_HTTP_REDIRECT
    client = _client(cfg, base)
    idp = _pick_idp(client, cfg)
    req_id, info = client.prepare_for_authenticate(entityid=idp, binding=BINDING_HTTP_REDIRECT)
    _prune()
    _OUTSTANDING[req_id] = time.time()
    return dict(info["headers"])["Location"]


def _first(identity: dict, names: list) -> Optional[str]:
    lower = {k.lower(): v for k, v in identity.items()}
    for n in names:
        vals = lower.get(n.lower())
        if vals:
            v = vals[0] if isinstance(vals, (list, tuple)) else vals
            if str(v).strip():
                return str(v).strip()
    return None


def _all(identity: dict, names: list) -> list:
    lower = {k.lower(): v for k, v in identity.items()}
    out = []
    for n in names:
        vals = lower.get(n.lower())
        if vals:
            out.extend(str(v) for v in (vals if isinstance(vals, (list, tuple)) else [vals]))
    return out


def _split_names(v) -> list:
    return [x.strip() for x in str(v or "").split(",") if x.strip()]


def consume_response(cfg: dict, base: str, saml_response_b64: str):
    """
    Validate a SAMLResponse posted to the ACS. Returns an AuthResult for the
    shared sign-in policy. Raises SamlError on any failure.
    """
    from saml2 import BINDING_HTTP_POST
    from .auth_providers import AuthResult

    if not saml_response_b64:
        raise SamlError("No SAML response was received.")
    client = _client(cfg, base)
    _prune()
    outstanding = {rid: "/" for rid in _OUTSTANDING}
    try:
        resp = client.parse_authn_request_response(
            saml_response_b64, BINDING_HTTP_POST, outstanding=outstanding)
    except Exception as e:
        log.warning("SAML response rejected: %s: %s", type(e).__name__, e)
        raise SamlError("The sign-in response could not be verified. Please try again.")
    if resp is None:
        raise SamlError("The sign-in response could not be verified. Please try again.")

    # Single use: consume the request ID so the same response can't be replayed.
    in_resp_to = getattr(resp, "in_response_to", None)
    if not in_resp_to or _OUTSTANDING.pop(in_resp_to, None) is None:
        raise SamlError("This sign-in response was already used or has expired.")

    identity = resp.get_identity() or {}
    name_id = getattr(getattr(resp, "name_id", None), "text", "") or ""

    email = _first(identity, _split_names(cfg.get("attr_email")) + EMAIL_ATTRS)
    if not email and "@" in name_id:
        email = name_id
    full_name = _first(identity, _split_names(cfg.get("attr_name")) + NAME_ATTRS)
    if not full_name:
        given = _first(identity, ["givenname", "urn:oid:2.5.4.42"]) or ""
        sn = _first(identity, ["sn", "surname", "urn:oid:2.5.4.4"]) or ""
        full_name = f"{given} {sn}".strip()
    groups = _all(identity, _split_names(cfg.get("attr_groups")) + GROUP_ATTRS)

    if not email:
        raise SamlError("The identity provider did not send an email address. "
                        "Ask your IdP administrator to release the 'mail' attribute.")
    return AuthResult(
        success=True, provider="saml",
        email=email.lower(), full_name=full_name or email,
        external_id=name_id or None,
        email_verified=None,      # the IdP is an institution directory the admin chose
        groups=groups,
    )
