"""
Диагностический слушатель.

Ловит ВСЕ входящие сообщения во всех чатах/каналах, где состоит аккаунт,
и печатает для каждого: название чата, его id, username и тип
(канал-вещалка / супергруппа / чат / личка) + превью текста.

Зачем: понять, из каких именно чатов реально приходят сообщения.
У каналов-вещалок (где пишут только админы) обсуждение людей идёт
в ОТДЕЛЬНОМ привязанном чате комментариев — у него свой id, который
и нужно добавить в config.CHANNELS.

Запуск: Run на этом файле. Открой нужные каналы, напиши/дождись сообщений,
посмотри, что печатается. Останов — Ctrl+C / Stop.
Файл сессии уже есть, повторный вход не нужен.
"""
from __future__ import annotations

import asyncio

from telethon import TelegramClient, events
from telethon.tl.types import Channel, Chat, User
from telethon.utils import get_display_name

from config import API_HASH, API_ID, SESSION_PATH


def _kind(chat) -> str:
    if isinstance(chat, Channel):
        return "канал-вещалка" if chat.broadcast else "супергруппа"
    if isinstance(chat, Chat):
        return "группа"
    if isinstance(chat, User):
        return "личка"
    return type(chat).__name__


async def main() -> None:
    client = TelegramClient(SESSION_PATH, API_ID, API_HASH)
    await client.start()
    me = await client.get_me()
    print(f"✅ Авторизован как {get_display_name(me)} (id={me.id})")
    print("👂 Слушаю ВСЕ входящие сообщения. Пиши в нужных каналах. Ctrl+C для выхода.\n")

    @client.on(events.NewMessage)
    async def handler(event: events.NewMessage.Event) -> None:
        chat = await event.get_chat()
        title = get_display_name(chat) or "?"
        username = getattr(chat, "username", None)
        uname = f"@{username}" if username else "—"
        text = (event.message.message or "").replace("\n", " ")
        if len(text) > 120:
            text = text[:120] + "…"
        print(
            f"[{_kind(chat):<14}] {title!r:<32} "
            f"id={event.chat_id}  username={uname}  | {text or '<без текста>'}"
        )

    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
