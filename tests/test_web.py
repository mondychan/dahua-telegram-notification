from types import SimpleNamespace

import pytest
from aiohttp.test_utils import TestClient, TestServer

from dahua_telegram_bridge.models import HealthState
from dahua_telegram_bridge.web import Store, create_web_app


@pytest.fixture
async def web_client(tmp_path):
    service = SimpleNamespace(health=HealthState())
    config = SimpleNamespace(
        telegram=SimpleNamespace(enabled=False),
        admin_username="admin",
        admin_password="secret",
        data_path=str(tmp_path / "db.sqlite3"),
    )
    app = create_web_app(service, config, Store(str(tmp_path / "db.sqlite3")))
    async with TestServer(app) as server:
        async with TestClient(server) as client:
            yield client


@pytest.mark.asyncio
async def test_web_requires_auth(web_client):
    response = await web_client.get("/api/system")
    assert response.status == 401


@pytest.mark.asyncio
async def test_web_login_and_rule(web_client):
    response = await web_client.post("/login", json={"username": "admin", "password": "secret"})
    assert response.status == 200
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
