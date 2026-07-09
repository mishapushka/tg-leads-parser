"""
Вход в Telegram по QR-коду (без ввода кода из SMS/приложения).

Запускать отдельно ОДИН раз (Run на этом файле). Скрипт:
  1. Подключается по ключам из .env.
  2. Если уже авторизованы — сообщает об этом и выходит.
  3. Иначе генерирует QR-код, сохраняет его в login_qr.png и печатает в консоль.
     Нужно: на телефоне открыть Telegram → Настройки → Устройства →
     «Подключить устройство» (Link Desktop Device) → навести камеру на QR.
  4. После сканирования вход завершается, создаётся parser_session.session,
     и больше логиниться не нужно — можно запускать main.py.

Требует: pip install -r requirements.txt   (там добавлен qrcode[pil])
"""
from __future__ import annotations

import asyncio

import qrcode
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

from config import API_HASH, API_ID, SESSION_PATH


def _show_qr(url: str) -> None:
    """Сохранить QR в PNG и вывести в консоль ASCII-версию."""
    img = qrcode.make(url)
    img.save("login_qr.png")
    print("\n📷 QR сохранён в файл login_qr.png (открой и отсканируй телефоном).")
    print("   Либо отсканируй прямо из консоли:\n")
    qr = qrcode.QRCode()
    qr.add_data(url)
    qr.print_ascii(invert=True)
    print("\nНа телефоне: Telegram → Настройки → Устройства → Подключить устройство → наведи камеру.\n")


async def main() -> None:
    client = TelegramClient(SESSION_PATH, API_ID, API_HASH)
    await client.connect()

    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"✅ Уже авторизован как: {me.first_name} (id={me.id}). QR не нужен.")
        await client.disconnect()
        return

    qr_login = await client.qr_login()
    _show_qr(qr_login.url)

    # QR живёт ограниченное время — если истёк, пересоздаём и показываем заново.
    while True:
        try:
            await qr_login.wait(timeout=30)
            break  # успешно вошли
        except asyncio.TimeoutError:
            await qr_login.recreate()
            print("⏳ QR обновлён (старый истёк). Сканируй новый:")
            _show_qr(qr_login.url)
        except SessionPasswordNeededError:
            pwd = input("🔒 Включена двухфакторка. Введи облачный пароль: ")
            await client.sign_in(password=pwd)
            break

    me = await client.get_me()
    print(f"\n✅ Готово! Вошёл как: {me.first_name} (id={me.id}).")
    print("   Файл сессии создан — теперь просто запускай main.py.")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
