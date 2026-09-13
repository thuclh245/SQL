import logging
import sys

import structlog


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
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(log_level)),
        cache_logger_on_first_use=True,
    )
