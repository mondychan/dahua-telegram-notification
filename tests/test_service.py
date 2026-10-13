import asyncio
from pathlib import Path
import tempfile
import pytest

from dahua_telegram_bridge.config import AppConfig, DahuaConfig, TelegramConfig
from dahua_telegram_bridge.dahua.parser import parse_event
from dahua_telegram_bridge.models import Timing
from dahua_telegram_bridge.service import BridgeService
from dahua_telegram_bridge.web import Store


class FakeDahua:
    def __init__(self, fail_snapshot=False):
        self.calls = 0
        self.fail_snapshot = fail_snapshot

    async def snapshot(self, channel, timeout_ms):
        self.calls += 1
        if self.fail_snapshot:
            raise RuntimeError("NVR snapshot timeout")
        return b"jpg"


class FakeTelegram:
    def __init__(self):
        self.calls = []

    async def send(self, caption, photo=None):
        self.calls.append((caption, photo))


@pytest.fixture
def tmp_store():
    tmp_path = Path(tempfile.mkdtemp()) / "test_bridge.sqlite3"
    store = Store(str(tmp_path))
    yield store
    store.close()


@pytest.mark.asyncio
async def test_start_snapshot_and_dedup():
    cfg = AppConfig(DahuaConfig("n"), TelegramConfig("token", "chat"), {"CrossLineDetection"})
    d, t = FakeDahua(), FakeTelegram()
    service = BridgeService(cfg, d, t)
    event = parse_event("Code=CrossLineDetection\naction=Start\nindex=1")
    assert event
    await service.handle(event)
    await service.handle(event)
    assert len(t.calls) == 1 and d.calls == 1


@pytest.mark.asyncio
async def test_stop_is_ignored():
    cfg = AppConfig(DahuaConfig("n"), TelegramConfig("token", "chat"), {"Human"})
    d, t = FakeDahua(), FakeTelegram()
    service = BridgeService(cfg, d, t)
    event = parse_event("Code=Human\naction=Stop")
    assert event
    await service.handle(event)
    assert not t.calls


def test_timing_durations():
    timing = Timing(1.0, 1.074, 1.100, 1.101, 1.218)
    assert timing.durations_ms() == {
        "event_to_snapshot": 100,
        "snapshot_to_telegram": 118,
        "total": 218,
    }


@pytest.mark.asyncio
async def test_dedup_distinguishes_objects_and_ttl(monkeypatch):
    cfg = AppConfig(
        DahuaConfig("n"), TelegramConfig("token", "chat"), {"Human"}, dedup_ttl_seconds=2
    )
    d, t = FakeDahua(), FakeTelegram()
    service = BridgeService(cfg, d, t)
    first = parse_event("Code=Human\naction=Start\nindex=1\nObjectType=Human")
    second = parse_event("Code=Human\naction=Start\nindex=1\nObjectType=Vehicle")
    assert first and second
    second.timestamp = first.timestamp
    await service.handle(first)
    await service.handle(first)
    await service.handle(second)
    assert len(t.calls) == 2
    service._seen.clear()
    await service.handle(first)
    assert len(t.calls) == 3


@pytest.mark.asyncio
async def test_channel_monitoring_toggle_off_and_on(tmp_store):
    cfg = AppConfig(DahuaConfig("n"), TelegramConfig("token", "chat"), {"CrossLineDetection"})
    d, t = FakeDahua(), FakeTelegram()
    service = BridgeService(cfg, d, t)
    service.store = tmp_store

    # Register and disable Channel 1 monitoring
    tmp_store.ensure_channel(channel_number=1, raw_index=0, camera_name="Gate")
    tmp_store.update_channel(1, {"monitoring_enabled": False})

    event_ch1 = parse_event(
        'Code=CrossLineDetection;action=Start;index=0;data={"Name": "Gate", "Object": {"ObjectType": "Human"}}'
    )
    assert event_ch1 is not None
    await service.handle(event_ch1)

    # Channel 1 is OFF: No snapshot and No telegram
    assert len(t.calls) == 0
    assert d.calls == 0

    saved_event = tmp_store.event(event_ch1.id)
    assert saved_event is not None
    assert saved_event["processing_status"] == "filtered"
    assert saved_event["filter_reason"] == "channel_monitoring_disabled"

    # Other channel (CH2, index 1) continues normally
    event_ch2 = parse_event(
        'Code=CrossLineDetection;action=Start;index=1;data={"Name": "Yard", "Object": {"ObjectType": "Vehicle"}}'
    )
    assert event_ch2 is not None
    await service.handle(event_ch2)
    assert len(t.calls) == 1
    assert d.calls == 1

    # Turn Channel 1 monitoring back ON at runtime
    tmp_store.update_channel(1, {"monitoring_enabled": True})
    service._seen.clear()

    event_ch1_new = parse_event(
        'Code=CrossLineDetection;action=Start;index=0;data={"Name": "Gate", "EventID": 999, "Object": {"ObjectType": "Human"}}'
    )
    assert event_ch1_new is not None
    await service.handle(event_ch1_new)
    assert len(t.calls) == 2
    assert d.calls == 2


