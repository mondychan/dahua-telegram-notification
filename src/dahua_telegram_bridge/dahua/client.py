from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator
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
                    sep_rn = buffer.find(b"\r\n\r\n")
                    sep_n = buffer.find(b"\n\n")
                    if sep_rn >= 0 and (sep_n < 0 or sep_rn <= sep_n):
                        separator = sep_rn
                        sep_len = 4
                    elif sep_n >= 0:
                        separator = sep_n
                        sep_len = 2
                    else:
                        break

                    headers = buffer[:separator].decode("latin1", "replace")
                    marker = "content-length:"
                    length = None
                    for line in headers.splitlines():
                        if line.lower().startswith(marker):
                            try:
                                length = int(line.split(":", 1)[1].strip())
                            except ValueError:
                                length = None
                            break

                    if length is not None:
                        start = separator + sep_len
                        if len(buffer) < start + length:
                            break
                        body = buffer[start : start + length]
                        buffer = buffer[start + length :]
                        stripped = body.strip()
                        if stripped and stripped.lower() != b"heartbeat":
                            yield body
                        continue

                    # If no Content-Length header, check for multipart boundary
                    boundary_match = re.search(r"--([A-Za-z0-9_.-]+)", headers)
                    if boundary_match:
                        b_marker = b"--" + boundary_match.group(1).encode("ascii")
                        next_b = buffer.find(b_marker, separator + sep_len)
                        if next_b >= 0:
                            body = buffer[separator + sep_len : next_b].strip()
                            buffer = buffer[next_b:]
                            if body and body.lower() != b"heartbeat":
                                yield body
                            continue
                        else:
                            # Wait for more data to reach next boundary
                            break

                    # If headers themselves contain Code=, yield it as body
                    if b"code=" in headers.lower().encode("latin1"):
                        body = buffer[:separator].strip()
                        buffer = buffer[separator + sep_len :]
                        if body and body.lower() != b"heartbeat":
                            yield body
                        continue

                    buffer = buffer[separator + sep_len :]

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
