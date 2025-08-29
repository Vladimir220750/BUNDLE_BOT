# app/core/logger.py
from __future__ import annotations

import sys
import os
import logging

import structlog
from loguru import logger as loguru_logger

def setup_logger(service_name: str, level: str | None = None):
    """
    Настройка loguru + structlog. Читает LOG_LEVEL из окружения, если level не указан.
    """
    if level is None:
        level = os.getenv("LOG_LEVEL", "INFO")
    level = level.upper()

    logging.basicConfig(level=level)

    # Настроим loguru
    loguru_logger.remove()
    loguru_logger.add(
        sys.stdout,
        level=level,
        colorize=True,
        enqueue=True,
        backtrace=True,
        diagnose=True,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    )

    # structlog для структурированных логов
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(level),
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.ExceptionRenderer(),
            structlog.processors.JSONRenderer(indent=2),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
    )

    return structlog.get_logger(service=service_name)


# Экспортируем глобальный logger, чтобы импорт вида `from app.core.logger import logger` работал
logger = setup_logger("core")
