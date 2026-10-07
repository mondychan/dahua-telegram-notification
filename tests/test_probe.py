from dahua_telegram_bridge.config import load_config
from dahua_telegram_bridge.config import validate_config
from dahua_telegram_bridge.config import AppConfig, DahuaConfig, TelegramConfig
import pytest


def test_config_has_nested_dahua():
    config = load_config()
    assert config.dahua.host
    assert hasattr(config.dahua, "username")


def test_validate_requires_admin_password():
    config = AppConfig(DahuaConfig("n"), TelegramConfig("", "", enabled=False))
    with pytest.raises(ValueError, match="ADMIN_PASSWORD"):
        validate_config(config)
