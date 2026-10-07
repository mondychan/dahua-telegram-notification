from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from .models import Event, HealthState, Timing, utcnow

log = logging.getLogger(__name__)


class BridgeService:
    def __init__(self, config: Any, dahua: Any, telegram: Any) -> None:
        self.config, self.dahua, self.telegram = config, dahua, telegram
        self.health = HealthState()
        self._seen: dict[str, float] = {}
        self.store: Any = None
        self.live_subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self.snapshot_cache: dict[str, bytes] = {}
        self.snapshot_cache_limit = 10

    def _allowed(self, event: Event) -> bool:
        if self.store is not None:
            rule = self.store.matching_rule(
                event.channel + self.config.event_channel_offset
                if event.channel is not None
                else None,
                event.event_type,
                event.object_type,
            )
            if rule is not None:
                return bool(rule["enabled"] and (self.config.send_stop or event.is_start))
        if not self.config.send_stop and not event.is_start:
            return False
        return bool(
            not self.config.enabled_events
            or event.event_type in self.config.enabled_events
            or (event.object_type and event.object_type in self.config.enabled_events)
        )

    def _duplicate(self, event: Event) -> bool:
        now = time.monotonic()
        self._seen = {
            k: v for k, v in self._seen.items() if now - v < self.config.dedup_ttl_seconds
        }
        key = f"{event.event_type}|{event.channel}|{event.rule_name}|{event.object_type}|{event.timestamp.timestamp():.0f}"
        if key in self._seen:
            return True
        self._seen[key] = now
        return False

    def caption(self, event: Event) -> str:
        name = self.config.event_names.get(event.event_type, event.event_type)
        obj = event.object_type or ""
        lines = [
            "Dahua event",
            f"Camera: {self.config.camera_name}",
            f"Event: {name}",
            f"Time: {event.display_timestamp}",
        ]
        if event.channel is not None:
            lines.insert(2, f"Channel: {event.channel + self.config.event_channel_offset}")
        if obj:
            lines.insert(3, f"Object: {obj}")
        return "\n".join(lines)

    async def handle(self, event: Event) -> None:
        received = time.monotonic()
        self.health.events_received += 1
        allowed = self._allowed(event)
        if self.store is not None:
            reason = (
                "allowed"
                if allowed
                else (
                    "stop event disabled"
                    if not event.is_start and not self.config.send_stop
                    else "no matching event rule"
                )
            )
            self.store.add_event(event, "eligible" if allowed else "filtered", reason)
        if not allowed:
            self.health.events_filtered += 1
            return
        if self.config.dedup_enabled and self._duplicate(event):
            self.health.events_deduplicated += 1
            return
        timing = Timing(received)
        payload = {
            "id": event.id,
            "timestamp": event.timestamp.isoformat(),
            "event_type": event.event_type,
            "action": event.action,
            "channel": event.channel,
            "object_type": event.object_type,
            "rule_name": event.rule_name,
        }
        for queue in list(self.live_subscribers):
            if not queue.full():
                queue.put_nowait(payload)
        self.health.last_event = utcnow()
        self.health.processed_events += 1
        photo = None
        if self.config.snapshot_enabled:
            try:
                timing.snapshot_started = time.monotonic()
                snapshot_channel = (
                    event.channel + self.config.event_channel_offset
                    if event.channel is not None
                    else self.config.dahua.channel
                )
                photo = await self.dahua.snapshot(snapshot_channel, self.config.snapshot_timeout_ms)
                self.snapshot_cache[event.id] = photo
                while len(self.snapshot_cache) > self.snapshot_cache_limit:
                    self.snapshot_cache.pop(next(iter(self.snapshot_cache)))
                timing.snapshot_received = time.monotonic()
                self.health.snapshots_success += 1
                self.health.last_snapshot = utcnow()
            except Exception as exc:
                self.health.snapshots_failed += 1
                log.warning("snapshot failed: %s", exc)
        try:
            timing.telegram_started = time.monotonic()
            await self.telegram.send(self.caption(event), photo)
            timing.telegram_sent = time.monotonic()
            self.health.last_telegram = utcnow()
            self.health.telegram_sent += 1
            durations = timing.durations_ms()
            log.info(
                "event=%s channel=%s object=%s event_to_snapshot=%sms snapshot_to_telegram=%sms total=%sms",
                event.event_type,
                event.channel,
                event.object_type,
                durations["event_to_snapshot"],
                durations["snapshot_to_telegram"],
                durations["total"],
            )
        except Exception:
            self.health.telegram_failed += 1
            self.health.failed_events += 1
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
