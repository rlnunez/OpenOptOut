#!/usr/bin/env python3
"""
OpenOptOut — Ephemeral RAM tmpfs (/tmp) Sizing & Stress Test (Roadmap Phase 15.2).

Tests /tmp filesystem performance, concurrency limits, and cleanup behavior
to determine safe RAM tmpfs sizing for Playwright browser automation and
plugin sandboxes without risking ENOSPC out-of-disk crashes.

Usage:
    python3 deploy/tests/test_tmpfs_sizing.py [--concurrency N] [--payload-mb M]
"""

import argparse
import concurrent.futures
import os
import shutil
import sys
import tempfile
import time
from typing import Dict, Any, List


def get_tmp_stats() -> Dict[str, Any]:
    """Retrieve filesystem statistics for /tmp."""
    tmp_path = tempfile.gettempdir()
    stat = os.statvfs(tmp_path)
    free_bytes = stat.f_bavail * stat.f_frsize
    total_bytes = stat.f_blocks * stat.f_frsize
    used_bytes = total_bytes - free_bytes

    is_tmpfs = False
    if sys.platform == "linux" and os.path.isfile("/proc/mounts"):
        try:
            with open("/proc/mounts", "r") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 3 and parts[1] == "/tmp" and parts[2] == "tmpfs":
                        is_tmpfs = True
                        break
        except Exception:
            pass

    return {
        "path": tmp_path,
        "is_tmpfs": is_tmpfs,
        "total_mb": round(total_bytes / (1024 * 1024), 2),
        "free_mb": round(free_bytes / (1024 * 1024), 2),
        "used_mb": round(used_bytes / (1024 * 1024), 2),
    }


def simulate_worker_workload(worker_id: int, payload_mb: int, duration_sec: float) -> Dict[str, Any]:
    """
    Simulates a Playwright browser worker:
    Creates temporary profile directories, browser caches, and screenshots in /tmp,
    holds them for a short duration, then cleans them up.
    """
    prefix = f"openoptout_test_worker_{worker_id}_"
    temp_dir = tempfile.mkdtemp(prefix=prefix)
    allocated_bytes = 0
    start_time = time.time()

    try:
        # Simulate browser cache files and download artifacts
        chunk = b"X" * (1024 * 1024)  # 1 MB chunk
        for i in range(payload_mb):
            file_path = os.path.join(temp_dir, f"cache_artifact_{i}.bin")
            with open(file_path, "wb") as f:
                f.write(chunk)
            allocated_bytes += len(chunk)

        time.sleep(duration_sec)
        success = True
        error = None
    except Exception as e:
        success = False
        error = str(e)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    elapsed = time.time() - start_time
    is_cleaned = not os.path.exists(temp_dir)

    return {
        "worker_id": worker_id,
        "allocated_mb": round(allocated_bytes / (1024 * 1024), 2),
        "success": success,
        "error": error,
        "cleaned_up": is_cleaned,
        "elapsed_sec": round(elapsed, 3),
    }


def run_tmpfs_stress_test(concurrency: int = 4, payload_mb: int = 25, duration_sec: float = 0.5) -> Dict[str, Any]:
    """Execute concurrent worker simulation and measure peak consumption and cleanup."""
    initial_stats = get_tmp_stats()
    start_time = time.time()

    results: List[Dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [
            executor.submit(simulate_worker_workload, i, payload_mb, duration_sec)
            for i in range(concurrency)
        ]
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())

    post_stats = get_tmp_stats()
    total_time = round(time.time() - start_time, 3)

    all_cleaned = all(r["cleaned_up"] for r in results)
    all_succeeded = all(r["success"] for r in results)
    total_simulated_mb = sum(r["allocated_mb"] for r in results)

    # Estimate safe minimum RAM tmpfs size: (peak workload * 2.0 safety factor)
    recommended_min_tmpfs_mb = max(256, int(total_simulated_mb * 2.0))

    return {
        "initial_stats": initial_stats,
        "post_stats": post_stats,
        "concurrency": concurrency,
        "payload_per_worker_mb": payload_mb,
        "total_simulated_mb": total_simulated_mb,
        "all_succeeded": all_succeeded,
        "all_cleaned": all_cleaned,
        "total_time_sec": total_time,
        "recommended_min_tmpfs_mb": recommended_min_tmpfs_mb,
        "worker_results": results,
    }


def main():
    parser = argparse.ArgumentParser(description="OpenOptOut /tmp tmpfs Sizing & Stress Benchmark")
    parser.add_argument("--concurrency", type=int, default=4, help="Number of concurrent simulated browser sessions")
    parser.add_argument("--payload-mb", type=int, default=25, help="Simulated profile/cache size per session in MB")
    parser.add_argument("--duration", type=float, default=0.2, help="Hold duration per session in seconds")
    args = parser.parse_args()

    print("=" * 65)
    print("  OpenOptOut Ephemeral /tmp RAM tmpfs Sizing & Stress Test")
    print("  (Roadmap Phase 15.2 — Testing)")
    print("=" * 65)

    stats = get_tmp_stats()
    print(f"\nFilesystem:      {stats['path']}")
    print(f"Type:            {'RAM tmpfs (ephemeral)' if stats['is_tmpfs'] else 'Standard disk / volume'}")
    print(f"Total capacity:  {stats['total_mb']} MB")
    print(f"Currently free:  {stats['free_mb']} MB")

    print(f"\nSimulating {args.concurrency} concurrent browser sessions ({args.payload_mb} MB each)...")
    res = run_tmpfs_stress_test(
        concurrency=args.concurrency,
        payload_mb=args.payload_mb,
        duration_sec=args.duration,
    )

    print("\nBenchmark Results:")
    print(f"  All tasks succeeded:     {'YES [✓]' if res['all_succeeded'] else 'NO [✗]'}")
    print(f"  All temp files cleaned:  {'YES [✓]' if res['all_cleaned'] else 'NO [✗]'}")
    print(f"  Simulated peak data:     {res['total_simulated_mb']} MB across {res['concurrency']} workers")
    print(f"  Execution time:          {res['total_time_sec']} seconds")

    print("\n" + "-" * 65)
    print("  RECOMMENDED RAM tmpfs SIZING:")
    print(f"  • Minimum safe size for {args.concurrency} workers: {res['recommended_min_tmpfs_mb']} MB")
    print("  • Production fleet standard: 512MB (small) / 1GB (high-throughput)")
    print("  Docker configuration snippet:")
    print("    tmpfs:")
    print(f"      - /tmp:size={max(512, res['recommended_min_tmpfs_mb'])}M")
    print("-" * 65)

    if res["all_succeeded"] and res["all_cleaned"]:
        print("\nVERDICT: PASS — /tmp handles concurrent workloads cleanly with zero leaks.\n")
        sys.exit(0)
    else:
        print("\nVERDICT: FAIL — Workload failed or leaked temporary files.\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
