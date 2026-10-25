"""
Software Bill of Materials (SBOM) Generator.

Aligns OpenOptOut with CISA "Secure by Design" Product Principles (Goal 7:
Supply Chain Dependency Transparency).

Produces a CycloneDX 1.5 JSON formatted Software Bill of Materials containing
all application components, declared libraries, runtime dependencies, licenses,
and Package URL (purl) identifiers.
"""

from __future__ import annotations

import importlib.metadata as md
import os
import re
import uuid
from datetime import datetime
from typing import Dict, List, Any

from .version import get_version


def _parse_requirements_file(path: str) -> List[Dict[str, str]]:
    """Parse a pip requirements.txt file for declared dependencies."""
    components = []
    if not os.path.isfile(path):
        return components
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # Match name==version (ignoring extras like [standard] or [email])
                m = re.match(r"^([A-Za-z0-9_\-\.]+)(?:\[[^\]]+\])?==([A-Za-z0-9_\-\.]+)", line)
                if m:
                    name = m.group(1).lower()
                    version = m.group(2)
                    components.append({
                        "name": name,
                        "version": version,
                        "purl": f"pkg:pypi/{name}@{version}",
                    })
    except Exception:
        pass
    return components


def generate_cyclonedx_sbom() -> Dict[str, Any]:
    """
    Generate a CycloneDX 1.5 JSON Software Bill of Materials.
    Includes OpenOptOut core appliance metadata and all Python runtime dependencies.
    """
    app_version = get_version()
    components_map: Dict[str, Dict[str, Any]] = {}

    # 1. Inspect live installed packages via standard library importlib.metadata
    try:
        for dist in md.distributions():
            raw_name = dist.metadata.get("Name")
            if not raw_name:
                continue
            name = raw_name.lower()
            version = dist.version
            components_map[name] = {
                "type": "library",
                "name": name,
                "version": version,
                "purl": f"pkg:pypi/{name}@{version}",
            }
    except Exception:
        pass

    # 2. Inspect declared requirements.txt for pinned dependencies
    backend_reqs = os.path.join(os.path.dirname(os.path.dirname(__file__)), "requirements.txt")
    for req in _parse_requirements_file(backend_reqs):
        name = req["name"]
        if name not in components_map:
            components_map[name] = {
                "type": "library",
                "name": name,
                "version": req["version"],
                "purl": req["purl"],
            }

    sorted_components = sorted(components_map.values(), key=lambda c: c["name"])

    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{uuid.uuid4()}",
        "version": 1,
        "metadata": {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "tools": [
                {
                    "vendor": "OpenOptOut",
                    "name": "openoptout-sbom-generator",
                    "version": app_version,
                }
            ],
            "component": {
                "type": "application",
                "name": "openoptout",
                "version": app_version,
                "description": "Self-hosted personal data removal and privacy automation appliance",
                "licenses": [
                    {"license": {"id": "AGPL-3.0-only"}}
                ],
                "purl": f"pkg:github/rlnunez/openoptout@{app_version}",
            },
        },
        "components": sorted_components,
    }

