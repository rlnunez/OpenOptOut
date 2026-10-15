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

RUN chmod +x /app/entrypoint.sh /app/updater.py

ENTRYPOINT ["/app/entrypoint.sh"]

