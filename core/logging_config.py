"""
Настройка логирования.

Логи пишутся одновременно:
  * в консоль (видно в окне Run PyCharm),
  * в файл logs/parser.log (с ротацией, чтобы не разрастался бесконечно).
"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from config import LOG_LEVEL, LOGS_DIR

_LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging() -> logging.Logger:
    """Настроить корневой логгер и вернуть логгер парсера."""
    root = logging.getLogger()
    root.setLevel(LOG_LEVEL)

    # Чтобы при повторном вызове не плодить хендлеры.
    if root.handlers:
        return logging.getLogger("parserbot")

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # Консоль
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    # Файл с ротацией: 5 файлов по 5 МБ
    file_handler = RotatingFileHandler(
        LOGS_DIR / "parser.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    # Telethon довольно болтлив на DEBUG — приглушим его до WARNING.
    logging.getLogger("telethon").setLevel(logging.WARNING)

    return logging.getLogger("parserbot")
