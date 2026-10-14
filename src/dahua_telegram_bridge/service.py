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

    def is_telegram_globally_enabled(self) -> bool:
        if not getattr(self.config.telegram, "enabled", True):
            return False
        if self.store is not None:
            return bool(self.store.get_global_setting("telegram_notifications_enabled", True))
        return True

    def _duplicate(self, event: Event) -> bool:
        now = time.monotonic()
        self._seen = {
            k: v for k, v in self._seen.items() if now - v < self.config.dedup_ttl_seconds
        }
        key = (
            f"{event.event_type}|{event.channel}|{event.rule_name}|"
            f"{event.object_type}|{event.object_id}|{event.timestamp.timestamp():.0f}"
        )
        if key in self._seen:
            return True
        self._seen[key] = now
        return False

    def caption(self, event: Event) -> str:
        name = self.config.event_names.get(event.event_type, event.event_type)
        obj = event.object_type or ""
        cam_name = event.camera_name or self.config.camera_name
        lines = [
            "Dahua event",
            f"Camera: {cam_name}",
            f"Event: {name}",
            f"Time: {event.display_timestamp}",
        ]
        if event.channel is not None:
            lines.insert(2, f"Channel: CH{event.channel}")
        if obj:
            lines.insert(3, f"Object: {obj}")
        if event.rule_name and event.rule_name != cam_name:
            lines.append(f"Rule: {event.rule_name}")
        return "\n".join(lines)

    async def handle(self, event: Event) -> None:
        received = time.monotonic()
        self.health.events_received += 1

        # 1. Channel Resolution
        raw_index = event.raw_index
        offset = getattr(self.config, "event_channel_offset", 1)
        monitoring_enabled = True
        snapshot_channel: int

        if self.store is not None:
            ch: dict[str, Any] | None = None
            if raw_index is not None:
                ch = self.store.get_channel_by_raw_index(raw_index)
            if ch is None and event.channel is not None:
                ch = self.store.get_channel(event.channel)

            if ch is not None:
                event.channel = ch["channel_number"]
                event.camera_name = (
                    ch["camera_name"] or event.camera_name or f"Camera {ch['channel_number']}"
                )
                event.channel_mapping_source = ch["channel_mapping_source"]
                monitoring_enabled = bool(ch["monitoring_enabled"])
                snap_ch = ch.get("snapshot_channel")
                snapshot_channel = snap_ch if snap_ch is not None else event.channel
            else:
                resolved_ch = (
                    (raw_index + offset) if raw_index is not None else (event.channel or 1)
                )
                event.channel = resolved_ch
                cam_name = event.camera_name or event.rule_name or f"Camera {resolved_ch}"
                event.camera_name = cam_name
                event.channel_mapping_source = "auto"
                monitoring_enabled = True
                snapshot_channel = resolved_ch
                self.store.ensure_channel(
                    channel_number=resolved_ch,
                    raw_index=raw_index,
                    camera_name=cam_name,
                    snapshot_channel=resolved_ch,
                    source="auto",
                )
        else:
            resolved_ch = (raw_index + offset) if raw_index is not None else (event.channel or 1)
            event.channel = resolved_ch
            monitoring_enabled = True
            snapshot_channel = resolved_ch

        # 2. Channel Monitoring Check
        if not monitoring_enabled:
            event.processing_status = "filtered"
            event.filter_reason = "channel_monitoring_disabled"
            self.health.events_filtered += 1
            if self.store is not None:
                self.store.add_event(event)
            return

        # 3. Event Notification Rule Check
        rule: dict[str, Any] | None = None
        if self.store is not None:
            rule = self.store.matching_rule(
                event.channel, event.event_type, event.object_type, event.rule_name
            )

        rule_telegram_enabled = True
        if rule is not None:
            is_monitored = bool(rule.get("monitoring_enabled", rule.get("enabled", 1)))
            if not is_monitored:
                event.processing_status = "filtered"
                event.filter_reason = "Filtered: event rule disabled"
                self.health.events_filtered += 1
                if self.store is not None:
                    self.store.add_event(event)
                return
            allowed_actions = [
                a.strip().lower() for a in str(rule.get("allowed_actions", "Start")).split(",")
            ]
            if event.action.lower() not in allowed_actions and not self.config.send_stop:
                event.processing_status = "filtered"
                event.filter_reason = "Filtered: action Stop"
                self.health.events_filtered += 1
                if self.store is not None:
                    self.store.add_event(event)
                return
            rule_telegram_enabled = bool(rule.get("telegram_enabled", 1))
        else:
            if self.store is not None and self.store.rules():
                # Rules are the single source of truth. A missing rule must be
                # visible as a filtered event rather than a hidden fallback.
                event.processing_status = "filtered"
                event.filter_reason = "Filtered: no matching notification rule"
                self.health.events_filtered += 1
                self.store.add_event(event)
                return
            # Compatibility for library users with an uninitialized store.
            if not self.config.send_stop and not event.is_start:
                event.processing_status = "filtered"
                event.filter_reason = "Filtered: action Stop"
                self.health.events_filtered += 1
                if self.store is not None:
                    self.store.add_event(event)
                return
            if (
                self.config.enabled_events
                and event.event_type not in self.config.enabled_events
                and event.object_type not in self.config.enabled_events
            ):
                event.processing_status = "filtered"
                event.filter_reason = "Filtered: event rule disabled"
                self.health.events_filtered += 1
                if self.store is not None:
                    self.store.add_event(event)
                return

        # 4. Deduplication
        if self.config.dedup_enabled and self._duplicate(event):
            event.processing_status = "deduplicated"
            event.filter_reason = "Deduplicated"
            self.health.events_deduplicated += 1
            if self.store is not None:
                self.store.add_event(event)
            return

        # 5. Broadcast to live subscribers
        timing = Timing(received)
        event.processing_status = "processed"
        self.health.last_event = utcnow()
        self.health.processed_events += 1

        payload = {
            "id": event.id,
            "timestamp": event.timestamp.isoformat(),
            "event_type": event.event_type,
            "action": event.action,
            "channel": event.channel,
            "raw_index": event.raw_index,
            "camera_name": event.camera_name,
            "object_type": event.object_type,
            "rule_name": event.rule_name,
            "decision": event.processing_status,
        }
        for queue in list(self.live_subscribers):
            if not queue.full():
                queue.put_nowait(payload)

        # 6. Global Telegram Gate and Rule Telegram Check
        if not getattr(self.config.telegram, "enabled", True):
            # Hard-disabled by environment
            event.notification_status = "Telegram disabled"
            event.filter_reason = "Telegram blocked by environment configuration"
            if self.store is not None:
                self.store.add_event(event)
            return

        if self.store is not None and not self.store.get_global_setting(
            "telegram_notifications_enabled", True
        ):
            # Globally disabled in application
            event.notification_status = "Telegram disabled"
            event.filter_reason = "Filtered: globally disabled"
            if self.store is not None:
                self.store.add_event(event)
            return

        if not rule_telegram_enabled:
            event.notification_status = "Telegram disabled"
            event.filter_reason = "Telegram disabled"
            if self.store is not None:
                self.store.add_event(event)
            return

        # 7. Snapshot Pipeline
        photo: bytes | None = None
        if self.config.snapshot_enabled:
            try:
                timing.snapshot_started = time.monotonic()
                photo = await self.dahua.snapshot(snapshot_channel, self.config.snapshot_timeout_ms)
                event.snapshot_status = "Snapshot success"
                self.snapshot_cache[event.id] = photo
                while len(self.snapshot_cache) > self.snapshot_cache_limit:
                    self.snapshot_cache.pop(next(iter(self.snapshot_cache)))
                timing.snapshot_received = time.monotonic()
                self.health.snapshots_success += 1
                self.health.last_snapshot = utcnow()
            except Exception as exc:
                event.snapshot_status = "Snapshot failed"
                self.health.snapshots_failed += 1
                log.warning(
                    "snapshot failed for channel %s (%s)",
                    snapshot_channel,
                    type(exc).__name__,
                )

        # 8. Telegram Send
        try:
            timing.telegram_started = time.monotonic()
            await self.telegram.send(self.caption(event), photo)
            timing.telegram_sent = time.monotonic()
            self.health.last_telegram = utcnow()
            self.health.telegram_sent += 1
            event.notification_status = "Telegram sent"
            event.filter_reason = None
            event.latency_metrics = timing.durations_ms()
            log.info(
                "event=%s channel=%s object=%s event_to_snapshot=%sms snapshot_to_telegram=%sms total=%sms",
                event.event_type,
                event.channel,
                event.object_type,
                event.latency_metrics["event_to_snapshot"],
                event.latency_metrics["snapshot_to_telegram"],
                event.latency_metrics["total"],
            )
        except Exception as exc:
            self.health.telegram_failed += 1
            self.health.failed_events += 1
            event.notification_status = "Telegram failed"
            log.exception("telegram request failed: %s", exc)

        if self.store is not None:
            self.store.add_event(event)

    async def run(self) -> None:
        delay = 1.0
        while True:
            try:
                self.health.nvr_connected = True
                async for raw in self.dahua.events():
                    from .dahua.parser import parse_event

                    try:
                        event = parse_event(raw)
                    except Exception as parse_exc:
                        log.warning("malformed event ignored: %s; raw: %r", parse_exc, raw[:100])
                        event = None

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
