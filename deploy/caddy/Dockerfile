# ==============================================================================
# Caddy "extended": stock Caddy plus modules OpenOptOut uses:
#   - caddy-dns/cloudflare   Let's Encrypt via Cloudflare DNS (ACME_CHALLENGE=cloudflare)
#   - mholt/caddy-ratelimit  per-visitor request limits (RATE_LIMIT=on)
#
# Built locally by Compose profile `https-caddy-extended` via enable-https.sh.
# Stock Caddy remains available when neither feature is required.
# Pinned versions match Caddy 2.8.4 compatibility.
# ==============================================================================
FROM caddy:2.8.4-builder-alpine@sha256:4ac56838081008c467ae701ebf425c53db62f91e5fa723151904b9ee75d09346 AS builder
RUN xcaddy build v2.8.4 \
      --with github.com/caddy-dns/cloudflare@v0.1.0 \
      --with github.com/mholt/caddy-ratelimit@b8d8c9a9d99ee352d675cbbe416ec2b489fc8cab

FROM caddy:2.8.4-alpine@sha256:af32e97399febea808609119bb21544d0265c58a02836576e32a2d082c262c17
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
# Same as the stock image: lets Caddy bind ports 80/443 (COPY drops file capabilities).
RUN setcap cap_net_bind_service=+ep /usr/bin/caddy
# Fails the build early if a module didn't make it in.
RUN caddy list-modules | grep -q '^dns.providers.cloudflare$' \
 && caddy list-modules | grep -q '^http.handlers.rate_limit$'

# Create unprivileged caddy user and configure ownership for runtime directories
RUN (getent group caddy || addgroup -g 1000 -S caddy) && \
    (getent passwd caddy || adduser -u 1000 -D -S -G caddy caddy) && \
    mkdir -p /config /data /etc/caddy && \
    chown -R caddy:caddy /config /data /etc/caddy

USER 1000:1000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD pidof caddy || exit 1
