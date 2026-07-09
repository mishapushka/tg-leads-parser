"""
Хранилище сообщений.

Пока что — простая запись в JSON Lines файл (data/messages.jsonl).
Каждая строка = один JSON-объект с нормализованным сообщением.

Формат намеренно «плоский» и стабильный, чтобы дальше его было удобно
читать на следующих этапах (фильтрация на Python → LLM → ответы).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from config import MESSAGES_FILE


def build_record(
    *,
    channel: str,
    channel_id: int | None,
    message_id: int | None,
    sender_id: int | None,
    text: str,
    raw_date: datetime | None,
) -> dict[str, Any]:
    """Собрать нормализованную запись о сообщении."""
    return {
        # Когда мы поймали сообщение (UTC, ISO-8601).
        "captured_at": datetime.now(timezone.utc).isoformat(),
        # Время самого сообщения по данным Telegram.
        "message_date": raw_date.isoformat() if raw_date else None,
        "channel": channel,
        "channel_id": channel_id,
        "message_id": message_id,
        "sender_id": sender_id,
        "text": text,
    }


def save_message(record: dict[str, Any]) -> None:
    """Дописать одну запись в JSONL-файл (потокобезопасно для одного процесса)."""
    line = json.dumps(record, ensure_ascii=False)
    with open(MESSAGES_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")
