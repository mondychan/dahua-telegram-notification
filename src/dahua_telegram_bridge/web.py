from __future__ import annotations

import asyncio
import hmac
import json
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any

from aiohttp import web


INDEX_HTML = """<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>Dahua Bridge</title><style>body{margin:0;background:#111827;color:#e5e7eb;font:14px system-ui}aside{position:fixed;width:210px;height:100vh;background:#0b1220;padding:24px;box-sizing:border-box}main{margin-left:210px;padding:28px;max-width:1100px}.nav{display:block;color:#9ca3af;padding:10px 0}.nav:hover{color:white}h1{margin-top:0}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px}.card{background:#1f2937;border:1px solid #374151;padding:18px;border-radius:6px}.value{font-size:24px;margin-top:8px}table{width:100%;border-collapse:collapse;margin-top:20px}td,th{text-align:left;padding:9px;border-bottom:1px solid #374151}code,pre{font-family:ui-monospace,monospace}.ok{color:#34d399}.bad{color:#f87171}</style></head><body><aside><h2>Dahua Bridge</h2><a class=nav href=#dashboard>Dashboard</a><a class=nav href=#nvr>NVR</a><a class=nav href=#channels>Channels</a><a class=nav href=#events>Events</a><a class=nav href=#notifications>Notifications</a><a class=nav href=#logs>Live Log</a><a class=nav href=#settings>Settings</a><a class=nav href=#system>System</a></aside><main><h1>Dashboard</h1><div id=cards class=grid></div><h2>Recent events</h2><table><thead><tr><th>Time</th><th>Channel</th><th>Event</th><th>Action</th><th>Rule</th></tr></thead><tbody id=events></tbody></table></main><script>async function refresh(){const h=await (await fetch('/api/health')).json();const s=await (await fetch('/api/system')).json();document.querySelector('#cards').innerHTML=[['NVR',h.nvr_connected?'CONNECTED':'DISCONNECTED'],['Events',h.events_received],['Processed',h.processed_events],['Snapshots',h.snapshots_success],['Telegram',s.telegram_enabled?(s.dry_run?'DRY RUN':'ENABLED'):'DISABLED'],['Reconnects',h.reconnect_count]].map(x=>`<div class=card><div>${x[0]}</div><div class=value>${x[1]}</div></div>`).join('');const e=await (await fetch('/api/events?limit=20')).json();document.querySelector('#events').innerHTML=e.map(x=>`<tr><td>${x.timestamp}</td><td>${x.channel??''}</td><td>${x.event_type}</td><td>${x.action}</td><td>${x.rule_name??''}</td></tr>`).join('')}refresh();setInterval(refresh,3000);</script></body></html>"""

LOGIN_HTML = """<!doctype html><meta name=viewport content='width=device-width,initial-scale=1'><title>Dahua Bridge Login</title><style>body{background:#111827;color:#e5e7eb;font:16px system-ui;display:grid;place-items:center;height:100vh}form{background:#1f2937;padding:28px;border-radius:8px;width:280px}input,button{display:block;width:100%;box-sizing:border-box;margin:10px 0;padding:10px;border-radius:4px;border:1px solid #4b5563}button{background:#2563eb;color:white;border:0}</style><form id=f><h2>Dahua Bridge</h2><input id=u placeholder=username autocomplete=username><input id=p type=password placeholder=password autocomplete=current-password><button>Sign in</button><p id=e></p></form><script>f.onsubmit=async e=>{e.preventDefault();let r=await fetch('/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:u.value,password:p.value})});if(r.ok)location.href='/';else document.querySelector('#e').textContent='Invalid credentials'}</script>"""

