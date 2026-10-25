"""
SCIM 2.0 (System for Cross-domain Identity Management) Implementation.

Conforms to:
  - RFC 7643: SCIM Core Schema
  - RFC 7644: SCIM Protocol

Provides automated enterprise and institutional provisioning, updating, and de-provisioning
for library systems and municipal authorities integrating with Okta, Microsoft Entra ID,
Google Workspace, or PingIdentity.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ..core import auth as auth_core, people
from ..core.database import get_db
from ..core.settings_store import get_secret_key, load_settings
from ..models import database as m

router = APIRouter(prefix="/api/scim/v2", tags=["SCIM 2.0"])

SCIM_USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"
SCIM_GROUP_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:Group"
SCIM_LIST_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
SCIM_ERROR_SCHEMA = "urn:ietf:params:scim:api:messages:2.0:Error"
SCIM_CONFIG_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"
SCIM_RESOURCE_TYPE_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:ResourceType"
SCIM_CONTENT_TYPE = "application/scim+json"


def require_scim_auth(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> None:
    """
    Authenticate SCIM API calls via Bearer token (RFC 7644 Section 2).
    Accepts system admin JWT or a configured SCIM provisioning bearer token.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization[7:].strip()
    secret = get_secret_key()
    cfg = load_settings() or {}
    scim_token = cfg.get("auth", {}).get("scim_bearer_token")

    # 1. Match explicit SCIM token if configured
    if scim_token and token == scim_token:
        return

    # 2. Or validate as admin JWT session token
    user = auth_core.resolve_user_from_token(token, db)
    if user and getattr(user, "role", None) == "admin":
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid SCIM bearer token.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _scim_user_representation(user: m.User, req: Optional[Request] = None) -> Dict[str, Any]:
    """Serialize a database User model into an RFC 7643 SCIM User representation."""
    base_url = str(req.base_url).rstrip("/") if req else ""
    user_id = str(user.id)
    email = user.email or f"user-{user_id}@openoptout.invalid"
    full_name = user.full_name or email.split("@")[0]
    parts = full_name.split(" ", 1)
    given_name = parts[0]
    family_name = parts[1] if len(parts) > 1 else ""

    now_iso = datetime.now(timezone.utc).isoformat()
    return {
        "schemas": [SCIM_USER_SCHEMA],
        "id": user_id,
        "userName": email,
        "name": {
            "formatted": full_name,
            "givenName": given_name,
            "familyName": family_name,
        },
        "displayName": full_name,
        "emails": [
            {
                "value": email,
                "type": "work",
                "primary": True,
            }
        ],
        "active": getattr(user, "is_active", True) if hasattr(user, "is_active") else True,
        "groups": [
            {
                "value": getattr(user, "role", "patron") or "patron",
                "display": (getattr(user, "role", "patron") or "patron").capitalize(),
            }
        ],
        "meta": {
            "resourceType": "User",
            "created": now_iso,
            "lastModified": now_iso,
            "location": f"{base_url}/api/scim/v2/Users/{user_id}",
        },
    }


# ── RFC 7643 Discovery Endpoints ──────────────────────────────────────────────

@router.get("/ServiceProviderConfig", response_class=JSONResponse)
def get_service_provider_config():
    """RFC 7643 Section 5: Specification for Service Provider Configuration."""
    return JSONResponse(
        content={
            "schemas": [SCIM_CONFIG_SCHEMA],
            "documentationUri": "https://github.com/rlnunez/OpenOptOut",
            "patch": {"supported": True},
            "bulk": {"supported": False, "maxOperations": 0, "maxPayloadSize": 0},
            "filter": {"supported": True, "maxResults": 100},
            "changePassword": {"supported": False},
            "sort": {"supported": False},
            "etag": {"supported": False},
            "authenticationSchemes": [
                {
                    "name": "OAuth Bearer Token",
                    "description": "Authentication scheme using the OAuth Bearer Token Standard",
                    "specUri": "http://www.rfc-editor.org/info/rfc6750",
                    "type": "oauthbearertoken",
                    "primary": True,
                }
            ],
            "meta": {
                "resourceType": "ServiceProviderConfig",
                "created": "2026-10-24T00:00:00Z",
                "lastModified": "2026-10-24T00:00:00Z",
            },
        },
        media_type=SCIM_CONTENT_TYPE,
    )


