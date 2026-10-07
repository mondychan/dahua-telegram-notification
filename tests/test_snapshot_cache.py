import pytest

from dahua_telegram_bridge.config import AppConfig, DahuaConfig, TelegramConfig
from dahua_telegram_bridge.dahua.parser import parse_event
from dahua_telegram_bridge.service import BridgeService


class D:
    async def snapshot(self, channel, timeout):
        return b"\xff\xd8jpg\xff\xd9"


class T:
    async def send(self, caption, photo=None):
        pass


@pytest.mark.asyncio
async def test_snapshot_cache_is_bounded():
    service = BridgeService(
        AppConfig(DahuaConfig("n"), TelegramConfig("x", "y"), {"Human"}), D(), T()
    )
    service.snapshot_cache_limit = 2
    for index in range(3):
        event = parse_event(f"Code=Human;action=Start;index={index};ObjectType=Human")
        assert event
        await service.handle(event)
    assert len(service.snapshot_cache) == 2
