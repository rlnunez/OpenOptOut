# RFC 9449 OAuth 2.0 Demonstrating Proof-of-Possession (DPoP)

This document specifies OpenOptOut's implementation of **RFC 9449: OAuth 2.0 Demonstrating Proof-of-Possession at the Application Layer (DPoP)**.

---

## 1. Overview & Threat Model

Traditional OAuth 2.0 / 2.1 access and refresh tokens are *Bearer* tokens: any party possessing the token can present it to access protected endpoints. If a bearer token is intercepted by a compromised TLS proxy, leaked in access logs, or exfiltrated via client-side malware, an attacker can replay it at will.

**DPoP (RFC 9449)** eliminates this vulnerability by binding tokens to an asymmetric key pair held by the legitimate client at the application layer:
* Every request must carry a freshly signed proof JWT in the `DPoP` HTTP header.
* The proof contains the request's exact HTTP method (`htm`), target URL (`htu`), timestamp (`iat`), and unique nonce (`jti`).
* Even if an attacker steals an active session or refresh token, they cannot use it without possession of the private key that generates matching DPoP proofs.

---

## 2. DPoP Proof Validation Pipeline

[`backend/core/dpop.py`](../../backend/core/dpop.py) verifies each presented proof:

1. **Typ Enforcement:** Header `typ` must strictly equal `"dpop+jwt"`.
2. **Algorithm Whitelist:** Must be an asymmetric signature algorithm (`ES256`, `RS256`, `EdDSA`); symmetric algorithms (`HS256`) and `none` are rejected.
3. **JWK Validation:** Public key object must be embedded in the header and cannot contain private parameters (`d`).
4. **Method & URI Verification:** The asserted `htm` and `htu` must match the incoming request exactly.
5. **Replay Protection:** Single-use `jti` is checked against an in-memory replay cache to prevent proof reuse.
6. **Thumbprint Binding:** Computes the RFC 7638 JWK Thumbprint (`jkt`) to bind tokens to the client key.

