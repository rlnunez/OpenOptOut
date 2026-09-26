"""
SAML 2.0 sign-in routes.

Public (the IdP and browsers hit these):
  GET  /api/auth/saml/metadata   SP metadata XML to register at the IdP
  GET  /api/auth/saml/login      start sign-in (redirects to the IdP)
  POST /api/auth/saml/acs        assertion consumer: validates the response,
                                 applies the shared sign-in policy, logs in
Super admin:
  GET  /api/auth/saml/config     current configuration + the SP URLs to give the IdP
  PUT  /api/auth/saml/config     save configuration (IdP metadata by paste or URL)

See core/saml_sp.py for the security model.
"""

import html
import json
import os
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..models.database import get_db, User
from ..core.auth import require_super_admin
from ..core.access import require_permission
from ..core.settings_store import load_settings, SETTINGS_FILE
from ..core import saml_sp
from .auth import _resolve_external_user, _sso_redirect

router = APIRouter(prefix="/api/auth/saml", tags=["saml"])

MAX_METADATA_BYTES = 2_000_000


def _cfg() -> dict:
    return load_settings().get("auth_providers", {}).get("saml", {}) or {}


def _base(cfg: dict, request: Request) -> str:
    return saml_sp.public_base_url(cfg, str(request.base_url))


def _error_page(message: str, status: int = 400) -> HTMLResponse:
    login = os.getenv("FRONTEND_URL", "").rstrip("/") + "/login"
    return HTMLResponse(status_code=status, content=(
        "<html><body style='font-family:sans-serif;background:#0f172a;color:#e2e8f0;"
        "padding:2rem;max-width:40rem'><h2>Sign-in didn't complete</h2>"
        f"<p>{html.escape(message)}</p><p><a style='color:#818cf8' href='{html.escape(login)}'>"
        "Back to sign in</a></p></body></html>"))


# ── Public ────────────────────────────────────────────────────────────────────

@router.get("/metadata")
def metadata(request: Request):
    cfg = _cfg()
    xml = saml_sp.sp_metadata_xml(cfg, _base(cfg, request))
    return Response(content=xml, media_type="application/samlmetadata+xml")


@router.get("/login")
def login(request: Request):
    cfg = _cfg()
    if not cfg.get("enabled"):
        return _error_page("SAML sign-in is not enabled.")
    try:
        return RedirectResponse(saml_sp.begin_login(cfg, _base(cfg, request)))
    except saml_sp.SamlError as e:
        return _error_page(str(e))


@router.post("/acs")
def acs(request: Request, SAMLResponse: str = Form(""), db: Session = Depends(get_db)):
    cfg = _cfg()
    if not cfg.get("enabled"):
        return _error_page("SAML sign-in is not enabled.")
    try:
        result = saml_sp.consume_response(cfg, _base(cfg, request), SAMLResponse)
        token = _resolve_external_user(result, db)["access_token"]
    except saml_sp.SamlError as e:
        return _error_page(str(e))
    except HTTPException as e:              # denied by the shared sign-in policy
        return _error_page(str(e.detail), status=e.status_code)
    return _sso_redirect(token)


# ── Admin configuration ───────────────────────────────────────────────────────

class SamlConfigIn(BaseModel):
    enabled: bool = False
    label: Optional[str] = None                 # login button text, e.g. "University SSO"
    sp_base_url: Optional[str] = None           # public URL, e.g. https://privacy.example.edu
    idp_metadata_xml: Optional[str] = None      # paste the IdP metadata, or…
    idp_metadata_url: Optional[str] = None      # …fetch it from a URL
    idp_entity_id: Optional[str] = None         # only if metadata lists several IdPs
    attr_email: Optional[str] = None            # override attribute names (comma-sep)
    attr_name: Optional[str] = None
    attr_groups: Optional[str] = None
    allowed_domains: Optional[str] = None
    required_groups: Optional[str] = None       # e.g. "staff,faculty" or "library-staff"
    default_role: Optional[str] = "parent"
    auto_provision: Optional[bool] = None


def _public_view(cfg: dict, request: Request) -> dict:
    base = _base(cfg, request)
    view = {k: cfg.get(k) for k in (
        "enabled", "label", "sp_base_url", "idp_metadata_url", "idp_entity_id",
        "attr_email", "attr_name", "attr_groups", "allowed_domains",
        "required_groups", "default_role", "auto_provision")}
    view["has_idp_metadata"] = bool((cfg.get("idp_metadata_xml") or "").strip())
    view["sp"] = saml_sp.sp_urls(base)
    view["idp_entity_ids"] = []
    if view["has_idp_metadata"]:
        from ..core.cert_monitor import saml_cert_status
        view["signing_cert"] = saml_cert_status(cfg)
        try:
            view["idp_entity_ids"] = saml_sp.idp_entity_ids(cfg, base)
        except Exception as e:
            view["metadata_error"] = str(e)
    return view


@router.get("/config")
def get_config(request: Request, _: User = Depends(require_permission("auth.providers"))):
    return _public_view(_cfg(), request)


@router.put("/config")
def save_config(body: SamlConfigIn, request: Request,
                _: User = Depends(require_permission("auth.providers"))):
    s = load_settings()
    ap = s.setdefault("auth_providers", {})
    cfg = dict(ap.get("saml", {}) or {})

    data = body.model_dump()
    url = (data.pop("idp_metadata_url") or "").strip()
    xml = (data.pop("idp_metadata_xml") or "").strip()
    for k, v in data.items():
        if v is not None:
            cfg[k] = v.strip() if isinstance(v, str) else v
    if url:
        cfg["idp_metadata_url"] = url
        try:
            import httpx
            r = httpx.get(url, timeout=15, follow_redirects=True)
            r.raise_for_status()
            if len(r.content) > MAX_METADATA_BYTES:
                raise HTTPException(400, "Metadata document is too large.")
            xml = r.text
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(400, f"Could not fetch IdP metadata: {e}")
    if xml:
        cfg["idp_metadata_xml"] = xml

    # Validate before saving: metadata must parse and contain an IdP.
    if cfg.get("idp_metadata_xml"):
        try:
            ids = saml_sp.idp_entity_ids(cfg, _base(cfg, request))
        except Exception as e:
            raise HTTPException(400, f"IdP metadata is not valid: {e}")
        if not ids:
            raise HTTPException(400, "The metadata does not describe an identity provider.")
    if cfg.get("enabled") and not cfg.get("idp_metadata_xml"):
        raise HTTPException(400, "Add the identity provider's metadata before enabling SAML.")

    ap["saml"] = cfg
    with open(SETTINGS_FILE, "w") as f:
        json.dump(s, f, indent=2)
    return _public_view(cfg, request)