@router.get("/Schemas", response_class=JSONResponse)
def get_schemas():
    """RFC 7643 Section 7: Introspect supported SCIM schemas."""
    return JSONResponse(
        content={
            "schemas": [SCIM_LIST_SCHEMA],
            "totalResults": 2,
            "itemsPerPage": 2,
            "startIndex": 1,
            "Resources": [
                {
                    "id": SCIM_USER_SCHEMA,
                    "name": "User",
                    "description": "Core User Resource Schema",
                    "schema": SCIM_USER_SCHEMA,
                },
                {
                    "id": SCIM_GROUP_SCHEMA,
                    "name": "Group",
                    "description": "Core Group Resource Schema",
                    "schema": SCIM_GROUP_SCHEMA,
                },
            ],
        },
        media_type=SCIM_CONTENT_TYPE,
    )


@router.get("/ResourceTypes", response_class=JSONResponse)
def get_resource_types(request: Request):
    """RFC 7643 Section 6: Introspect supported SCIM resource types."""
    base_url = str(request.base_url).rstrip("/")
    return JSONResponse(
        content={
            "schemas": [SCIM_LIST_SCHEMA],
            "totalResults": 2,
            "itemsPerPage": 2,
            "startIndex": 1,
            "Resources": [
                {
                    "schemas": [SCIM_RESOURCE_TYPE_SCHEMA],
                    "id": "User",
                    "name": "User",
                    "endpoint": f"{base_url}/api/scim/v2/Users",
                    "description": "User Account Resource",
                    "schema": SCIM_USER_SCHEMA,
                },
                {
                    "schemas": [SCIM_RESOURCE_TYPE_SCHEMA],
                    "id": "Group",
                    "name": "Group",
                    "endpoint": f"{base_url}/api/scim/v2/Groups",
                    "description": "User Group Resource",
                    "schema": SCIM_GROUP_SCHEMA,
                },
            ],
        },
        media_type=SCIM_CONTENT_TYPE,
    )


# ── RFC 7644 User Management Endpoints ────────────────────────────────────────

@router.get("/Users", response_class=JSONResponse)
def list_users(
    request: Request,
    filter: Optional[str] = Query(None),
    startIndex: int = Query(1, ge=1),
    count: int = Query(50, ge=1, le=100),
    _: None = Depends(require_scim_auth),
    db: Session = Depends(get_db),
):
    """
    RFC 7644 Section 3.4.2: Query users with pagination and simple filtering.
    Supports filters like: `userName eq "alice@example.org"` or `emails.value eq "..."`.
    """
    query = db.query(m.User)
    if filter:
        # Match 'userName eq "value"' or 'emails.value eq "value"'
        m_filter = re.search(r'(?:userName|emails\.value)\s+eq\s+["\']([^"\']+)["\']', filter, re.IGNORECASE)
        if m_filter:
            target_email = m_filter.group(1).strip().lower()
            query = query.filter(m.User.email == target_email)

    total_results = query.count()
    users = query.offset(startIndex - 1).limit(count).all()
    resources = [_scim_user_representation(u, request) for u in users]

    return JSONResponse(
        content={
            "schemas": [SCIM_LIST_SCHEMA],
            "totalResults": total_results,
            "startIndex": startIndex,
            "itemsPerPage": len(resources),
            "Resources": resources,
        },
        media_type=SCIM_CONTENT_TYPE,
    )


@router.get("/Users/{user_id}", response_class=JSONResponse)
def get_user(
    user_id: int,
    request: Request,
    _: None = Depends(require_scim_auth),
    db: Session = Depends(get_db),
):
    """RFC 7644 Section 3.4.1: Retrieve single user by ID."""
    user = db.query(m.User).filter(m.User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found.",
        )
    return JSONResponse(
        content=_scim_user_representation(user, request),
        media_type=SCIM_CONTENT_TYPE,
    )