ADMIN_HTML = """<!doctype html><meta name=viewport content='width=device-width,initial-scale=1'><title>Dahua Bridge Admin</title><style>body{margin:0;background:#111827;color:#e5e7eb;font:14px system-ui}nav{background:#0b1220;padding:14px;display:flex;gap:18px;flex-wrap:wrap}nav button{background:none;border:0;color:#9ca3af;cursor:pointer}nav button.active{color:#fff}main{padding:24px;max-width:1200px;margin:auto}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}.card{background:#1f2937;border:1px solid #374151;padding:16px;border-radius:6px}.value{font-size:24px;margin-top:8px}table{width:100%;border-collapse:collapse;margin-top:16px}th,td{text-align:left;padding:8px;border-bottom:1px solid #374151}pre{background:#030712;padding:12px;overflow:auto}.hidden{display:none}.ok{color:#34d399}.bad{color:#f87171}</style><nav>${['dashboard','nvr','channels','events','notifications','logs','settings','system'].map(x=>`<button data-tab=${x}>${x[0].toUpperCase()+x.slice(1)}</button>`).join('')}</nav><main><section id=dashboard><h1>Dashboard</h1><div id=cards class=grid></div></section><section id=nvr class=hidden><h1>NVR</h1><pre id=nvrdata></pre></section><section id=channels class=hidden><h1>Channels</h1><table><tbody id=chdata></tbody></table></section><section id=events class=hidden><h1>Events</h1><table><thead><tr><th>Time</th><th>Channel</th><th>Event</th><th>Action</th><th>Rule</th></tr></thead><tbody id=evdata></tbody></table></section><section id=notifications class=hidden><h1>Notifications</h1><pre id=rules></pre></section><section id=logs class=hidden><h1>Live Log</h1><pre id=logdata></pre></section><section id=settings class=hidden><h1>Settings</h1><pre id=settingsdata></pre></section><section id=system class=hidden><h1>System</h1><pre id=sysdata></pre></section></main><script>const tabs=[...document.querySelectorAll('[data-tab]')];tabs.forEach(b=>b.onclick=()=>{tabs.forEach(x=>x.classList.remove('active'));b.classList.add('active');document.querySelectorAll('section').forEach(x=>x.classList.toggle('hidden',x.id!==b.dataset.tab));load(b.dataset.tab)});tabs[0].click();async function j(url){let r=await fetch(url);if(r.status===401){location.reload();throw Error('auth')}return r.json()}async function load(tab){if(tab==='dashboard'){let h=await j('/api/health'),s=await j('/api/system');cards.innerHTML=[['NVR',h.nvr_connected?'CONNECTED':'DISCONNECTED'],['Events',h.events_received],['Processed',h.processed_events],['Snapshots',h.snapshots_success],['Telegram',s.dry_run?'DRY RUN':(s.telegram_enabled?'ENABLED':'DISABLED')],['Reconnects',h.reconnect_count]].map(x=>`<div class=card>${x[0]}<div class=value>${x[1]}</div></div>`).join('')}if(tab==='nvr')nvrdata.textContent=JSON.stringify(await j('/api/nvr'),null,2);if(tab==='channels')chdata.innerHTML=(await j('/api/channels')).map(x=>`<tr><td>CH${x.channel}</td><td>${x.event_count}</td><td>${x.last_event||''}</td></tr>`).join('');if(tab==='events')evdata.innerHTML=(await j('/api/events?limit=100')).map(x=>`<tr><td>${x.timestamp}</td><td>${x.channel??''}</td><td>${x.event_type}</td><td>${x.action}</td><td>${x.rule_name||''}</td></tr>`).join('');if(tab==='notifications')rules.textContent=JSON.stringify(await j('/api/notifications'),null,2);if(tab==='logs')logdata.textContent=(await j('/api/logs')).map(x=>`${x.level} ${x.logger} ${x.message}`).join('\n');if(tab==='settings')settingsdata.textContent=JSON.stringify(await j('/api/config'),null,2);if(tab==='system')sysdata.textContent=JSON.stringify(await j('/api/system'),null,2)}setInterval(()=>load(document.querySelector('button.active')?.dataset.tab||'dashboard'),5000);const es=new EventSource('/api/events/live');es.onmessage=e=>console.debug('event',JSON.parse(e.data));</script>"""


