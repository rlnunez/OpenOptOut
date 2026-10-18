#!/usr/bin/env python3
"""
openoptout-calc — Infrastructure Capacity Planner CLI (Roadmap Item 9).

Calibrated against empirical Playwright Firefox benchmarks (docs/admin/hardware-sizing.md).
Estimates required worker concurrency, vCPU, RAM, ephemeral tmpfs, and residential proxy bandwidth
for community and institutional deployments.

Usage:
  python3 scripts/openoptout-calc.py [--profiles N] [--brokers N] [--days D] [--json]
  ./scripts/openoptout-calc.py --profiles 500 --brokers 80 --days 7
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

# Try importing calculation engine from backend.core, or fallback to embedded logic
try:
    ROOT_DIR = Path(__file__).resolve().parent.parent
    if str(ROOT_DIR) not in sys.path:
        sys.path.insert(0, str(ROOT_DIR))
    from backend.core.capacity_planner import calculate_capacity_plan
    HAS_BACKEND = True
except Exception:
    HAS_BACKEND = False


def calculate_fallback(
    profiles: int,
    brokers: int,
    target_days: float,
    form_ratio: float = 0.85,
    use_postgres: bool = False,
) -> dict:
    target_hours = target_days * 24.0
    total_jobs = profiles * brokers
    browser_form_jobs = int(math.ceil(total_jobs * form_ratio))
    email_jobs = total_jobs - browser_form_jobs

    throughput_per_slot_hr = 300.0  # 12 sec per removal
    required_throughput_per_hr = browser_form_jobs / target_hours if target_hours > 0 else float(browser_form_jobs)
    required_slots = max(1, int(math.ceil(required_throughput_per_hr / throughput_per_slot_hr)))

    tmpfs_needed = max(512.0, math.ceil(required_slots * 28.0 * 2.0))
    db_ram = 200.0 if use_postgres else 64.0
    standalone_ram_mb = 512.0 + 180.0 + db_ram + (required_slots * 45.0) + 125.0 + tmpfs_needed
    estimated_proxy_bandwidth_gb = round((browser_form_jobs * 1.2) / 1024.0, 2)

    if required_slots <= 1:
        rec_profile = {
            "profile_id": "Profile A",
            "name": "Single-Node Standalone (Family / Small Community)",
            "topology": "standalone",
            "description": "Ideal for single households, individual privacy advocates, or small neighborhood associations (1–10 family members).",
            "vcpu_min": 1,
            "vcpu_recommended": 2,
            "ram_gb_min": 1.0,
            "ram_gb_recommended": 2.0,
            "tmpfs_mb": 512,
            "storage_ssd_gb_min": 10,
            "storage_ssd_gb_recommended": 20,
            "worker_concurrency": 1,
            "worker_nodes_count": 1,
        }
        worker_nodes_needed = 0
        total_cluster_slots = 1
    elif required_slots == 2:
        rec_profile = {
            "profile_id": "Profile B",
            "name": "Single-Node Standalone (Housing Authority / Small Library)",
            "topology": "standalone",
            "description": "Ideal for municipal housing authorities, community shelters, or branch public libraries (10–500 profiles).",
            "vcpu_min": 2,
            "vcpu_recommended": 4,
            "ram_gb_min": 2.0,
            "ram_gb_recommended": 4.0,
            "tmpfs_mb": 512,
            "storage_ssd_gb_min": 20,
            "storage_ssd_gb_recommended": 40,
            "worker_concurrency": 2,
            "worker_nodes_count": 1,
        }
        worker_nodes_needed = 0
        total_cluster_slots = 2
    else:
        worker_nodes_needed = int(math.ceil(required_slots / 4))
        total_cluster_slots = worker_nodes_needed * 4
        rec_profile = {
            "profile_id": "Profile C/D",
            "name": "Distributed Cluster (Control Plane + Dedicated Worker Fleet)",
            "topology": "distributed",
            "description": f"Recommended for institutional consortiums or municipal deployments. Requires 1 Control Plane node plus {worker_nodes_needed} stateless worker nodes (4 slots each).",
            "vcpu_min": 2,
            "vcpu_recommended": 4,
            "ram_gb_min": 2.0,
            "ram_gb_recommended": 4.0,
            "tmpfs_mb": 1024,
            "storage_ssd_gb_min": 40,
            "storage_ssd_gb_recommended": 80,
            "worker_concurrency": 4,
            "worker_nodes_count": worker_nodes_needed,
        }

    return {
        "profiles": profiles,
        "brokers": brokers,
        "target_days": round(target_days, 2),
        "target_hours": round(target_hours, 1),
        "total_jobs": total_jobs,
        "browser_form_jobs": browser_form_jobs,
        "email_jobs": email_jobs,
        "required_throughput_per_hr": round(required_throughput_per_hr, 1),
        "required_slots": required_slots,
        "recommended_profile": rec_profile,
        "standalone_ram_mb": round(standalone_ram_mb, 1),
        "cluster_worker_nodes_needed": worker_nodes_needed,
        "cluster_total_worker_slots": total_cluster_slots,
        "ephemeral_tmpfs_mb": int(tmpfs_needed),
        "estimated_proxy_bandwidth_gb": estimated_proxy_bandwidth_gb,
    }


def format_cli_output(data: dict) -> str:
    rec = data["recommended_profile"]
    lines = [
        "================================================================================",
        "  OpenOptOut — Infrastructure Capacity Planner (Playwright Firefox Calibrated)",
        "================================================================================",
        f"  Workload Parameters:",
        f"    • Profiles (Family/Patrons):      {data['profiles']:,}",
        f"    • Active Brokers:                 {data['brokers']:,}",
        f"    • Target Completion Window:       {data['target_days']} days ({data['target_hours']} hours)",
        f"    • Total Jobs:                     {data['total_jobs']:,} ({data['browser_form_jobs']:,} browser forms, {data['email_jobs']:,} emails)",
        "",
        f"  Throughput & Concurrency Requirements:",
        f"    • Target Throughput:              {data['required_throughput_per_hr']:.1f} removals / hour",
        f"    • Minimum Concurrency Slots:      {data['required_slots']} slot(s)",
        "",
        f"  Recommended Architecture:           {rec['name']}",
        f"    • Topology:                       {rec['topology'].upper()}",
        f"    • Details:                        {rec['description']}",
        "",
        "  Hardware Sizing Breakdown:",
    ]

    if rec["topology"] == "standalone":
        lines.extend([
            f"    • Recommended vCPU:               {rec['vcpu_min']}–{rec['vcpu_recommended']} Cores",
            f"    • Recommended System RAM:         {rec['ram_gb_min']}–{rec['ram_gb_recommended']} GB (Model: {data['standalone_ram_mb']:.0f} MB peak)",
            f"    • Ephemeral /tmp tmpfs:           {data['ephemeral_tmpfs_mb']} MB (backed by RAM)",
            f"    • Storage (SSD):                  {rec['storage_ssd_gb_min']}–{rec['storage_ssd_gb_recommended']} GB",
            f"    • Concurrency Setting:            WORKER_CONCURRENCY={data['required_slots']}",
        ])
    else:
        lines.extend([
            f"    • Control Plane Node (1x):        2–4 vCPU, 2–4 GB RAM, 40–80 GB SSD (WORKER_CONCURRENCY=0)",
            f"    • Worker Nodes Count:             {data['cluster_worker_nodes_needed']} Node(s)",
            f"    • Per-Worker Node Specs:          2–4 vCPU, 4 GB RAM, 1024 MB tmpfs (WORKER_CONCURRENCY=4)",
            f"    • Total Cluster Concurrency:      {data['cluster_total_worker_slots']} Slots across {data['cluster_worker_nodes_needed']} worker(s)",
        ])

    lines.extend([
        "",
        f"  Network & Proxy Bandwidth Estimate:",
        f"    • Est. Egress Traffic:            ~{data['estimated_proxy_bandwidth_gb']:.2f} GB total",
        "================================================================================",
    ])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="OpenOptOut Infrastructure Capacity Planner CLI",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--profiles", "-p", type=int, default=100, help="Number of family members or patron profiles")
    parser.add_argument("--brokers", "-b", type=int, default=80, help="Number of active broker plugins in pool")
    parser.add_argument("--days", "-d", type=float, default=7.0, help="Target removal completion window in days")
    parser.add_argument("--form-ratio", type=float, default=0.85, help="Proportion of brokers requiring browser forms")
    parser.add_argument("--postgres", action="store_true", help="Use PostgreSQL memory footprint instead of SQLite")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    args = parser.parse_args()

    if HAS_BACKEND:
        res = calculate_capacity_plan(
            profiles=args.profiles,
            brokers=args.brokers,
            target_days=args.days,
            form_ratio=args.form_ratio,
            use_postgres=args.postgres,
        )
        data = res.model_dump() if hasattr(res, "model_dump") else res.dict()
    else:
        data = calculate_fallback(
            profiles=args.profiles,
            brokers=args.brokers,
            target_days=args.days,
            form_ratio=args.form_ratio,
            use_postgres=args.postgres,
        )

    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print(format_cli_output(data))


if __name__ == "__main__":
    main()
