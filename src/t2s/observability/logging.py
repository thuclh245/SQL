import logging
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog

from t2s.security.sanitization import sanitize_data


def _scrub_secrets_processor(
    logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Structlog processor that redacts credentials and tokens from log events."""
    sanitized: MutableMapping[str, Any] = sanitize_data(event_dict)
    return sanitized


def configure_structured_logging(log_level: str) -> None:
    logging.basicConfig(
        format="%(message)s",
        level=log_level,
        stream=sys.stdout,
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _scrub_secrets_processor,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(log_level)),
        cache_logger_on_first_use=True,
    )
