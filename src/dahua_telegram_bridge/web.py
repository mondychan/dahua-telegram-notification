from __future__ import annotations

import asyncio
import hmac
import json
import secrets
import sqlite3
from pathlib import Path
from typing import Any

from aiohttp import web


INDEX_HTML = """<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>Dahua Bridge</title><style>body{margin:0;background:#111827;color:#e5e7eb;font:14px system-ui}aside{position:fixed;width:210px;height:100vh;background:#0b1220;padding:24px;box-sizing:border-box}main{margin-left:210px;padding:28px;max-width:1100px}.nav{display:block;color:#9ca3af;padding:10px 0}.nav:hover{color:white}h1{margin-top:0}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px}.card{background:#1f2937;border:1px solid #374151;padding:18px;border-radius:6px}.value{font-size:24px;margin-top:8px}table{width:100%;border-collapse:collapse;margin-top:20px}td,th{text-align:left;padding:9px;border-bottom:1px solid #374151}code,pre{font-family:ui-monospace,monospace}.ok{color:#34d399}.bad{color:#f87171}</style></head><body><aside><h2>Dahua Bridge</h2><a class=nav href=#dashboard>Dashboard</a><a class=nav href=#nvr>NVR</a><a class=nav href=#channels>Channels</a><a class=nav href=#events>Events</a><a class=nav href=#notifications>Notifications</a><a class=nav href=#logs>Live Log</a><a class=nav href=#settings>Settings</a><a class=nav href=#system>System</a></aside><main><h1>Dashboard</h1><div id=cards class=grid></div><h2>Recent events</h2><table><thead><tr><th>Time</th><th>Channel</th><th>Event</th><th>Action</th><th>Rule</th></tr></thead><tbody id=events></tbody></table></main><script>async function refresh(){const h=await (await fetch('/api/health')).json();const s=await (await fetch('/api/system')).json();document.querySelector('#cards').innerHTML=[['NVR',h.nvr_connected?'CONNECTED':'DISCONNECTED'],['Events',h.events_received],['Processed',h.processed_events],['Snapshots',h.snapshots_success],['Telegram',s.telegram_enabled?(s.dry_run?'DRY RUN':'ENABLED'):'DISABLED'],['Reconnects',h.reconnect_count]].map(x=>`<div class=card><div>${x[0]}</div><div class=value>${x[1]}</div></div>`).join('');const e=await (await fetch('/api/events?limit=20')).json();document.querySelector('#events').innerHTML=e.map(x=>`<tr><td>${x.timestamp}</td><td>${x.channel??''}</td><td>${x.event_type}</td><td>${x.action}</td><td>${x.rule_name??''}</td></tr>`).join('')}refresh();setInterval(refresh,3000);</script></body></html>"""


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
        return dict(self.db.execute("SELECT * FROM rules WHERE id=?", (cur.lastrowid,)).fetchone())


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

    @web.middleware
    async def auth_middleware(request: web.Request, handler: Any) -> web.StreamResponse:
        if request.path in {"/", "/login"} or request.path.startswith("/static"):
            return await handler(request)  # type: ignore[no-any-return]
        if not _auth(request):
            return web.json_response({"error": "authentication required"}, status=401)
        return await handler(request)  # type: ignore[no-any-return]

    app.middlewares.append(auth_middleware)

    async def index(_request: web.Request) -> web.Response:
        return web.Response(text=INDEX_HTML, content_type="text/html")

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

    async def events(request: web.Request) -> web.Response:
        return web.json_response(store.events(int(request.query.get("limit", "100"))))

    async def rules(_request: web.Request) -> web.Response:
        return web.json_response(store.rules())

    async def create_rule(request: web.Request) -> web.Response:
        if not hmac.compare_digest(request.headers.get("X-CSRF-Token", ""), app["csrf_token"]):
            return web.json_response({"error": "csrf token required"}, status=403)
        try:
            return web.json_response(store.create_rule(await request.json()), status=201)
        except (ValueError, json.JSONDecodeError) as exc:
            return web.json_response({"error": str(exc)}, status=400)

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
    app.router.add_get("/api/events", events)
    app.router.add_get("/api/notifications", rules)
    app.router.add_post("/api/notifications", create_rule)
    app.router.add_get("/api/events/live", live_events)
    return app
