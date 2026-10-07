from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx


class TelegramClient:
    def __init__(self, config: Any) -> None:
        self.config = config
        self.client = httpx.AsyncClient(timeout=config.timeout_seconds)

    async def close(self) -> None:
        await self.client.aclose()

    async def send(self, caption: str, photo: bytes | None = None) -> None:
        if not self.config.enabled:
            logging.getLogger(__name__).info("dry-run telegram send photo=%s", bool(photo))
            return
        url = (
            f"https://api.telegram.org/bot{self.config.bot_token}/sendPhoto"
            if photo
            else f"https://api.telegram.org/bot{self.config.bot_token}/sendMessage"
        )
        for attempt in range(self.config.max_retries + 1):
            try:
                if photo:
                    response = await self.client.post(
                        url,
                        data={"chat_id": self.config.chat_id, "caption": caption},
                        files={"photo": ("snapshot.jpg", photo, "image/jpeg")},
                    )
                else:
                    response = await self.client.post(
                        url, data={"chat_id": self.config.chat_id, "text": caption}
                    )
                if response.status_code == 429 and attempt < self.config.max_retries:
                    await asyncio.sleep(
                        float(
                            response.headers.get(
                                "retry-after", self.config.backoff_seconds * (2**attempt)
                            )
                        )
                    )
                    continue
                if response.status_code >= 500 and attempt < self.config.max_retries:
                    await asyncio.sleep(self.config.backoff_seconds * (2**attempt))
                    continue
                response.raise_for_status()
                return
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt >= self.config.max_retries:
                    raise
                await asyncio.sleep(self.config.backoff_seconds * (2**attempt))
