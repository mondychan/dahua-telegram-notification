from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from ..models import Event, payload_value

log = logging.getLogger(__name__)


def parse_event(payload: str | bytes) -> Event | None:
    text = payload.decode("utf-8", "replace") if isinstance(payload, bytes) else payload
    text = text.strip()
    if not text or text.lower() == "heartbeat":
        return None

    # Strip any leading HTTP headers / boundaries if passed directly to parse_event
    match_code_start = re.search(r"(?:^|[\r\n])(Code\s*=)", text, flags=re.IGNORECASE)
    if match_code_start and match_code_start.start() > 0:
        text = text[match_code_start.start() :].lstrip("\r\n")

    fields: dict[str, Any] = {}
    nested: dict[str, Any] = {}

    data_match = re.search(r"data\s*=\s*(\{)", text, flags=re.DOTALL)
    if data_match:
        header_text = text[: data_match.start()]
        json_text = text[data_match.start(1) :]
        try:
            nested_decoded, end_pos = json.JSONDecoder().raw_decode(json_text)
            if isinstance(nested_decoded, dict):
                nested = nested_decoded
            trailer = json_text[end_pos:]
        except json.JSONDecodeError as exc:
            log.warning("failed to decode nested JSON in event: %s", exc)
            nested = {}
            trailer = ""
        combined_headers = f"{header_text};{trailer}"
    elif text.startswith("{"):
        try:
            nested_decoded = json.loads(text)
            if isinstance(nested_decoded, dict):
                nested = nested_decoded
        except json.JSONDecodeError:
            nested = {}
        combined_headers = ""
    else:
        combined_headers = text

    for part in re.split(r"[;\r\n]+", combined_headers):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            fields[k.strip()] = v.strip()

    if nested:
        fields["data"] = nested

    event_type = payload_value(fields, "Code", "code", "event", "Event") or (
        str(nested["Code"]) if "Code" in nested else None
    )
    if not event_type:
        match = re.search(r"(?:Code|event)\s*[:=]\s*([A-Za-z0-9_]+)", text, flags=re.IGNORECASE)
        event_type = match.group(1) if match else None

    if not event_type:
        return None

    action = (
        payload_value(fields, "action", "Action", "Status")
        or (str(nested["Action"]) if "Action" in nested else None)
        or "Start"
    )

    raw_index_str = payload_value(fields, "index", "Index") or (
        str(nested["Index"]) if "Index" in nested else None
    )
    raw_index: int | None = None
    if raw_index_str is not None:
        try:
            raw_index = int(raw_index_str)
        except ValueError:
            raw_index = None

    channel_str = payload_value(fields, "channel", "Channel", "chn") or (
        str(nested["Channel"]) if "Channel" in nested else None
    )
    channel: int | None = None
    if channel_str is not None:
        try:
            channel = int(channel_str)
        except ValueError:
            channel = (raw_index + 1) if raw_index is not None else None
    else:
        channel = (raw_index + 1) if raw_index is not None else None

    timestamp_raw = (
        payload_value(fields, "Time", "time", "timestamp", "Timestamp")
        or (str(nested["LocaleTime"]) if "LocaleTime" in nested else None)
        or (str(nested["UTC"]) if "UTC" in nested else None)
    )
    timestamp = datetime.now(timezone.utc)
    if timestamp_raw:
        parsed_ts = None
        if timestamp_raw.isdigit():
            try:
                parsed_ts = datetime.fromtimestamp(int(timestamp_raw), tz=timezone.utc)
            except (ValueError, OverflowError):
                pass
        if parsed_ts is None:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
                try:
                    dt = datetime.strptime(timestamp_raw, fmt)
                    parsed_ts = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
                    break
                except ValueError:
                    continue
        if parsed_ts is not None:
            timestamp = parsed_ts

    rule_name = (
        payload_value(fields, "Name", "Rule", "rule", "EventName")
        or (str(nested["Name"]) if "Name" in nested else None)
        or (str(nested["Rule"]) if "Rule" in nested else None)
    )

    direction = payload_value(fields, "Direction") or (
        str(nested["Direction"]) if "Direction" in nested else None
    )

    event_id_raw = payload_value(fields, "EventID") or (
        str(nested["EventID"]) if "EventID" in nested else None
    )
    event_id: int | None = None
    if event_id_raw is not None:
        try:
            event_id = int(event_id_raw)
        except ValueError:
            event_id = None

    group_id_raw = payload_value(fields, "GroupID") or (
        str(nested["GroupID"]) if "GroupID" in nested else None
    )
    group_id: int | None = None
    if group_id_raw is not None:
        try:
            group_id = int(group_id_raw)
        except ValueError:
            group_id = None

    with_snap_raw = fields.get("WithSnap") if "WithSnap" in fields else nested.get("WithSnap")
    with_snap: bool | None = None
    if isinstance(with_snap_raw, bool):
        with_snap = with_snap_raw
    elif isinstance(with_snap_raw, str):
        with_snap = with_snap_raw.lower() in ("true", "1")

    object_type: str | None = None
    object_id: int | str | None = None

    nested_obj = nested.get("Object")
    if isinstance(nested_obj, dict):
        if "ObjectType" in nested_obj and nested_obj["ObjectType"] is not None:
            object_type = str(nested_obj["ObjectType"])
        if "ObjectID" in nested_obj and nested_obj["ObjectID"] is not None:
            object_id = nested_obj["ObjectID"]

    nested_obj_list = nested.get("object") or nested.get("Objects")
    if isinstance(nested_obj_list, list) and nested_obj_list:
        first = nested_obj_list[0]
        if isinstance(first, dict):
            if object_type is None and "ObjectType" in first:
                object_type = str(first["ObjectType"])
            if object_id is None:
                # Firmware may use HumamID or HumanID or VehicleID or ObjectID
                object_id = (
                    first.get("HumamID")
                    or first.get("HumanID")
                    or first.get("VehicleID")
                    or first.get("ObjectID")
                )

    if object_type is None:
        object_type = payload_value(fields, "ObjectType", "object", "Object", "type") or (
            str(nested["ObjectType"]) if "ObjectType" in nested else None
        )

    code_lower = event_type.lower()
    if code_lower == "videomotion":
        # VideoMotion represents general motion detection and must not be
        # classified as Human or Vehicle.
        object_type = None
    elif object_type is None:
        if "smartmotionhuman" in code_lower or "human" in code_lower or "person" in code_lower:
            object_type = "Human"
        elif "smartmotionvehicle" in code_lower or "vehicle" in code_lower or "car" in code_lower:
            object_type = "Vehicle"

    if object_type is not None:
        ot_lower = object_type.lower()
        if ot_lower in ("human", "person"):
            object_type = "Human"
        elif ot_lower in ("vehicle", "car"):
            object_type = "Vehicle"

    if object_id is None:
        object_id = payload_value(fields, "ObjectID", "object_id") or (
            nested.get("ObjectID") if isinstance(nested, dict) else None
        )

    fingerprint_source = (
        f"{event_type}:{action}:{channel}:{raw_index}:{event_id}:{rule_name}:{object_type}:"
        f"{timestamp.isoformat()}"
    )
    fingerprint = hashlib.sha1(fingerprint_source.encode(), usedforsecurity=False).hexdigest()[:16]

    camera_name = rule_name if event_type == "VideoMotion" else None

    return Event(
        id=fingerprint,
        timestamp=timestamp,
        event_type=event_type,
        action=action,
        channel=channel,
        object_type=object_type,
        rule_name=rule_name,
        raw_payload=fields,
        raw_index=raw_index,
        camera_name=camera_name,
        object_id=object_id,
        direction=direction,
        event_id=event_id,
        group_id=group_id,
        with_snap=with_snap,
        data=nested,
    )


def iter_event_chunks(chunk: bytes) -> list[bytes]:
    if b"--" in chunk:
        parts = re.split(rb"--[A-Za-z0-9_.-]+", chunk)
        return [part.strip() for part in parts if part.strip()]
    if chunk.count(b"Code=") > 1:
        indices = [m.start() for m in re.finditer(rb"Code=", chunk)]
        results: list[bytes] = []
        for i, idx in enumerate(indices):
            end = indices[i + 1] if i + 1 < len(indices) else len(chunk)
            part = chunk[idx:end].strip()
            if part:
                results.append(part)
        return results
    return [part for part in re.split(rb"\r?\n\r?\n", chunk) if part.strip()]