@pytest.mark.asyncio
async def test_event_rule_monitoring_and_telegram_toggle(tmp_store):
    cfg = AppConfig(DahuaConfig("n"), TelegramConfig("token", "chat"), set())
    d, t = FakeDahua(), FakeTelegram()
    service = BridgeService(cfg, d, t)
    service.store = tmp_store

    # Create rule: Monitoring ON, Telegram OFF
    rule = tmp_store.create_rule(
        {
            "channel": 1,
            "event_type": "CrossLineDetection",
            "object_type": "Vehicle",
            "monitoring_enabled": True,
            "telegram_enabled": False,
        }
    )

    event = parse_event(
        'Code=CrossLineDetection;action=Start;index=0;data={"Object": {"ObjectType": "Vehicle"}}'
    )
    assert event is not None
    await service.handle(event)

    # Event was recorded, but Telegram was not sent
    assert len(t.calls) == 0
    saved = tmp_store.event(event.id)
    assert saved is not None
    assert saved["notification_status"] == "Telegram disabled"

    # Turn Telegram ON in rule
    tmp_store.update_rule(rule["id"], {"telegram_enabled": True})
    service._seen.clear()

    event_new = parse_event(
        'Code=CrossLineDetection;action=Start;index=0;data={"EventID": 888, "Object": {"ObjectType": "Vehicle"}}'
    )
    assert event_new is not None
    await service.handle(event_new)
    assert len(t.calls) == 1


@pytest.mark.asyncio
async def test_global_telegram_switch_off_and_on(tmp_store):
    cfg = AppConfig(DahuaConfig("n"), TelegramConfig("token", "chat"), {"CrossLineDetection"})
    d, t = FakeDahua(), FakeTelegram()
    service = BridgeService(cfg, d, t)
    service.store = tmp_store

    # Disable global Telegram switch
    tmp_store.set_global_setting("telegram_notifications_enabled", False)

    event = parse_event("Code=CrossLineDetection;action=Start;index=0")
    assert event is not None
    await service.handle(event)

    # Event is processed in store, but telegram send is suppressed
    assert len(t.calls) == 0
    saved = tmp_store.event(event.id)
    assert saved is not None
    assert saved["filter_reason"] == "Filtered: globally disabled"

    # Turn global Telegram switch back ON
    tmp_store.set_global_setting("telegram_notifications_enabled", True)
    service._seen.clear()

    event2 = parse_event('Code=CrossLineDetection;action=Start;index=0;data={"EventID": 777}')
    assert event2 is not None
    await service.handle(event2)
    assert len(t.calls) == 1


@pytest.mark.asyncio
async def test_env_hard_disabled_telegram_blocks_all_sending(tmp_store):
    # ENV sets TelegramConfig(enabled=False)
    cfg = AppConfig(DahuaConfig("n"), TelegramConfig("token", "chat", enabled=False), {"Human"})
    d, t = FakeDahua(), FakeTelegram()
    service = BridgeService(cfg, d, t)
    service.store = tmp_store

    # Global setting in DB is ON
    tmp_store.set_global_setting("telegram_notifications_enabled", True)

    event = parse_event("Code=Human;action=Start;index=0;ObjectType=Human")
    assert event is not None
    await service.handle(event)

    # Zero telegram requests
    assert len(t.calls) == 0
    saved = tmp_store.event(event.id)
    assert saved is not None
    assert "Telegram blocked by environment configuration" in saved["filter_reason"]


