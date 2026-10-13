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
        dahua=SimpleNamespace(
            host="nvr",
            port=80,
            username="admin",
            password="dahua_super_secret",
            channel=1,
            https=False,
        ),
        telegram=SimpleNamespace(
            enabled=False, bot_token="secret_bot_token_12345", chat_id="chat_999"
        ),
        enabled_events={"Human"},
        send_stop=False,
        snapshot_enabled=True,
        snapshot_timeout_ms=1000,
        snapshot_mode="auto",
        dedup_enabled=True,
        dedup_ttl_seconds=2,
        admin_username="admin",
        admin_password="secret_admin_password",
        data_path=str(tmp_path / "db.sqlite3"),
    )
    store = Store(str(tmp_path / "db.sqlite3"))
    store.ensure_channel(channel_number=1, raw_index=0, camera_name="Gate Camera")
    app = create_web_app(service, config, store)
    async with TestServer(app) as server:
        async with TestClient(server) as client:
            yield client
    app["store"].close()


@pytest.mark.asyncio
async def test_web_requires_auth(web_client):
    response = await web_client.get("/api/system")
    assert response.status == 401
    for path in (
        "/api/config",
        "/api/settings",
        "/api/events",
        "/api/channels",
        "/api/logs",
        "/api/audit",
        "/api/notification-rules",
    ):
        assert (await web_client.get(path)).status == 401


@pytest.mark.asyncio
async def test_web_login_and_rule(web_client):
    response = await web_client.post(
        "/login", json={"username": "admin", "password": "secret_admin_password"}
    )
    assert response.status == 200
    config = await web_client.get("/api/config")
    assert config.status == 200
    assert "bot_token_12345" not in await config.text()
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
async def test_admin_navigation_is_rendered_as_html(web_client):
    assert (
        await web_client.post(
            "/login", json={"username": "admin", "password": "secret_admin_password"}
        )
    ).status == 200
    response = await web_client.get("/")
    body = await response.text()
    assert response.status == 200
    assert "<button data-tab=dashboard>Dashboard</button>" in body
    assert "${['dashboard'" not in body
    assert "document.getElementById('cards')" in body
    assert "document.getElementById('nvrdata')" in body
    assert "join('\\\\n\\\\n')" in body
    assert "toISOString()" in body
    assert "white-space:pre-wrap" in body


@pytest.mark.asyncio
async def test_channel_management_api(web_client):
    assert (
        await web_client.post(
            "/login", json={"username": "admin", "password": "secret_admin_password"}
        )
    ).status == 200
    csrf = web_client.session.cookie_jar.filter_cookies(web_client.make_url("/"))[
        "csrf_token"
    ].value

    # GET /api/channels
    ch_res = await web_client.get("/api/channels")
    assert ch_res.status == 200
    channels = await ch_res.json()
    assert len(channels) >= 1
    assert channels[0]["channel_number"] == 1
    assert channels[0]["monitoring_enabled"] == 1

    # CSRF check
    no_csrf = await web_client.patch("/api/channels/1", json={"monitoring_enabled": False})
    assert no_csrf.status == 403

    # Toggle Channel 1 monitoring OFF
    patch_res = await web_client.patch(
        "/api/channels/1",
        json={"monitoring_enabled": False},
        headers={"X-CSRF-Token": csrf},
    )
    assert patch_res.status == 200
    updated = await patch_res.json()
    assert updated["monitoring_enabled"] == 0

    # Verify audit recorded
    audit_res = await web_client.get("/api/audit")
    assert audit_res.status == 200
    audits = await audit_res.json()
    assert any(a["setting_type"] == "channel_monitoring" and a["channel"] == 1 for a in audits)

    # Mapping fields are persisted independently and marked manual.
    mapped = await web_client.patch(
        "/api/channels/1",
        json={"raw_index": 4, "snapshot_channel": 7},
        headers={"X-CSRF-Token": csrf},
    )
    assert mapped.status == 200
    row = await mapped.json()
    assert row["raw_index"] == 4
    assert row["snapshot_channel"] == 7
    assert row["channel_mapping_source"] == "manual"

    invalid = await web_client.patch(
        "/api/channels/1",
        json={"snapshot_channel": 0},
        headers={"X-CSRF-Token": csrf},
    )
    assert invalid.status == 400


