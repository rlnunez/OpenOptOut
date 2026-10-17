# User Roles and Access Control

OpenOptOut enforces strict server-side role-based access control (RBAC). Upon initial installation, the first registered user is automatically designated as the **Super Admin**.

---

## Role Hierarchy and Capabilities

| Role | Permissions & Scope | Recommended Use |
|---|---|---|
| **Super Admin** | Full root system access: system settings, branding, email configuration, database maintenance, user management, and global vault inspection. | System administrator or host operator. |
| **Admin** | Manages users, views aggregate operational reports, and configures broker scripts. Cannot modify white-label branding, alter core email credentials, or delete the instance. | IT staff, department leads, or branch supervisors. |
| **Manager** | Performs delegated administrative actions, including plugin management and broker catalog review, without broader system or user access. | Operational staff managing broker catalogs. |
| **Parent** | Manages household records: adds and edits family members, creates Identity Vault profiles, initiates opt-out workflows, and inspects status. | Household heads, family organizers, or library staff sponsors. |
| **Member** | Self-service view: inspects their own removal progress and personal Identity Vault attributes. Cannot access records belonging to other household or tenant members. | Children, patrons, or individual organization members. |

---

## Security and Partitioning Rules

- **Server-Side Enforcement**: All permission checks are evaluated on the backend API routes; UI state changes alone cannot bypass role gates.
- **Tenant & Family Isolation**: Direct API requests cannot access another family unit's data. Cross-tenant queries are blocked at the database and routing layers.
- **Patron Boundaries**: In institutional deployments (e.g., SIP2 library card logins or SSO integrations), users default to the **Member** role to maintain strict patron privacy by default.
