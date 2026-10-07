#!/bin/sh
set -eu
IMAGE="${IMAGE:-ghcr.io/mondychan/dahua-telegram-notification:latest}"
COMPOSE="docker compose -f deploy/docker-compose.prod.yml"
mkdir -p deploy
printf '%s\n' "$IMAGE" > deploy/previous-image
docker pull "$IMAGE"
$COMPOSE up -d
for i in $(seq 1 30); do
  if $COMPOSE ps --format '{{.Health}}' | grep -q healthy; then exit 0; fi
  sleep 2
done
echo "Healthcheck failed" >&2
exit 1
