FROM node:26-alpine@sha256:0b36e8c136b94cd4fcf02188228e76c31ad5872eef3fec8cbd2eee500cfd9e80 AS builder
WORKDIR /app
RUN chown -R node:node /app
USER 1000:1000
COPY --chown=node:node package.json package-lock.json .npmrc* ./
RUN npm ci --legacy-peer-deps
COPY --chown=node:node . .
RUN npm run build

FROM nginx:alpine
# Upgrade all Alpine base packages to resolve security vulnerabilities (libexpat, libuuid, etc.)
# Install libcap to allow nginx to bind port 80 as unprivileged 'nginx' user
# hadolint ignore=DL3018
RUN apk update && apk upgrade --no-cache && \
    apk add --no-cache libcap curl && \
    setcap 'cap_net_bind_service=+ep' /usr/sbin/nginx && \
    sed -i '/user  nginx;/d' /etc/nginx/nginx.conf && \
    sed -i 's|/var/run/nginx.pid|/tmp/nginx.pid|g' /etc/nginx/nginx.conf && \
    touch /tmp/nginx.pid && \
    chown -R nginx:nginx /tmp/nginx.pid /var/cache/nginx /var/log/nginx /etc/nginx

COPY --from=builder --chown=nginx:nginx /app/dist /usr/share/nginx/html
COPY --chown=nginx:nginx nginx.conf /etc/nginx/conf.d/default.conf

USER 101:101
EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD ["curl", "-f", "http://127.0.0.1/"]
