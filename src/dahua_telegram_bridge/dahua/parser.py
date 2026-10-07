from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone

from ..models import Event, payload_value


def parse_event(payload: str | bytes) -> Event | None:
    text = payload.decode("utf-8", "replace") if isinstance(payload, bytes) else payload
    fields: dict[str, str] = {}
    for line in text.replace(";", "\n").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            fields[key.strip()] = value.strip()
    nested: dict[str, object] = {}
    data_start = text.find("data={")
    if data_start >= 0:
        try:
            nested = json.loads(text[data_start + 5:])
        except json.JSONDecodeError:
            nested = {}
    event_type = payload_value(fields, "Code", "code", "event", "Event")
    action = payload_value(fields, "action", "Action", "Status") or "Start"
    if not event_type:
        match = re.search(r"(?:Code|event)\s*[:=]\s*([A-Za-z0-9_]+)", text)
        event_type = match.group(1) if match else None
    if not event_type:
        return None
    channel_raw = payload_value(fields, "channel", "Channel", "chn") or str(nested.get("Channel", "")) or payload_value(fields, "index")
    try:
        channel = int(channel_raw) if channel_raw is not None else None
    except ValueError:
        channel = None
    timestamp_raw = payload_value(fields, "Time", "time", "timestamp", "Timestamp")
    timestamp = datetime.now(timezone.utc)
    if timestamp_raw:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
            try:
                timestamp = datetime.strptime(timestamp_raw, fmt).replace(tzinfo=timezone.utc)
                break
            except ValueError:
                continue
    object_type = payload_value(fields, "ObjectType", "object", "Object", "type") or (str(nested["ObjectType"]) if "ObjectType" in nested else None)
    rule = payload_value(fields, "Name", "Rule", "rule", "EventName")
    fingerprint = hashlib.sha1(text.encode(), usedforsecurity=False).hexdigest()[:16]
    return Event(fingerprint, timestamp, event_type, action, channel, object_type, rule, fields)


def iter_event_chunks(chunk: bytes) -> list[bytes]:
    return [part for part in re.split(rb"\r?\n\r?\n", chunk) if part.strip()]
