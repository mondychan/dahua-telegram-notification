from __future__ import annotations

import logging
import re
from collections import deque
from typing import Any


class LogBuffer(logging.Handler):
    def __init__(self, max_items: int = 500) -> None:
        super().__init__()
        self.items: deque[dict[str, Any]] = deque(maxlen=max_items)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
            message = re.sub(r"(?i)(password|token|authorization)=?\S+", r"\1=[REDACTED]", message)
            self.items.append(
                {
                    "timestamp": record.created,
                    "level": record.levelname,
                    "logger": record.name,
                    "message": message,
                }
            )
        except Exception:
            self.handleError(record)

    def recent(self, limit: int = 100) -> list[dict[str, Any]]:
        return list(self.items)[-max(1, min(limit, len(self.items))) :]
