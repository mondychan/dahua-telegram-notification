from __future__ import annotations

from collections.abc import AsyncIterator
import logging
from typing import Any

import httpx


log = logging.getLogger(__name__)


class DahuaClient:
    def __init__(self, config: Any) -> None:
        self.config = config
        self.client = httpx.AsyncClient(
            auth=httpx.DigestAuth(config.username, config.password),
            timeout=config.timeout_seconds,
            verify=False,
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def events(self) -> AsyncIterator[bytes]:
        path = "/cgi-bin/eventManager.cgi?action=attach&codes=[All]&heartbeat=5"
        if self.config.stream == "snapmanager":
            path = "/cgi-bin/snapManager.cgi?action=attachFileProc&Flags[0]=Event&Events=[All]&heartbeat=5"
        async with self.client.stream("GET", self.config.base_url + path) as response:
            response.raise_for_status()
            buffer = b""
            async for chunk in response.aiter_bytes():
                buffer += chunk
                while True:
                    separator = buffer.find(b"\r\n\r\n")
                    if separator < 0:
                        break
                    headers = buffer[:separator].decode("latin1", "replace")
                    marker = "content-length:"
                    length = None
                    for line in headers.splitlines():
                        if line.lower().startswith(marker):
                            length = int(line.split(":", 1)[1].strip())
                            break
                    if length is None:
                        buffer = buffer[separator + 4 :]
                        continue
                    start = separator + 4
                    if len(buffer) < start + length:
                        break
                    body = buffer[start : start + length]
                    buffer = buffer[start + length :]
                    if body.strip().lower() != b"heartbeat":
                        yield body

    async def snapshot(self, channel: int, timeout_ms: int) -> bytes:
        response = await self.client.get(
            f"{self.config.base_url}/cgi-bin/snapshot.cgi",
            params={"channel": channel},
            timeout=timeout_ms / 1000,
        )
        response.raise_for_status()
        return response.content

    async def system_info(self) -> dict[str, str]:
        response = await self.client.get(
            f"{self.config.base_url}/cgi-bin/magicBox.cgi", params={"action": "getSystemInfo"}
        )
        response.raise_for_status()
        result: dict[str, str] = {}
        for line in response.text.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                result[key.strip()] = value.strip()
        return result

    async def channel_titles(self) -> dict[str, str]:
        response = await self.client.get(
            f"{self.config.base_url}/cgi-bin/configManager.cgi",
            params={"action": "getConfig", "name": "ChannelTitle"},
        )
        response.raise_for_status()
        result: dict[str, str] = {}
        for line in response.text.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                result[key.strip()] = value.strip()
        return result
