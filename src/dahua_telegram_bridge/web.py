from __future__ import annotations

import asyncio
import hmac
import json
import re
import secrets
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aiohttp import web


LOGIN_HTML = """<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>Dahua Bridge Login</title><style>body{background:#111827;color:#e5e7eb;font:16px system-ui;display:grid;place-items:center;height:100vh;margin:0}form{background:#1f2937;padding:28px;border-radius:8px;width:300px;border:1px solid #374151}input,button{display:block;width:100%;box-sizing:border-box;margin:10px 0;padding:10px;border-radius:4px;border:1px solid #4b5563;background:#111827;color:#fff}button{background:#2563eb;color:white;border:0;cursor:pointer;font-weight:600}button:hover{background:#1d4ed8}.err{color:#f87171;font-size:13px;margin:5px 0}</style></head><body><form id=f><h2>Dahua Bridge</h2><p style='color:#9ca3af;font-size:13px;margin-top:-10px'>Sign in to manage cameras and notifications</p><input id=u placeholder=username autocomplete=username value=admin><input id=p type=password placeholder=password autocomplete=current-password><button>Sign in</button><p id=e class=err></p></form><script>f.onsubmit=async ev=>{ev.preventDefault();let r=await fetch('/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:u.value,password:p.value})});if(r.ok)location.href='/';else document.querySelector('#e').textContent='Invalid credentials'}</script></body></html>"""

