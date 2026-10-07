from types import SimpleNamespace

import pytest
from aiohttp.test_utils import TestClient, TestServer

from dahua_telegram_bridge.models import HealthState
from dahua_telegram_bridge.web import Store, create_web_app


@pytest.fixture
async def web_client(tmp_path):
    class Dahua:
        async def system_info(self):
            return {"deviceType": "31"}

        async def channel_titles(self):
            return {"table.ChannelTitle[0].Name": "gate"}

    health = HealthState(nvr_connected=True)
    service = SimpleNamespace(health=health, dahua=Dahua(), snapshot_cache={})
    config = SimpleNamespace(
        dahua=SimpleNamespace(host="nvr", port=80, username="admin", channel=1, https=False),
        telegram=SimpleNamespace(enabled=False, bot_token="", chat_id=""),
        enabled_events={"Human"},
        send_stop=False,
        snapshot_enabled=True,
        snapshot_timeout_ms=1000,
        snapshot_mode="auto",
        dedup_enabled=True,
        dedup_ttl_seconds=2,
        admin_username="admin",
        admin_password="secret",
        data_path=str(tmp_path / "db.sqlite3"),
    )
    app = create_web_app(service, config, Store(str(tmp_path / "db.sqlite3")))
    async with TestServer(app) as server:
        async with TestClient(server) as client:
            yield client
    app["store"].close()


@pytest.mark.asyncio
async def test_web_requires_auth(web_client):
    response = await web_client.get("/api/system")
    assert response.status == 401


@pytest.mark.asyncio
async def test_web_login_and_rule(web_client):
    response = await web_client.post("/login", json={"username": "admin", "password": "secret"})
    assert response.status == 200
    config = await web_client.get("/api/config")
    assert config.status == 200
    assert "bot_token" not in await config.text()
    csrf = web_client.session.cookie_jar.filter_cookies(web_client.make_url("/"))[
        "csrf_token"
    ].value
    response = await web_client.post(
        "/api/notifications",
        json={"channel": 1, "event_type": "Human"},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status == 201
    rules = await web_client.get("/api/notifications")
    assert rules.status == 200
    rule = (await rules.json())[0]
    response = await web_client.patch(
        f"/api/notifications/{rule['id']}", json={"enabled": False}, headers={"X-CSRF-Token": csrf}
    )
    assert response.status == 200 and (await response.json())["enabled"] == 0
    response = await web_client.delete(
        f"/api/notifications/{rule['id']}", headers={"X-CSRF-Token": csrf}
    )
    assert response.status == 200


@pytest.mark.asyncio
async def test_event_filtering(web_client):
    response = await web_client.post("/login", json={"username": "admin", "password": "secret"})
    assert response.status == 200
    assert (await web_client.get("/api/events?event_type=Human")).status == 200
    assert (await web_client.get("/api/nvr")).status == 200
    assert (await web_client.get("/api/audit")).status == 200


@pytest.mark.asyncio
async def test_nvr_discovery_and_snapshot_not_found(web_client):
    response = await web_client.post("/login", json={"username": "admin", "password": "secret"})
    assert response.status == 200
    nvr = await web_client.get("/api/nvr")
    assert nvr.status == 200
    assert (await nvr.json())["system_info"]["deviceType"] == "31"
    assert (await web_client.get("/api/events/missing/snapshot")).status == 404
