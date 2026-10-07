from dahua_telegram_bridge.config import load_config


def test_config_has_nested_dahua():
    config = load_config()
    assert config.dahua.host
    assert hasattr(config.dahua, "username")
