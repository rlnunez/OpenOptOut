# OpenOptOut System Updater & Release Notification Service

OpenOptOut provides an optional, automated companion service (`openoptout-updater`) that notifies administrators when new releases are published, checks the host Docker engine for updates, and coordinates safe, zero-downtime container upgrades without interrupting active data-broker removal jobs.

---

## Architecture Overview

```
┌────────────────────────────────────────────────────────────────────────┐
│ Host Machine                                                           │
│                                                                        │
│   ┌───────────────────────┐         ┌──────────────────────────────┐   │
│   │  api & worker fleets  │◄───────┐│ openoptout-updater (sidecar) │   │
│   │                       │  pause ││                              │   │
│   │ (active opt-out jobs) │  drain ││ • Polls GitHub Releases API  │   │
│   └──────────┬────────────┘        ││ • Queries Docker Engine API  │   │
│              │                     ││ • Orchestrates drain/backup  │   │
│              ▼                     ││ • Manages compose lifecycle  │   │
│       /api/health (200)            │└──────────────┬───────────────┘   │
│                                    │               │                   │
│                                    │               ▼                   │
│                                    │       /var/run/docker.sock        │
│                                    │       (Host Docker Daemon)        │
│                                    └───────────────────────────────────┘
```

### Why a Dedicated Sidecar Container?
In a Docker environment, a container cannot reliably update or restart itself from within its own execution context. Running `docker compose down && docker compose up` from inside the `api` container would cause the Docker daemon to send `SIGTERM` to `api`, immediately killing the update process midway. 

A dedicated `openoptout-updater` container runs independently, connects to `/var/run/docker.sock`, and supervises the update process while verifying the API's health post-update.

---

## Security Model & Trust Boundaries

1. **Opt-In Profile (`profiles: ["updater"]`):**
   Access to `/var/run/docker.sock` grants root-equivalent control over the host Docker daemon. To preserve OpenOptOut's strict security posture, the updater service is **disabled by default** and enabled only when an operator explicitly opts in.
2. **Zero Network Ingress:**
   The updater publishes **no ports** to the host or public internet. It communicates strictly with the `api` service over the private internal Docker bridge network and with the local Docker daemon via the Unix socket.
3. **Role-Based Access Control:**
   All updater APIs (`/api/system/updates/*`) require the `super_admin` role (`require_super_admin`). Standard users, parents, and managers cannot inspect or trigger system updates.
4. **Resilient Offline / Air-Gapped Operation:**
   If the deployment has no outbound internet access or GitHub's API is rate-limited, update checks fail gracefully without disrupting core opt-out operations.

---

## Update Policies

Update preferences are configured via the administrative UI (**Admin → System updates**) and stored in `openoptout_settings.json`:

| Policy | Behavior |
|---|---|
| **`approval_required` (Default)** | Checks for updates every 6 hours. When a new release is available, displays a notification badge in the admin navigation. Releases are downloaded/pre-pulled, but installation requires an explicit click on **"Install Update"** by a super admin. |
| **`notify_only`** | Operates purely as a notification service. Alerts administrators to new releases and release notes, but performs no automated Docker pull or container restart operations. |
| **`auto_install`** | Checks periodically and automatically initiates the safe draining and upgrade sequence during configured maintenance windows. |
| **`ignore_release`** | Skips notifications and actions for a specific release tag (e.g., ignoring `v0.11.0-rc1` while awaiting `v0.11.0` final). |
| **`disabled`** | Disables all outbound update checks and GitHub API polling. |

---

## Workload Draining & Removal Safety

Applying an update while a Playwright headless browser is submitting an opt-out form can corrupt state, lose one-time verification tokens, or leave a removal half-submitted. 

The updater enforces a strict 4-step state machine:

1. **Pause Task Dispatcher (`POST /api/scheduler/pause`):**
   Suspends the automated opt-out scheduler and task queue, preventing new pending removal requests from being dispatched to workers.
2. **Drain Active Workers:**
   Queries the distributed worker fleet (`GET /api/workers` and queue depth) and waits for in-flight browser sessions to finish cleanly (`in_flight_count == 0`). A configurable timeout (default: 5 minutes) ensures wedged workers do not stall updates indefinitely.
3. **Pre-Flight Database Snapshot:**
   Invokes OpenOptOut's snapshot backup engine (`core/backup.py`) to create a pre-update archive of the database and encryption keys before any schema migrations run.
4. **Compose Upgrade & Health Verification:**
   Executes `docker compose pull && docker compose up -d --remove-orphans api web`. The updater then polls `http://api:8000/api/health` until HTTP 200 is confirmed and the reported version matches the expected release. If health verification fails after 90 seconds, the updater logs an emergency notice and restores the previous image tags.

---

## Host Docker Engine Auditing

The updater connects to `/var/run/docker.sock` and queries the Docker Engine API endpoint `GET /version`:
- **Docker Engine Version:** Reports the running Docker daemon version (e.g., `24.0.7`, `27.1.0`).
- **Compatibility Verification:** Confirms that the host Docker version supports Compose v2 file specifications, `tmpfs` mounts, and resource ulimits.
- **Update Prompts:** If an outdated Docker version (e.g., Docker < 24.0 or Compose v1) is detected, an informational notice is surfaced on the System Updates dashboard with recommended host upgrade commands (`apt-get upgrade docker-ce`).

---

## Quickstart & Activation

To enable the updater container:

```bash
# 1. Enable the updater profile in .env:
echo "COMPOSE_PROFILES=updater" >> .env

# 2. Start the updater container alongside the core services:
docker compose --profile updater up -d updater
```

To check updater status and run an on-demand check from the CLI:
```bash
docker compose exec updater python3 /updater/updater.py --check
```

