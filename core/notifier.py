"""
Отправитель сообщений в Telegram-группу через бота (aiogram).

Используется ОДИН постоянный экземпляр бота на весь процесс — он создаётся
при старте парсера и закрывается при остановке. Это быстрее и безопаснее
по лимитам, чем создавать нового бота на каждое сообщение.

В дальнейшем сюда же можно добавить форматирование, кнопки, темы и т.д.
"""
from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter

logger = logging.getLogger("parserbot.notifier")

# Telegram ограничивает длину сообщения 4096 символами.
_MAX_LEN = 4000


class Notifier:
    """Обёртка над aiogram Bot для отправки текста в заданную группу."""

    def __init__(self, token: str, chat_id: int) -> None:
        self._bot = Bot(token=token)
        self._chat_id = chat_id

    async def send(self, text: str) -> None:
        """Отправить текст в группу. Ошибки логируются, но не роняют парсер."""
        if not text:
            return
        if len(text) > _MAX_LEN:
            text = text[:_MAX_LEN] + "…"
        try:
            await self._bot.send_message(chat_id=self._chat_id, text=text)
        except TelegramRetryAfter as exc:
            # Превышен лимит частоты — Telegram просит подождать.
            logger.warning("Flood-лимит, пропускаю сообщение (ждать %s c).", exc.retry_after)
        except Exception as exc:  # noqa: BLE001
            logger.error("Не удалось отправить в группу: %s: %s", type(exc).__name__, exc)

    async def close(self) -> None:
        """Корректно закрыть сессию бота при остановке."""
        await self._bot.session.close()