@pytest.mark.asyncio
async def test_snapshot_failure_falls_back_to_text_telegram(tmp_store):
    cfg = AppConfig(DahuaConfig("n"), TelegramConfig("token", "chat"), {"CrossLineDetection"})
    d, t = FakeDahua(fail_snapshot=True), FakeTelegram()
    service = BridgeService(cfg, d, t)
    service.store = tmp_store

    event = parse_event("Code=CrossLineDetection;action=Start;index=0")
    assert event is not None
    # Listener does NOT crash on snapshot error
    await service.handle(event)

    # Text fallback notification was sent (photo is None)
    assert len(t.calls) == 1
    caption, photo = t.calls[0]
    assert photo is None
    assert "Dahua event" in caption
    saved = tmp_store.event(event.id)
    assert saved is not None
    assert saved["snapshot_status"] == "Snapshot failed"
    assert saved["notification_status"] == "Telegram sent"


@pytest.mark.asyncio
async def test_end_to_end_multipart_pipeline(tmp_store):
    fixture_path = Path("tests/fixtures/dahua/crossline_vehicle_start.txt")
    raw_payload = fixture_path.read_text(encoding="utf-8")

    cfg = AppConfig(
        dahua=DahuaConfig("192.168.1.100"),
        telegram=TelegramConfig("token", "chat"),
        enabled_events={"CrossLineDetection"},
        event_channel_offset=1,
    )
    dahua = FakeDahua()
    telegram = FakeTelegram()
    service = BridgeService(cfg, dahua, telegram)
    service.store = tmp_store

    # 1. Parse
    event = parse_event(raw_payload)
    assert event is not None
    assert event.event_type == "CrossLineDetection"
    assert event.object_type == "Vehicle"
    assert event.raw_index == 0

    # 2. Handle through complete pipeline
    await service.handle(event)

    # 3. Channel resolution: index 0 mapped to CH1
    assert event.channel == 1

    # 4. Snapshot called for CH1
    assert dahua.calls == 1

    # 5. Telegram sendPhoto called with caption & photo
    assert len(telegram.calls) == 1
    caption, photo = telegram.calls[0]
    assert photo == b"jpg"
    assert "Channel: CH1" in caption
    assert "Object: Vehicle" in caption

    # 6. Saved in catalog
    saved = tmp_store.event(event.id)
    assert saved is not None
    assert saved["notification_status"] == "Telegram sent"
    assert saved["raw_payload"]["data"] != "{"


@pytest.mark.asyncio
async def test_live_subscriber_receives_normalized_event():
    cfg = AppConfig(DahuaConfig("n"), TelegramConfig("token", "chat"), {"Human"})
    service = BridgeService(cfg, FakeDahua(), FakeTelegram())

    queue = asyncio.Queue()
    service.live_subscribers.add(queue)
    event = parse_event("Code=Human;action=Start;index=0;ObjectType=Human")
    assert event
    await service.handle(event)
    payload = await queue.get()
    assert payload["event_type"] == "Human" and payload["action"] == "Start"


@pytest.mark.asyncio
async def test_run_reconnects_after_stream_failure(monkeypatch):
    cfg = AppConfig(DahuaConfig("n"), TelegramConfig("token", "chat"), {"Human"})

    class ReconnectingDahua(FakeDahua):
        def __init__(self):
            super().__init__()
            self.calls = 0

        async def events(self):
            self.calls += 1
            if self.calls == 1:
                raise ConnectionError("reset")
            event = b"Code=Human;action=Start;index=0;ObjectType=Human"
            yield event
            raise asyncio.CancelledError

    dahua = ReconnectingDahua()
    service = BridgeService(cfg, dahua, FakeTelegram())

    async def no_sleep(_delay):
        return None

    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    with pytest.raises(asyncio.CancelledError):
        await service.run()
    assert dahua.calls >= 2
