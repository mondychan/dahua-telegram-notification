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


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def payload_value(payload: dict[str, str], *keys: str) -> str | None:
    for key in keys:
        if key in payload:
            return payload[key]
    return None
