"""
Диагностика входа.

Запускать отдельно (Run на этом файле). Скрипт:
  1. Подключается к Telegram по ключам из .env и подтверждает, что они валидны.
  2. Если уже авторизованы — печатает, под каким аккаунтом, и выходит.
  3. Если нет — запрашивает код и ПЕЧАТАЕТ способ доставки кода:
       SentCodeTypeApp  → код пришёл в приложение Telegram (чат «Telegram»)
       SentCodeTypeSms  → код пришёл по SMS
       SentCodeTypeCall → код продиктуют звонком
       SentCodeTypeFlashCall / Missed → звонок, код = часть номера

Это нужно, чтобы точно понять, КУДА Telegram отправляет код.
Файл сессии тут НЕ создаётся (вход не завершаем) — только проверка.
"""
from __future__ import annotations

import asyncio

from telethon import TelegramClient

from config import API_HASH, API_ID, SESSION_PATH


async def main() -> None:
    client = TelegramClient(SESSION_PATH, API_ID, API_HASH)
    await client.connect()
    print("✅ Соединение установлено — api_id / api_hash приняты сервером Telegram.")

    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"✅ Уже авторизован как: {me.first_name} (id={me.id}, phone={me.phone})")
        await client.disconnect()
        return

    phone = input("Введи номер телефона (+7...): ").strip()
    try:
        sent = await client.send_code_request(phone)
    except Exception as exc:  # noqa: BLE001
        print(f"❌ Ошибка при запросе кода: {type(exc).__name__}: {exc}")
        await client.disconnect()
        return

    print("✅ Сервер принял номер и отправил код.")
    print(f"   Способ доставки кода: {type(sent.type).__name__}")
    print("   Расшифровка:")
    print("     SentCodeTypeApp  → ищи код в приложении Telegram, чат «Telegram»")
    print("     SentCodeTypeSms  → код придёт по SMS")
    print("     SentCodeTypeCall → код продиктуют звонком")
    print("     SentCodeTypeFlashCall/Missed → входящий звонок, код = часть номера")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
