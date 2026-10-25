# OpenSSF SLSA Level 3 & Supply Chain Security

This document details OpenOptOut's alignment with the **OpenSSF Supply-chain Levels for Software Artifacts (SLSA) v1.0 Level 3** specification and **Sigstore / Cosign** container signing.

---

## 1. Overview & Purpose

As a self-hosted privacy automation appliance handling sensitive personal records, OpenOptOut must be protected against supply chain tampering, unauthorized artifact modification, and build pipeline compromises.

SLSA Level 3 guarantees that all published container images and release artifacts are:
1. **Produced on a dedicated, hardened build platform** (GitHub Actions hosted runners).
2. **Accompanied by non-falsifiable cryptographic provenance attestations** generated via Sigstore transparency logs.
3. **Signed keylessly via OpenID Connect (OIDC)**, enabling operators to verify that a running container image originated from this exact repository and Git commit.

---

## 2. SLSA Level 3 Security Controls

| SLSA Requirement | OpenOptOut Implementation | Verification |
| :--- | :--- | :--- |
| **Source: Version Controlled** | Git repository hosted on GitHub with branch protection rules. | Signed Git commits and tags (`v*`). |
| **Source: Verified History** | Every change is recorded in immutable commit logs with no history rewriting. | `git log --show-signature` |
| **Build: Build Service** | Builds run strictly in GitHub Actions isolated runners (`ubuntu-latest`). | `.github/workflows/build-provenance.yml` |
| **Build: Build as Code** | Build definition is versioned in Dockerfiles and workflow YAML. | `backend/Dockerfile` |
| **Build: Ephemeral Environment** | Clean container and runner provisioned for every workflow run. | GitHub Actions runner lifecycle |
| **Build: Isolated** | Build steps cannot interact with concurrent builds or persistent runner state. | Ephemeral runner VM |
| **Provenance: Available** | Cryptographic provenance attestation published alongside image. | `actions/attest-build-provenance@v2` |
| **Provenance: Authenticated** | Attestation signed with GitHub's OIDC certificate authority. | Sigstore Fulcio & Rekor |
| **Provenance: Non-falsifiable** | Attestation generated directly by the build service, not user code. | GitHub Attestations API |

---

## 3. Container Verification Guide for Operators

Self-hosting administrators and library IT departments can cryptographically verify container authenticity prior to deployment:

### Step 1: Verify SLSA Provenance Attestation using GitHub CLI

```bash
gh attestation verify oci://ghcr.io/rlnunez/openoptout/backend:<tag> \
  --owner rlnunez
```

### Step 2: Verify Image Signature using Cosign

```bash
cosign verify \
  --certificate-identity-regexp "https://github.com/rlnunez/OpenOptOut/" \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
  ghcr.io/rlnunez/openoptout/backend:<tag>
```

