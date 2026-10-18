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
import shutil
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
UPDATE_ROLLBACK_FILE = os.getenv("UPDATE_ROLLBACK_FILE", "/data/update_rollback.json")
UPDATE_SNAPSHOT_DIR = os.getenv("UPDATE_SNAPSHOT_DIR", "/data/snapshot_pre_update")
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "30"))
DOCKER_CMD = os.getenv("DOCKER_CMD", "docker")
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
    """Pause scheduler, broadcast fleet drain, and wait for active removal jobs to finish."""
    log.info("Pausing scheduler and requesting worker fleet drain...")
    write_status("draining", "Pausing scheduler and draining active removal jobs...")

    # Pause scheduler and broadcast fleet drain signal
    api_request("POST", "/api/scheduler/pause")
    api_request("POST", "/api/workers/fleet/drain", payload={"drain": True})

    start = time.time()
    while time.time() - start < timeout_seconds:
        # Check if worker summary reports 0 active slots and 0 in-flight tasks
        summary = api_request("GET", "/api/workers/summary")
        if summary:
            active = summary.get("active_slots", 0)
            in_flight = summary.get("in_flight_count", 0)
            if active == 0 and in_flight == 0:
                log.info("All worker slots and in-flight tasks drained successfully.")
                return True
            log.info("Waiting for %d active worker slot(s) and %d in-flight task(s) to drain...", active, in_flight)
        else:
            # Standalone single-container fallback: wait 5s to ensure in-flight HTTP requests complete
            time.sleep(5)
            return True
        time.sleep(3)

    log.warning("Drain timeout reached (%ds). Proceeding with upgrade.", timeout_seconds)
    return True


def resume_fleet():
    """Un-drain worker fleet and resume scheduler after update completes or rolls back."""
    log.info("Clearing fleet drain signal and resuming scheduler...")
    try:
        api_request("POST", "/api/workers/fleet/drain", payload={"drain": False})
        api_request("POST", "/api/scheduler/resume")
    except Exception as e:
        log.warning("Failed to un-drain worker fleet / resume scheduler: %s", e)




