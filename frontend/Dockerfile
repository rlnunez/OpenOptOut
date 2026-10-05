FROM node:26-alpine AS builder
WORKDIR /app
RUN chown -R node:node /app
USER node
COPY --chown=node:node package.json package-lock.json* .npmrc* ./
RUN npm install --legacy-peer-deps
COPY --chown=node:node . .
RUN npm run build

FROM nginx:alpine
# Upgrade all Alpine base packages to resolve security vulnerabilities (libexpat, libuuid, etc.)
# Install libcap to allow nginx to bind port 80 as unprivileged 'nginx' user
RUN apk update && apk upgrade --no-cache && \
    apk add --no-cache libcap && \
    setcap 'cap_net_bind_service=+ep' /usr/sbin/nginx && \
    sed -i '/user  nginx;/d' /etc/nginx/nginx.conf && \
    sed -i 's|/var/run/nginx.pid|/tmp/nginx.pid|g' /etc/nginx/nginx.conf && \
    touch /tmp/nginx.pid && \
    chown -R nginx:nginx /tmp/nginx.pid /var/cache/nginx /var/log/nginx /etc/nginx

COPY --from=builder --chown=nginx:nginx /app/dist /usr/share/nginx/html
COPY --chown=nginx:nginx nginx.conf /etc/nginx/conf.d/default.conf

USER nginx
EXPOSE 80
