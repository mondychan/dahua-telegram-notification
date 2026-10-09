# Dahua Telegram Bridge

Persistentní bridge pro Dahua NVR event stream a Telegram Bot API. Používá `eventManager.cgi`, okamžitě po příchodu události vyhodnocuje pravidla, stahuje snapshot ze `snapshot.cgi` a odesílá `sendPhoto`; při výpadku snapshotu bezpečně odesílá textový fallback.

## Klíčové vlastnosti

- **Parsování reálných Dahua IVS / SMD eventů:**
  - `CrossLineDetection`: spolehlivá detekce objektů `Human` i `Vehicle`, směru `Direction`, `RuleID`, `EventID` a vnořených struktur bez uříznutí payloadu (`data` není `{"`).
  - `SmartMotionHuman`: tolerance pro firmware klíče `HumamID` i `HumanID`, extrakce detekčního obdélníku `Rect`.
  - `SmartMotionVehicle`: normalizace typu `Vehicle`, extrakce `VehicleID` a `Rect`.
  - `VideoMotion`: obecná detekce pohybu, nezaměňována za klasifikovaného člověka či vozidlo.
  - Plná podpora variant `Start` i `Stop`.
- **Kanály a číslování:**
  - Oddělené uchovávání `raw_index` (0-based z firmware) a uživatelského `channel_number` (CH1, CH2, ...).
  - Možnost automatického nebo manuálního mapování kanálů a vlastního číslování snapshotů.
- **Správa kanálů v UI (Per-Channel Monitoring):**
  - Každou kameru lze v UI přepnout na `Monitoring ON / OFF`.
  - Při vypnutí monitoringu listener zůstává připojen k NVR, eventy se zaznamenávají jako diagnostické záznamy s důvodem `Filtered: channel monitoring disabled`, ale netestují snapshot ani neposílají Telegram.
- **Pravidla jednotlivých eventů (Per-Event Rules):**
  - Granulární nastavení pravidel pro kombinace Channel, Event Type, Object Type.
  - Oddělené povolení monitoringu eventu a Telegram notifikace.
- **Globální Master Switch pro Telegram:**
  - Persistentní přepínač `Telegram notifications: ON / OFF` na Dashboardu a v Settings.
  - Bezpečnostní pojistka: `TELEGRAM_ENABLED=false` v systémovém ENV představuje absolutní zákaz odesílání, který UI nemůže obejít.
- **Audit změn konfigurace:**
  - Každá změna z UI je auditována v SQLite se záznamem času, typu nastavení, kanálu, staré a nové hodnoty.
  - Citlivé údaje (tokeny, hesla) jsou v logu i API automaticky maskovány.

## Spuštění a deployment

Zkopírujte `.env.example` do `.env`, vyplňte údaje a spusťte:

```bash
docker compose -f deploy/docker-compose.prod.yml up -d
```

Lokální spuštění:
```bash
pip install -e '.[dev]'
python -m dahua_telegram_bridge.main
```

## Ověřovací příkazy

```bash
ruff check .
ruff format --check .
mypy src
pytest -q
pytest --cov=src --cov-report=term-missing
docker build -t dahua-telegram-bridge .
```
