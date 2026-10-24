#!/bin/sh
set -e

# The real socket is never mounted into this container (CIS Docker Benchmark
# 5.32) — docker-compose.yml routes it through docker-socket-proxy instead,
# via DOCKER_HOST, which the docker/docker-compose CLIs read automatically.
if [ -z "$DOCKER_HOST" ] && [ ! -e /var/run/docker.sock ]; then
    echo "[updater] WARNING: neither DOCKER_HOST nor /var/run/docker.sock is set. The updater needs one of them to manage containers."
fi

exec python3 /app/updater.py "$@"

