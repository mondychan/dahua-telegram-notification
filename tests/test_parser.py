from dahua_telegram_bridge.dahua.parser import parse_event


def test_parse_crossline():
    event = parse_event(
        "Code=CrossLineDetection\naction=Start\nindex=1\nObjectType=Human\nName=Gate"
    )
    assert event and event.event_type == "CrossLineDetection" and event.channel == 1
    assert event.object_type == "Human" and event.is_start


def test_malformed_is_ignored():
    assert parse_event("garbage without fields") is None


def test_parse_nested_dahua_data():
    event = parse_event('Code=RecordDelete;action=Pulse;index=0;data={"Channel": 6, "Type": 0}')
    assert event and event.channel == 6


def test_parse_real_video_motion_payload():
    payload = """Code=VideoMotion;action=Start;index=2;data={
   "LocaleTime" : "2026-10-07 13:26:48",
   "Name" : "zahrada",
   "WithSnap" : true
}
"""
    event = parse_event(payload)
    assert event and event.channel == 2
    assert event.rule_name == "zahrada"
    assert event.timestamp.strftime("%Y-%m-%d %H:%M:%S") == "2026-10-07 13:26:48"


def test_parse_real_smart_motion_vehicle_payload():
    payload = """Code=SmartMotionVehicle;action=Start;index=4;data={
  "LocaleTime" : "2026-10-07 14:36:59",
  "Name" : "IPC",
  "RealUTC" : 1791376618,
  "UTC" : 1791376619
}
"""
    event = parse_event(payload)
    assert event and event.event_type == "SmartMotionVehicle"
    assert event.object_type == "Vehicle"
    assert event.channel == 4 and event.rule_name == "IPC"


def test_parse_real_smart_motion_human_payload():
    payload = open("tests/fixtures/dahua/smart_motion_human.txt", encoding="utf-8").read()
    event = parse_event(payload)
    assert event and event.event_type == "SmartMotionHuman"
    assert event.object_type == "Human"
    assert event.channel == 4 and event.rule_name == "IPC"
