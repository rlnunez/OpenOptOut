# Upgrading OpenOptOut

This guide details procedures for safely updating OpenOptOut deployments, including automated schema migrations and storage volume transitions.

---

## Standard Upgrade Procedures

### Docker Compose Deployments

```bash
# 1. Fetch latest release tags
git fetch origin

# 2. Checkout desired release tag (e.g., v0.10.0-rc2)
git checkout v0.10.0-rc2

# 3. Stop running containers
docker compose down

# 4. Rebuild images with latest source
docker compose build

# 5. Restart application in background
docker compose up -d
```

### Native Installations (systemd + nginx)

```bash
# Pull latest code and recompile dependencies
git fetch origin
git checkout v0.10.0-rc2
sudo ./deploy/installer/setup.sh --update
```

---

## Database Migrations

- The database schema is migrated automatically on application startup.
- SQLAlchemy runs additive schema migrations on boot (adding new tables and non-breaking columns).
- When destructive or manual migrations are required, explicit instructions are provided in the release notes.

---

## Storage Volume Consolidation (Pre-v0.9 Upgrades)

Older OpenOptOut deployments utilized three independent Docker volumes: `db_data`, `screenshots`, and `logo_data`. Modern configurations consolidate all application state into a single volume: `app_data` mounted at `/data`.

If you are upgrading an older instance and wish to migrate to the consolidated volume:

1. Stop existing containers: `docker compose down`.
2. Inspect the contents of your existing `db_data` volume.
3. Copy data files from `db_data` into the new `app_data` volume before starting containers with the updated Compose definition.
4. Alternatively, retain your legacy volume mounts within a custom `docker-compose.override.yml`.
