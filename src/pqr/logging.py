"""JSON logging, never logging request headers or secret configuration."""

import logging
import sys

import structlog


def configure_logging() -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stderr, level=logging.INFO)
    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
    )
