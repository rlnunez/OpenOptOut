ARG RCLONE_VERSION=v1.75.2
# Pinned to bookworm (Debian 12). The unpinned python:3.12-slim now resolves to
# trixie (Debian 13), where several packages Playwright 1.44's `install-deps`
# expects were renamed/removed (libgdk-pixbuf2.0-0, ttf-unifont,
# ttf-ubuntu-font-family), breaking the browser dependency install. Bookworm
# matches Playwright 1.44's dependency list and has arm64 images for Mac Silicon.
# Declared before any FROM so it's usable as a global build arg in every
# FROM below (Docker requires that placement, not just an earlier line).
ARG PYTHON_BASE=python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258

# Stage 0: Build rclone with patched Go runtime (remediating CVE-2026-111943)
# and patched chi v5.4.0 (remediating CVE-2026-114437)
FROM golang:1.27.3-bookworm@sha256:972b4110ba0f47539a975c31e52c64765e1ff19f2d74469ae4a595c6676e80a5 AS rclone-builder
ARG RCLONE_VERSION
RUN git clone --depth 1 --branch ${RCLONE_VERSION} https://github.com/rclone/rclone.git /src/rclone
WORKDIR /src/rclone
RUN go get github.com/go-chi/chi/v5@v5.4.0 && \
    CGO_ENABLED=0 go build -ldflags="-s -w" -o /go/bin/rclone .

# Stage 1: compile the Python deps that ship no prebuilt wheels (python-ldap
# needs libldap2-dev/libsasl2-dev headers; sqlcipher3-binary may need to build
# from source on platforms with no prebuilt wheel). gcc/build-essential/the
# -dev packages never leave this stage (CIS Docker Benchmark 4.3) — the final
# image below only gets the compiled result plus the runtime shared libraries
# those compiled extensions actually load (verified via `ldd` against the
# compiled _ldap.so).
FROM ${PYTHON_BASE} AS pydeps-builder
WORKDIR /app
COPY requirements.txt requirements-encryption.txt install_deps.py ./
# hadolint ignore=DL3008
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc build-essential libldap2-dev libsasl2-dev libsqlcipher-dev \
    && rm -rf /var/lib/apt/lists/*
ARG WITH_ENCRYPTION=true
ENV WITH_ENCRYPTION=${WITH_ENCRYPTION}
RUN --mount=type=cache,target=/root/.cache/pip python3 install_deps.py && \
    rm -rf /usr/local/lib/python*/ensurepip/_bundled \
           /usr/local/lib/python*/site-packages/pip-25* \
           /usr/local/lib/python*/site-packages/pip/_vendor/bom.cdx.json

FROM ${PYTHON_BASE}

# Which git commit this image was built from, if known (docker-compose.yml
# passes it as a build arg; scripts/install.sh and deploy/native/install.sh
# capture it automatically from the checkout when it's a real git checkout).
# Read by core/version.py — logged at startup and served from /api/health, so
# there's never a question of exactly what code is running versus what was
# deployed. "unknown" (the default) if nothing supplied one — a downloaded
# zip release, for instance, has no commit to report.
ARG GIT_COMMIT=unknown
ENV GIT_COMMIT=${GIT_COMMIT}

# Runtime-only system deps for Playwright Firefox + plugin sandboxing
# (bubblewrap) + the shared libraries python-ldap's compiled extension and
# (on platforms where it built) sqlcipher3's extension load at import time —
# no compiler or header package among them.
# hadolint ignore=DL3008
RUN apt-get update && \
    apt-get upgrade -y --no-install-recommends && \
    apt-get install -y --no-install-recommends \
    wget curl ca-certificates fonts-liberation git \
    libpci3 \
    libasound2 \
    libatk-bridge2.0-0 libatk1.0-0 libcups2 libdbus-1-3 \
    libdrm2 libgbm1 libgtk-3-0 libnspr4 libnss3 \
    libx11-xcb1 libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libxss1 libxtst6 xdg-utils \
    bubblewrap libseccomp2 python3-seccomp \
    xmlsec1 \
    libldap-2.5-0 libsasl2-2 libsqlcipher0 \
    && rm -rf /var/lib/apt/lists/*

# Purge base-image pre-bundled site-packages and ensurepip bootstrap wheels
# before copying the hardened site-packages from the builder stage, preventing
# stale dist-info (pip 25.0.1, setuptools 70.3.0) from persisting in the final image.
RUN rm -rf /usr/local/lib/python*/site-packages/* /usr/local/lib/python*/ensurepip/_bundled

