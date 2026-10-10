# ==============================================================================
# Caddy with the Cloudflare DNS module, for ACME_CHALLENGE=cloudflare.
#
# The stock caddy image can't create DNS records, so Let's Encrypt via
# Cloudflare DNS needs this build. It's only used by the `caddy-dns` service
# (Compose profile https-caddy-dns); everyone else keeps the stock image and
# never builds this.
#
# Versions are pinned together on purpose: caddy-dns/cloudflare v0.2.x needs
# Caddy 2.10+ (newer certmagic/libdns). v0.1.0 is the release whose
# dependencies match Caddy 2.8.4. Bump both together.
# ==============================================================================
FROM caddy:2.8.4-builder-alpine AS builder
RUN xcaddy build v2.8.4 --with github.com/caddy-dns/cloudflare@v0.1.0

FROM caddy:2.8.4-alpine
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
# Same as the stock image: lets Caddy bind ports 80/443 (COPY drops file capabilities).
RUN setcap cap_net_bind_service=+ep /usr/bin/caddy
# Fails the build early if the module didn't make it in.
RUN caddy list-modules | grep -q '^dns.providers.cloudflare$'
