#!/usr/bin/env bash
# Start isolated scanner toolbox container and install schemathesis
set -euo pipefail

mkdir -p dast-reports dast-private && chmod 777 dast-reports
docker run -d --name dast-tools -v "$PWD:/work" -w /work python:3.12-slim sleep infinity
docker exec dast-tools pip install --quiet "schemathesis==${SCHEMATHESIS_VERSION}"
docker network connect "$DAST_NET" dast-tools