ADMIN_HTML = """<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>Dahua Bridge Admin</title><style>body{margin:0;background:#111827;color:#e5e7eb;font:14px system-ui}nav{background:#0b1220;padding:14px 24px;display:flex;gap:16px;flex-wrap:wrap;border-bottom:1px solid #1f2937}nav button{background:none;border:0;color:#9ca3af;cursor:pointer;font-size:14px;padding:6px 12px;border-radius:4px}nav button.active{color:#fff;background:#1f2937;font-weight:bold}main{padding:24px;max-width:1300px;margin:auto}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:20px}.card{background:#1f2937;border:1px solid #374151;padding:16px;border-radius:6px}.card-title{color:#9ca3af;font-size:12px;text-transform:uppercase}.value{font-size:22px;font-weight:bold;margin-top:6px}table{width:100%;border-collapse:collapse;margin-top:16px;background:#1f2937;border-radius:6px;overflow:hidden}th,td{text-align:left;padding:10px 12px;border-bottom:1px solid #374151;font-size:13px}th{background:#111827;color:#9ca3af}pre{background:#030712;padding:14px;border-radius:6px;overflow:auto;white-space:pre-wrap;word-break:break-word;line-height:1.5;font-family:ui-monospace,monospace;font-size:12px}.hidden{display:none}.ok{color:#34d399;font-weight:600}.bad{color:#f87171;font-weight:600}.warn{color:#fbbf24;font-weight:600}.badge{display:inline-block;padding:3px 8px;border-radius:12px;font-size:11px;font-weight:bold}.badge-ok{background:#065f46;color:#6ee7b7}.badge-bad{background:#7f1d1d;color:#fca5a5}.badge-warn{background:#78350f;color:#fcd34d}.badge-info{background:#1e3a8a;color:#93c5fd}.banner{padding:12px 16px;border-radius:6px;margin-bottom:16px;display:flex;align-items:center;justify-content:space-between;border:1px solid}.banner-warn{background:#451a03;border-color:#b45309;color:#fef3c7}.banner-info{background:#172554;border-color:#1d4ed8;color:#dbeafe}.switch-btn{padding:5px 12px;border-radius:4px;border:1px solid #4b5563;cursor:pointer;font-weight:600;font-size:12px}.switch-btn.on{background:#059669;color:#fff;border-color:#10b981}.switch-btn.off{background:#dc2626;color:#fff;border-color:#ef4444}.filter-bar{display:flex;gap:10px;margin-bottom:14px;flex-wrap:wrap;align-items:center}select,input{background:#111827;border:1px solid #4b5563;color:#fff;padding:6px 10px;border-radius:4px}button.action{background:#2563eb;color:#fff;border:0;padding:6px 14px;border-radius:4px;cursor:pointer;font-weight:600}button.action:hover{background:#1d4ed8}button.del{background:#dc2626;color:#fff;border:0;padding:4px 8px;border-radius:4px;cursor:pointer}form.card-form{background:#1f2937;border:1px solid #374151;padding:16px;border-radius:6px;margin-bottom:16px;display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;align-items:end}#modal{position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.7);display:flex;align-items:center;justify-content:center;z-index:99}#modal.hidden{display:none}#modal-content{background:#1f2937;border:1px solid #4b5563;border-radius:8px;max-width:800px;width:90%;max-height:85vh;overflow:auto;padding:20px}</style></head><body><nav><button data-tab=dashboard>Dashboard</button><button data-tab=nvr>NVR</button><button data-tab=channels>Channels</button><button data-tab=events>Events</button><button data-tab=notifications>Notifications</button><button data-tab=logs>Live Log</button><button data-tab=settings>Settings</button><button data-tab=system>System</button></nav><main><div id=globalbanner></div><section id=dashboard><h1>Dashboard</h1><div id=cards class=grid></div><div style='background:#1f2937;border:1px solid #374151;padding:16px;border-radius:6px;margin-bottom:20px;display:flex;align-items:center;justify-content:space-between'><div><strong style='font-size:16px'>Telegram Notifications Master Switch</strong><div id=tgdesc style='color:#9ca3af;font-size:12px;margin-top:4px'>Controls outbound Telegram messages across all channels</div></div><div id=tgswitchbox></div></div><h2>Recent Events</h2><table><thead><tr><th>Time</th><th>Channel</th><th>Event</th><th>Object</th><th>Action</th><th>Rule</th><th>Decision</th><th>Reason</th><th>Snapshot</th></tr></thead><tbody id=evquick></tbody></table></section><section id=nvr class=hidden><h1>NVR Discovery</h1><pre id=nvrdata></pre></section><section id=channels class=hidden><div style='display:flex;justify-content:space-between;align-items:center'><h1>Camera Channels</h1><button class=action onclick='loadChannels()'>Refresh</button></div><table><thead><tr><th>Channel</th><th>Camera Name</th><th>Model</th><th>Status</th><th>Monitoring</th><th>Known Events</th><th>Last Event</th><th>Count</th><th>Last Notification</th><th>Raw Index</th><th>Snapshot Ch</th><th>Mapping</th><th>Actions</th></tr></thead><tbody id=chdata></tbody></table></section><section id=events class=hidden><div style='display:flex;justify-content:space-between;align-items:center'><h1>Event Catalog</h1><div class=filter-bar><select id=flt_ch><option value=''>All Channels</option></select><select id=flt_ev><option value=''>All Event Types</option><option value=CrossLineDetection>CrossLineDetection</option><option value=SmartMotionHuman>SmartMotionHuman</option><option value=SmartMotionVehicle>SmartMotionVehicle</option><option value=VideoMotion>VideoMotion</option></select><select id=flt_obj><option value=''>All Objects</option><option value=Human>Human</option><option value=Vehicle>Vehicle</option></select><select id=flt_dec><option value=''>All Decisions</option><option value=processed>Processed</option><option value=filtered>Filtered</option><option value=deduplicated>Deduplicated</option></select><button class=action onclick='loadEvents()'>Filter</button></div></div><table><thead><tr><th>Time</th><th>Channel</th><th>Event</th><th>Object</th><th>Action</th><th>Rule</th><th>Decision</th><th>Reason</th><th>Details</th></tr></thead><tbody id=evdata></tbody></table></section><section id=notifications class=hidden><h1>Event Notification Rules</h1><form id=addruleform class=card-form><div><label style='font-size:11px;color:#9ca3af'>Channel (CH# or blank for all)</label><input id=rf_ch type=number placeholder='All'></div><div><label style='font-size:11px;color:#9ca3af'>Event Type</label><select id=rf_type><option value=CrossLineDetection>CrossLineDetection</option><option value=SmartMotionHuman>SmartMotionHuman</option><option value=SmartMotionVehicle>SmartMotionVehicle</option><option value=VideoMotion>VideoMotion</option></select></div><div><label style='font-size:11px;color:#9ca3af'>Object Type</label><select id=rf_obj><option value=''>Any</option><option value=Human>Human</option><option value=Vehicle>Vehicle</option></select></div><div><label style='font-size:11px;color:#9ca3af'>Rule Name (opt)</label><input id=rf_rule placeholder='e.g. Rule1'></div><div><label style='font-size:11px;color:#9ca3af'>Allowed Actions</label><input id=rf_act value='Start'></div><div><label style='font-size:11px;color:#9ca3af'>Monitoring</label><select id=rf_mon><option value=1>ON</option><option value=0>OFF</option></select></div><div><label style='font-size:11px;color:#9ca3af'>Telegram</label><select id=rf_tg><option value=1>ON</option><option value=0>OFF</option></select></div><div><button type=submit class=action style='width:100%'>Add Rule</button></div></form><table><thead><tr><th>ID</th><th>Channel</th><th>Event Type</th><th>Object</th><th>Rule Name</th><th>Allowed Actions</th><th>Monitoring</th><th>Telegram</th><th>Actions</th></tr></thead><tbody id=rulesbody></tbody></table><h2 style='margin-top:24px'>Raw Rules JSON</h2><pre id=rules></pre></section><section id=logs class=hidden><div style='display:flex;justify-content:space-between;align-items:center'><h1>Live Log</h1><button class=action onclick='loadLogs()'>Refresh</button></div><pre id=logdata></pre></section><section id=settings class=hidden><h1>Settings & Audit</h1><div style='background:#1f2937;border:1px solid #374151;padding:16px;border-radius:6px;margin-bottom:20px'><h3 style='margin-top:0'>Global Telegram Switch</h3><div id=settgswitchbox style='margin-bottom:12px'></div><p style='color:#9ca3af;font-size:12px;margin-bottom:0'>Safety Rule: If TELEGRAM_ENABLED=false in environment, Telegram is strictly blocked by deployment configuration.</p></div><h2>Recent Configuration Audit Log</h2><table><thead><tr><th>Time</th><th>Source</th><th>Setting Type</th><th>Channel</th><th>Event Type</th><th>Old Value</th><th>New Value</th><th>Result</th></tr></thead><tbody id=auditbody></tbody></table><h2>System Configuration</h2><pre id=settingsdata></pre></section><section id=system class=hidden><h1>System Diagnostics</h1><pre id=sysdata></pre></section></main><div id=modal class=hidden><div id=modal-content><div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:14px'><h2 id=modal-title style='margin:0'>Event Details</h2><button class=action onclick='document.getElementById(\"modal\").classList.add(\"hidden\")'>Close</button></div><pre id=modal-body></pre></div></div><script>const cards=document.getElementById('cards'),nvrdata=document.getElementById('nvrdata'),chdata=document.getElementById('chdata'),evdata=document.getElementById('evdata'),rules=document.getElementById('rules'),logdata=document.getElementById('logdata'),settingsdata=document.getElementById('settingsdata'),sysdata=document.getElementById('sysdata');const tabs=[...document.querySelectorAll('nav [data-tab]')];tabs.forEach(b=>b.onclick=()=>{tabs.forEach(x=>x.classList.remove('active'));b.classList.add('active');document.querySelectorAll('section').forEach(x=>x.classList.toggle('hidden',x.id!==b.dataset.tab));load(b.dataset.tab)});tabs[0].click();function getCsrf(){let m=document.cookie.match(/(?:^|; )csrf_token=([^;]+)/);return m?decodeURIComponent(m[1]):''}async function j(url,opts={}){opts.headers=opts.headers||{};let token=getCsrf();if(token)opts.headers['X-CSRF-Token']=token;let r=await fetch(url,opts);if(r.status===401){location.reload();throw Error('auth')}return r.json()}function badge(val){val=val||'';if(val.toLowerCase().includes('processed')||val.toLowerCase().includes('sent')||val.toLowerCase().includes('success')||val.toLowerCase().includes('eligible'))return `<span class="badge badge-ok">${val}</span>`;if(val.toLowerCase().includes('filter')||val.toLowerCase().includes('stop')||val.toLowerCase().includes('disable')||val.toLowerCase().includes('blocked'))return `<span class="badge badge-warn">${val}</span>`;if(val.toLowerCase().includes('fail')||val.toLowerCase().includes('error'))return `<span class="badge badge-bad">${val}</span>`;return `<span class="badge badge-info">${val}</span>`}async function toggleGlobalTg(target){try{let r=await j('/api/settings',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({telegram_notifications_enabled:target})});if(r.error)alert('Error: '+r.error);else load('dashboard')}catch(e){alert('Failed to update: '+e.message)}}async function toggleChannelMon(ch,target){try{let r=await j('/api/channels/'+ch,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({monitoring_enabled:target})});if(r.error)alert('Error: '+r.error);else loadChannels()}catch(e){alert('Failed to update: '+e.message)}}async function toggleRuleMon(id,target){try{let r=await j('/api/notifications/'+id,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({monitoring_enabled:target})});if(r.error)alert('Error: '+r.error);else loadRules()}catch(e){alert('Failed to update: '+e.message)}}async function toggleRuleTg(id,target){try{let r=await j('/api/notifications/'+id,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({telegram_enabled:target})});if(r.error)alert('Error: '+r.error);else loadRules()}catch(e){alert('Failed to update: '+e.message)}}async function deleteRule(id){if(!confirm('Delete rule '+id+'?'))return;try{let r=await j('/api/notifications/'+id,{method:'DELETE'});if(r.error)alert('Error: '+r.error);else loadRules()}catch(e){alert('Failed to delete: '+e.message)}}addruleform.onsubmit=async e=>{e.preventDefault();let data={channel:rf_ch.value?parseInt(rf_ch.value):null,event_type:rf_type.value,object_type:rf_obj.value||null,rule_name:rf_rule.value||null,allowed_actions:rf_act.value||'Start',monitoring_enabled:rf_mon.value==='1',telegram_enabled:rf_tg.value==='1'};try{let r=await j('/api/notifications',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});if(r.error)alert('Error: '+r.error);else{rf_rule.value='';loadRules()}}catch(err){alert('Failed to create: '+err.message)}};function renderTgSwitch(cfg,containerId){let box=document.getElementById(containerId);if(!box)return;if(cfg.telegram_blocked_by_env){box.innerHTML=`<button class="switch-btn off" disabled title="Blocked by ENV">Telegram blocked by environment configuration</button>`}else if(cfg.telegram_effective_enabled){box.innerHTML=`<button class="switch-btn on" onclick="toggleGlobalTg(false)">Telegram notifications: ON</button>`}else{box.innerHTML=`<button class="switch-btn off" onclick="toggleGlobalTg(true)">Telegram notifications: OFF</button>`}}async function loadDashboard(){let h=await j('/api/health'),s=await j('/api/system'),c=await j('/api/settings');cards.innerHTML=[['NVR',h.nvr_connected?'CONNECTED':'DISCONNECTED'],['Events',h.events_received],['Processed',h.processed_events],['Snapshots',h.snapshots_success],['Telegram',s.dry_run?'DRY RUN':(c.telegram_effective_enabled?'ENABLED':'DISABLED')],['Reconnects',h.reconnect_count]].map(x=>`<div class=card><div class=card-title>${x[0]}</div><div class="value ${x[1]==='CONNECTED'||x[1]==='ENABLED'?'ok':(x[1]==='DISCONNECTED'||x[1]==='DISABLED'?'bad':'')}">${x[1]}</div></div>`).join('');renderTgSwitch(c,'tgswitchbox');if(c.telegram_blocked_by_env){globalbanner.innerHTML=`<div class="banner banner-warn"><span>⚠️ Telegram blocked by environment configuration (TELEGRAM_ENABLED=false)</span></div>`}else{globalbanner.innerHTML=''}let evs=await j('/api/events?limit=15');evquick.innerHTML=evs.map(x=>`<tr><td>${x.timestamp}</td><td>CH${x.channel??x.raw_index??''}</td><td>${x.event_type}</td><td>${x.object_type||'—'}</td><td>${x.action}</td><td>${x.rule_name||'—'}</td><td>${badge(x.decision||x.processing_status)}</td><td>${badge(x.reason||x.filter_reason)}</td><td>${x.snapshot_status==='Snapshot success'?`<a href="/api/events/${x.id}/snapshot" target=_blank style="color:#60a5fa">View</a>`:(x.snapshot_status||'—')}</td></tr>`).join('')}async function editChannel(ch){let raw=prompt('Event raw index (0-based):',ch.raw_index??'');if(raw===null)return;let snap=prompt('Snapshot channel (1-based):',ch.snapshot_channel??ch.channel_number);if(snap===null)return;let r=await j('/api/channels/'+ch.channel_number,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({raw_index:raw===''?null:parseInt(raw),snapshot_channel:parseInt(snap),channel_mapping_source:'manual'})});if(r.error)alert('Error: '+r.error);else loadChannels()}async function loadChannels(){let list=await j('/api/channels');chdata.innerHTML=list.map(x=>`<tr><td><strong>CH${x.channel_number}</strong></td><td>${x.camera_name}</td><td>${x.camera_model||'—'}</td><td><span class="${x.online_status==='online'?'ok':'warn'}">${x.online_status}</span></td><td><button class="switch-btn ${x.monitoring_enabled?'on':'off'}" onclick="toggleChannelMon(${x.channel_number},${!x.monitoring_enabled})">${x.monitoring_enabled?'MONITORING ON':'MONITORING OFF'}</button></td><td>${x.known_events||'—'}</td><td>${x.last_event||'—'}</td><td>${x.event_count}</td><td>${x.last_notification||'—'}</td><td>${x.raw_index??'—'}</td><td>${x.snapshot_channel??x.channel_number}</td><td>${x.channel_mapping_source||'auto'}</td><td><button class=action onclick='editChannel(${JSON.stringify(x)})'>Edit mapping</button></td></tr>`).join('');let sel=document.getElementById('flt_ch');if(sel&&sel.options.length<=1){list.forEach(c=>{let o=document.createElement('option');o.value=c.channel_number;o.textContent='CH'+c.channel_number+' ('+c.camera_name+')';sel.appendChild(o)})}}async function loadEvents(){let ch=flt_ch.value,et=flt_ev.value,obj=flt_obj.value,dec=flt_dec.value;let url=`/api/events?limit=100`;if(ch)url+=`&channel=${ch}`;if(et)url+=`&event_type=${et}`;if(obj)url+=`&object_type=${obj}`;if(dec)url+=`&decision=${dec}`;let list=await j(url);evdata.innerHTML=list.map(x=>`<tr><td>${x.timestamp}</td><td>CH${x.channel??''}</td><td>${x.event_type}</td><td>${x.object_type||'—'}</td><td>${x.action}</td><td>${x.rule_name||'—'}</td><td>${badge(x.decision||x.processing_status)}</td><td>${badge(x.reason||x.filter_reason)}</td><td><button class=action style="padding:2px 8px;font-size:11px" onclick='showEventDetail(${JSON.stringify(x).replace(/'/g,"&#39;")})'>JSON</button></td></tr>`).join('')}function showEventDetail(ev){document.getElementById('modal-title').textContent=`Event ${ev.id} (${ev.event_type})`;document.getElementById('modal-body').textContent=JSON.stringify(ev,null,2);document.getElementById('modal').classList.remove('hidden')}async function loadRules(){let list=await j('/api/notifications');rules.textContent=JSON.stringify(list,null,2);rulesbody.innerHTML=list.map(x=>`<tr><td>${x.id}</td><td>${x.channel!==null&&x.channel!==undefined?'CH'+x.channel:'All'}</td><td><strong>${x.event_type}</strong></td><td>${x.object_type||'Any'}</td><td>${x.rule_name||'—'}</td><td>${x.allowed_actions||'Start'}</td><td><button class="switch-btn ${x.monitoring_enabled?'on':'off'}" onclick="toggleRuleMon(${x.id},${!x.monitoring_enabled})">${x.monitoring_enabled?'ON':'OFF'}</button></td><td><button class="switch-btn ${x.telegram_enabled?'on':'off'}" onclick="toggleRuleTg(${x.id},${!x.telegram_enabled})">${x.telegram_enabled?'ON':'OFF'}</button></td><td><button class=del onclick="deleteRule(${x.id})">Delete</button></td></tr>`).join('')}async function loadLogs(){logdata.textContent=(await j('/api/logs')).map(x=>`${new Date(x.timestamp*1000).toISOString()}  ${x.level.padEnd(7)} ${x.logger}\\n  ${x.message}`).join('\\\\n\\\\n')}async function loadSettings(){let cfg=await j('/api/settings');settingsdata.textContent=JSON.stringify(cfg,null,2);renderTgSwitch(cfg,'settgswitchbox');let aud=await j('/api/audit');auditbody.innerHTML=aud.map(x=>`<tr><td>${x.timestamp}</td><td>${x.source}</td><td><strong>${x.setting_type||x.setting}</strong></td><td>${x.channel!==null&&x.channel!==undefined?'CH'+x.channel:'—'}</td><td>${x.event_type||'—'}</td><td><code>${x.old_value||'—'}</code></td><td><code>${x.new_value||'—'}</code></td><td><span class="${x.result==='SUCCESS'?'ok':'bad'}">${x.result}</span></td></tr>`).join('')}async function load(tab){if(tab==='dashboard')await loadDashboard();if(tab==='nvr')nvrdata.textContent=JSON.stringify(await j('/api/nvr'),null,2);if(tab==='channels')await loadChannels();if(tab==='events')await loadEvents();if(tab==='notifications')await loadRules();if(tab==='logs')await loadLogs();if(tab==='settings')await loadSettings();if(tab==='system')sysdata.textContent=JSON.stringify(await j('/api/system'),null,2)}setInterval(()=>{let act=document.querySelector('nav button.active')?.dataset.tab;if(act==='dashboard')loadDashboard();if(act==='logs')loadLogs()},5000);const es=new EventSource('/api/events/live');es.onmessage=e=>{try{let d=JSON.parse(e.data);let act=document.querySelector('nav button.active')?.dataset.tab;if(act==='dashboard'||act==='events')load(act)}catch(err){}};</script></body></html>"""