# The compiled Python packages from the builder stage above (site-packages)
# plus their console-script entry points (uvicorn, playwright, ...) — same
# base image/Python build as this stage, so this is a same-lineage copy, not
# a cross-image one.
COPY --from=pydeps-builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=pydeps-builder /usr/local/bin /usr/local/bin
RUN rm -rf /usr/local/lib/python*/site-packages/pip-25* \
           /usr/local/lib/python*/site-packages/pip/_vendor/bom.cdx.json \
           /root/.cache

# rclone, for the "Other cloud storage" backup option (Proton Drive, Box,
# pCloud, MEGA, Nextcloud...). Built from source via rclone-builder using
# Go 1.27.3 to remediate CVE-2026-111943 (crypto/x509 intermediate CA vulnerability).
# Best-effort: without it, only that one backup option is unavailable.
COPY --from=rclone-builder /go/bin/rclone /usr/local/bin/rclone
RUN chmod 755 /usr/local/bin/rclone && /usr/local/bin/rclone --version

WORKDIR /app

ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    XDG_CACHE_HOME=/tmp/.cache \
    XDG_CONFIG_HOME=/tmp/.config \
    MOZ_DISABLE_RDD_SANDBOX=1
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

# VERSION must be a real, non-empty file inside this build context. A symlink pointing outside ./backend arrives dangling and the API would report "unknown", so fail the build loudly instead of shipping that.
RUN if [ -L VERSION ] || [ ! -s VERSION ]; then \
      echo "ERROR: backend/VERSION must be a real non-empty file (not a symlink) inside the build context" >&2; exit 1; \
    fi

# Data directories (screenshots, plugins, plugin storage) and unprivileged user
RUN groupadd -g 1000 appuser && \
    useradd -u 1000 -g appuser -m -s /bin/bash appuser && \
    mkdir -p /data/screenshots /data/plugins /data/plugin_storage \
             /home/appuser/.cache /home/appuser/.mozilla \
             /root/.cache /root/.mozilla && \
    chown -R appuser:appuser /data /app /ms-playwright /home/appuser && \
    touch /app/__init__.py && \
    for d in models routers core; do \
      [ -d "/app/$d" ] && touch "/app/$d/__init__.py"; \
    done

# Strip setuid/setgid from every multi-user-system binary this single-user,
# non-interactive container never calls (su, passwd, mount, chage, the dbus
# launch helper, etc. — CIS Docker Benchmark 4.8). bubblewrap (bwrap) is
# deliberately NOT setuid in this image to begin with — plugin sandboxing
# gets its privilege from this container's own cap_add: SYS_ADMIN grant
# (docker-compose.yml), never from a setuid-root bwrap — so there is nothing
# here that sandboxing depends on.
RUN find / -xdev -type f \( -perm -4000 -o -perm -2000 \) -exec chmod a-s {} \; 2>/dev/null || true

# NOTE ON SECCOMP: the plugin syscall filter needs libseccomp (libseccomp2, installed
# above) plus Python bindings that THIS interpreter can import. Debian's
# python3-seccomp only serves the distro's own /usr/bin/python3, not the python.org
# interpreter this image runs, so requirements.txt installs `pyseccomp` (pure Python
# over ctypes) instead. If the bindings are ever missing the plugin runner degrades
# gracefully and the admin UI reports the reduced posture.

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["curl", "-f", "http://localhost:8000/api/health"]
# Run from / so that `app` is importable as a package; main.py's relative
# imports (from .models, from .routers, from .core) then resolve correctly.
WORKDIR /
USER 1000:1000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
