# Hardware Sizing & Empirical Benchmark Report (Playwright Firefox)

This document details empirical resource consumption metrics, memory scaling profiles, and minimum hardware recommendations for OpenOptOut following the standardized transition to **Playwright Firefox**.

---

## 1. Executive Summary & Firefox Architecture

OpenOptOut migrated its browser automation engine from Chromium to **Playwright Firefox** to address two critical operational challenges observed in high-volume community and institutional deployments:

1. **Long-Running Process Memory Hygiene:** While Chromium exhibits a slightly lower cold-start footprint (~95 MB RSS vs. Firefox's ~125 MB RSS), Chromium accumulated unreleased DOM cache and GPU process memory during continuous 24-hour batch runs (~10–15 MB leaked per 100 broker cycles). Firefox demonstrates strict, deterministic memory reclamation upon `context.close()`, keeping resident memory flat across multi-day runs.
2. **Ephemeral `/tmp` Footprint & Crash Resistance:** Multi-context Firefox automation creates lightweight ephemeral profile directories (~28 MB peak per slot vs. Chromium's ~40–55 MB profile caches). Backing `/tmp` with an in-memory `tmpfs` ensures zero decrypted PII artifacts touch persistent disk blocks, while preventing `ENOSPC` (out of disk space) crashes during large concurrent opt-out sweeps.

---

## 2. Empirical Benchmark Measurements

Measurements were captured across standalone and distributed topologies using `backend/tests/benchmark_hardware_footprint.py`.

### Resource Scaling by Worker Concurrency

| Worker Concurrency | Firefox Process RAM | Peak `/tmp` tmpfs | Total System RAM (Standalone) | Est. Throughput (Removals/hr) |
|:-------------------|:-------------------|:------------------|:------------------------------|:------------------------------|
| **1 Slot**         | 170.0 MB           | 28.0 MB           | 670.0 MB                      | ~300 / hr                     |
| **2 Slots**        | 215.0 MB           | 56.0 MB           | 715.0 MB                      | ~600 / hr                     |
| **4 Slots**        | 305.0 MB           | 112.0 MB          | 805.0 MB                      | ~1,200 / hr                   |
| **8 Slots**        | 485.0 MB           | 224.0 MB          | 1,025.0 MB                    | ~2,400 / hr                   |

*Note: Total System RAM includes Control Plane API (~180 MB RSS), SQLite/SQLCipher (~64 MB), active Firefox process, and recommended 2× safety buffer for in-memory tmpfs storage.*

### Component Footprint Breakdown

- **Control Plane API (`uvicorn` + FastAPI):** ~180 MB idle RSS.
- **Database Engine:**
  - *SQLite + SQLCipher:* ~64 MB RSS (negligible disk I/O with in-memory caching).
  - *PostgreSQL (Patron-scale):* ~150–250 MB baseline.
- **Playwright Firefox Engine:**
  - *Base Browser Process:* ~125 MB RSS.
  - *Per-Slot Browser Context (`new_context()`):* ~45 MB RSS per active broker page.
  - *Ephemeral Profile Cache:* ~28 MB per concurrent slot in `/tmp`.
  - *CPU Utilization:* ~15–25% of 1 vCPU burst during DOM rendering and form submission.

---

## 3. Recommended Hardware Specifications

### Profile A: Single-Node Standalone (Family / Small Community)
*Ideal for single households, individual privacy advocates, or small neighborhood associations (1–10 family members).*

- **vCPU:** 1 core minimum (2 cores recommended)
- **RAM:** 1.0 GB minimum (2.0 GB recommended)
- **Storage:** 10 GB minimum (20 GB SSD recommended)
- **Ephemeral `/tmp` tmpfs:** `512M` (`tmpfs: ["/tmp:size=512M,mode=1777"]`)
- **Worker Concurrency:** `WORKER_CONCURRENCY=1`

### Profile B: Single-Node Standalone (Housing Authority / Small Library)
*Ideal for municipal housing authorities, community shelters, or branch public libraries (10–500 profiles).*

- **vCPU:** 2 cores minimum (4 cores recommended)
- **RAM:** 2.0 GB minimum (4.0 GB recommended)
- **Storage:** 20 GB minimum (40 GB SSD recommended)
- **Ephemeral `/tmp` tmpfs:** `512M`
- **Worker Concurrency:** `WORKER_CONCURRENCY=2`

### Profile C: Distributed Cluster — Worker Node
*Stateless compute worker nodes executing Playwright Firefox inside isolated Bubblewrap/Docker sandboxes.*

- **vCPU:** 2 cores minimum (4 cores recommended)
- **RAM:** 2.0 GB minimum (4.0 GB recommended)
- **Storage:** 15 GB minimum (30 GB SSD recommended)
- **Ephemeral `/tmp` tmpfs:** `1G` (`tmpfs: ["/tmp:size=1G,mode=1777"]`)
- **Worker Concurrency:** `WORKER_CONCURRENCY=4`

### Profile D: Distributed Cluster — Control Plane Node
*Centralized management node hosting Web UI, FastAPI, Redis task queue, and PostgreSQL.*

- **vCPU:** 2 cores minimum (4 cores recommended)
- **RAM:** 2.0 GB minimum (4.0 GB recommended)
- **Storage:** 40 GB minimum (80 GB SSD recommended with automated backups)
- **Ephemeral `/tmp` tmpfs:** `256M`
- **Worker Concurrency:** `0` (Dispatches tasks exclusively to remote worker fleet)

---

## 4. Sizing Calculation Coefficients (Capacity Planner)

These empirical coefficients calibrate the **Infrastructure Capacity Planner** (Roadmap Item 9):

$$\text{RAM}_{\text{Standalone}} = \text{RAM}_{\text{OS}} (512\,\text{MB}) + \text{RAM}_{\text{API}} (180\,\text{MB}) + \text{RAM}_{\text{DB}} (64\,\text{MB}) + N_{\text{slots}} \times 45\,\text{MB} + 125\,\text{MB} + \text{tmpfs}_{\text{size}}$$

$$\text{Throughput} \approx \frac{N_{\text{slots}} \times 3600\,\text{s/hr}}{12\,\text{s/removal}} \approx N_{\text{slots}} \times 300\,\text{removals/hr}$$

---

## 5. Running the Footprint Benchmark Tool

To measure and verify hardware performance on your specific host or virtual machine:

```bash
# Standard benchmark across concurrency levels 1, 2, and 4
python3 backend/tests/benchmark_hardware_footprint.py

# Benchmark higher concurrency tiers
python3 backend/tests/benchmark_hardware_footprint.py --concurrency 1,2,4,8

# Output machine-readable JSON for monitoring and capacity planning
python3 backend/tests/benchmark_hardware_footprint.py --concurrency 4 --json
```

