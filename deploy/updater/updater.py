#!/usr/bin/env python3
"""
OpenOptOut Companion Updater Daemon.

Supervises container updates, release notifications, and workload draining
from outside the core application containers.
"""

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Optional, Dict, Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [updater] %(levelname)s: %(message)s",
)
log = logging.getLogger("updater")

API_URL = os.getenv("API_URL", "http://api:8000").rstrip("/")
UPDATE_REQUEST_FILE = os.getenv("UPDATE_REQUEST_FILE", "/data/update_request.json")
UPDATE_STATUS_FILE = os.getenv("UPDATE_STATUS_FILE", "/data/update_status.json")
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "30"))
DOCKER_COMPOSE_CMD = os.getenv("DOCKER_COMPOSE_CMD", "docker compose")

_running = True


def handle_signals(signum, frame):
    global _running
    log.info("Signal received, stopping updater daemon gracefully...")
    _running = False


signal.signal(signal.SIGINT, handle_signals)
signal.signal(signal.SIGTERM, handle_signals)


def api_request(method: str, path: str, payload: Optional[dict] = None) -> Optional[dict]:
    """Helper to query the OpenOptOut API container."""
    import urllib.parse
    url = f"{API_URL}{path}"
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() not in ("http", "https"):
        raise ValueError(f"Disallowed URL scheme: {parsed.scheme}")
    data = json.dumps(payload).encode("utf-8") if payload else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # nosec: B310 -- scheme is validated to http/https
            if resp.status in (200, 201, 204):
                content = resp.read()
                return json.loads(content.decode("utf-8")) if content else {}
    except Exception as e:
        log.warning("API request %s %s failed: %s", method, path, e)
    return None


def write_status(state: str, message: str, details: Optional[dict] = None) -> None:
    data = {
        "state": state,
        "message": message,
        "details": details or {},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    tmp_path = UPDATE_STATUS_FILE + ".tmp"
    try:
        with open(tmp_path, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, UPDATE_STATUS_FILE)
    except Exception as e:
        log.warning("Failed to write update status: %s", e)


def check_api_health(timeout_seconds: int = 90) -> bool:
    """Poll API /api/health until it answers HTTP 200."""
    start = time.time()
    while time.time() - start < timeout_seconds:
        res = api_request("GET", "/api/health")
        if res and res.get("status") == "ok":
            log.info("API health verified: version %s (commit %s)", res.get("version"), res.get("commit"))
            return True
        time.sleep(2)
    return False


def wait_for_drain(timeout_seconds: int = 120) -> bool:
    """Pause scheduler and wait for active removal jobs to finish."""
    log.info("Pausing scheduler and requesting worker fleet drain...")
    write_status("draining", "Pausing scheduler and draining active removal jobs...")

    # Pause scheduler
    api_request("POST", "/api/scheduler/pause")

    start = time.time()
    while time.time() - start < timeout_seconds:
        # Check if worker summary reports 0 active slots
        summary = api_request("GET", "/api/workers/summary")
        if summary:
            active = summary.get("active_slots", 0)
            if active == 0:
                log.info("All worker slots drained successfully.")
                return True
            log.info("Waiting for %d active worker slots to drain...", active)
        else:
            # Standalone single-container fallback: wait 5s to ensure in-flight HTTP requests complete
            time.sleep(5)
            return True
        time.sleep(3)

    log.warning("Drain timeout reached (%ds). Proceeding with upgrade.", timeout_seconds)
    return True


def execute_compose_upgrade(target_version: str) -> bool:
    """Execute docker compose pull and restart for api and web."""
    log.info("Executing container upgrade for target %s...", target_version)
    write_status("updating", f"Pulling images and recreating containers for {target_version}...")

    # Set image tag if provided or run docker compose pull
    try:
        import shlex
        # 1. Pull updated containers
        cmd_pull = shlex.split(f"{DOCKER_COMPOSE_CMD} pull api web")
        log.info("Running: %s", " ".join(cmd_pull))
        res_pull = subprocess.run(cmd_pull, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res_pull.returncode != 0:
            log.warning("Compose pull output: %s", res_pull.stderr.decode("utf-8", errors="replace"))

        # 2. Recreate containers
        cmd_up = shlex.split(f"{DOCKER_COMPOSE_CMD} up -d --remove-orphans api web")
        log.info("Running: %s", " ".join(cmd_up))
        res_up = subprocess.run(cmd_up, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res_up.returncode != 0:
            err = res_up.stderr.decode("utf-8", errors="replace")
            log.error("Compose up failed (code %d): %s", res_up.returncode, err)
            write_status("error", f"Compose upgrade failed: {err}")
            return False

        # 3. Verify health
        write_status("verifying", "Verifying application health post-upgrade...")
        if check_api_health():
            write_status("complete", f"Successfully upgraded to {target_version}.")
            log.info("Upgrade to %s completed successfully.", target_version)
            return True
        else:
            write_status("error", "Application failed health check after upgrade.")
            return False

    except Exception as e:
        log.error("Exception during compose upgrade: %s", e)
        write_status("error", f"Upgrade error: {e}")
        return False


def process_pending_update_requests():
    """Check if /data/update_request.json exists and process it."""
    if not os.path.isfile(UPDATE_REQUEST_FILE):
        return

    try:
        with open(UPDATE_REQUEST_FILE, "r") as f:
            req = json.load(f)
    except Exception as e:
        log.error("Failed to read update request file: %s", e)
        return

    action = req.get("action")
    target_version = req.get("target_version", "latest")

    if action == "upgrade":
        log.info("Processing pending upgrade request to version %s...", target_version)
        try:
            wait_for_drain()
            success = execute_compose_upgrade(target_version)
        finally:
            # Remove request file once processed
            try:
                os.remove(UPDATE_REQUEST_FILE)
            except OSError:
                pass


def run_daemon():
    """Main loop for updater container."""
    log.info("OpenOptOut companion updater daemon started.")
    write_status("idle", "Updater daemon is running and monitoring for updates.")

    while _running:
        process_pending_update_requests()
        for _ in range(POLL_INTERVAL_SECONDS):
            if not _running:
                break
            time.sleep(1)

    log.info("Updater daemon stopped.")


def main():
    parser = argparse.ArgumentParser(description="OpenOptOut System Updater Daemon")
    parser.add_argument("--check", action="store_true", help="Run a one-time check for updates")
    args = parser.parse_args()

    if args.check:
        log.info("Running on-demand check...")
        process_pending_update_requests()
    else:
        run_daemon()


if __name__ == "__main__":
    main()

