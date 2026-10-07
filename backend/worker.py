#!/usr/bin/env python3
"""
OpenOptOut Worker Daemon CLI (Roadmap Phase 7.3).

Standalone executable entrypoint to run a stateless worker node in a
distributed fleet. Operates independently of the FastAPI web application.

Usage:
    python -m backend.worker [OPTIONS]
    python worker.py [OPTIONS]

Options:
    --worker-id TEXT       Unique identifier for this worker node
    --concurrency INT      Number of parallel job execution slots (default: 1)
    --queue-url TEXT       Redis connection URL (default: env REDIS_URL or InProcess)
    --dry-run              Execute actions in dry-run mode without live browser
    --headless / --no-headless  Toggle browser headless mode (default: headless)
    --once                 Process a single job from the queue and exit
    --poll-interval FLOAT  Seconds between queue polling checks (default: 0.5)
"""

import argparse
import asyncio
import logging
import os
import signal
import sys

# Ensure backend root is on sys.path
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from core.distributed.worker import WorkerConfig, WorkerDaemon, WorkerBrowserPool
from core.distributed.queue import get_queue

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (%(name)s) %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("openoptout.worker")


def parse_args():
    parser = argparse.ArgumentParser(
        description="OpenOptOut Stateless Worker Daemon (Phase 7.3)"
    )
    parser.add_argument(
        "--worker-id",
        type=str,
        default=os.getenv("WORKER_ID"),
        help="Unique worker identifier",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=int(os.getenv("WORKER_CONCURRENCY", "1")),
        help="Number of concurrent worker slots",
    )
    parser.add_argument(
        "--queue-url",
        type=str,
        default=os.getenv("REDIS_URL"),
        help="Redis connection URL for distributed queue",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=os.getenv("WORKER_DRY_RUN", "0").lower() in ("1", "true", "yes"),
        help="Run without launching live Playwright browsers",
    )
    parser.add_argument(
        "--no-headless",
        dest="headless",
        action="store_false",
        default=True,
        help="Run browser in headful mode for debugging",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process one envelope and terminate",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=0.5,
        help="Queue polling interval in seconds",
    )
    return parser.parse_args()


async def main():
    # Enforce zero-core-dump memory hygiene policy (prevents PII disk dumps on crash)
    from core.memory_hygiene import disable_core_dumps
    disable_core_dumps()

    args = parse_args()

    config = WorkerConfig(
        worker_id=args.worker_id or f"worker-{os.uname().nodename}",
        concurrency=args.concurrency,
        queue_url=args.queue_url,
        dry_run=args.dry_run,
        headless=args.headless,
        poll_interval=args.poll_interval,
        secret_key=os.getenv("SECRET_KEY"),
    )

    queue = get_queue(url=config.queue_url, secret_key=config.secret_key)
    daemon = WorkerDaemon(config=config, queue=queue)

    # Attach signal handlers for graceful draining
    loop = asyncio.get_running_loop()

    def _sig_handler(sig_name):
        log.info("Received %s signal. Triggering graceful shutdown...", sig_name)
        daemon.request_stop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, lambda s=sig.name: _sig_handler(s))
        except NotImplementedError:
            # Signal handling on Windows / restricted loops
            signal.signal(sig, lambda s, f: daemon.request_stop())

    if args.once:
        log.info("Worker [%s] running in single-shot mode (--once)", config.worker_id)
        processed = await daemon.process_one(timeout=config.poll_interval)
        log.info("Single-shot execution finished (processed=%s)", processed)
        return

    await daemon.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Worker process exited.")
