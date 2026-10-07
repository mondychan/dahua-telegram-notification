from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


def _expand(value: Any) -> Any:
    if isinstance(value, str):
        return re.sub(r"\$\{([^}]+)\}", lambda m: os.getenv(m.group(1), ""), value)
    if isinstance(value, dict):
        return {k: _expand(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand(v) for v in value]
    return value


def _load_dotenv() -> None:
    """Load a local .env without overriding explicitly exported variables."""
    env_path = Path.cwd() / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


@dataclass(slots=True)
class DahuaConfig:
    host: str
    port: int = 80
    username: str = "admin"
    password: str = ""
    channel: int = 1
    https: bool = False
    stream: str = "event"
    timeout_seconds: float = 10.0

    @property
    def base_url(self) -> str:
        return f"{'https' if self.https else 'http'}://{self.host}:{self.port}"


@dataclass(slots=True)
class TelegramConfig:
    bot_token: str
    chat_id: str
    timeout_seconds: float = 10.0
    enabled: bool = True
    max_retries: int = 3
    backoff_seconds: float = 1.0


@dataclass(slots=True)
class AppConfig:
    dahua: DahuaConfig
    telegram: TelegramConfig
    enabled_events: set[str] = field(default_factory=set)
    snapshot_enabled: bool = True
    snapshot_timeout_ms: int = 1000
    dedup_enabled: bool = True
    dedup_ttl_seconds: float = 2.0
    send_stop: bool = False
    camera_name: str = "Dahua camera"
    event_names: dict[str, str] = field(default_factory=dict)
    log_level: str = "INFO"
    health_host: str = "0.0.0.0"
    health_port: int = 8080
    snapshot_mode: str = "auto"


def load_config(path: str | None = None) -> AppConfig:
    _load_dotenv()
    raw: dict[str, Any] = {}
    if path and Path(path).exists():
        raw = _expand(yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {})
    d = raw.get("dahua", {})
    t = raw.get("telegram", {})
    e = raw.get("events", {})
    s = raw.get("snapshot", {})
    dedup = raw.get("dedup", {})
    logging = raw.get("logging", {})
    return AppConfig(
        dahua=DahuaConfig(
            host=d.get("host", os.getenv("DAHUA_HOST", "127.0.0.1")),
            port=int(d.get("port", os.getenv("DAHUA_PORT", 80))),
            username=d.get("username", os.getenv("DAHUA_USERNAME", "admin")),
            password=d.get("password", os.getenv("DAHUA_PASSWORD", "")),
            channel=int(d.get("channel", os.getenv("DAHUA_CHANNEL", 1))),
            https=bool(d.get("https", False)),
            stream=d.get("stream", os.getenv("DAHUA_STREAM", "event")),
            timeout_seconds=float(d.get("timeout_seconds", 10)),
        ),
        telegram=TelegramConfig(
            bot_token=t.get("bot_token", os.getenv("TELEGRAM_BOT_TOKEN", "")),
            chat_id=str(t.get("chat_id", os.getenv("TELEGRAM_CHAT_ID", ""))),
            timeout_seconds=float(t.get("timeout_seconds", 10)),
            enabled=os.getenv("TELEGRAM_ENABLED", "true").lower() == "true",
            max_retries=int(t.get("max_retries", 3)),
            backoff_seconds=float(t.get("backoff_seconds", 1)),
        ),
        enabled_events=set(e.get("enabled", ["CrossLineDetection", "Human", "SMD"])),
        snapshot_enabled=bool(s.get("enabled", True)),
        snapshot_timeout_ms=int(s.get("timeout_ms", 1000)),
        dedup_enabled=bool(dedup.get("enabled", True)),
        dedup_ttl_seconds=float(dedup.get("ttl_seconds", 2)),
        send_stop=bool(e.get("send_stop", False)),
        camera_name=raw.get("camera_name", "Dahua camera"),
        event_names=raw.get("names", {}),
        log_level=logging.get("level", "INFO"),
        health_host=raw.get("health", {}).get("host", "0.0.0.0"),
        health_port=int(raw.get("health", {}).get("port", 8080)),
        snapshot_mode=raw.get("snapshot_mode", os.getenv("SNAPSHOT_MODE", "auto")),
    )


def validate_config(config: AppConfig) -> None:
    if not config.dahua.host or config.dahua.host == "127.0.0.1":
        raise ValueError("DAHUA_HOST is required")
    if config.telegram.enabled and (not config.telegram.bot_token or not config.telegram.chat_id):
        raise ValueError(
            "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required when Telegram is enabled"
        )