def _mask_secret(text: str) -> str:
    return re.sub(r"(?i)(token|password|secret|key)=?\S+", r"\1=[REDACTED]", text)


class Store:
    def __init__(self, path: str = "/data/bridge.sqlite3") -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS channels(
                channel_number INTEGER PRIMARY KEY,
                raw_index INTEGER,
                camera_name TEXT NOT NULL DEFAULT '',
                camera_model TEXT DEFAULT '',
                monitoring_enabled INTEGER NOT NULL DEFAULT 1,
                snapshot_channel INTEGER,
                channel_mapping_source TEXT NOT NULL DEFAULT 'auto',
                online_status TEXT NOT NULL DEFAULT 'unknown',
                created_at TEXT,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS rules(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel INTEGER,
                event_type TEXT NOT NULL,
                object_type TEXT,
                rule_name TEXT,
                allowed_actions TEXT NOT NULL DEFAULT 'Start',
                monitoring_enabled INTEGER NOT NULL DEFAULT 1,
                telegram_enabled INTEGER NOT NULL DEFAULT 1,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS global_settings(
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS events(
                id TEXT PRIMARY KEY,
                timestamp TEXT,
                event_type TEXT,
                action TEXT,
                channel INTEGER,
                raw_index INTEGER,
                camera_name TEXT,
                object_type TEXT,
                object_id TEXT,
                rule_name TEXT,
                direction TEXT,
                event_id INTEGER,
                group_id INTEGER,
                with_snap INTEGER,
                raw_payload TEXT,
                processing_status TEXT,
                filter_reason TEXT,
                snapshot_status TEXT,
                notification_status TEXT,
                latency_metrics TEXT,
                channel_mapping_source TEXT,
                decision TEXT,
                reason TEXT
            );

            CREATE TABLE IF NOT EXISTS audit(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                source TEXT NOT NULL DEFAULT 'web',
                setting_type TEXT,
                channel INTEGER,
                event_type TEXT,
                setting TEXT,
                old_value TEXT,
                new_value TEXT,
                result TEXT NOT NULL DEFAULT 'SUCCESS'
            );
            """
        )

        # Migrations for existing databases
        event_columns = [
            ("raw_index", "INTEGER"),
            ("camera_name", "TEXT"),
            ("object_id", "TEXT"),
            ("direction", "TEXT"),
            ("event_id", "INTEGER"),
            ("group_id", "INTEGER"),
            ("with_snap", "INTEGER"),
            ("snapshot_status", "TEXT"),
            ("notification_status", "TEXT"),
            ("latency_metrics", "TEXT"),
            ("channel_mapping_source", "TEXT"),
            ("processing_status", "TEXT"),
            ("filter_reason", "TEXT"),
            ("decision", "TEXT"),
            ("reason", "TEXT"),
        ]
        for col, col_type in event_columns:
            try:
                self.db.execute(f"ALTER TABLE events ADD COLUMN {col} {col_type}")
            except sqlite3.OperationalError:
                pass

        rule_columns = [
            ("rule_name", "TEXT"),
            ("allowed_actions", "TEXT NOT NULL DEFAULT 'Start'"),
            ("monitoring_enabled", "INTEGER NOT NULL DEFAULT 1"),
            ("telegram_enabled", "INTEGER NOT NULL DEFAULT 1"),
            ("enabled", "INTEGER NOT NULL DEFAULT 1"),
            ("created_at", "TEXT"),
            ("updated_at", "TEXT"),
        ]
        for col, col_type in rule_columns:
            try:
                self.db.execute(f"ALTER TABLE rules ADD COLUMN {col} {col_type}")
            except sqlite3.OperationalError:
                pass

        audit_columns = [
            ("setting_type", "TEXT"),
            ("channel", "INTEGER"),
            ("event_type", "TEXT"),
        ]
        for col, col_type in audit_columns:
            try:
                self.db.execute(f"ALTER TABLE audit ADD COLUMN {col} {col_type}")
            except sqlite3.OperationalError:
                pass

        # Default global setting
        self.db.execute(
            "INSERT OR IGNORE INTO global_settings(key, value, updated_at) VALUES('telegram_notifications_enabled', 'true', datetime('now'))"
        )

        # If channels table is empty, auto-populate from existing events
        ch_count = self.db.execute("SELECT COUNT(*) FROM channels").fetchone()[0]
        if ch_count == 0:
            self.db.execute(
                """
                INSERT OR IGNORE INTO channels(channel_number, raw_index, camera_name, snapshot_channel, channel_mapping_source, created_at, updated_at)
                SELECT DISTINCT
                    channel,
                    channel,
                    COALESCE(camera_name, rule_name, 'Camera ' || channel),
                    channel,
                    'auto',
                    datetime('now'),
                    datetime('now')
                FROM events WHERE channel IS NOT NULL
                """
            )
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    # --- Global Settings ---
    def get_global_setting(self, key: str, default: Any = None) -> Any:
        row = self.db.execute("SELECT value FROM global_settings WHERE key=?", (key,)).fetchone()
        if row is None:
            return default
        val = row[0]
        if val.lower() in ("true", "1", "yes"):
            return True
        if val.lower() in ("false", "0", "no"):
            return False
        return val

    def set_global_setting(self, key: str, value: Any, source: str = "web") -> None:
        str_val = "true" if value is True else ("false" if value is False else str(value))
        old = self.get_global_setting(key, None)
        self.db.execute(
            "INSERT INTO global_settings(key, value, updated_at) VALUES(?,?,datetime('now')) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, str_val),
        )
        self.db.commit()
        self.add_audit(
            setting_type=f"global_{key}",
            old_value=str(old),
            new_value=str_val,
            result="SUCCESS",
            source=source,
        )

    # --- Channels ---
    def channels(self) -> list[dict[str, Any]]:
        rows = self.db.execute(
            """
            SELECT
                c.channel_number,
                c.channel_number AS channel,
                c.raw_index,
                c.camera_name,
                c.camera_model,
                c.monitoring_enabled,
                c.snapshot_channel,
                c.channel_mapping_source,
                c.online_status,
                COUNT(e.id) AS event_count,
                MAX(e.timestamp) AS last_event,
                MAX(CASE WHEN e.notification_status = 'Telegram sent' THEN e.timestamp ELSE NULL END) AS last_notification,
                GROUP_CONCAT(DISTINCT e.event_type) AS known_events
            FROM channels c
            LEFT JOIN events e ON c.channel_number = e.channel
            GROUP BY c.channel_number
            ORDER BY c.channel_number
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def get_channel(self, channel_number: int) -> dict[str, Any] | None:
        row = self.db.execute(
            "SELECT * FROM channels WHERE channel_number=?", (channel_number,)
        ).fetchone()
        return dict(row) if row else None

    def get_channel_by_raw_index(self, raw_index: int) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM channels WHERE raw_index=?", (raw_index,)).fetchone()
        return dict(row) if row else None

    def ensure_channel(
        self,
        channel_number: int,
        raw_index: int | None = None,
        camera_name: str = "",
        snapshot_channel: int | None = None,
        source: str = "auto",
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            """
            INSERT OR IGNORE INTO channels(channel_number, raw_index, camera_name, snapshot_channel, channel_mapping_source, created_at, updated_at)
            VALUES(?,?,?,?,?,?,?)
            """,
            (
                channel_number,
                raw_index,
                camera_name,
                snapshot_channel or channel_number,
                source,
                now,
                now,
            ),
        )
        self.db.commit()

    def sync_inventory_channels(self, titles: dict[str, str]) -> None:
        """Reconcile discovered NVR channel indexes with stable 1-based UI channels."""
        entries: list[tuple[int, str]] = []
        for key, value in titles.items():
            match = re.search(r"ChannelTitle\[(\d+)\]\.Name$", key)
            if match and value.strip():
                raw = int(match.group(1))
                if 0 <= raw <= 4:
                    entries.append((raw, value.strip()))
        if not entries:
            return
        self.db.execute("BEGIN")
        try:
            # Move matching rows to temporary negative keys to avoid unique collisions.
            for raw, _name in entries:
                self.db.execute(
                    "UPDATE channels SET channel_number=? WHERE raw_index=?",
                    (-(raw + 1), raw),
                )
            for raw, name in entries:
                target = raw + 1
                self.db.execute("UPDATE events SET channel=? WHERE raw_index=?", (target, raw))
                row = self.db.execute(
                    "SELECT channel_number FROM channels WHERE channel_number=?", (-(raw + 1),)
                ).fetchone()
                if row:
                    self.db.execute(
                        "UPDATE channels SET channel_number=?, camera_name=?, snapshot_channel=? WHERE channel_number=?",
                        (target, name, target, -(raw + 1)),
                    )
                else:
                    self.db.execute(
                        "INSERT OR IGNORE INTO channels(channel_number,raw_index,camera_name,snapshot_channel,channel_mapping_source,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                        (
                            target,
                            raw,
                            name,
                            target,
                            "discovered",
                            datetime.now(timezone.utc).isoformat(),
                            datetime.now(timezone.utc).isoformat(),
                        ),
                    )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def update_channel(self, channel_number: int, data: dict[str, Any]) -> dict[str, Any] | None:
        current = self.get_channel(channel_number)
        if current is None:
            return None

        allowed = {
            "monitoring_enabled",
            "camera_name",
            "camera_model",
            "snapshot_channel",
            "raw_index",
            "channel_mapping_source",
        }
        unknown = set(data) - allowed
        if unknown:
            raise ValueError(f"unsupported channel fields: {', '.join(sorted(unknown))}")

        new_mon = (
            int(bool(data["monitoring_enabled"]))
            if "monitoring_enabled" in data
            else current["monitoring_enabled"]
        )
        new_name = data.get("camera_name", current["camera_name"])
        new_model = data.get("camera_model", current["camera_model"])
        try:
            new_snap = (
                int(data["snapshot_channel"])
                if data.get("snapshot_channel") is not None
                else current["snapshot_channel"]
            )
            new_raw = (
                int(data["raw_index"])
                if data.get("raw_index") is not None
                else current["raw_index"]
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("raw_index and snapshot_channel must be integers") from exc
        if new_snap is not None and new_snap < 1:
            raise ValueError("snapshot_channel must be >= 1")
        if new_raw is not None and new_raw < 0:
            raise ValueError("raw_index must be >= 0")
        new_src = data.get("channel_mapping_source", current["channel_mapping_source"])
        if new_src not in {"auto", "manual", "discovered"}:
            raise ValueError("channel_mapping_source must be auto, manual, or discovered")
        if (
            any(k in data for k in ("raw_index", "snapshot_channel"))
            and "channel_mapping_source" not in data
        ):
            new_src = "manual"

        now = datetime.now(timezone.utc).isoformat()
        self.db.execute(
            """
            UPDATE channels
            SET monitoring_enabled=?, camera_name=?, camera_model=?, snapshot_channel=?, raw_index=?, channel_mapping_source=?, updated_at=?
            WHERE channel_number=?
            """,
            (new_mon, new_name, new_model, new_snap, new_raw, new_src, now, channel_number),
        )
        self.db.commit()

        if "monitoring_enabled" in data and bool(data["monitoring_enabled"]) != bool(
            current["monitoring_enabled"]
        ):
            self.add_audit(
                setting_type="channel_monitoring",
                channel=channel_number,
                old_value=f"monitoring={'ON' if current['monitoring_enabled'] else 'OFF'}",
                new_value=f"monitoring={'ON' if new_mon else 'OFF'}",
                result="SUCCESS",
            )
        else:
            self.add_audit(
                setting_type="channel_config",
                channel=channel_number,
                old_value=str(dict(current)),
                new_value=str(data),
                result="SUCCESS",
            )

        return self.get_channel(channel_number)

    # --- Rules ---
    def rules(self) -> list[dict[str, Any]]:
        rows = self.db.execute("SELECT * FROM rules ORDER BY id DESC").fetchall()
        return [dict(row) for row in rows]

    def create_rule(self, data: dict[str, Any]) -> dict[str, Any]:
        if not data.get("event_type"):
            raise ValueError("event_type is required")
        ch = data.get("channel")
        ev_type = str(data["event_type"])
        obj_type = data.get("object_type")
        r_name = data.get("rule_name")
        actions = str(data.get("allowed_actions", "Start"))
        mon_en = int(bool(data.get("monitoring_enabled", data.get("enabled", True))))
        tg_en = int(bool(data.get("telegram_enabled", True)))
        en = int(bool(data.get("enabled", mon_en)))
        now = datetime.now(timezone.utc).isoformat()

        cur = self.db.execute(
            """
            INSERT INTO rules(channel, event_type, object_type, rule_name, allowed_actions, monitoring_enabled, telegram_enabled, enabled, created_at, updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?)
            """,
            (ch, ev_type, obj_type, r_name, actions, mon_en, tg_en, en, now, now),
        )
        self.db.commit()
        rule_id = cur.lastrowid
        self.add_audit(
            setting_type="notification_rule",
            channel=ch,
            event_type=ev_type,
            old_value="none",
            new_value=json.dumps(data),
            result="CREATED",
        )
        return dict(self.db.execute("SELECT * FROM rules WHERE id=?", (rule_id,)).fetchone())

    def update_rule(self, rule_id: int, data: dict[str, Any]) -> dict[str, Any] | None:
        current = self.db.execute("SELECT * FROM rules WHERE id=?", (rule_id,)).fetchone()
        if current is None:
            return None
        cur_dict = dict(current)

        ch = data.get("channel", cur_dict["channel"])
        ev_type = data.get("event_type", cur_dict["event_type"])
        obj_type = data.get("object_type", cur_dict["object_type"])
        r_name = data.get("rule_name", cur_dict["rule_name"])
        actions = data.get("allowed_actions", cur_dict["allowed_actions"] or "Start")

        mon_en = (
            int(bool(data["monitoring_enabled"]))
            if "monitoring_enabled" in data
            else (
                int(bool(data["enabled"])) if "enabled" in data else cur_dict["monitoring_enabled"]
            )
        )
        tg_en = (
            int(bool(data["telegram_enabled"]))
            if "telegram_enabled" in data
            else cur_dict["telegram_enabled"]
        )
        en = mon_en
        now = datetime.now(timezone.utc).isoformat()

        self.db.execute(
            """
            UPDATE rules
            SET channel=?, event_type=?, object_type=?, rule_name=?, allowed_actions=?, monitoring_enabled=?, telegram_enabled=?, enabled=?, updated_at=?
            WHERE id=?
            """,
            (ch, ev_type, obj_type, r_name, actions, mon_en, tg_en, en, now, rule_id),
        )
        self.db.commit()
        self.add_audit(
            setting_type="notification_rule",
            channel=ch,
            event_type=ev_type,
            old_value=str(cur_dict),
            new_value=str(data),
            result="UPDATED",
        )
        return dict(self.db.execute("SELECT * FROM rules WHERE id=?", (rule_id,)).fetchone())

    def delete_rule(self, rule_id: int) -> bool:
        cur_row = self.db.execute("SELECT * FROM rules WHERE id=?", (rule_id,)).fetchone()
        if not cur_row:
            return False
        cur_dict = dict(cur_row)
        cur = self.db.execute("DELETE FROM rules WHERE id=?", (rule_id,))
        self.db.commit()
        if cur.rowcount:
            self.add_audit(
                setting_type="notification_rule",
                channel=cur_dict.get("channel"),
                event_type=cur_dict.get("event_type"),
                old_value=str(cur_dict),
                new_value="none",
                result="DELETED",
            )
        return cur.rowcount > 0

    def matching_rule(
        self,
        channel: int | None,
        event_type: str,
        object_type: str | None,
        rule_name: str | None = None,
    ) -> dict[str, Any] | None:
        rows = self.db.execute(
            """
            SELECT * FROM rules
            WHERE event_type=?
              AND (channel IS NULL OR channel=?)
              AND (object_type IS NULL OR object_type=?)
              AND (rule_name IS NULL OR rule_name=?)
            ORDER BY
              (rule_name IS NOT NULL) DESC,
              (object_type IS NOT NULL) DESC,
              (channel IS NOT NULL) DESC
            LIMIT 1
            """,
            (event_type, channel, object_type, rule_name),
        ).fetchall()
        return dict(rows[0]) if rows else None

    # --- Events ---
    def add_event(self, event: Any, decision: str | None = None, reason: str | None = None) -> None:
        proc_status = decision or getattr(event, "processing_status", "processed")
        flt_reason = (
            reason
            if reason is not None
            else getattr(event, "filter_reason", getattr(event, "reason", ""))
        )
        raw_payload_str = (
            json.dumps(event.raw_payload)
            if isinstance(getattr(event, "raw_payload", None), (dict, list))
            else str(getattr(event, "raw_payload", "{}"))
        )
        metrics_str = (
            json.dumps(event.latency_metrics)
            if getattr(event, "latency_metrics", None) is not None
            else None
        )

        self.db.execute(
            """
            INSERT OR REPLACE INTO events(
                id, timestamp, event_type, action, channel, raw_index, camera_name,
                object_type, object_id, rule_name, direction, event_id, group_id,
                with_snap, raw_payload, processing_status, filter_reason,
                snapshot_status, notification_status, latency_metrics,
                channel_mapping_source, decision, reason
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                event.id,
                event.timestamp.isoformat()
                if hasattr(event.timestamp, "isoformat")
                else str(event.timestamp),
                event.event_type,
                event.action,
                event.channel,
                getattr(event, "raw_index", None),
                getattr(event, "camera_name", None),
                getattr(event, "object_type", None),
                str(getattr(event, "object_id", ""))
                if getattr(event, "object_id", None) is not None
                else None,
                getattr(event, "rule_name", None),
                getattr(event, "direction", None),
                getattr(event, "event_id", None),
                getattr(event, "group_id", None),
                int(bool(getattr(event, "with_snap", False)))
                if getattr(event, "with_snap", None) is not None
                else None,
                raw_payload_str,
                proc_status,
                flt_reason,
                getattr(event, "snapshot_status", None),
                getattr(event, "notification_status", None),
                metrics_str,
                getattr(event, "channel_mapping_source", None),
                proc_status,
                flt_reason,
            ),
        )
        self.db.commit()

    def events(
        self,
        limit: int = 100,
        channel: int | None = None,
        event_type: str | None = None,
        object_type: str | None = None,
        decision: str | None = None,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM events WHERE 1=1"
        params: list[Any] = []
        if channel is not None:
            query += " AND channel=?"
            params.append(channel)
        if event_type:
            query += " AND event_type=?"
            params.append(event_type)
        if object_type:
            query += " AND object_type=?"
            params.append(object_type)
        if decision:
            query += " AND (processing_status=? OR decision=?)"
            params.extend([decision, decision])

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(max(1, min(limit, 500)))

        rows = self.db.execute(query, tuple(params)).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            d = dict(row)
            if d.get("raw_payload"):
                try:
                    d["raw_payload"] = json.loads(d["raw_payload"])
                except Exception:
                    pass
            if d.get("latency_metrics"):
                try:
                    d["latency_metrics"] = json.loads(d["latency_metrics"])
                except Exception:
                    pass
            result.append(d)
        return result

    def event(self, event_id: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        if d.get("raw_payload"):
            try:
                d["raw_payload"] = json.loads(d["raw_payload"])
            except Exception:
                pass
        if d.get("latency_metrics"):
            try:
                d["latency_metrics"] = json.loads(d["latency_metrics"])
            except Exception:
                pass
        return d

    # --- Audit ---
    def audit(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT * FROM audit ORDER BY id DESC LIMIT ?", (max(1, min(limit, 500)),)
        ).fetchall()
        return [dict(row) for row in rows]

    def add_audit(
        self,
        setting_type: str,
        old_value: str,
        new_value: str,
        channel: int | None = None,
        event_type: str | None = None,
        result: str = "SUCCESS",
        source: str = "web",
        setting: str | None = None,
    ) -> None:
        clean_old = _mask_secret(old_value)
        clean_new = _mask_secret(new_value)
        self.db.execute(
            """
            INSERT INTO audit(timestamp, source, setting_type, channel, event_type, setting, old_value, new_value, result)
            VALUES(datetime('now'),?,?,?,?,?,?,?,?)
            """,
            (
                source,
                setting_type,
                channel,
                event_type,
                setting or setting_type,
                clean_old,
                clean_new,
                result,
            ),
        )
        self.db.commit()


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
    app["nvr_cache"] = {
        "nvr_expires": 0.0,
        "nvr_data": {},
        "titles_expires": 0.0,
        "titles_data": {},
    }

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

    def _verify_csrf(request: web.Request) -> bool:
        return hmac.compare_digest(request.headers.get("X-CSRF-Token", ""), app["csrf_token"])

    async def index(request: web.Request) -> web.Response:
        if not _auth(request):
            return web.Response(text=LOGIN_HTML, content_type="text/html")
        return web.Response(text=ADMIN_HTML, content_type="text/html")

    async def login(request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)
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
                "snapshots_success": h.snapshots_success,
                "snapshots_failed": h.snapshots_failed,
                "telegram_sent": h.telegram_sent,
                "telegram_failed": h.telegram_failed,
                "reconnect_count": h.reconnect_count,
            }
        )

    async def metrics(_request: web.Request) -> web.Response:
        h = service.health
        return web.json_response(
            {
                "events_received": h.events_received,
                "events_filtered": h.events_filtered,
                "events_deduplicated": h.events_deduplicated,
                "processed_events": h.processed_events,
                "failed_events": h.failed_events,
                "snapshots_success": h.snapshots_success,
                "snapshots_failed": h.snapshots_failed,
                "telegram_sent": h.telegram_sent,
                "telegram_failed": h.telegram_failed,
                "reconnect_count": h.reconnect_count,
            }
        )

    async def system(_request: web.Request) -> web.Response:
        env_tg = getattr(config.telegram, "enabled", True)
        global_tg = store.get_global_setting("telegram_notifications_enabled", True)
        effective_tg = bool(env_tg and global_tg)
        return web.json_response(
            {
                "telegram_enabled": effective_tg,
                "dry_run": not effective_tg,
                "version": "0.1.0",
                "env_telegram_enabled": env_tg,
                "global_telegram_enabled": global_tg,
            }
        )

    async def nvr(_request: web.Request) -> web.Response:
        cache = app["nvr_cache"]
        now = time.monotonic()
        if now > cache["nvr_expires"] and service.health.nvr_connected:
            try:
                cache["nvr_data"] = await service.dahua.system_info()
                cache["nvr_expires"] = now + 60
            except Exception:
                cache["nvr_expires"] = now + 10

        if now > cache["titles_expires"] and service.health.nvr_connected:
            try:
                cache["titles_data"] = await service.dahua.channel_titles()
                cache["titles_expires"] = now + 60
            except Exception:
                cache["titles_expires"] = now + 10

        return web.json_response(
            {
                "host": config.dahua.host,
                "port": config.dahua.port,
                "https": config.dahua.https,
                "connected": service.health.nvr_connected,
                "channel": config.dahua.channel,
                "system_info": cache["nvr_data"],
                "channel_titles": cache["titles_data"],
            }
        )

    async def config_view(_request: web.Request) -> web.Response:
        env_tg = getattr(config.telegram, "enabled", True)
        global_tg = store.get_global_setting("telegram_notifications_enabled", True)
        effective_tg = bool(env_tg and global_tg)
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
                    "enabled": effective_tg,
                    "env_enabled": env_tg,
                    "global_enabled": global_tg,
                    "blocked_by_env": not env_tg,
                    "configured": bool(config.telegram.bot_token and config.telegram.chat_id),
                    "token": "**************" if config.telegram.bot_token else None,
                    "chat_id_configured": bool(config.telegram.chat_id),
                },
                "telegram_env_enabled": env_tg,
                "telegram_global_enabled": global_tg,
                "telegram_effective_enabled": effective_tg,
                "telegram_blocked_by_env": not env_tg,
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

    async def update_settings(request: web.Request) -> web.Response:
        if not _verify_csrf(request):
            return web.json_response({"error": "csrf token required"}, status=403)
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)

        if "telegram_notifications_enabled" in data:
            val = bool(data["telegram_notifications_enabled"])
            store.set_global_setting("telegram_notifications_enabled", val)

        return await config_view(request)

    async def events(request: web.Request) -> web.Response:
        try:
            limit = int(request.query.get("limit", "100"))
        except (TypeError, ValueError):
            return web.json_response({"error": "limit must be an integer"}, status=400)
        if limit < 1 or limit > 1000:
            return web.json_response({"error": "limit must be between 1 and 1000"}, status=400)
        event_type = request.query.get("event_type")
        channel = (
            int(request.query["channel"])
            if request.query.get("channel") is not None and request.query["channel"].isdigit()
            else None
        )
        object_type = request.query.get("object_type")
        decision = request.query.get("decision")
        result = store.events(
            limit=limit,
            channel=channel,
            event_type=event_type,
            object_type=object_type,
            decision=decision,
        )
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

    async def channels_list(_request: web.Request) -> web.Response:
        if service.health.nvr_connected:
            try:
                app["nvr_cache"]["titles_data"] = await service.dahua.channel_titles()
                app["nvr_cache"]["nvr_data"] = await service.dahua.system_info()
                store.sync_inventory_channels(app["nvr_cache"]["titles_data"])
            except Exception:
                pass
        channels = [c for c in store.channels() if 1 <= int(c["channel_number"]) <= 255]
        titles = app["nvr_cache"].get("titles_data", {})
        system = app["nvr_cache"].get("nvr_data", {})
        for channel in channels:
            raw = channel.get("raw_index")
            title = None
            if raw is not None:
                for key in (
                    f"table.ChannelTitle[{raw}].Name",
                    f"ChannelTitle[{raw}].Name",
                ):
                    title = titles.get(key)
                    if title:
                        break
            if title and (
                not channel.get("camera_name") or channel["camera_name"].startswith("Camera ")
            ):
                channel["camera_name"] = title
            if system.get("deviceType") and not channel.get("camera_model"):
                channel["camera_model"] = system["deviceType"]
            if service.health.nvr_connected:
                channel["online_status"] = "online"
        return web.json_response(channels)

    async def update_channel(request: web.Request) -> web.Response:
        if not _verify_csrf(request):
            return web.json_response({"error": "csrf token required"}, status=403)
        try:
            ch_num = int(request.match_info["id"])
            data = await request.json()
        except (ValueError, json.JSONDecodeError):
            return web.json_response({"error": "invalid channel id or payload"}, status=400)

        try:
            result = store.update_channel(ch_num, data)
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)
        return (
            web.json_response(result)
            if result
            else web.json_response({"error": "channel not found"}, status=404)
        )

    async def rules_list(_request: web.Request) -> web.Response:
        return web.json_response(store.rules())

    async def create_rule(request: web.Request) -> web.Response:
        if not _verify_csrf(request):
            return web.json_response({"error": "csrf token required"}, status=403)
        try:
            return web.json_response(store.create_rule(await request.json()), status=201)
        except (ValueError, json.JSONDecodeError) as exc:
            return web.json_response({"error": str(exc)}, status=400)

    async def update_rule(request: web.Request) -> web.Response:
        if not _verify_csrf(request):
            return web.json_response({"error": "csrf token required"}, status=403)
        try:
            rule_id = int(request.match_info["id"])
            result = store.update_rule(rule_id, await request.json())
        except (ValueError, json.JSONDecodeError):
            return web.json_response({"error": "invalid rule id or payload"}, status=400)
        return (
            web.json_response(result)
            if result
            else web.json_response({"error": "not found"}, status=404)
        )

    async def delete_rule(request: web.Request) -> web.Response:
        if not _verify_csrf(request):
            return web.json_response({"error": "csrf token required"}, status=403)
        try:
            rule_id = int(request.match_info["id"])
        except ValueError:
            return web.json_response({"error": "invalid rule id"}, status=400)
        return web.json_response({"deleted": store.delete_rule(rule_id)})

    async def audit_list(_request: web.Request) -> web.Response:
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
    app.router.add_get("/api/metrics", metrics)
    app.router.add_get("/api/system", system)
    app.router.add_get("/api/nvr", nvr)
    app.router.add_get("/api/config", config_view)
    app.router.add_get("/api/settings", config_view)
    app.router.add_patch("/api/settings", update_settings)
    app.router.add_get("/api/events", events)
    app.router.add_get("/api/events/{id}", event_detail)
    app.router.add_get("/api/events/{id}/snapshot", snapshot)

    # Channels
    app.router.add_get("/api/channels", channels_list)
    app.router.add_patch("/api/channels/{id}", update_channel)

    # Notification rules (both endpoint names for full spec & backward compatibility)
    app.router.add_get("/api/notification-rules", rules_list)
    app.router.add_post("/api/notification-rules", create_rule)
    app.router.add_patch("/api/notification-rules/{id}", update_rule)
    app.router.add_delete("/api/notification-rules/{id}", delete_rule)

    app.router.add_get("/api/notifications", rules_list)
    app.router.add_post("/api/notifications", create_rule)
    app.router.add_patch("/api/notifications/{id}", update_rule)
    app.router.add_delete("/api/notifications/{id}", delete_rule)

    app.router.add_get("/api/audit", audit_list)
    app.router.add_get("/api/logs", logs)
    app.router.add_get("/api/events/live", live_events)
    return app
