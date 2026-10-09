from pathlib import Path

from dahua_telegram_bridge.dahua.parser import iter_event_chunks, parse_event

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "dahua"


def test_regression_raw_payload_data_is_not_truncated():
    payload = (FIXTURES_DIR / "crossline_vehicle_start.txt").read_text(encoding="utf-8")
    event = parse_event(payload)
    assert event is not None
    # Crucial regression test: raw_payload["data"] must NOT be "{"
    assert event.raw_payload["data"] != "{"
    assert isinstance(event.raw_payload["data"], dict)
    assert event.raw_payload["data"]["Direction"] == "RightToLeft"
    assert event.event_type == "CrossLineDetection"
    assert event.action == "Start"
    assert event.object_type == "Vehicle"
    assert event.rule_name == "Rule1"
    assert event.raw_index == 0
    assert event.event_id == 10033
    assert event.group_id == 32
    assert event.with_snap is True
    assert event.object_id == 4185
    assert event.direction == "RightToLeft"
    assert event.data["Object"]["ObjectType"] == event.object_type


def test_parse_crossline_human_start_fixture():
    payload = (FIXTURES_DIR / "crossline_human_start.txt").read_text(encoding="utf-8")
    event = parse_event(payload)
    assert event is not None
    assert event.event_type == "CrossLineDetection"
    assert event.action == "Start"
    assert event.is_start is True
    assert event.object_type == "Human"
    assert event.rule_name == "Rule1"
    assert event.raw_index == 0
    assert event.event_id == 10032
    assert event.group_id == 31
    assert event.with_snap is True
    assert event.object_id == 4184
    assert event.data["Object"]["ObjectType"] == "Human"


def test_parse_crossline_stop_fixture():
    payload = (FIXTURES_DIR / "crossline_stop.txt").read_text(encoding="utf-8")
    event = parse_event(payload)
    assert event is not None
    assert event.event_type == "CrossLineDetection"
    assert event.action == "Stop"
    assert event.is_start is False
    assert event.object_type == "Vehicle"
    assert event.with_snap is False


def test_parse_smart_motion_human_with_humamid_tolerance():
    payload = (FIXTURES_DIR / "smart_motion_human_start.txt").read_text(encoding="utf-8")
    event = parse_event(payload)
    assert event is not None
    assert event.event_type == "SmartMotionHuman"
    assert event.action == "Start"
    assert event.object_type == "Human"
    assert event.object_id == 5598
    assert event.event_id == 3767606
    assert event.with_snap is True
    assert "object" in event.data
    assert event.data["object"][0]["HumamID"] == 5598
    assert event.data["object"][0]["Rect"] == [7352, 3112, 7544, 4024]


def test_parse_smart_motion_human_with_humanid_variant():
    payload = """Code=SmartMotionHuman;action=Start;index=1;data={
  "EventID": 3767607,
  "LocaleTime": "2026-10-08 09:43:38",
  "WithSnap": true,
  "object": [
    {
      "HumanID": 9988,
      "Rect": [1000, 2000, 3000, 4000]
    }
  ]
}
"""
    event = parse_event(payload)
    assert event is not None
    assert event.event_type == "SmartMotionHuman"
    assert event.object_type == "Human"
    assert event.object_id == 9988
    assert event.raw_index == 1


def test_parse_smart_motion_human_stop():
    payload = (FIXTURES_DIR / "smart_motion_human_stop.txt").read_text(encoding="utf-8")
    event = parse_event(payload)
    assert event is not None
    assert event.event_type == "SmartMotionHuman"
    assert event.action == "Stop"
    assert event.is_start is False
    assert event.object_type == "Human"


def test_parse_smart_motion_vehicle_start_and_stop():
    start_payload = (FIXTURES_DIR / "smart_motion_vehicle_start.txt").read_text(encoding="utf-8")
    ev_start = parse_event(start_payload)
    assert ev_start is not None
    assert ev_start.event_type == "SmartMotionVehicle"
    assert ev_start.action == "Start"
    assert ev_start.object_type == "Vehicle"
    assert ev_start.object_id == 768523
    assert ev_start.event_id == 3654275
    assert ev_start.with_snap is True
    assert ev_start.data["object"][0]["VehicleID"] == 768523

    stop_payload = (FIXTURES_DIR / "smart_motion_vehicle_stop.txt").read_text(encoding="utf-8")
    ev_stop = parse_event(stop_payload)
    assert ev_stop is not None
    assert ev_stop.event_type == "SmartMotionVehicle"
    assert ev_stop.action == "Stop"
    assert ev_stop.is_start is False
    assert ev_stop.object_type == "Vehicle"


def test_parse_videomotion_is_not_classified_as_human_or_vehicle():
    start_payload = (FIXTURES_DIR / "video_motion_start.txt").read_text(encoding="utf-8")
    event = parse_event(start_payload)
    assert event is not None
    assert event.event_type == "VideoMotion"
    assert event.action == "Start"
    # VideoMotion must NOT be confused with classified Human or Vehicle
    assert event.object_type is None
    assert event.raw_index == 2
    assert event.channel == 3
    assert event.rule_name == "zahrada"
    assert event.with_snap is True

    stop_payload = (FIXTURES_DIR / "video_motion_stop.txt").read_text(encoding="utf-8")
    ev_stop = parse_event(stop_payload)
    assert ev_stop is not None
    assert ev_stop.event_type == "VideoMotion"
    assert ev_stop.action == "Stop"
    assert ev_stop.object_type is None
    assert ev_stop.with_snap is False


def test_malformed_and_unknown_events():
    # Completely invalid string returns None
    assert parse_event("garbage without fields") is None
    assert parse_event("") is None
    assert parse_event(b"heartbeat") is None

    # Unknown event code still parses safely without raising exceptions
    unknown_payload = 'Code=CustomSensorAlert;action=Start;index=7;data={"Sensor": "Gate"}'
    ev_unk = parse_event(unknown_payload)
    assert ev_unk is not None
    assert ev_unk.event_type == "CustomSensorAlert"
    assert ev_unk.action == "Start"
    assert ev_unk.raw_index == 7


def test_iter_event_chunks_with_multiple_events():
    chunk = (
        b"--myboundary\r\nContent-Length: 50\r\n\r\nCode=CrossLineDetection;action=Start;index=0\r\n"
        b"--myboundary\r\nContent-Length: 45\r\n\r\nCode=SmartMotionHuman;action=Start;index=1\r\n"
    )
    chunks = iter_event_chunks(chunk)
    assert len(chunks) == 2
    assert b"CrossLineDetection" in chunks[0]
    assert b"SmartMotionHuman" in chunks[1]


def test_iter_event_chunks_code_splitter():
    chunk = (
        b'Code=CrossLineDetection;action=Start;index=0;data={"Rule": 1}\n'
        b'Code=SmartMotionVehicle;action=Start;index=2;data={"Rule": 2}\n'
    )
    chunks = iter_event_chunks(chunk)
    assert len(chunks) == 2
    assert b"CrossLineDetection" in chunks[0]
    assert b"SmartMotionVehicle" in chunks[1]
