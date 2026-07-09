"""
Точка входа парсера.

Запуск: просто нажми Run в PyCharm на этом файле
(или из терминала:  python main.py).

При первом запуске Telethon попросит ввести номер телефона и код
подтверждения прямо в консоли — это нужно один раз, дальше авторизация
хранится в файле сессии (*.session).
"""
from __future__ import annotations

import asyncio

from core.listener import run
from core.logging_config import setup_logging


def main() -> None:
    logger = setup_logging()
    logger.info("=== Запуск parser-bot ===")
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("Остановлено пользователем (Ctrl+C).")
    except Exception:  # noqa: BLE001 — хотим увидеть полный трейс в логах
        logger.exception("Парсер упал с необработанной ошибкой.")
    finally:
        logger.info("=== parser-bot завершён ===")


if __name__ == "__main__":
    main()
