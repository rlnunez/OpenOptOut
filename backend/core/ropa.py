"""
ISO/IEC 27701:2019 Privacy Information Management System (PIMS) Generator.

Generates statutory privacy compliance documentation:
  1. Record of Processing Activities (ROPA) under GDPR Article 30 & ISO/IEC 27701 Cl. 7.2.5.
  2. Data Protection Impact Assessment (DPIA) under GDPR Article 35 & ISO/IEC 27701 Cl. 7.2.6.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .version import get_version


def generate_ropa_report(cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Generates a formal, machine-readable Record of Processing Activities (ROPA)
    conforming to GDPR Article 30 and ISO/IEC 27701:2019 Clause 7.2.5.
    """
    app_version = get_version()
    now_iso = datetime.now(timezone.utc).isoformat()
    cfg = cfg or {}
    branding = cfg.get("branding") or {}
    app_name = branding.get("app_name") or "OpenOptOut"

    return {
        "report_type": "Record of Processing Activities (ROPA)",
        "standards": ["ISO/IEC 27701:2019 Cl. 7.2.5", "GDPR Article 30"],
        "generated_at": now_iso,
        "appliance": {
            "name": app_name,
            "version": app_version,
            "deployment_mode": "Self-Hosted Privacy Appliance",
        },
        "controller": {
            "entity": "Self-Hosting Institution / Account Holder",
            "contact": "Instance Administrator (configured via Settings)",
            "dpo_contact": "Instance Privacy Officer",
            "representative": "Instance Administrator",
        },
        "processing_activities": [
            {
                "activity_id": "PA-01",
                "name": "Data Broker Discovery & Exposure Mapping",
                "purpose": "Identify active personal data listings on people-search and commercial data-broker sites.",
                "legal_basis": ["GDPR Art. 6(1)(a) Consent", "GDPR Art. 6(1)(f) Legitimate Interests"],
                "data_subjects": ["Account Holders", "Authorized Family Members", "Library Patrons"],
                "data_categories": ["Full Name", "City/State of Residence", "Phone Numbers", "Known Aliases"],
                "recipients": ["Local Search Bot Runners (Ephemeral Memory Only)"],
                "retention_period": "Retained until removal request execution or patron profile deletion",
            },
            {
                "activity_id": "PA-02",
                "name": "Opt-Out Request Compilation & Automated Submission",
                "purpose": "Exercise statutory opt-out, deletion, and do-not-sell rights under CCPA/CPRA, GDPR, and state laws.",
                "legal_basis": ["GDPR Art. 17 Right to Erasure", "CCPA/CPRA § 1798.105/120", "COPPA § 6502"],
                "data_subjects": ["Adult Consumers", "Minor Dependents under age 13 (Parental Authorization)"],
                "data_categories": ["Name", "Contact Address", "Disassociated Relay Email", "Listing URLs"],
                "recipients": ["Designated Data Brokers (Opt-Out Gateways)", "Data Rights Protocol (DRP) Endpoints"],
                "retention_period": "30 days for minor verification links; permanent crypto-shredding on demand",
            },
            {
                "activity_id": "PA-03",
                "name": "Identity Vault Storage & Cryptographic Protection",
                "purpose": "Secure long-term storage of patron identity profiles for recurring removal verification.",
                "legal_basis": ["GDPR Art. 6(1)(a) Explicit Consent", "ISO/IEC 27701 Privacy by Design"],
                "data_categories": ["AES-256-GCM Encrypted Names", "Addresses", "Hashed Search Indexes"],
                "never_collected": [
                    "Social Security Numbers (SSNs)",
                    "Government ID Card Images",
                    "Payment Card Details",
                    "Plaintext Passwords",
                ],
                "recipients": ["None (Stored in encrypted database only)"],
                "retention_period": "User-controlled; crypto-shredded immediately upon profile deletion",
            },
        ],
        "technical_and_organizational_measures": [
            "NIST SP 800-38D AES-256-GCM authenticated field encryption with epoch key versioning",
            "NIST SP 800-88 Rev. 1 media sanitization and SQLite WAL checkpoint truncation",
            "FIDO2 / WebAuthn Level 3 hardware-bound user verification and step-up authentication",
            "Process sandboxing with Linux bubblewrap namespaces, seccomp filters, and read-only filesystems",
            "Zero outbound analytics, marketing pixels, or third-party telemetry integrations",
            "W3C Global Privacy Control (GPC) universal opt-out preference header injection",
        ],
    }


def generate_dpia_assessment(cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Generates a Data Protection Impact Assessment (DPIA) matrix
    conforming to GDPR Article 35 and ISO/IEC 27701:2019 Clause 7.2.6.
    """
    app_version = get_version()
    now_iso = datetime.now(timezone.utc).isoformat()

    return {
        "assessment_type": "Data Protection Impact Assessment (DPIA)",
        "standards": ["ISO/IEC 27701:2019 Cl. 7.2.6", "GDPR Article 35"],
        "evaluated_version": app_version,
        "assessment_date": now_iso,
        "overall_risk_rating": "LOW (Controlled via Disassociated Processing & Cryptographic Erasure)",
        "risk_evaluations": [
            {
                "risk_id": "RSK-01",
                "description": "Exposure of family or minor PII during automated headless browser form filling.",
                "inherent_risk": "HIGH",
                "mitigations": [
                    "Minimal field transmission: only broker-requested fields are sent.",
                    "Ephemeral runner isolation: Playwright browser profiles are destroyed after each run.",
                    "No local disk persistence of unencrypted member payload files.",
                ],
                "residual_risk": "LOW",
            },
            {
                "risk_id": "RSK-02",
                "description": "Leakage of personal details in CAPTCHA challenge solving requests.",
                "inherent_risk": "HIGH",
                "mitigations": [
                    "Automated visual challenge masking (captcha_privacy.py) blacks out PII before solver egress.",
                    "No names, phone numbers, or email addresses ever sent in solver metadata.",
                ],
                "residual_risk": "LOW",
            },
            {
                "risk_id": "RSK-03",
                "description": "Residual storage of deleted patron records in database transaction logs.",
                "inherent_risk": "MEDIUM",
                "mitigations": [
                    "NIST SP 800-88 Rev. 1 Cryptographic Erase execution.",
                    "PRAGMA wal_checkpoint(TRUNCATE) eliminates historic WAL frame residuals on disk.",
                    "Incremental vacuuming reclaims and zeroizes unallocated page space.",
                ],
                "residual_risk": "VERY LOW",
            },
        ],
    }
