# Dahua Telegram Bridge

Persistentní bridge pro Dahua NVR event stream a Telegram Bot API. Používá `eventManager.cgi` (volitelně `snapManager.cgi`), po eventu ihned zkusí snapshot a odešle `sendPhoto`; při chybě snapshotu odešle text.

Zkopírujte `.env.example` do `.env`, vyplňte údaje a spusťte `docker compose up -d --build`. Health endpoint je `GET /health`. Lokálně: `pip install -e '.[dev]' && python -m dahua_telegram_bridge.main`.

Diagnostika: `DAHUA_CONFIG=config.example.yaml python -m tools.probe_dahua`. Probe vypisuje raw payload i normalizovaný event a neukazuje tajné hodnoty. Parser toleruje různé názvy klíčů (`Code`, `action`, `index/channel`, `ObjectType`, `Name/Rule`). Povolené eventy jsou v `events.enabled`.

Vývojové kontroly: `pytest`, `ruff check .`, `mypy src`. Reálný NVR režim je oddělen od CI a používá proměnné `DAHUA_HOST`, `DAHUA_USERNAME`, `DAHUA_PASSWORD`, `DAHUA_CHANNEL`.

## Production operation

The event path is a persistent `eventManager.cgi` connection with Digest authentication, followed by `snapshot.cgi` and Telegram `sendPhoto`. Set `DAHUA_STREAM=snapmanager` to probe the alternative `snapManager.cgi` stream; the current NVR accepted the endpoint but produced no payload during the observation window. `SNAPSHOT_MODE=auto` is reserved for selecting the event-stream/direct strategy.

Set `TELEGRAM_ENABLED=false` for a dry run. The service logs the notification decision and never calls Telegram. Health is available at `/health`; counters are exposed at `/metrics`.

The production compose and deployment helper are in `deploy/`. They pull `ghcr.io/mondychan/dahua-telegram-notification:latest`, run as a restricted container, enforce a healthcheck, memory/CPU limits, and JSON log rotation. Real-NVR integration tests are under `tests/integration/` and require `DAHUA_INTEGRATION=1`; they never require Telegram.

CI runs Ruff, mypy, pytest, coverage, and Docker build on pushes and pull requests. A push to `main` publishes the container to GHCR; version tags `vX.Y.Z` are also supported by the release workflow.

Current validation status: the real NVR stream and direct JPEG snapshot are verified, while CrossLineDetection and Human/SMD still require a manually triggered camera event. The `snapManager.cgi` endpoint returned HTTP 200 but produced no event/JPEG during the observation window. Local tests cover parser, filtering, deduplication, timing, dry-run, and Telegram retry behavior; NVR event HTTP integration remains mock/integration-only.
