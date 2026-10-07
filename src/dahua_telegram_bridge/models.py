from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(slots=True)
class Event:
    id: str
    timestamp: datetime
    event_type: str
    action: str
    channel: int | None = None
    object_type: str | None = None
    rule_name: str | None = None
    raw_payload: dict[str, str] = field(default_factory=dict)

    @property
    def is_start(self) -> bool:
        return self.action.lower() in {"start", "active", "1"}

    @property
    def display_timestamp(self) -> str:
        return self.timestamp.astimezone().strftime("%Y-%m-%d %H:%M:%S")


@dataclass(slots=True)
class HealthState:
    nvr_connected: bool = False
    last_event: datetime | None = None
    last_telegram: datetime | None = None
    reconnect_count: int = 0
    processed_events: int = 0
    failed_events: int = 0
    snapshots_success: int = 0
    snapshots_failed: int = 0
    telegram_sent: int = 0
    telegram_failed: int = 0
    events_received: int = 0
    events_filtered: int = 0
    events_deduplicated: int = 0
    last_snapshot: datetime | None = None


@dataclass(slots=True)
class Timing:
    event_received: float
    snapshot_started: float | None = None
    snapshot_received: float | None = None
    telegram_started: float | None = None
    telegram_sent: float | None = None

    def durations_ms(self) -> dict[str, int | None]:
        def delta(end: float | None, start: float | None) -> int | None:
            return round((end - start) * 1000) if end is not None and start is not None else None

        return {
            "event_to_snapshot": delta(self.snapshot_received, self.event_received),
            "snapshot_to_telegram": delta(self.telegram_sent, self.snapshot_received),
            "total": delta(self.telegram_sent, self.event_received),
        }


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def payload_value(payload: dict[str, str], *keys: str) -> str | None:
    for key in keys:
        if key in payload:
            return payload[key]
    return None
