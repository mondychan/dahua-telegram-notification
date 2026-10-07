import httpx
import pytest

from dahua_telegram_bridge.telegram.client import TelegramClient


class Config:
    bot_token = "x"
    chat_id = "1"
    timeout_seconds = 1
    enabled = True
    max_retries = 2
    backoff_seconds = 0


@pytest.mark.asyncio
async def test_telegram_retries_500(monkeypatch):
    client = TelegramClient(Config())
    calls = 0

    async def post(*args, **kwargs):
        nonlocal calls
        calls += 1
        status = 500 if calls == 1 else 200
        return httpx.Response(status, request=httpx.Request("POST", "http://x"))

    monkeypatch.setattr(client.client, "post", post)
    await client.send("hello", b"jpg")
    assert calls == 2
    await client.close()


@pytest.mark.asyncio
async def test_telegram_dry_run(monkeypatch):
    Config.enabled = False
    client = TelegramClient(Config())

    async def fail(*args, **kwargs):
        raise AssertionError("network called")

    monkeypatch.setattr(client.client, "post", fail)
    await client.send("hello")
    Config.enabled = True
    await client.close()