@router.post("/Users", status_code=status.HTTP_201_CREATED, response_class=JSONResponse)
def create_user(
    payload: Dict[str, Any],
    request: Request,
    _: None = Depends(require_scim_auth),
    db: Session = Depends(get_db),
):
    """RFC 7644 Section 3.3: Provision a new user via SCIM."""
    user_name = payload.get("userName")
    emails = payload.get("emails") or []
    email = user_name or (emails[0].get("value") if emails else None)
    if not email:
        raise HTTPException(status_code=400, detail="userName or email is required")
    email = email.strip().lower()

    existing = db.query(m.User).filter(m.User.email == email).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"User with email '{email}' already exists.")

    name_obj = payload.get("name") or {}
    full_name = payload.get("displayName") or name_obj.get("formatted")
    if not full_name:
        first = name_obj.get("givenName", "")
        last = name_obj.get("familyName", "")
        full_name = f"{first} {last}".strip() or email.split("@")[0]

    # Create User
    new_user = m.User(
        email=email,
        full_name=full_name,
        role="patron",
        email_verified=True,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=_scim_user_representation(new_user, request),
        media_type=SCIM_CONTENT_TYPE,
    )


@router.patch("/Users/{user_id}", response_class=JSONResponse)
def patch_user(
    user_id: int,
    payload: Dict[str, Any],
    request: Request,
    _: None = Depends(require_scim_auth),
    db: Session = Depends(get_db),
):
    """
    RFC 7644 Section 3.5.2: Update / Deactivate user.
    Handles operations such as `{"op": "replace", "path": "active", "value": false}`.
    """
    user = db.query(m.User).filter(m.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found.")

    operations = payload.get("Operations") or []
    for op in operations:
        op_type = str(op.get("op", "")).lower()
        path = str(op.get("path", "")).lower()
        val = op.get("value")

        if op_type in ("replace", "add"):
            if path == "active" or (isinstance(val, dict) and "active" in val):
                active_val = val if path == "active" else val["active"]
                if hasattr(user, "is_active"):
                    user.is_active = bool(active_val)
                # If deactivating, revoke all active sessions immediately
                if not bool(active_val):
                    db.query(m.UserSession).filter(m.UserSession.user_id == user.id).delete(synchronize_session=False)

            if path == "displayname" and isinstance(val, str):
                user.full_name = val
            elif path == "username" and isinstance(val, str):
                user.email = val.strip().lower()

    db.commit()
    db.refresh(user)
    return JSONResponse(
        content=_scim_user_representation(user, request),
        media_type=SCIM_CONTENT_TYPE,
    )


@router.delete("/Users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    _: None = Depends(require_scim_auth),
    db: Session = Depends(get_db),
):
    """
    RFC 7644 Section 3.6: Deprovision / Crypto-shred a user via SCIM.
    Executes full NIST SP 800-88 Rev. 1 compliant crypto-shredding and DB removal.
    """
    user = db.query(m.User).filter(m.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found.")

    people.delete_person(db, user)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── RFC 7644 Groups Endpoints ─────────────────────────────────────────────────

@router.get("/Groups", response_class=JSONResponse)
def list_groups(
    _: None = Depends(require_scim_auth),
    db: Session = Depends(get_db),
):
    """RFC 7644 Section 3.4.2: List system roles as SCIM groups."""
    groups = [
        {"id": "admin", "displayName": "Administrators"},
        {"id": "staff", "displayName": "Staff"},
        {"id": "patron", "displayName": "Patrons"},
    ]
    return JSONResponse(
        content={
            "schemas": [SCIM_LIST_SCHEMA],
            "totalResults": len(groups),
            "startIndex": 1,
            "itemsPerPage": len(groups),
            "Resources": groups,
        },
        media_type=SCIM_CONTENT_TYPE,
    )
