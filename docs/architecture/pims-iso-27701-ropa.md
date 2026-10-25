# ISO/IEC 27701:2019 Privacy Information Management & ROPA

This document details OpenOptOut's compliance with **ISO/IEC 27701:2019 (Privacy Information Management System — PIMS)** and **GDPR Article 30 / Article 35**.

---

## 1. Overview & Statutory Requirements

ISO/IEC 27701 extends ISO/IEC 27001 by establishing technical and organizational requirements for PII Controllers and PII Processors.

Under GDPR Article 30 and ISO/IEC 27701 Clause 7.2.5, organizations must maintain an up-to-date **Record of Processing Activities (ROPA)**. OpenOptOut exposes machine-readable and printable reports via:
* `GET /api/privacy/ropa`: Record of Processing Activities report.
* `GET /api/privacy/dpia`: Data Protection Impact Assessment matrix.

---

## 2. Record of Processing Activities (ROPA) Summary

The ROPA report details:
1. **Controller Information:** Self-hosting institution or family account holder.
2. **Processing Activities:**
   * Discovery & Exposure Reconnaissance (`PA-01`).
   * Opt-Out Submission & DRP Execution (`PA-02`).
   * Identity Vault Storage & Encryption (`PA-03`).
3. **Data Categories:** Names, residential addresses, emails, phone numbers, and DOBs. Explicitly excludes SSNs, IDs, and financial records.
4. **Recipients & Third Parties:** Direct broker gateways (80+ catalog plugins), DRP endpoints, and privacy-masked CAPTCHA proxies.
5. **Retention & Erasure Schedules:** 30-day retention floor for minor aux records; on-demand NIST SP 800-88 Cryptographic Erase.
6. **Technical & Organizational Measures (TOMs):** Documented encryption, sandbox isolation, and access logging.

