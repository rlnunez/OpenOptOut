# Pinned to bookworm (Debian 12). The unpinned python:3.12-slim now resolves to
# trixie (Debian 13), where several packages Playwright 1.44's `install-deps`
# expects were renamed/removed (libgdk-pixbuf2.0-0, ttf-unifont,
# ttf-ubuntu-font-family), breaking the browser dependency install. Bookworm
# matches Playwright 1.44's dependency list and has arm64 images for Mac Silicon.
FROM python:3.12-slim-bookworm@sha256:54c85f3c47607a77f32adec749d3c81d1348bf25833671f512b26a9b6d778cb3

# Which git commit this image was built from, if known (docker-compose.yml
# passes it as a build arg; scripts/install.sh and deploy/native/install.sh
# capture it automatically from the checkout when it's a real git checkout).
# Read by core/version.py — logged at startup and served from /api/health, so
# there's never a question of exactly what code is running versus what was
# deployed. "unknown" (the default) if nothing supplied one — a downloaded
# zip release, for instance, has no commit to report.
ARG GIT_COMMIT=unknown
ENV GIT_COMMIT=${GIT_COMMIT}

# Install system deps for Playwright Firefox + plugin sandboxing (bubblewrap)
# and the build toolchain + headers required to compile python-ldap
# (libldap2-dev, libsasl2-dev) which ships no prebuilt wheels.
# hadolint ignore=DL3008
RUN apt-get update && \
    apt-get upgrade -y --no-install-recommends && \
    apt-get install -y --no-install-recommends \
    wget curl ca-certificates fonts-liberation \
    libatk-bridge2.0-0 libatk1.0-0 libcups2 libdbus-1-3 \
    libdrm2 libgbm1 libgtk-3-0 libnspr4 libnss3 \
    libx11-xcb1 libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libxss1 libxtst6 xdg-utils \
    bubblewrap libseccomp2 python3-seccomp \
    xmlsec1 \
    gcc build-essential libldap2-dev libsasl2-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt requirements-encryption.txt install_deps.py ./

# Optional: file-level SQLCipher encryption. Off by default so the image builds
# on every platform (the app falls back to unencrypted SQLite and reports the
# reduced posture). Enable with:  docker build --build-arg WITH_ENCRYPTION=true
# The install is best-effort: if no wheel exists for the build platform it is
# skipped rather than failing the whole image.
ARG WITH_ENCRYPTION=false
ENV WITH_ENCRYPTION=${WITH_ENCRYPTION}
RUN python3 install_deps.py

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN playwright install firefox && \
    playwright install-deps firefox

COPY . .

# Compile plugin gRPC protocol stubs (best-effort; plugin system degrades
# gracefully if unavailable). Build context is the backend dir, so the proto
# lives at plugins/proto/ inside /app.
RUN python -m grpc_tools.protoc -Iplugins/proto \
      --python_out=plugins/proto --grpc_python_out=plugins/proto \
      plugins/proto/plugin.proto && \
    sed -i 's/^import plugin_pb2 as/from . import plugin_pb2 as/' plugins/proto/plugin_pb2_grpc.py && \
    touch plugins/proto/__init__.py \
    || echo "WARN: proto compile skipped — plugin system will be inactive"

# Data directories (screenshots, plugins, plugin storage) and unprivileged user
RUN groupadd -g 1000 appuser && \
    useradd -u 1000 -g appuser -m -s /bin/bash appuser && \
    mkdir -p /data/screenshots /data/plugins /data/plugin_storage && \
    chown -R appuser:appuser /data /app /ms-playwright && \
    touch /app/__init__.py && \
    for d in models routers core; do \
      [ -d "/app/$d" ] && touch "/app/$d/__init__.py"; \
    done

# NOTE ON SECCOMP: python3-seccomp (installed above) provides libseccomp
# bindings. If the slim Python image cannot import them, the plugin runner
# degrades gracefully — namespace isolation (bubblewrap) + resource limits
# still apply, and the admin UI reports the reduced posture. For guaranteed
# seccomp on the python.org image, install the bindings into the app's
# interpreter (e.g. build libseccomp bindings) — see docs/PLUGINS.md.

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["curl", "-f", "http://localhost:8000/api/health"]
# Run from / so that `app` is importable as a package; main.py's relative
# imports (from .models, from .routers, from .core) then resolve correctly.
WORKDIR /
USER 1000:1000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
