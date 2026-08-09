from __future__ import annotations

import json
import logging
from datetime import datetime, timezone


class JSONLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)


def configure_logging(log_level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JSONLogFormatter())
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)
