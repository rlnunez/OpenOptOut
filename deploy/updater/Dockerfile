FROM alpine:3.20@sha256:d9e853e87e55526f6b2917df91a2115c36dd7c696a35be12163d44e6e2a4b6bc

RUN apk add --no-cache \
    python3 \
    bash \
    docker-cli \
    docker-cli-compose \
    curl \
    ca-certificates

WORKDIR /app

COPY updater.py /app/updater.py
COPY entrypoint.sh /app/entrypoint.sh

RUN chmod +x /app/entrypoint.sh /app/updater.py && \
    addgroup -S -g 999 docker && \
    addgroup -S -g 1000 updater && \
    adduser -S -u 1000 -G updater -D -s /bin/sh updater && \
    addgroup updater docker

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python3 /app/updater.py --check || exit 1

USER 1000:1000

ENTRYPOINT ["/app/entrypoint.sh"]
