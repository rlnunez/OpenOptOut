"""
Data Rights Protocol (DRP) schemas and identity models.

Implements the standard Data Rights Protocol technical specification (v0.9/v1.0)
developed by Consumer Reports Innovation Lab, Electronic Frontier Foundation,
and consumer privacy organizations.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import re


DRP_VERSION = "0.9"

# Standard DRP privacy regimes
REGIMES = ("ccpa", "gdpr", "coppa", "general", "lgpd")

# Standard DRP exercise action types
VALID_RIGHTS = (
    "sale:opt-out",
    "deletion",
    "access",
    "access:categories",
    "access:specific",
)

# Standard DRP request lifecycle statuses
STATUSES = (
    "in_progress",
    "completed",
    "user_action_required",
    "denied",
    "expired",
    "revoked",
)


@dataclass
class DrpIdentity:
    """
    Consumer identity container formatted for Data Rights Protocol ingestion.
    Never logged or exposed unencrypted.
    """
    full_name: str = ""
    email: str = ""
    phone: str = ""
    street_address: str = ""
    city: str = ""
    state: str = ""
    postal_code: str = ""
    country: str = "US"

    def to_drp_dict(self) -> Dict[str, Any]:
        """Convert into canonical DRP identity dictionary."""
        d: Dict[str, Any] = {}
        if self.full_name:
            d["name"] = self.full_name
        if self.email:
            d["email"] = self.email
        if self.phone:
            # Clean non-digits while keeping leading +
            cleaned = re.sub(r"[^\d+]", "", self.phone)
            d["phone"] = cleaned
        
        address_parts: Dict[str, str] = {}
        if self.street_address:
            address_parts["street"] = self.street_address
        if self.city:
            address_parts["city"] = self.city
        if self.state:
            address_parts["state"] = self.state
        if self.postal_code:
            address_parts["postal_code"] = self.postal_code
        if self.country:
            address_parts["country"] = self.country

        if address_parts:
            d["address"] = address_parts

        return d


@dataclass
class DrpExerciseRequest:
    """Payload sent to a Covered Business's DRP exercise endpoint."""
    regime: str
    exercise: List[str]
    identity: Dict[str, Any]
    relationships: List[str] = field(default_factory=lambda: ["consumer"])
    status_callback: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=lambda: {"version": DRP_VERSION, "agent": "OpenOptOut"})

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "regime": self.regime,
            "exercise": list(self.exercise),
            "identity": dict(self.identity),
            "relationships": list(self.relationships),
            "meta": dict(self.meta),
        }
        if self.status_callback:
            payload["status_callback"] = self.status_callback
        return payload


@dataclass
class DrpExerciseResponse:
    """Response returned by a Covered Business after receiving a DRP request."""
    ok: bool
    request_id: str = ""
    status: str = "in_progress"
    received_at: str = ""
    expected_by: str = ""
    reason: str = ""
    user_action_url: str = ""
    raw_response: Dict[str, Any] = field(default_factory=dict)
    error: str = ""


@dataclass
class DrpStatusResponse:
    """Response from querying a DRP request status endpoint."""
    ok: bool
    request_id: str = ""
    status: str = "in_progress"
    reason: str = ""
    updated_at: str = ""
    raw_response: Dict[str, Any] = field(default_factory=dict)
    error: str = ""

