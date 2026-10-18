"""
Infrastructure Capacity Planner (Roadmap Item 9).

Calibrated against empirical Playwright Firefox benchmark data (Item 71 / docs/admin/hardware-sizing.md).
Calculates required worker concurrency, vCPU, RAM, ephemeral tmpfs, and residential proxy bandwidth
for community and institutional deployments based on profile count, broker pool, and target completion window.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Optional

try:
    from pydantic import BaseModel, Field
    from .limits import LimitedModel
    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False

    class BaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

        def model_dump(self):
            return {
                k: (v.model_dump() if hasattr(v, "model_dump") else v)
                for k, v in self.__dict__.items()
                if not k.startswith("_")
            }

        def dict(self):
            return self.model_dump()

    class LimitedModel(BaseModel):
        pass

    def Field(default=None, **kwargs):
        return default

# ── Empirical Benchmark Constants (docs/admin/hardware-sizing.md) ─────────────

# Average automated removal form duration in seconds
AVG_FORM_DURATION_SEC: float = 12.0

# Throughput per active worker slot: (3600 sec / 12 sec = 300 removals/hr)
THROUGHPUT_PER_SLOT_HR: float = 3600.0 / AVG_FORM_DURATION_SEC

# Baseline resident memory (MB)
RAM_OS_BASELINE_MB: float = 512.0
RAM_API_CONTROL_PLANE_MB: float = 180.0
RAM_DB_SQLITE_MB: float = 64.0
RAM_DB_POSTGRES_MB: float = 200.0
RAM_FIREFOX_BASE_MB: float = 125.0
RAM_FIREFOX_PER_SLOT_MB: float = 45.0

# Ephemeral /tmp tmpfs allocations
TMPFS_PEAK_PER_SLOT_MB: float = 28.0
TMPFS_SAFETY_MULTIPLIER: float = 2.0
TMPFS_MIN_MB: float = 512.0

# Network proxy transfer per automated opt-out cycle (compressed DOM, assets, form POST)
PROXY_TRANSFER_PER_JOB_MB: float = 1.2

# Standard distributed worker node slot packaging
DISTRIBUTED_SLOTS_PER_NODE: int = 4


class CapacityPlanRequest(LimitedModel):
    profiles: int = Field(100, ge=1, le=1_000_000, description="Total family members or patron profiles")
    brokers: int = Field(80, ge=1, le=1000, description="Active broker plugins in scope")
    target_days: float = Field(7.0, ge=0.01, le=365.0, description="Target removal completion window in days")
    form_ratio: float = Field(0.85, ge=0.0, le=1.0, description="Proportion of brokers requiring browser form automation (vs email)")
    use_postgres: bool = Field(False, description="Whether deployment utilizes PostgreSQL instead of SQLite")


class HardwareProfileRecommendation(BaseModel):
    profile_id: str
    name: str
    topology: str  # "standalone" | "distributed"
    description: str
    vcpu_min: int
    vcpu_recommended: int
    ram_gb_min: float
    ram_gb_recommended: float
    tmpfs_mb: int
    storage_ssd_gb_min: int
    storage_ssd_gb_recommended: int
    worker_concurrency: int
    worker_nodes_count: int = 1


class CapacityPlanResult(BaseModel):
    profiles: int
    brokers: int
    target_days: float
    target_hours: float
    total_jobs: int
    browser_form_jobs: int
    email_jobs: int
    required_throughput_per_hr: float
    required_slots: int
    
    # Recommended hardware and topology
    recommended_profile: HardwareProfileRecommendation
    standalone_ram_mb: float
    cluster_worker_nodes_needed: int
    cluster_total_worker_slots: int
    
    # Storage & Network
    ephemeral_tmpfs_mb: int
    estimated_proxy_bandwidth_gb: float
    
    # Live fleet comparison (if available)
    current_fleet_slots: Optional[int] = None
    current_fleet_deficit_slots: Optional[int] = None
    current_fleet_est_completion_days: Optional[float] = None


def calculate_capacity_plan(
    profiles: int = 100,
    brokers: int = 80,
    target_days: float = 7.0,
    form_ratio: float = 0.85,
    use_postgres: bool = False,
    current_fleet_slots: Optional[int] = None,
) -> CapacityPlanResult:
    """
    Calculate empirical infrastructure capacity requirements for given workload parameters.
    """
    if profiles < 1:
        raise ValueError("Profile count must be at least 1")
    if brokers < 1:
        raise ValueError("Broker count must be at least 1")
    if target_days <= 0:
        raise ValueError("Target days must be positive")

    target_hours = target_days * 24.0
    total_jobs = profiles * brokers
    browser_form_jobs = int(math.ceil(total_jobs * form_ratio))
    email_jobs = total_jobs - browser_form_jobs

    # Hourly throughput required for browser automation
    # Email jobs are dispatched near-instantaneously by comparison (<100ms)
    required_throughput_per_hr = browser_form_jobs / target_hours if target_hours > 0 else float(browser_form_jobs)

    # Concurrency slots required (minimum 1)
    raw_slots = required_throughput_per_hr / THROUGHPUT_PER_SLOT_HR
    required_slots = max(1, int(math.ceil(raw_slots)))

    # Ephemeral /tmp tmpfs allocation
    tmpfs_needed = max(TMPFS_MIN_MB, math.ceil(required_slots * TMPFS_PEAK_PER_SLOT_MB * TMPFS_SAFETY_MULTIPLIER))

    # Single-node standalone RAM estimate formula from docs/admin/hardware-sizing.md:
    # RAM = RAM_OS (512) + RAM_API (180) + RAM_DB (64 or 200) + N_slots * 45 + 125 (Firefox Base) + tmpfs
    db_ram = RAM_DB_POSTGRES_MB if use_postgres else RAM_DB_SQLITE_MB
    standalone_ram_mb = (
        RAM_OS_BASELINE_MB
        + RAM_API_CONTROL_PLANE_MB
        + db_ram
        + (required_slots * RAM_FIREFOX_PER_SLOT_MB)
        + RAM_FIREFOX_BASE_MB
        + tmpfs_needed
    )

    # Estimated proxy transfer
    estimated_proxy_bandwidth_gb = round((browser_form_jobs * PROXY_TRANSFER_PER_JOB_MB) / 1024.0, 2)

    # Select Recommended Hardware Profile
    if required_slots <= 1:
        rec_profile = HardwareProfileRecommendation(
            profile_id="Profile A",
            name="Single-Node Standalone (Family / Small Community)",
            topology="standalone",
            description="Ideal for single households, individual privacy advocates, or small neighborhood associations (1–10 family members).",
            vcpu_min=1,
            vcpu_recommended=2,
            ram_gb_min=1.0,
            ram_gb_recommended=2.0,
            tmpfs_mb=512,
            storage_ssd_gb_min=10,
            storage_ssd_gb_recommended=20,
            worker_concurrency=1,
            worker_nodes_count=1,
        )
        worker_nodes_needed = 0
        total_cluster_slots = 1
    elif required_slots == 2:
        rec_profile = HardwareProfileRecommendation(
            profile_id="Profile B",
            name="Single-Node Standalone (Housing Authority / Small Library)",
            topology="standalone",
            description="Ideal for municipal housing authorities, community shelters, or branch public libraries (10–500 profiles).",
            vcpu_min=2,
            vcpu_recommended=4,
            ram_gb_min=2.0,
            ram_gb_recommended=4.0,
            tmpfs_mb=512,
            storage_ssd_gb_min=20,
            storage_ssd_gb_recommended=40,
            worker_concurrency=2,
            worker_nodes_count=1,
        )
        worker_nodes_needed = 0
        total_cluster_slots = 2
    else:
        # Multi-node distributed cluster
        worker_nodes_needed = int(math.ceil(required_slots / DISTRIBUTED_SLOTS_PER_NODE))
        total_cluster_slots = worker_nodes_needed * DISTRIBUTED_SLOTS_PER_NODE
        rec_profile = HardwareProfileRecommendation(
            profile_id="Profile C/D",
            name="Distributed Cluster (Control Plane + Dedicated Worker Fleet)",
            topology="distributed",
            description=f"Recommended for institutional consortiums or municipal deployments. Requires 1 Control Plane node plus {worker_nodes_needed} stateless worker nodes ({DISTRIBUTED_SLOTS_PER_NODE} slots each).",
            vcpu_min=2,
            vcpu_recommended=4,
            ram_gb_min=2.0,
            ram_gb_recommended=4.0,
            tmpfs_mb=1024,
            storage_ssd_gb_min=40,
            storage_ssd_gb_recommended=80,
            worker_concurrency=DISTRIBUTED_SLOTS_PER_NODE,
            worker_nodes_count=worker_nodes_needed,
        )

    # Live Fleet Telemetry Comparison
    deficit_slots = None
    est_completion_days = None
    if current_fleet_slots is not None:
        deficit_slots = max(0, required_slots - current_fleet_slots)
        if current_fleet_slots > 0:
            current_throughput = current_fleet_slots * THROUGHPUT_PER_SLOT_HR
            est_completion_hours = browser_form_jobs / current_throughput
            est_completion_days = round(est_completion_hours / 24.0, 2)
        else:
            est_completion_days = None

    return CapacityPlanResult(
        profiles=profiles,
        brokers=brokers,
        target_days=round(target_days, 2),
        target_hours=round(target_hours, 1),
        total_jobs=total_jobs,
        browser_form_jobs=browser_form_jobs,
        email_jobs=email_jobs,
        required_throughput_per_hr=round(required_throughput_per_hr, 1),
        required_slots=required_slots,
        recommended_profile=rec_profile,
        standalone_ram_mb=round(standalone_ram_mb, 1),
        cluster_worker_nodes_needed=worker_nodes_needed,
        cluster_total_worker_slots=total_cluster_slots,
        ephemeral_tmpfs_mb=int(tmpfs_needed),
        estimated_proxy_bandwidth_gb=estimated_proxy_bandwidth_gb,
        current_fleet_slots=current_fleet_slots,
        current_fleet_deficit_slots=deficit_slots,
        current_fleet_est_completion_days=est_completion_days,
    )