class Store:
    def __init__(self, path: str = "/data/bridge.sqlite3") -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(
            """CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,timestamp TEXT,event_type TEXT,action TEXT,channel INTEGER,object_type TEXT,rule_name TEXT,raw_payload TEXT); CREATE TABLE IF NOT EXISTS rules(id INTEGER PRIMARY KEY AUTOINCREMENT,channel INTEGER,event_type TEXT,object_type TEXT,enabled INTEGER NOT NULL DEFAULT 1); CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT,timestamp TEXT,source TEXT,setting TEXT,old_value TEXT,new_value TEXT,result TEXT);"""
        )
        self.db.commit()

    def add_event(self, event: Any) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO events VALUES(?,?,?,?,?,?,?,?)",
            (
                event.id,
                event.timestamp.isoformat(),
                event.event_type,
                event.action,
                event.channel,
                event.object_type,
                event.rule_name,
                json.dumps(event.raw_payload),
            ),
        )
        self.db.commit()

    def events(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT * FROM events ORDER BY timestamp DESC LIMIT ?", (max(1, min(limit, 500)),)
        ).fetchall()
        return [dict(row) for row in rows]

    def rules(self) -> list[dict[str, Any]]:
        return [
            dict(row) for row in self.db.execute("SELECT * FROM rules ORDER BY id DESC").fetchall()
        ]

    def create_rule(self, data: dict[str, Any]) -> dict[str, Any]:
        if not data.get("event_type"):
            raise ValueError("event_type is required")
        cur = self.db.execute(
            "INSERT INTO rules(channel,event_type,object_type,enabled) VALUES(?,?,?,?)",
            (
                data.get("channel"),
                data["event_type"],
                data.get("object_type"),
                int(bool(data.get("enabled", True))),
            ),
        )
        self.db.commit()
        self.add_audit(f"notification rule {cur.lastrowid}", "none", "created")
        return dict(self.db.execute("SELECT * FROM rules WHERE id=?", (cur.lastrowid,)).fetchone())

    def update_rule(self, rule_id: int, data: dict[str, Any]) -> dict[str, Any] | None:
        current = self.db.execute("SELECT * FROM rules WHERE id=?", (rule_id,)).fetchone()
        if current is None:
            return None
        self.db.execute(
            "UPDATE rules SET channel=?, event_type=?, object_type=?, enabled=? WHERE id=?",
            (
                data.get("channel", current["channel"]),
                data.get("event_type", current["event_type"]),
                data.get("object_type", current["object_type"]),
                int(bool(data.get("enabled", current["enabled"]))),
                rule_id,
            ),
        )
        self.db.commit()
        self.add_audit(f"notification rule {rule_id}", str(dict(current)), str(data))
        return dict(self.db.execute("SELECT * FROM rules WHERE id=?", (rule_id,)).fetchone())

    def delete_rule(self, rule_id: int) -> bool:
        cur = self.db.execute("DELETE FROM rules WHERE id=?", (rule_id,))
        self.db.commit()
        if cur.rowcount:
            self.add_audit(f"notification rule {rule_id}", "configured", "deleted")
        return cur.rowcount > 0

    def channels(self) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT channel, COUNT(*) AS event_count, MAX(timestamp) AS last_event FROM events WHERE channel IS NOT NULL GROUP BY channel ORDER BY channel"
        ).fetchall()
        return [dict(row) for row in rows]

    def audit(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT * FROM audit ORDER BY id DESC LIMIT ?", (max(1, min(limit, 500)),)
        ).fetchall()
        return [dict(row) for row in rows]

    def add_audit(
        self, setting: str, old_value: str, new_value: str, result: str = "SUCCESS"
    ) -> None:
        self.db.execute(
            "INSERT INTO audit(timestamp,source,setting,old_value,new_value,result) VALUES(datetime('now'),?,?,?,?,?)",
            ("web", setting, old_value, new_value, result),
        )
        self.db.commit()

    def event(self, event_id: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        return dict(row) if row else None

    def matching_rule(
        self, channel: int | None, event_type: str, object_type: str | None
    ) -> dict[str, Any] | None:
        rows = self.db.execute(
            "SELECT * FROM rules WHERE event_type=? AND (channel IS NULL OR channel=?) AND (object_type IS NULL OR object_type=?) ORDER BY object_type IS NOT NULL DESC, channel IS NOT NULL DESC",
            (event_type, channel, object_type),
        ).fetchall()
        return dict(rows[0]) if rows else None


def _auth(request: web.Request) -> bool:
    expected = request.app["admin_password"]
    return bool(
        expected
        and hmac.compare_digest(
            request.cookies.get("admin_session", ""), request.app["session_token"]
        )
    )


def create_web_app(service: Any, config: Any, store: Store | None = None) -> web.Application:
    store = store or Store(getattr(config, "data_path", "/data/bridge.sqlite3"))
    app = web.Application()
    app["store"] = store
    app["admin_password"] = getattr(config, "admin_password", "")
    app["admin_username"] = getattr(config, "admin_username", "admin")
    app["session_token"] = secrets.token_urlsafe(32)
    app["csrf_token"] = secrets.token_urlsafe(24)
    app["nvr_info"] = {"expires": 0.0, "data": {}}
    app["channel_titles"] = {"expires": 0.0, "data": {}}

    @web.middleware
    async def auth_middleware(request: web.Request, handler: Any) -> web.StreamResponse:
        if request.path in {"/", "/login", "/health", "/metrics"} or request.path.startswith(
            "/static"
        ):
            return await handler(request)  # type: ignore[no-any-return]
        if not _auth(request):
            return web.json_response({"error": "authentication required"}, status=401)
        return await handler(request)  # type: ignore[no-any-return]

    app.middlewares.append(auth_middleware)

    async def index(request: web.Request) -> web.Response:
        if not _auth(request):
            return web.Response(text=LOGIN_HTML, content_type="text/html")
        return web.Response(text=ADMIN_HTML, content_type="text/html")

    async def login(request: web.Request) -> web.Response:
        data = await request.json()
        if hmac.compare_digest(
            str(data.get("username", "")), app["admin_username"]
        ) and hmac.compare_digest(str(data.get("password", "")), app["admin_password"]):
            response = web.json_response({"ok": True})
            response.set_cookie(
                "admin_session", app["session_token"], httponly=True, samesite="Strict"
            )
            response.set_cookie("csrf_token", app["csrf_token"], httponly=False, samesite="Strict")
            return response
        return web.json_response({"error": "invalid credentials"}, status=401)

    async def health(_request: web.Request) -> web.Response:
        h = service.health
        return web.json_response(
            {
                "alive": True,
                "nvr_connected": h.nvr_connected,
                "last_event": h.last_event.isoformat() if h.last_event else None,
                "last_snapshot": h.last_snapshot.isoformat() if h.last_snapshot else None,
                "last_telegram": h.last_telegram.isoformat() if h.last_telegram else None,
                "events_received": h.events_received,
                "processed_events": h.processed_events,
                "failed_events": h.failed_events,
                "reconnect_count": h.reconnect_count,
            }
        )

    async def system(_request: web.Request) -> web.Response:
        return web.json_response(
            {
                "telegram_enabled": config.telegram.enabled,
                "dry_run": not config.telegram.enabled,
                "version": "0.1.0",
            }
        )

    async def nvr(_request: web.Request) -> web.Response:
        if time.monotonic() > app["nvr_info"]["expires"] and service.health.nvr_connected:
            try:
                app["nvr_info"] = {
                    "expires": time.monotonic() + 60,
                    "data": await service.dahua.system_info(),
                }
            except Exception:
                app["nvr_info"] = {"expires": time.monotonic() + 10, "data": {}}
        if time.monotonic() > app["channel_titles"]["expires"] and service.health.nvr_connected:
            try:
                app["channel_titles"] = {
                    "expires": time.monotonic() + 60,
                    "data": await service.dahua.channel_titles(),
                }
            except Exception:
                app["channel_titles"] = {"expires": time.monotonic() + 10, "data": {}}
        return web.json_response(
            {
                "host": config.dahua.host,
                "port": config.dahua.port,
                "https": config.dahua.https,
                "connected": service.health.nvr_connected,
                "channel": config.dahua.channel,
                "system_info": app["nvr_info"]["data"],
                "channel_titles": app["channel_titles"]["data"],
            }
        )

    async def config_view(_request: web.Request) -> web.Response:
        return web.json_response(
            {
                "dahua": {
                    "host": config.dahua.host,
                    "port": config.dahua.port,
                    "username": config.dahua.username,
                    "channel": config.dahua.channel,
                    "https": config.dahua.https,
                },
                "telegram": {
                    "enabled": config.telegram.enabled,
                    "configured": bool(config.telegram.bot_token and config.telegram.chat_id),
                    "token": "**************" if config.telegram.bot_token else None,
                    "chat_id_configured": bool(config.telegram.chat_id),
                },
                "events": {"enabled": sorted(config.enabled_events), "send_stop": config.send_stop},
                "snapshot": {
                    "enabled": config.snapshot_enabled,
                    "timeout_ms": config.snapshot_timeout_ms,
                    "mode": config.snapshot_mode,
                },
                "dedup": {"enabled": config.dedup_enabled, "ttl_seconds": config.dedup_ttl_seconds},
                "admin": {
                    "username": config.admin_username,
                    "password_configured": bool(config.admin_password),
                },
            }
        )

    async def events(request: web.Request) -> web.Response:
        result = store.events(int(request.query.get("limit", "100")))
        event_type = request.query.get("event_type")
        channel = request.query.get("channel")
        if event_type:
            result = [item for item in result if item["event_type"] == event_type]
        if channel is not None:
            result = [item for item in result if str(item["channel"]) == channel]
        return web.json_response(result)

    async def event_detail(request: web.Request) -> web.Response:
        item = store.event(request.match_info["id"])
        return (
            web.json_response(item)
            if item
            else web.json_response({"error": "not found"}, status=404)
        )

    async def snapshot(request: web.Request) -> web.Response:
        data = service.snapshot_cache.get(request.match_info["id"])
        return (
            web.Response(body=data, content_type="image/jpeg")
            if data
            else web.json_response({"error": "not found"}, status=404)
        )

    async def rules(_request: web.Request) -> web.Response:
        return web.json_response(store.rules())

    async def create_rule(request: web.Request) -> web.Response:
        if not hmac.compare_digest(request.headers.get("X-CSRF-Token", ""), app["csrf_token"]):
            return web.json_response({"error": "csrf token required"}, status=403)
        try:
            return web.json_response(store.create_rule(await request.json()), status=201)
        except (ValueError, json.JSONDecodeError) as exc:
            return web.json_response({"error": str(exc)}, status=400)

    async def update_rule(request: web.Request) -> web.Response:
        if not hmac.compare_digest(request.headers.get("X-CSRF-Token", ""), app["csrf_token"]):
            return web.json_response({"error": "csrf token required"}, status=403)
        result = store.update_rule(int(request.match_info["id"]), await request.json())
        return (
            web.json_response(result)
            if result
            else web.json_response({"error": "not found"}, status=404)
        )

    async def delete_rule(request: web.Request) -> web.Response:
        if not hmac.compare_digest(request.headers.get("X-CSRF-Token", ""), app["csrf_token"]):
            return web.json_response({"error": "csrf token required"}, status=403)
        return web.json_response({"deleted": store.delete_rule(int(request.match_info["id"]))})

    async def channels(_request: web.Request) -> web.Response:
        return web.json_response(store.channels())

    async def audit(_request: web.Request) -> web.Response:
        return web.json_response(store.audit())

    async def logs(request: web.Request) -> web.Response:
        buffer = request.app.get("log_buffer")
        return web.json_response(
            buffer.recent(int(request.query.get("limit", "100"))) if buffer else []
        )

    async def live_events(_request: web.Request) -> web.StreamResponse:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=50)
        service.live_subscribers.add(queue)
        response = web.StreamResponse(
            headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"}
        )
        await response.prepare(_request)
        try:
            while True:
                item = await asyncio.wait_for(queue.get(), timeout=15)
                await response.write(f"data: {json.dumps(item)}\n\n".encode())
        except (asyncio.TimeoutError, asyncio.CancelledError, ConnectionResetError):
            return response
        finally:
            service.live_subscribers.discard(queue)

    app.router.add_get("/", index)
    app.router.add_post("/login", login)
    app.router.add_get("/api/health", health)
    app.router.add_get("/api/system", system)
    app.router.add_get("/api/nvr", nvr)
    app.router.add_get("/api/config", config_view)
    app.router.add_get("/api/events", events)
    app.router.add_get("/api/events/{id}", event_detail)
    app.router.add_get("/api/events/{id}/snapshot", snapshot)
    app.router.add_get("/api/notifications", rules)
    app.router.add_post("/api/notifications", create_rule)
    app.router.add_patch("/api/notifications/{id}", update_rule)
    app.router.add_delete("/api/notifications/{id}", delete_rule)
    app.router.add_get("/api/channels", channels)
    app.router.add_get("/api/audit", audit)
    app.router.add_get("/api/logs", logs)
    app.router.add_get("/api/events/live", live_events)
    return app
