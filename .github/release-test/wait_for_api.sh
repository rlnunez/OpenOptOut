#!/usr/bin/env bash
# Wait until the api container answers /api/health (checked from INSIDE the
# container, so nginx doesn't log "connection refused" while the API boots).
# Fails early if any container exits. Run from the directory with docker-compose.yml.
#
#   wait_for_api.sh [seconds] [containers-report-file]
set -uo pipefail

limit="${1:-420}"
report="${2:-/dev/null}"
start=$(date +%s)

while :; do
  if docker compose exec -T api curl -fsS http://localhost:8000/api/health >/dev/null 2>&1; then
    echo "API healthy after $(( $(date +%s) - start ))s"
    break
  fi
  if [ -n "$(docker compose ps -a --status exited -q)" ]; then
    echo "::error::A container exited during startup."
    break
  fi
  if [ $(( $(date +%s) - start )) -ge "$limit" ]; then
    echo "::error::API was not healthy after ${limit}s."
    break
  fi
  sleep 3
done

docker compose ps -a | tee "$report"
exited="$(docker compose ps -a --status exited --format '{{.Name}} (exit code {{.ExitCode}})' | tr '\n' ' ')"
if [ -n "$exited" ]; then
  echo "::error::These containers stopped: $exited"
  exit 1
fi
docker compose exec -T api curl -fsS http://localhost:8000/api/health && echo
