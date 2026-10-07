import httpx
import pytest

from dahua_telegram_bridge.config import DahuaConfig
from dahua_telegram_bridge.dahua.client import DahuaClient


@pytest.mark.asyncio
async def test_dahua_read_only_endpoints():
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("snapshot.cgi"):
            return httpx.Response(200, content=b"\xff\xd8jpg\xff\xd9", request=request)
        if request.url.path.endswith("magicBox.cgi"):
            return httpx.Response(200, text="deviceType=31\nserialNumber=abc\n", request=request)
        return httpx.Response(200, text="table.ChannelTitle[0].Name=gate\n", request=request)

    client = DahuaClient(DahuaConfig("n"))
    await client.client.aclose()
    client.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    assert (await client.system_info())["serialNumber"] == "abc"
    assert (await client.channel_titles())["table.ChannelTitle[0].Name"] == "gate"
    assert (await client.snapshot(1, 1000)).startswith(b"\xff\xd8")
    await client.close()
