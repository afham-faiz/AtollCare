# F-M7.8 Structured JSON logs; case_id is attached from the request path via a context variable.
from __future__ import annotations

import contextvars
import json
import logging
import sys
from datetime import UTC, datetime

case_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("case_id", default=None)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
        }
        case_id = case_id_var.get()
        if case_id:
            payload["case_id"] = case_id
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
