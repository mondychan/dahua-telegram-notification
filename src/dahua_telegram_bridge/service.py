from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from .models import Event, HealthState, utcnow

log = logging.getLogger(__name__)


class BridgeService:
    def __init__(self, config: Any, dahua: Any, telegram: Any) -> None:
        self.config, self.dahua, self.telegram = config, dahua, telegram
        self.health = HealthState()
        self._seen: dict[str, float] = {}

    def _allowed(self, event: Event) -> bool:
        if not self.config.send_stop and not event.is_start:
            return False
        return bool(not self.config.enabled_events or event.event_type in self.config.enabled_events or (event.object_type and event.object_type in self.config.enabled_events))

    def _duplicate(self, event: Event) -> bool:
        now = time.monotonic()
        self._seen = {k: v for k, v in self._seen.items() if now - v < self.config.dedup_ttl_seconds}
        key = f"{event.event_type}|{event.channel}|{event.rule_name}|{event.object_type}|{event.timestamp.timestamp():.0f}"
        if key in self._seen:
            return True
        self._seen[key] = now
        return False

    def caption(self, event: Event) -> str:
        name = self.config.event_names.get(event.event_type, event.event_type)
        obj = event.object_type or ""
        lines = ["Dahua event", f"Camera: {self.config.camera_name}", f"Event: {name}", f"Time: {event.display_timestamp}"]
        if event.channel is not None:
            lines.insert(2, f"Channel: {event.channel}")
        if obj:
            lines.insert(3, f"Object: {obj}")
        return "\n".join(lines)

    async def handle(self, event: Event) -> None:
        if not self._allowed(event) or (self.config.dedup_enabled and self._duplicate(event)):
            return
        self.health.last_event = utcnow()
        photo = None
        if self.config.snapshot_enabled:
            try:
                photo = await self.dahua.snapshot(event.channel or self.config.dahua.channel, self.config.snapshot_timeout_ms)
            except Exception as exc:
                log.warning("snapshot failed: %s", exc)
        try:
            await self.telegram.send(self.caption(event), photo)
            self.health.last_telegram = utcnow()
        except Exception:
            log.exception("telegram request failed")

    async def run(self) -> None:
        delay = 1.0
        while True:
            try:
                self.health.nvr_connected = True
                async for raw in self.dahua.events():
                    from .dahua.parser import parse_event
                    event = parse_event(raw)
                    if event:
                        await self.handle(event)
                raise ConnectionError("event stream ended")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.health.nvr_connected = False
                self.health.reconnect_count += 1
                log.warning("NVR stream disconnected: %s; retrying in %.1fs", exc, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)
            else:
                delay = 1.0
