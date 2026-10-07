import os

import pytest

from dahua_telegram_bridge.config import load_config
from dahua_telegram_bridge.dahua.client import DahuaClient


pytestmark = pytest.mark.skipif(
    os.getenv("DAHUA_INTEGRATION") != "1", reason="set DAHUA_INTEGRATION=1"
)


@pytest.mark.asyncio
async def test_real_snapshot_without_telegram():
    client = DahuaClient(load_config().dahua)
    try:
        data = await client.snapshot(client.config.channel, 3000)
        assert data[:2] == b"\xff\xd8"
    finally:
        await client.close()
