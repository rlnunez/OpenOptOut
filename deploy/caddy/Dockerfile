# ==============================================================================
# Caddy "extended": stock Caddy plus two modules OpenOptOut uses —
#   - caddy-dns/cloudflare     Let's Encrypt via Cloudflare DNS (ACME_CHALLENGE=cloudflare)
#   - mholt/caddy-ratelimit    per-visitor request limits (RATE_LIMIT=on)
#
# The stock caddy image has neither, so the `caddy-extended` service (Compose profile https-caddy-extended) builds this locally the first time it starts; enable-https.sh picks that profile whenever either feature is on. The stock `caddy` service stays for anyone who turns both off.
#
# Versions are pinned together on purpose — bump them together:
#   - caddy-dns/cloudflare v0.2.x needs Caddy 2.10+ (newer certmagic/libdns); v0.1.0 is the release whose dependencies match Caddy 2.8.4.
#   - caddy-ratelimit has no recent tags; b8d8c9a (2026-01-16) is the newest commit still built against Caddy 2.8 (the next one moves to 2.10).
# .github/workflows/front-door.yml builds this image and checks the generated configs against it.
# ==============================================================================
FROM caddy:2.8.4-builder-alpine AS builder
RUN xcaddy build v2.8.4 \
      --with github.com/caddy-dns/cloudflare@v0.1.0 \
      --with github.com/mholt/caddy-ratelimit@b8d8c9a9d99ee352d675cbbe416ec2b489fc8cab

FROM caddy:2.8.4-alpine
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
# Same as the stock image: lets Caddy bind ports 80/443 (COPY drops file capabilities).
RUN setcap cap_net_bind_service=+ep /usr/bin/caddy
# Fails the build early if a module didn't make it in.
RUN caddy list-modules | grep -q '^dns.providers.cloudflare$' \
 && caddy list-modules | grep -q '^http.handlers.rate_limit$'
