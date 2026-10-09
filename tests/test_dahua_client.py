from collections.abc import AsyncIterator
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


@pytest.mark.asyncio
async def test_dahua_events_stream_multipart_and_boundaries():
    stream_data = (
        b"--myboundary\r\n"
        b"Content-Type: text/plain\r\n"
        b"Content-Length: 46\r\n\r\n"
        b"Code=CrossLineDetection;action=Start;index=0\r\n"
        b"--myboundary\r\n"
        b"Content-Type: text/plain\r\n"
        b"Content-Length: 9\r\n\r\n"
        b"heartbeat\r\n"
        b"--myboundary\r\n"
        b"Content-Type: text/plain\r\n\r\n"
        b"Code=SmartMotionHuman;action=Start;index=1\r\n"
        b"--myboundary\r\n"
    )

    class StreamTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            async def body_stream() -> AsyncIterator[bytes]:
                yield stream_data[:50]
                yield stream_data[50:100]
                yield stream_data[100:]

            return httpx.Response(
                200,
                headers={"Content-Type": "multipart/x-mixed-replace;boundary=myboundary"},
                content=body_stream(),
                request=request,
            )

    client = DahuaClient(DahuaConfig("n"))
    await client.client.aclose()
    client.client = httpx.AsyncClient(transport=StreamTransport())

    received = []
    async for event_bytes in client.events():
        received.append(event_bytes)
        if len(received) == 2:
            break

    assert len(received) == 2
    assert b"CrossLineDetection" in received[0]
    assert b"SmartMotionHuman" in received[1]
    await client.close()
