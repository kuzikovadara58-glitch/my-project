"""Настройка логирования (docs/SPEC.md, раздел 17 этапа 3).

Пишет в файл в пользовательском каталоге логов (см. journal_automation/paths.py)
и в консоль. Не print — единственный способ узнать, что происходило,
особенно в фоновом потоке планировщика.

В лог не попадают пароли, фотографии и лишние персональные данные — только
идентификаторы занятий/групп (CLAUDE.md, правило 15).
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOGGER_NAME = "journal_automation"
_configured = False


def configure_logging(log_dir: Path, level: int = logging.INFO) -> logging.Logger:
    global _configured
    logger = logging.getLogger(_LOGGER_NAME)
    if _configured:
        return logger

    logger.setLevel(level)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_dir / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    _configured = True
    return logger
