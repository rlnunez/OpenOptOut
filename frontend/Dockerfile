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
RUN apk update && apk upgrade --no-cache
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