@pytest.mark.asyncio
async def test_global_settings_and_telegram_switch_api(web_client):
    assert (
        await web_client.post(
            "/login", json={"username": "admin", "password": "secret_admin_password"}
        )
    ).status == 200
    csrf = web_client.session.cookie_jar.filter_cookies(web_client.make_url("/"))[
        "csrf_token"
    ].value

    # GET /api/settings
    settings_res = await web_client.get("/api/settings")
    assert settings_res.status == 200
    cfg = await settings_res.json()
    assert cfg["telegram_global_enabled"] is True
    assert (
        cfg["telegram_blocked_by_env"] is True
    )  # because config.telegram.enabled is False in fixture

    # PATCH /api/settings without CSRF -> 403
    assert (
        await web_client.patch("/api/settings", json={"telegram_notifications_enabled": False})
    ).status == 403

    # PATCH /api/settings with CSRF
    patch_res = await web_client.patch(
        "/api/settings",
        json={"telegram_notifications_enabled": False},
        headers={"X-CSRF-Token": csrf},
    )
    assert patch_res.status == 200
    updated_cfg = await patch_res.json()
    assert updated_cfg["telegram_global_enabled"] is False


@pytest.mark.asyncio
async def test_notification_rules_crud_and_csrf(web_client):
    assert (
        await web_client.post(
            "/login", json={"username": "admin", "password": "secret_admin_password"}
        )
    ).status == 200
    csrf = web_client.session.cookie_jar.filter_cookies(web_client.make_url("/"))[
        "csrf_token"
    ].value

    # POST /api/notification-rules without CSRF -> 403
    rule_data = {
        "channel": 1,
        "event_type": "CrossLineDetection",
        "object_type": "Human",
        "monitoring_enabled": True,
        "telegram_enabled": False,
        "allowed_actions": "Start,Stop",
    }
    assert (await web_client.post("/api/notification-rules", json=rule_data)).status == 403

    # POST with CSRF -> 201
    post_res = await web_client.post(
        "/api/notification-rules",
        json=rule_data,
        headers={"X-CSRF-Token": csrf},
    )
    assert post_res.status == 201
    created = await post_res.json()
    assert created["event_type"] == "CrossLineDetection"
    assert created["object_type"] == "Human"
    assert created["telegram_enabled"] == 0

    rule_id = created["id"]

    # PATCH /api/notification-rules/{id}
    patch_res = await web_client.patch(
        f"/api/notification-rules/{rule_id}",
        json={"telegram_enabled": True},
        headers={"X-CSRF-Token": csrf},
    )
    assert patch_res.status == 200
    assert (await patch_res.json())["telegram_enabled"] == 1

    # DELETE /api/notification-rules/{id}
    del_res = await web_client.delete(
        f"/api/notification-rules/{rule_id}",
        headers={"X-CSRF-Token": csrf},
    )
    assert del_res.status == 200
    assert (await del_res.json())["deleted"] is True


@pytest.mark.asyncio
async def test_secrets_never_exposed_in_api(web_client):
    assert (
        await web_client.post(
            "/login", json={"username": "admin", "password": "secret_admin_password"}
        )
    ).status == 200

    cfg_text = await (await web_client.get("/api/config")).text()
    assert "dahua_super_secret" not in cfg_text
    assert "secret_bot_token_12345" not in cfg_text
    assert "secret_admin_password" not in cfg_text

    audit_text = await (await web_client.get("/api/audit")).text()
    assert "dahua_super_secret" not in audit_text
    assert "secret_bot_token_12345" not in audit_text
    assert "secret_admin_password" not in audit_text


@pytest.mark.asyncio
async def test_event_filtering(web_client):
    assert (
        await web_client.post(
            "/login", json={"username": "admin", "password": "secret_admin_password"}
        )
    ).status == 200
    assert (await web_client.get("/api/events?event_type=Human")).status == 200
    assert (await web_client.get("/api/nvr")).status == 200
    assert (await web_client.get("/api/audit")).status == 200


@pytest.mark.asyncio
async def test_nvr_discovery_and_snapshot_not_found(web_client):
    assert (
        await web_client.post(
            "/login", json={"username": "admin", "password": "secret_admin_password"}
        )
    ).status == 200
    nvr = await web_client.get("/api/nvr")
    assert nvr.status == 200
    assert (await nvr.json())["system_info"]["deviceType"] == "31"
    assert (await web_client.get("/api/events/missing/snapshot")).status == 404
