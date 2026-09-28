# Database & Storage Configuration

PrivacyShield supports SQLite for personal/family deployments and PostgreSQL for enterprise and institutional scale. Both backends support optional encryption at rest.

---

## Backend Selection

### SQLite (Default)
SQLite is pre-configured and zero-maintenance. The database is stored inside a Docker volume at `/data/privacy_pipeline.db` (or `./privacy_pipeline.db` in native installs) and persists across restarts.
- **Recommended for:** Personal use, families, and staff-only institutional deployments (up to a few hundred users).
- **Limitations:** SQLite uses file-level locking for write transactions. Under high concurrency with background workers and many active web users, write contention can lead to lock timeouts.

### PostgreSQL (Institutional Scale)
PostgreSQL is recommended for patron-facing deployments, school districts, universities, and organizations serving thousands of concurrent users.

To switch to PostgreSQL, set `DATABASE_URL` in your `.env` file:
```env
DATABASE_URL=postgresql://user:password@db.example.org:5432/privacyshield
```

---

## Enterprise PostgreSQL Authentication

For hardened institutional environments, PrivacyShield provides a structured connection manager (**Admin → Database → Connection**) that supports enterprise authentication methods without storing credentials in the database:

- **SSL/TLS Modes:** Configurable SSL validation (`disable`, `allow`, `prefer`, `require`, `verify-ca`, `verify-full`).
- **Mutual TLS (mTLS):** Client certificate and private key authentication alongside root CA validation.
- **Cloud IAM Tokens:** Dynamic authentication using cloud identity tokens:
  - **AWS RDS IAM** token generation
  - **Google Cloud SQL IAM** connector / auth
  - **Azure Active Directory (Entra ID)** managed identity tokens
- **Kerberos / GSSAPI:** Single sign-on database authentication for on-premises enterprise Active Directory environments.

> [!NOTE]
> Database passwords, SSL keys, and IAM credentials are read exclusively from environment variables or securely mounted files; they are never written to the application database.

---

## Migrating from SQLite to PostgreSQL

To migrate an existing SQLite installation to PostgreSQL without losing data:

1. Deploy your PostgreSQL database instance and create an empty database (`privacyshield`).
2. Log into PrivacyShield as a Super Administrator.
3. Navigate to **Admin → Database → Migrate to Postgres**.
4. Enter the target PostgreSQL connection string and test connectivity.
5. Click **Migrate**. The migration utility will:
   - Create all tables, indexes, and foreign keys.
   - Stream records table-by-table while preserving UUID keys and relationships.
   - Reset auto-increment sequences to match migrated row IDs.
6. Once complete, update `DATABASE_URL` in `.env` and restart the application container.
7. Retain your old SQLite database file as a backup for at least 30 days.

---

## Encryption at Rest

PrivacyShield provides two independent layers of encryption at rest, which can be used individually or together:

### Layer 1: Full Database Encryption (SQLCipher)
For SQLite deployments, the entire database file can be encrypted on disk using 256-bit AES via SQLCipher.
- Configured by setting `DB_ENCRYPTION_KEY` in `.env`.
- To migrate an existing unencrypted SQLite database to SQLCipher:
  ```bash
  docker exec privacyshield-api python -m app.core.encryption migrate
  ```

### Layer 2: Field-Level Encryption (Fernet)
Sensitive Personally Identifiable Information (PII) — including member name variants, email addresses, phone numbers, and physical addresses — can be encrypted with authenticated symmetric encryption (Fernet) before insertion into database columns.
- Configured by setting `FIELD_ENCRYPTION_KEY` in `.env` (generate using `openssl rand -base64 32`).
- Protects patron PII even if database read replicas, query logs, or unencrypted database dumps are exposed.

### Managed PostgreSQL Encryption
When using PostgreSQL on managed cloud infrastructure (e.g. AWS RDS, Google Cloud SQL, Azure Database for PostgreSQL), combine PrivacyShield field-level encryption with cloud provider volume encryption:
- AWS RDS storage encryption (KMS)
- Google Cloud SQL Customer-Managed Encryption Keys (CMEK)
- Azure Transparent Data Encryption (TDE)
