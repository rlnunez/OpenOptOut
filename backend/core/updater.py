"""
OpenOptOut System Updater & Release Notification Core.

Handles:
  - Checking GitHub releases API for application updates.
  - Querying the local Docker daemon (/var/run/docker.sock) for Docker Engine status.
  - Managing update policies: approval_required (default), notify_only, auto_install, disabled.
  - Coordinating workload draining before container upgrades.
"""

import json
import logging
import os
import re
import socket
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Tuple
from http.client import HTTPConnection

from .settings_store import load_settings, save_settings
from .version import get_version, get_commit

log = logging.getLogger(__name__)

DOCKER_SOCKET_PATH = os.getenv("DOCKER_SOCKET_PATH", "/var/run/docker.sock")
GITHUB_API_URL = "https://api.github.com/repos/rlnunez/OpenOptOut/releases"
CACHE_TTL_SECONDS = 3600  # 1 hour
UPDATE_REQUEST_FILE = os.getenv("UPDATE_REQUEST_FILE", "/data/update_request.json")
UPDATE_STATUS_FILE = os.getenv("UPDATE_STATUS_FILE", "/data/update_status.json")

DEFAULT_UPDATER_CONFIG = {
    "policy": "approval_required",  # approval_required, notify_only, auto_install, disabled
    "channel": "stable",            # stable, pre_release
    "ignored_releases": [],
    "last_checked": None,
    "latest_release": None,
    "docker_info": None,
    "state": "idle",                # idle, checking, draining, updating, error
    "state_message": "",
}


class _UnixSocketHTTPConnection(HTTPConnection):
    """HTTPConnection that communicates over a Unix Domain Socket."""
    def __init__(self, socket_path: str, timeout: int = 5):
        super().__init__("localhost", timeout=timeout)
        self.socket_path = socket_path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.socket_path)


def get_updater_config() -> Dict[str, Any]:
    s = load_settings()
    cfg = dict(DEFAULT_UPDATER_CONFIG)
    cfg.update(s.get("updater", {}))
    return cfg


def save_updater_config(cfg: Dict[str, Any]) -> None:
    s = load_settings()
    s["updater"] = cfg
    save_settings(s)


def parse_semver(tag: str) -> Tuple[int, int, int, str]:
    """Parse semver string into comparable tuple: (major, minor, patch, pre_release_tag)."""
    clean = tag.lstrip("v").strip()
    match = re.match(r"^(\d+)\.(\d+)(?:\.(\d+))?(?:-([a-zA-Z0-9.\-_]+))?$", clean)
    if not match:
        return (0, 0, 0, tag)
    major = int(match.group(1))
    minor = int(match.group(2))
    patch = int(match.group(3) or 0)
    pre = match.group(4) or ""
    return (major, minor, patch, pre)


def is_newer_version(candidate_tag: str, current_tag: str) -> bool:
    """Return True if candidate_tag is strictly newer than current_tag."""
    if not candidate_tag:
        return False
    cand_parts = parse_semver(candidate_tag)
    curr_parts = parse_semver(current_tag)

    # Compare major.minor.patch
    if cand_parts[:3] > curr_parts[:3]:
        return True
    if cand_parts[:3] < curr_parts[:3]:
        return False

    # Same major.minor.patch: final release is newer than release candidates / alphas
    cand_pre, curr_pre = cand_parts[3], curr_parts[3]
    if not cand_pre and curr_pre:
        return True
    if cand_pre and not curr_pre:
        return False
    if cand_pre and curr_pre:
        return cand_pre > curr_pre
    return False


def query_docker_socket() -> Optional[Dict[str, Any]]:
    """Query local Docker engine API over /var/run/docker.sock if present."""
    if not os.path.exists(DOCKER_SOCKET_PATH):
        return None

    try:
        conn = _UnixSocketHTTPConnection(DOCKER_SOCKET_PATH, timeout=3)
        conn.request("GET", "/version")
        resp = conn.getresponse()
        if resp.status == 200:
            data = json.loads(resp.read().decode("utf-8"))
            conn.close()
            version_str = data.get("Version", "unknown")
            return {
                "available": True,
                "version": version_str,
                "api_version": data.get("ApiVersion", ""),
                "os": data.get("Os", ""),
                "arch": data.get("Arch", ""),
                "needs_host_update": _check_docker_outdated(version_str),
            }
        conn.close()
    except Exception as e:
        log.debug("Docker socket query failed: %s", e)

    return {"available": False, "version": None, "needs_host_update": False}


