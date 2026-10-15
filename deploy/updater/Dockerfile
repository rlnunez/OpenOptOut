FROM alpine:3.20

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

