#!/bin/sh
set -e

if [ ! -e /var/run/docker.sock ]; then
    echo "[updater] WARNING: /var/run/docker.sock not found. The updater requires access to the host Docker socket to manage containers."
fi

exec python3 /app/updater.py "$@"