def _check_docker_outdated(docker_version: str) -> bool:
    """Audit Docker Engine version; flag if below modern Compose v2 / tmpfs baseline (Docker 24+)."""
    try:
        clean = docker_version.split("-")[0]
        major = int(clean.split(".")[0])
        return major < 24
    except Exception:
        return False


def fetch_github_releases(channel: str = "stable") -> Optional[Dict[str, Any]]:
    """Fetch latest release from GitHub Releases API."""
    req = urllib.request.Request(
        GITHUB_API_URL,
        headers={
            "User-Agent": f"OpenOptOut-Updater/{get_version()}",
            "Accept": "application/vnd.github.v3+json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status != 200:
                return None
            releases = json.loads(resp.read().decode("utf-8"))
            if not isinstance(releases, list) or not releases:
                return None

            for r in releases:
                if r.get("draft"):
                    continue
                is_prerelease = bool(r.get("prerelease"))
                if channel == "stable" and is_prerelease:
                    continue

                tag = r.get("tag_name", "").strip()
                return {
                    "tag_name": tag,
                    "name": r.get("name") or tag,
                    "published_at": r.get("published_at"),
                    "body": r.get("body", ""),
                    "html_url": r.get("html_url", ""),
                    "prerelease": is_prerelease,
                }
    except Exception as e:
        log.warning("Failed to fetch releases from GitHub: %s", e)
        return None

    return None


def check_for_updates(force: bool = False) -> Dict[str, Any]:
    """Audit for new OpenOptOut releases and Docker engine status."""
    cfg = get_updater_config()
    current_ver = get_version()

    if cfg.get("policy") == "disabled":
        return {
            "policy": "disabled",
            "current_version": current_ver,
            "has_update": False,
            "latest_release": None,
            "docker_info": None,
        }

    now_ts = int(time.time())
    last_checked_ts = cfg.get("_last_checked_ts", 0)

    # Use cached release if within TTL and not forcing
    if not force and cfg.get("latest_release") and (now_ts - last_checked_ts < CACHE_TTL_SECONDS):
        latest = cfg.get("latest_release")
        docker_info = cfg.get("docker_info") or query_docker_socket()
    else:
        latest = fetch_github_releases(channel=cfg.get("channel", "stable"))
        docker_info = query_docker_socket()
        if latest:
            cfg["latest_release"] = latest
            cfg["_last_checked_ts"] = now_ts
            cfg["last_checked"] = datetime.now(timezone.utc).isoformat()
        if docker_info:
            cfg["docker_info"] = docker_info
        save_updater_config(cfg)

    latest_tag = latest.get("tag_name", "") if latest else ""
    is_newer = is_newer_version(latest_tag, current_ver)
    is_ignored = latest_tag in cfg.get("ignored_releases", [])

    return {
        "policy": cfg.get("policy", "approval_required"),
        "channel": cfg.get("channel", "stable"),
        "current_version": current_ver,
        "latest_release": latest,
        "has_update": is_newer and not is_ignored,
        "is_ignored": is_ignored,
        "ignored_releases": cfg.get("ignored_releases", []),
        "last_checked": cfg.get("last_checked"),
        "docker_info": docker_info,
        "state": cfg.get("state", "idle"),
        "state_message": cfg.get("state_message", ""),
    }


def request_system_update(target_tag: Optional[str] = None) -> Dict[str, Any]:
    """
    Queue an update request for the companion updater daemon:
      1. Pauses scheduler to stop dispatching new removals.
      2. Writes atomic update request envelope to /data/update_request.json.
    """
    cfg = get_updater_config()
    current_ver = get_version()
    target = target_tag or (cfg.get("latest_release", {}) or {}).get("tag_name")

    if not target:
        raise ValueError("No target release specified or available to install.")

    # 1. Pause scheduler
    try:
        from .scheduler import pause_scheduler
        pause_scheduler()
    except Exception as e:
        log.warning("Could not pause scheduler directly: %s", e)

    # 2. Write request envelope for the updater container
    payload = {
        "action": "upgrade",
        "current_version": current_ver,
        "target_version": target,
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "status": "pending_drain",
    }

    tmp_file = UPDATE_REQUEST_FILE + ".tmp"
    with open(tmp_file, "w") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp_file, UPDATE_REQUEST_FILE)

    cfg["state"] = "draining"
    cfg["state_message"] = f"Draining active broker removals before updating to {target}..."
    save_updater_config(cfg)

    return {"status": "ok", "target_version": target, "state": "draining"}

