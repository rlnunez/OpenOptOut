"""
Version reporting — so there's never a question of exactly what code is
running. Logged clearly at startup and exposed via GET /api/health, so an
admin comparing "what I deployed" against "what's actually running" (or
attaching a log to a bug report) always has an unambiguous answer.

Two files, kept in sync manually (documented in README): backend/VERSION is
canonical for the running app (it's what actually ships inside the Docker
image — the build context is backend/ only, so a repo-root file wouldn't be
visible to the build); frontend/package.json's own "version" field is the
frontend's. The repo-root VERSION file exists as a plain, easy-to-find
reference for anyone looking at the source tree, not for either build.
"""

import os
import subprocess

_VERSION_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "VERSION")


def get_version() -> str:
    try:
        with open(_VERSION_FILE) as f:
            return f.read().strip() or "unknown"
    except Exception:
        return "unknown"


def get_commit() -> str:
    """
    The short git commit the running image was built from. Set at build
    time via the GIT_COMMIT build-arg/env var (docker-compose.yml passes it
    through; scripts/install.sh and the native installers capture it
    automatically from the checkout being built, when it's a git checkout at
    all — a downloaded zip or shallow/gitless copy has no commit to report).
    Falls back to asking git directly for a native/dev run where the env var
    was never set; "unknown" if neither source has an answer. Never raises.
    """
    env_commit = os.getenv("GIT_COMMIT", "").strip()
    if env_commit:
        return env_commit
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=os.path.dirname(_VERSION_FILE), capture_output=True, text=True, timeout=3,
        )
        if r.returncode == 0:
            out = r.stdout.strip()
            if out:
                return out
    except Exception:
        pass
    return "unknown"


def version_string() -> str:
    """e.g. 'PrivacyShield 0.1.0 (commit a1b2c3d)' or '... (commit unknown)'."""
    return f"PrivacyShield {get_version()} (commit {get_commit()})"
