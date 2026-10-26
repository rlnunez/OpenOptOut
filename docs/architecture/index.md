# OpenOptOut Architecture & Standards Guide

This directory contains OpenOptOut's core architectural specifications, formal governance mappings, and compliance frameworks. Each document details how OpenOptOut enforces security, privacy engineering, cryptographic rigor, and institutional standards across all system components.

---

## Architecture Navigation Index

```
┌─────────────────────────────────┬─────────────────────────────────┐
│  Security & Supply Chain        │  Privacy Engineering            │
├─────────────────────────────────┼─────────────────────────────────┤
│ • ISO/IEC 27001:2022 ISMS & SoA │ • ISO/IEC 29100 Privacy Engine  │
│ • CISA Secure by Design (RFC9116)│ • NIST Privacy Framework v1.0   │
│ • Marketplace Security (Item 8) │ • ISO/IEC 27701 PIMS ROPA/DPIA  │
│ • SLSA Level 3 Supply Chain     │ • FERPA Student Privacy (CFR 99)│
│                                 │ • NIST SP 800-88 Sanitization   │
├─────────────────────────────────┼─────────────────────────────────┤
│  Identity, Auth & Key Management│  AI Governance & Trust          │
├─────────────────────────────────┼─────────────────────────────────┤
│ • NIST SP 800-63A/B/C (IAL/FAL) │ • NIST AI RMF 1.0 Risk Engine   │
│ • NIST SP 800-57 Key Epochs     │ • ISO/IEC 42001:2023 AI ISMS    │
│ • RFC 9449 DPoP Replay Defense  │ • Air-Gapped Local Model Rules  │
│ • RFC 7643/7644 SCIM 2.0 Sync   │ • Prompt Injection Boundaries   │
└─────────────────────────────────┴─────────────────────────────────┘
```

---

## 1. Information Security Management & Supply Chain

- **[ISO/IEC 27001:2022 ISMS Statement of Applicability](isms-iso-27001.md)**
  Comprehensive information security architecture addressing all 93 controls across Annex A: Organizational (37), People (8), Physical (14), and Technological (34), establishing zero-trust container baselines and verifiable audit evidence.
- **[CISA Secure by Design Principles](cisa-secure-by-design.md)**
  Alignment with joint guidance from CISA, NSA, FBI, and international cyber authorities: default-deny credentials, vulnerability class elimination, memory hygiene, RFC 9116 `security.txt`, and automated CycloneDX SBOM generation.
- **[Marketplace Security Invariants](marketplace-security-invariants.md)**
  Formal specification of the six non-negotiable architectural invariants governing the plugin ecosystem and community add-on marketplace (Roadmap Item #8): declarative pure data, Cosign/Sigstore cryptographic signatures, tiered trust publishers, Bubblewrap/seccomp syscall sandboxing, emergency CRL revocation, and air-gapped registry mirroring.
- **[SLSA Level 3 & Supply Chain Security](slsa-supply-chain.md)**
  OpenSSF Supply-chain Levels for Software Artifacts (SLSA) Level 3 build provenance: isolated GitHub Actions runners, non-falsifiable in-toto attestations, cryptographic digest pinning for all base images, and zero-token runtime execution.

---

## 2. Privacy Engineering & Data Protection

- **[ISO/IEC 29100 Privacy Framework Alignment](privacy-framework-29100.md)**
  Architectural mapping of OpenOptOut's role as a Data Processor/Collector to the 11 ISO/IEC 29100 privacy principles, defining identity vault cryptographic envelopes, data minimization boundaries, and tenant isolation models.
- **[NIST Privacy Framework Profile](nist-privacy-profile.md)**
  Formal mapping to the NIST Privacy Framework Version 1.0 and CSF Privacy Profile across Identify-P, Govern-P, Control-P, Communicate-P, and Protect-P, providing enterprise audit cross-references.
- **[Privacy Information Management (ROPA & DPIA)](pims-iso-27701-ropa.md)**
  ISO/IEC 27701:2019 and GDPR Article 30/35 compliance documentation: automated Record of Processing Activities (ROPA) generation, Data Protection Impact Assessment (DPIA) triggers, and lawful basis accounting.
- **[FERPA Alignment & Student Privacy](ferpa-alignment.md)**
  Institutional educational compliance guide under 34 CFR Part 99: qualifying under the School Official exception, student directory information opt-outs, FERPA-compliant SCIM automation, and zero-PII campus analytics.
- **[Media Sanitization & Cryptographic Erasure](media-sanitization-800-88.md)**
  NIST SP 800-88 Rev. 1 media sanitization architecture: per-record cryptographic shredding (ephemeral key destruction), WAL purge routines, and automated, signed Certificate of Sanitization issuance.

---

## 3. Digital Identity, Authentication & Cryptography

- **[Digital Identity Guidelines (NIST SP 800-63A/B/C)](digital-identity-800-63.md)**
  Identity Assurance Level (IAL1/IAL2), Authenticator Assurance Level (AAL1/AAL2/AAL3), and Federation Assurance Level (FAL1/FAL2/FAL3) framework establishing the cryptographic base for Federated Re-Anchoring (Roadmap Item #72).
- **[Key Management & Epoch Versioning](nist-key-management-800-57.md)**
  NIST SP 800-57 Part 1 Rev. 5 cryptoperiod management: HKDF-SHA256 epoch key derivation, versioned ciphertexts (`gcm:v{N}:`), non-destructive key rotation, and automated background re-encryption passes.
- **[DPoP Sender-Constrained Tokens](dpop-rfc-9449.md)**
  RFC 9449 Demonstrating Proof-of-Possession: binding access tokens to client ephemeral key pairs, preventing token theft, replay attacks, and man-in-the-middle impersonation.
- **[SCIM 2.0 Enterprise Identity Synchronization](scim-enterprise-identity.md)**
  RFC 7643 / RFC 7644 System for Cross-domain Identity Management: automated provisioning, department/branch filtering, immediate account deprovisioning, and global user-session revocation.

---

## 4. Artificial Intelligence Governance

- **[AI Governance Guide (NIST AI RMF 1.0 & ISO/IEC 42001:2023)](ai-governance-nist-iso.md)**
  Governance architecture governing AI-assisted broker spec drafting: prompt injection isolation, PII pre-flight scrubbing, synthetic rehearsal verification, local/air-gapped model enforcement (Ollama/LM Studio), and continuous telemetry tracking.

---

## Cross-References

- **[User & Family Documentation](../user/index.md)**
- **[Administrator & Operations Guide](../admin/index.md)**
- **[Developer Internal Guide](../dev/index.md)**
- **[Security Policy & RFC 9116](../../SECURITY.md)**
- **[Accessibility & Section 508 VPAT](../../ACCESSIBILITY.md)**

