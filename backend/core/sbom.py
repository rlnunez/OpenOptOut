"""
Software Bill of Materials (SBOM) Generator.

Aligns OpenOptOut with:
  1. CISA "Secure by Design" Product Principles (Goal 7: Supply Chain Dependency Transparency).
  2. ISO/IEC 5962:2021 (SPDX 2.3 Specification).
  3. NTIA Minimum Elements for SBOM (Dependency tree and relationships).
  4. CycloneDX 1.5 JSON Specification.

Produces machine-readable SBOMs in both CycloneDX 1.5 JSON and SPDX 2.3 JSON formats.
"""

from __future__ import annotations

import importlib.metadata as md
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Any, Set, Tuple

from .version import get_version


def _clean_spdx_id(name: str) -> str:
    """Produces a valid SPDX ID fragment matching [A-Za-z0-9_.-]+"""
    return re.sub(r"[^A-Za-z0-9\.\-]", "-", name)


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


def _get_components_and_dependencies() -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Set[str]]]:
    """
    Inspect installed distributions and requirements.txt, returning
    (components_map, dependencies_map) for dependency relationship tracking.
    """
    components_map: Dict[str, Dict[str, Any]] = {}
    dep_map: Dict[str, Set[str]] = {}

    # 1. Live installed distributions via standard library importlib.metadata
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
            # Extract declared requirements for dependency graph
            deps: Set[str] = set()
            if dist.requires:
                for req_str in dist.requires:
                    m = re.match(r"^([A-Za-z0-9_\-\.]+)", req_str.strip())
                    if m:
                        dep_name = m.group(1).lower()
                        # Exclude extra markers (e.g. 'extra == ...') if desired, or include package
                        if dep_name != name:
                            deps.add(dep_name)
            if deps:
                dep_map[name] = deps
    except Exception:
        pass

    # 2. Inspect declared requirements.txt for pinned project dependencies
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

    return components_map, dep_map


def generate_cyclonedx_sbom() -> Dict[str, Any]:
    """
    Generate a CycloneDX 1.5 JSON Software Bill of Materials.
    Includes OpenOptOut core appliance metadata, runtime dependencies, and NTIA dependency graph.
    """
    app_version = get_version()
    components_map, dep_map = _get_components_and_dependencies()
    sorted_components = sorted(components_map.values(), key=lambda c: c["name"])

    # Build CycloneDX dependency elements (NTIA Minimum Elements)
    root_ref = f"pkg:github/rlnunez/openoptout@{app_version}"
    dependencies_list: List[Dict[str, Any]] = [
        {
            "ref": root_ref,
            "dependsOn": [c["purl"] for c in sorted_components],
        }
    ]
    for comp in sorted_components:
        name = comp["name"]
        if name in dep_map:
            child_purls = [components_map[d]["purl"] for d in dep_map[name] if d in components_map]
            if child_purls:
                dependencies_list.append({
                    "ref": comp["purl"],
                    "dependsOn": child_purls,
                })

    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{uuid.uuid4()}",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(),
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
                "purl": root_ref,
            },
        },
        "components": sorted_components,
        "dependencies": dependencies_list,
    }


def generate_spdx_sbom() -> Dict[str, Any]:
    """
    Generate an ISO/IEC 5962:2021 (SPDX 2.3) compliant JSON Software Bill of Materials.
    Fulfills NTIA Minimum Elements for SBOM dependency tracking.
    """
    app_version = get_version()
    components_map, dep_map = _get_components_and_dependencies()
    doc_uuid = uuid.uuid4()
    doc_namespace = f"https://github.com/rlnunez/OpenOptOut/spdxdocs/openoptout-{app_version}-{doc_uuid}"
    root_spdx_id = "SPDXRef-Package-openoptout"

    # Root application package
    packages: List[Dict[str, Any]] = [
        {
            "SPDXID": root_spdx_id,
            "name": "openoptout",
            "versionInfo": app_version,
            "supplier": "Organization: OpenOptOut Community",
            "downloadLocation": "https://github.com/rlnunez/OpenOptOut",
            "filesAnalyzed": False,
            "homepage": "https://github.com/rlnunez/OpenOptOut",
            "licenseConcluded": "AGPL-3.0-only",
            "licenseDeclared": "AGPL-3.0-only",
            "copyrightText": "Copyright (c) OpenOptOut Authors",
            "summary": "Self-hosted personal data removal and privacy automation appliance",
            "externalRefs": [
                {
                    "referenceCategory": "PACKAGE-MANAGER",
                    "referenceType": "purl",
                    "referenceLocator": f"pkg:github/rlnunez/openoptout@{app_version}",
                }
            ],
        }
    ]

    relationships: List[Dict[str, Any]] = [
        {
            "spdxElementId": "SPDXRef-DOCUMENT",
            "relatedSpdxElement": root_spdx_id,
            "relationshipType": "DESCRIBES",
        }
    ]

    # Add components
    for comp in sorted(components_map.values(), key=lambda c: c["name"]):
        pkg_spdx_id = f"SPDXRef-Package-{_clean_spdx_id(comp['name'])}"
        packages.append({
            "SPDXID": pkg_spdx_id,
            "name": comp["name"],
            "versionInfo": comp["version"],
            "supplier": "NOASSERTION",
            "downloadLocation": "NOASSERTION",
            "filesAnalyzed": False,
            "licenseConcluded": "NOASSERTION",
            "licenseDeclared": "NOASSERTION",
            "copyrightText": "NOASSERTION",
            "externalRefs": [
                {
                    "referenceCategory": "PACKAGE-MANAGER",
                    "referenceType": "purl",
                    "referenceLocator": comp["purl"],
                }
            ],
        })
        relationships.append({
            "spdxElementId": root_spdx_id,
            "relatedSpdxElement": pkg_spdx_id,
            "relationshipType": "DEPENDS_ON",
        })

    # Add inter-package dependencies
    for name, deps in dep_map.items():
        src_id = f"SPDXRef-Package-{_clean_spdx_id(name)}"
        for dep in deps:
            if dep in components_map:
                target_id = f"SPDXRef-Package-{_clean_spdx_id(dep)}"
                relationships.append({
                    "spdxElementId": src_id,
                    "relatedSpdxElement": target_id,
                    "relationshipType": "DEPENDS_ON",
                })

    return {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": "openoptout",
        "documentNamespace": doc_namespace,
        "creationInfo": {
            "created": datetime.now(timezone.utc).isoformat(),
            "creators": [
                f"Tool: openoptout-sbom-generator-{app_version}",
                "Organization: OpenOptOut Community",
            ],
            "licenseListVersion": "3.22",
        },
        "packages": packages,
        "relationships": relationships,
    }
