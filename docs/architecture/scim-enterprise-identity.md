# SCIM 2.0 Enterprise Identity Management

This document specifies OpenOptOut's implementation of **System for Cross-domain Identity Management (SCIM) 2.0**, conforming to:
- **RFC 7643:** SCIM Core Schema and Representation
- **RFC 7644:** SCIM Protocol and Endpoint Operations

---

## 1. Overview & Architecture

OpenOptOut exposes a standard SCIM 2.0 service provider interface mounted at:
```text
/api/scim/v2/
```

This interface enables institutional identity providers—including **Okta**, **Microsoft Entra ID (Azure AD)**, **Google Workspace**, and **PingIdentity**—to automate patron, staff, and administrator identity lifecycles without manual intervention.

### Supported Operations:
1. **Automated Account Provisioning:** Creation of patrons and staff accounts upon onboarding in the central directory.
2. **Real-Time Attribute Synchronization:** Updates to full name, email address, and role mappings.
3. **Instant Session Revocation & Suspension:** Setting `"active": false` terminates all active user sessions (`UserSession`) and pauses pending automated opt-outs.
4. **Verifiable Deprovisioning & Crypto-Shredding:** `DELETE /api/scim/v2/Users/{id}` initiates cascading NIST SP 800-88 Rev. 1 cryptographic erasure, purging all member vault keys, identities, and audit records.

---

## 2. API Endpoints Reference

| Method | Endpoint | Description | Schema |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/scim/v2/ServiceProviderConfig` | Service provider capabilities & auth schemes | `urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig` |
| `GET` | `/api/scim/v2/Schemas` | Introspect supported SCIM schemas | `urn:ietf:params:scim:api:messages:2.0:ListResponse` |
| `GET` | `/api/scim/v2/ResourceTypes` | Introspect User and Group resource types | `urn:ietf:params:scim:schemas:core:2.0:ResourceType` |
| `GET` | `/api/scim/v2/Users` | Query users with pagination and filtering (`filter=userName eq "..."`) | `urn:ietf:params:scim:api:messages:2.0:ListResponse` |
| `GET` | `/api/scim/v2/Users/{id}` | Retrieve single user representation | `urn:ietf:params:scim:schemas:core:2.0:User` |
| `POST` | `/api/scim/v2/Users` | Provision a new user account | `urn:ietf:params:scim:schemas:core:2.0:User` |
| `PATCH` | `/api/scim/v2/Users/{id}` | Modify attributes or deactivate (`active: false`) | `urn:ietf:params:scim:schemas:core:2.0:User` |
| `DELETE` | `/api/scim/v2/Users/{id}` | Deprovision user with cascading crypto-shredding | HTTP 204 No Content |
| `GET` | `/api/scim/v2/Groups` | Introspect system roles as SCIM groups | `urn:ietf:params:scim:api:messages:2.0:ListResponse` |

---

## 3. Authentication & Security

All SCIM calls require an HTTP Bearer token conforming to RFC 7644 Section 2:
```http
Authorization: Bearer <SCIM_BEARER_TOKEN>
```

Tokens are validated against:
1. Configured dedicated SCIM token (`auth.scim_bearer_token` in system settings).
2. Administrator JWT sessions with `settings.system` administrative privilege.
