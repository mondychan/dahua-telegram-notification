import logging

from dahua_telegram_bridge.logbuffer import LogBuffer


def test_logbuffer_redacts_secrets():
    buffer = LogBuffer(2)
    buffer.setFormatter(logging.Formatter("%(message)s"))
    record = logging.LogRecord(
        "test", logging.INFO, "", 0, "token=secret password=hunter2", (), None
    )
    buffer.emit(record)
    item = buffer.recent()[0]
    assert "secret" not in item["message"] and "hunter2" not in item["message"]
