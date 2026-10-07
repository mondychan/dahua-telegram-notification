#!/bin/sh
set -eu
IMAGE="${IMAGE:-ghcr.io/mondychan/dahua-telegram-notification:latest}"
COMPOSE="docker compose -f deploy/docker-compose.prod.yml"
mkdir -p deploy
CURRENT="$($COMPOSE ps -q dahua-telegram-bridge 2>/dev/null | head -n 1 || true)"
if [ -n "$CURRENT" ]; then
  docker inspect --format '{{.Config.Image}}' "$CURRENT" > deploy/previous-image
fi
docker pull "$IMAGE"
$COMPOSE up -d
for i in $(seq 1 30); do
  if $COMPOSE ps --format '{{.Health}}' | grep -q healthy; then exit 0; fi
  sleep 2
done
echo "Healthcheck failed" >&2
if [ -s deploy/previous-image ]; then
  PREVIOUS=$(cat deploy/previous-image)
  echo "Rolling back to $PREVIOUS" >&2
  IMAGE="$PREVIOUS" $COMPOSE up -d
  for i in $(seq 1 30); do
    if $COMPOSE ps --format '{{.Health}}' | grep -q healthy; then exit 1; fi
    sleep 2
  done
fi
exit 1
