# Dahua Telegram Bridge

Persistentní bridge pro Dahua NVR event stream a Telegram Bot API. Používá `eventManager.cgi` (volitelně `snapManager.cgi`), po eventu ihned zkusí snapshot a odešle `sendPhoto`; při chybě snapshotu odešle text.

Zkopírujte `.env.example` do `.env`, vyplňte údaje a spusťte `docker compose up -d --build`. Health endpoint je `GET /health`. Lokálně: `pip install -e '.[dev]' && python -m dahua_telegram_bridge.main`.

Diagnostika: `DAHUA_CONFIG=config.example.yaml python -m tools.probe_dahua`. Probe vypisuje raw payload i normalizovaný event a neukazuje tajné hodnoty. Parser toleruje různé názvy klíčů (`Code`, `action`, `index/channel`, `ObjectType`, `Name/Rule`). Povolené eventy jsou v `events.enabled`.

Vývojové kontroly: `pytest`, `ruff check .`, `mypy src`. Reálný NVR režim je oddělen od CI a používá proměnné `DAHUA_HOST`, `DAHUA_USERNAME`, `DAHUA_PASSWORD`, `DAHUA_CHANNEL`.
