import pytest
from dahua_telegram_bridge.config import AppConfig, DahuaConfig, TelegramConfig
from dahua_telegram_bridge.dahua.parser import parse_event
from dahua_telegram_bridge.service import BridgeService
from dahua_telegram_bridge.models import Timing


class FakeDahua:
    def __init__(self):
        self.calls = 0

    async def snapshot(self, channel, timeout_ms):
        self.calls += 1
        return b"jpg"


class FakeTelegram:
    def __init__(self):
        self.calls = []

    async def send(self, caption, photo=None):
        self.calls.append((caption, photo))


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
async def test_persistent_rule_overrides_allowlist():
    from dahua_telegram_bridge.web import Store
    import tempfile
    from pathlib import Path

    cfg = AppConfig(DahuaConfig("n"), TelegramConfig("token", "chat"), {"Human"})
    d, t = FakeDahua(), FakeTelegram()
    service = BridgeService(cfg, d, t)
    service.store = Store(str(Path(tempfile.mkdtemp()) / "db.sqlite"))
    service.store.create_rule(
        {"channel": 1, "event_type": "Human", "object_type": "Human", "enabled": False}
    )
    event = parse_event("Code=Human\naction=Start\nindex=0\nObjectType=Human")
    assert event
    await service.handle(event)
    assert not t.calls


@pytest.mark.asyncio
async def test_live_subscriber_receives_normalized_event():
    cfg = AppConfig(DahuaConfig("n"), TelegramConfig("token", "chat"), {"Human"})
    service = BridgeService(cfg, FakeDahua(), FakeTelegram())
    import asyncio

    queue = asyncio.Queue()
    service.live_subscribers.add(queue)
    event = parse_event("Code=Human;action=Start;index=0;ObjectType=Human")
    assert event
    await service.handle(event)
    payload = await queue.get()
    assert payload["event_type"] == "Human" and payload["action"] == "Start"
