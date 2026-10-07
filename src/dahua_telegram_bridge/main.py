from __future__ import annotations

import asyncio
import logging
from aiohttp import web

from .config import load_config
from .dahua.client import DahuaClient
from .service import BridgeService
from .telegram.client import TelegramClient


async def run(config_path: str | None = None) -> None:
    config = load_config(config_path)
    logging.basicConfig(level=getattr(logging, config.log_level.upper(), logging.INFO), format="%(asctime)s %(levelname)s %(name)s %(message)s")
    dahua, telegram = DahuaClient(config.dahua), TelegramClient(config.telegram)
    service = BridgeService(config, dahua, telegram)
    app = web.Application()
    async def health(_request: web.Request) -> web.Response:
        return web.json_response({"alive": True, "nvr_connected": service.health.nvr_connected, "last_event": service.health.last_event.isoformat() if service.health.last_event else None, "last_telegram": service.health.last_telegram.isoformat() if service.health.last_telegram else None, "reconnect_count": service.health.reconnect_count})

    app.router.add_get("/health", health)
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
