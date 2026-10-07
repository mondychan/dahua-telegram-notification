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
