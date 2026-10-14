from __future__ import annotations

import asyncio
import logging
from aiohttp import web

from .config import load_config, validate_config
from .dahua.client import DahuaClient
from .service import BridgeService
from .telegram.client import TelegramClient
from .web import create_web_app
from .logbuffer import LogBuffer


async def run(config_path: str | None = None) -> None:
    config = load_config(config_path)
    validate_config(config)
    logging.basicConfig(
        level=getattr(logging, config.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    # httpx logs full request URLs. Telegram embeds the bot token in its URL.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    log_buffer = LogBuffer()
    log_buffer.setFormatter(logging.Formatter("%(message)s"))
    logging.getLogger().addHandler(log_buffer)
    dahua, telegram = DahuaClient(config.dahua), TelegramClient(config.telegram)
    service = BridgeService(config, dahua, telegram)
    app = create_web_app(service, config)
    service.store = app["store"]
    app["log_buffer"] = log_buffer

    async def health(_request: web.Request) -> web.Response:
        return web.json_response(
            {
                "alive": True,
                "nvr_connected": service.health.nvr_connected,
                "last_event": service.health.last_event.isoformat()
                if service.health.last_event
                else None,
                "last_telegram": service.health.last_telegram.isoformat()
                if service.health.last_telegram
                else None,
                "last_snapshot": service.health.last_snapshot.isoformat()
                if service.health.last_snapshot
                else None,
                "reconnect_count": service.health.reconnect_count,
                "processed_events": service.health.processed_events,
                "failed_events": service.health.failed_events,
                "snapshots_success": service.health.snapshots_success,
                "snapshots_failed": service.health.snapshots_failed,
                "telegram_sent": service.health.telegram_sent,
                "telegram_failed": service.health.telegram_failed,
            }
        )

    app.router.add_get("/health", health)

    async def metrics(_request: web.Request) -> web.Response:
        h = service.health
        values = {
            "events_received_total": h.events_received,
            "events_processed_total": h.processed_events,
            "events_filtered_total": h.events_filtered,
            "events_deduplicated_total": h.events_deduplicated,
            "events_failed_total": h.failed_events,
            "snapshots_success_total": h.snapshots_success,
            "snapshots_failed_total": h.snapshots_failed,
            "telegram_sent_total": h.telegram_sent,
            "telegram_failed_total": h.telegram_failed,
            "nvr_reconnect_total": h.reconnect_count,
        }
        return web.Response(
            text="\n".join(f"{key} {value}" for key, value in values.items()) + "\n",
            content_type="text/plain",
        )

    app.router.add_get("/metrics", metrics)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, config.health_host, config.health_port).start()
    try:
        await service.run()
    finally:
        await runner.cleanup()
        await dahua.close()
        await telegram.close()


if __name__ == "__main__":
    asyncio.run(run())
