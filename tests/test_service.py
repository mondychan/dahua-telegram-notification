import pytest
from dahua_telegram_bridge.config import AppConfig, DahuaConfig, TelegramConfig
from dahua_telegram_bridge.dahua.parser import parse_event
from dahua_telegram_bridge.service import BridgeService

class FakeDahua:
    def __init__(self):
        self.calls = 0
    async def snapshot(self, channel, timeout_ms):
        self.calls += 1
        return b"jpg"
class FakeTelegram:
    def __init__(self): self.calls = []
    async def send(self, caption, photo=None): self.calls.append((caption, photo))

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
