"""
OASIS Common Security Advisory Framework (CSAF) 2.0 Implementation.

Serves CSAF 2.0 Provider Metadata conforming to the OASIS Standard (Section 7: Provider Metadata),
enabling enterprise vulnerability scanning platforms, municipal SIEMs, and CISA automated systems
to discover machine-readable security advisories.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict


def get_csaf_provider_metadata() -> Dict[str, Any]:
    """
    Returns the OASIS CSAF 2.0 Provider Metadata document.
    """
    return {
        "canonical_url": "https://raw.githubusercontent.com/rlnunez/OpenOptOut/main/.well-known/csaf/provider-metadata.json",
        "csaf_version": "2.0",
        "last_updated": "2026-10-24T00:00:00.000Z",
        "publisher": {
            "category": "vendor",
            "name": "OpenOptOut Project",
            "namespace": "https://github.com/rlnunez/OpenOptOut",
            "contact_details": "https://github.com/rlnunez/OpenOptOut/security/advisories/new",
            "issuing_authority": "OpenOptOut Security Team",
        },
        "distributions": [
            {
                "directory_url": "https://raw.githubusercontent.com/rlnunez/OpenOptOut/main/.well-known/csaf/",
            }
        ],
        "security_txt": "https://raw.githubusercontent.com/rlnunez/OpenOptOut/main/.well-known/security.txt",
    }

