import logging
from typing import Any

from app.core.config import get_settings


logger = logging.getLogger("audit")


def audit_log(
    event: str,
    user_id: int | None = None,
    status: str = "SUCCESS",
    **fields: Any,
) -> None:
    if not get_settings().audit_log_enabled:
        return

    safe_fields = {
        key: value
        for key, value in fields.items()
        if value is not None and key not in {"password", "token", "access_token"}
    }
    field_text = " ".join(
        f"{key}={value}"
        for key, value in sorted(safe_fields.items())
    )
    logger.info(
        "audit event=%s status=%s user_id=%s %s",
        event,
        status,
        user_id,
        field_text,
    )
