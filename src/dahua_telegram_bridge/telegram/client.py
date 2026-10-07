from __future__ import annotations

import httpx
from typing import Any


class TelegramClient:
    def __init__(self, config: Any) -> None:
        self.config = config
        self.client = httpx.AsyncClient(timeout=config.timeout_seconds)

    async def close(self) -> None:
        await self.client.aclose()

    async def send(self, caption: str, photo: bytes | None = None) -> None:
        url = f"https://api.telegram.org/bot{self.config.bot_token}/sendPhoto" if photo else f"https://api.telegram.org/bot{self.config.bot_token}/sendMessage"
        if photo:
            response = await self.client.post(url, data={"chat_id": self.config.chat_id, "caption": caption}, files={"photo": ("snapshot.jpg", photo, "image/jpeg")})
        else:
            response = await self.client.post(url, data={"chat_id": self.config.chat_id, "text": caption})
        response.raise_for_status()