def run_cmd(cmd_list: list) -> tuple:
    """Run shell command safely and return (exit_code, stdout, stderr)."""
    try:
        res = subprocess.run(cmd_list, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out = res.stdout.decode("utf-8", errors="replace").strip()
        err = res.stderr.decode("utf-8", errors="replace").strip()
        return res.returncode, out, err
    except Exception as e:
        return 1, "", str(e)


def get_service_image_id(service: str) -> Optional[str]:
    """Get the currently running Image ID for a service container."""
    container_name = f"openoptout-{service}"
    code, out, _ = run_cmd([DOCKER_CMD, "inspect", "--format={{.Image}}", container_name])
    if code == 0 and out:
        return out
    import shlex
    code2, out2, _ = run_cmd(shlex.split(f"{DOCKER_COMPOSE_CMD} images -q {service}"))
    if code2 == 0 and out2:
        lines = [line.strip() for line in out2.splitlines() if line.strip()]
        if lines:
            return lines[0]
    return None


def get_service_image_ref(service: str) -> Optional[str]:
    """Get the image tag/reference for a container (e.g. openoptout-api)."""
    container_name = f"openoptout-{service}"
    code, out, _ = run_cmd([DOCKER_CMD, "inspect", "--format={{.Config.Image}}", container_name])
    if code == 0 and out:
        return out
    return None


def create_pre_update_snapshot(current_version: str, target_version: str) -> Dict[str, Any]:
    """
    Tag running container images and snapshot SQLite database/settings before pulling new images.
    """
    log.info("Creating pre-update safety snapshot (current: %s, target: %s)...", current_version, target_version)
    os.makedirs(UPDATE_SNAPSHOT_DIR, exist_ok=True)

    rollback_info: Dict[str, Any] = {
        "previous_version": current_version,
        "target_version": target_version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "images": {},
        "snapshots": {},
    }

    # 1. Tag running images for api and web
    for svc in ("api", "web"):
        img_id = get_service_image_id(svc)
        img_ref = get_service_image_ref(svc)
        if img_id:
            rollback_tag = f"openoptout-rollback:{svc}"
            code, _, err = run_cmd([DOCKER_CMD, "tag", img_id, rollback_tag])
            if code == 0:
                log.info("Tagged %s (%s) as %s", svc, img_id[:12], rollback_tag)
                rollback_info["images"][svc] = {
                    "image_id": img_id,
                    "image_ref": img_ref,
                    "rollback_tag": rollback_tag,
                }
            else:
                log.warning("Failed to tag %s for rollback: %s", svc, err)
        elif img_ref:
            rollback_info["images"][svc] = {
                "image_ref": img_ref,
                "rollback_tag": f"openoptout-rollback:{svc}",
            }

    # 2. Snapshot SQLite DB if present in /data
    db_file = "/data/privacy_pipeline.db"
    if os.path.isfile(db_file):
        snap_db = os.path.join(UPDATE_SNAPSHOT_DIR, "privacy_pipeline.db")
        try:
            shutil.copy2(db_file, snap_db)
            rollback_info["snapshots"]["db"] = snap_db
            log.info("Created SQLite safety snapshot: %s", snap_db)
            for ext in ("-wal", "-shm"):
                wal_file = db_file + ext
                if os.path.isfile(wal_file):
                    shutil.copy2(wal_file, snap_db + ext)
        except Exception as e:
            log.warning("Could not snapshot SQLite database: %s", e)

    # 3. Snapshot settings file
    settings_file = "/data/openoptout_settings.json"
    if os.path.isfile(settings_file):
        snap_settings = os.path.join(UPDATE_SNAPSHOT_DIR, "openoptout_settings.json")
        try:
            shutil.copy2(settings_file, snap_settings)
            rollback_info["snapshots"]["settings"] = snap_settings
            log.info("Created settings safety snapshot: %s", snap_settings)
        except Exception as e:
            log.warning("Could not snapshot settings: %s", e)

    # 4. Write rollback manifest
    try:
        tmp_rb = UPDATE_ROLLBACK_FILE + ".tmp"
        with open(tmp_rb, "w") as f:
            json.dump(rollback_info, f, indent=2)
        os.replace(tmp_rb, UPDATE_ROLLBACK_FILE)
    except Exception as e:
        log.warning("Failed to save rollback manifest: %s", e)

    return rollback_info


def execute_rollback(rollback_info: Optional[Dict[str, Any]] = None) -> bool:
    """
    Restore previous container images, database snapshot, and restart containers.
    """
    if not rollback_info:
        if os.path.isfile(UPDATE_ROLLBACK_FILE):
            try:
                with open(UPDATE_ROLLBACK_FILE, "r") as f:
                    rollback_info = json.load(f)
            except Exception as e:
                log.error("Failed to read rollback manifest: %s", e)
                write_status("error", f"Rollback failed: manifest unreadable ({e})")
                return False
        else:
            log.error("No rollback manifest found at %s", UPDATE_ROLLBACK_FILE)
            write_status("error", "Rollback failed: no previous release snapshot available.")
            return False

    prev_ver = rollback_info.get("previous_version", "previous version")
    target_ver = rollback_info.get("target_version", "latest")
    log.warning("Executing rollback to %s...", prev_ver)
    write_status("reverting", f"Reverting update: restoring previous release {prev_ver}...")

    # 1. Restore images by retagging rollback tags back to image refs if known
    images = rollback_info.get("images", {})
    for svc, info in images.items():
        rollback_tag = info.get("rollback_tag", f"openoptout-rollback:{svc}")
        image_ref = info.get("image_ref")
        if image_ref:
            code, _, err = run_cmd([DOCKER_CMD, "tag", rollback_tag, image_ref])
            if code == 0:
                log.info("Restored image tag %s -> %s", rollback_tag, image_ref)
            else:
                log.warning("Failed to retag %s to %s: %s", rollback_tag, image_ref, err)

    # 2. Restore SQLite database snapshot if present
    snapshots = rollback_info.get("snapshots", {})
    if "db" in snapshots and os.path.isfile(snapshots["db"]):
        try:
            if os.path.isfile("/data/privacy_pipeline.db"):
                failed_backup = f"/data/privacy_pipeline.db.failed-{target_ver}"
                shutil.copy2("/data/privacy_pipeline.db", failed_backup)
            shutil.copy2(snapshots["db"], "/data/privacy_pipeline.db")
            for ext in ("-wal", "-shm"):
                wal_snap = snapshots["db"] + ext
                if os.path.isfile(wal_snap):
                    shutil.copy2(wal_snap, f"/data/privacy_pipeline.db{ext}")
                elif os.path.isfile(f"/data/privacy_pipeline.db{ext}"):
                    try:
                        os.remove(f"/data/privacy_pipeline.db{ext}")
                    except OSError:
                        pass
            log.info("Restored SQLite database from pre-update snapshot.")
        except Exception as e:
            log.warning("Failed to restore SQLite snapshot during rollback: %s", e)

    # 3. Restore settings snapshot if present
    if "settings" in snapshots and os.path.isfile(snapshots["settings"]):
        try:
            shutil.copy2(snapshots["settings"], "/data/openoptout_settings.json")
            log.info("Restored settings from pre-update snapshot.")
        except Exception as e:
            log.warning("Failed to restore settings snapshot: %s", e)

    # 4. Recreate containers using restored images
    import shlex
    cmd_up = shlex.split(f"{DOCKER_COMPOSE_CMD} up -d --remove-orphans api web")
    log.info("Running compose restart for rollback: %s", " ".join(cmd_up))
    code, out, err = run_cmd(cmd_up)
    if code != 0:
        log.error("Compose up during rollback failed (code %d): %s", code, err)
        write_status("critical_error", f"Rollback container restart failed: {err}")
        return False

    # 5. Verify API health post-rollback
    write_status("verifying", f"Verifying application health after rollback to {prev_ver}...")
    if check_api_health(timeout_seconds=90):
        write_status("reverted", f"Successfully reverted to {prev_ver}.", details={"reverted_to": prev_ver})
        log.info("Rollback to %s completed successfully and verified healthy.", prev_ver)
        return True
    else:
        write_status("critical_error", f"Reverted containers started but failed health check for {prev_ver}.")
        log.error("Reverted containers failed health check.")
        return False


def execute_compose_upgrade(target_version: str, current_version: str = "unknown") -> bool:
    """
    Execute pre-update safety snapshot, docker compose pull, container recreation,
    and automated health verification with automatic rollback if anything goes wrong.
    """
    log.info("Executing container upgrade from %s to target %s...", current_version, target_version)
    write_status("updating", f"Creating pre-update safety snapshot and upgrading to {target_version}...")

    # Step 1: Create rollback safety snapshot before pulling or touching containers
    rollback_info = create_pre_update_snapshot(current_version, target_version)

    try:
        import shlex
        # Step 2: Pull updated containers
        cmd_pull = shlex.split(f"{DOCKER_COMPOSE_CMD} pull api web")
        log.info("Running: %s", " ".join(cmd_pull))
        code_pull, out_pull, err_pull = run_cmd(cmd_pull)
        if code_pull != 0:
            log.warning("Compose pull output: %s", err_pull)

        # Step 3: Recreate containers
        cmd_up = shlex.split(f"{DOCKER_COMPOSE_CMD} up -d --remove-orphans api web")
        log.info("Running: %s", " ".join(cmd_up))
        code_up, out_up, err_up = run_cmd(cmd_up)
        if code_up != 0:
            log.error("Compose up failed (code %d): %s. Initiating automatic rollback...", code_up, err_up)
            write_status("reverting", f"Compose upgrade failed: {err_up}. Automatically rolling back...")
            execute_rollback(rollback_info)
            return False

        # Step 4: Verify health
        write_status("verifying", "Verifying application health post-upgrade...")
        if check_api_health():
            write_status("complete", f"Successfully upgraded to {target_version}.", details={"version": target_version})
            log.info("Upgrade to %s completed successfully.", target_version)
            return True
        else:
            log.error("Application failed health check after upgrade to %s. Initiating automatic rollback...", target_version)
            write_status("reverting", f"Application failed health check after upgrade. Automatically rolling back to {current_version}...")
            execute_rollback(rollback_info)
            return False

    except Exception as e:
        log.error("Exception during compose upgrade: %s. Initiating automatic rollback...", e)
        write_status("reverting", f"Upgrade error: {e}. Automatically rolling back...")
        execute_rollback(rollback_info)
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
    current_version = req.get("current_version", "unknown")

    if action == "upgrade":
        log.info("Processing pending upgrade request to version %s...", target_version)
        try:
            wait_for_drain()
            execute_compose_upgrade(target_version, current_version)
        finally:
            resume_fleet()
            try:
                os.remove(UPDATE_REQUEST_FILE)
            except OSError:
                pass
    elif action == "rollback":
        log.info("Processing pending rollback request to previous version %s...", target_version)
        try:
            wait_for_drain()
            execute_rollback()
        finally:
            resume_fleet()
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

