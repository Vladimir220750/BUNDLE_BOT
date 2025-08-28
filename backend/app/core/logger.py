import sys
import structlog
from loguru import logger as loguru_logger
from ..core.config import settings

def setup_logger(service_name: str, level: str = settings.log_level):
    """
    Configures a non-blocking async-friendly logger using structlog + loguru.
    """

    import logging
    logging.basicConfig(level=level.upper())

    loguru_logger.remove()
    loguru_logger.add(
        sys.stdout,
        level=level.upper(),
        colorize=True,
        enqueue=True,
        backtrace=True,
        diagnose=True,
        format="<green>{time:HH:mm:ss}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
               "<level>{message}</level>",
    )

    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(level),
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.ExceptionRenderer(),
            structlog.processors.JSONRenderer(indent=2)
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
    )

    return structlog.get_logger(service=service_name)

logger = setup_logger("bundle_bot")