"""
Конфигурация парсера.

Здесь хранятся:
  * пути к каталогам данных/логов,
  * чтение секретов из .env,
  * список каналов, которые слушаем.

В дальнейшем CHANNELS можно будет вынести в БД/JSON и редактировать
из конструктора — пока это статический список для фундамента.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# ── Базовые пути ──────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"

# Файл, в который пишем все входящие сообщения в формате JSON Lines
# (по одному JSON-объекту на строку — удобно дописывать и читать построчно).
MESSAGES_FILE = DATA_DIR / "messages.jsonl"

# Гарантируем, что каталоги существуют.
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# ── Секреты из .env ───────────────────────────────────────────
load_dotenv(BASE_DIR / ".env")


def _require(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Не задана переменная окружения {name}. "
            f"Проверь файл .env (см. .env.example)."
        )
    return value


API_ID: int = int(_require("TELEGRAM_API_ID"))
API_HASH: str = _require("TELEGRAM_API_HASH")
SESSION_NAME: str = os.getenv("TELEGRAM_SESSION_NAME", "parser_session")
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

# Путь к файлу сессии Telethon (хранит авторизацию, чтобы не логиниться каждый раз).
SESSION_PATH = str(BASE_DIR / SESSION_NAME)

# ── Бот-отправитель (вывод результатов в Telegram-группу) ─────
# Токен бота из @BotFather и id группы-получателя.
# Бот ОБЯЗАТЕЛЬНО должен быть добавлен в эту группу (и желательно админом).
BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
OUTPUT_CHAT_ID: int | None = int(os.getenv("OUTPUT_CHAT_ID", "0")) or None

# Пересылать ли пойманные сообщения в группу.
# Пока нет слоя фильтрации/LLM — при True шлём всё подряд (для проверки связки).
# Позже здесь будет включаться отправка только отфильтрованных сообщений.
FORWARD_TO_GROUP: bool = os.getenv("FORWARD_TO_GROUP", "true").lower() in (
    "1",
    "true",
    "yes",
    "on",
)

# ── Фильтрация ───────────────────────────────────────────────
# Файл с правилами (ключевые слова, стоп-слова, мин. длина) — редактируется вручную.
FILTERS_FILE = BASE_DIR / "filters.json"

# Включена ли фильтрация. Если False — в группу уходит всё подряд (как раньше).
FILTER_ENABLED: bool = os.getenv("FILTER_ENABLED", "true").lower() in (
    "1",
    "true",
    "yes",
    "on",
)

# ── LLM-слой: квалификация + черновик ответа ─────────────────
# Справочники (правятся без кода).
BUSINESS_LOGIC_FILE = BASE_DIR / "business_logic.json"     # что за лид и сколько стоит
COMPANY_PROFILE_FILE = BASE_DIR / "company_profile.json"   # как студия о себе говорит

# Какой провайдер использовать: deepseek | anthropic
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "deepseek").lower()

# DeepSeek (по умолчанию). Ключ: https://platform.deepseek.com/
DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")

# Anthropic (если LLM_PROVIDER=anthropic). Ключ: https://console.anthropic.com/
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")

# Включён ли LLM-слой. По умолчанию ВКЛЮЧЁН (умный режим).
# Если нет ключа провайдера — парсер не падает, а работает без LLM (см. логи).
LLM_ENABLED: bool = os.getenv("LLM_ENABLED", "true").lower() in (
    "1",
    "true",
    "yes",
    "on",
)

# Показывать ли техническую строку (оценка/тип/цена) в карточке — для тебя.
SHOW_TECH_LINE: bool = os.getenv("SHOW_TECH_LINE", "true").lower() in (
    "1",
    "true",
    "yes",
    "on",
)

# Минимальная категория лида для отправки в группу. Всё, что НИЖЕ, — не шлём.
# Порядок: hot > warm > cold > trash. По умолчанию шлём warm и выше.
LLM_MIN_SCORE: str = os.getenv("LLM_MIN_SCORE", "warm").lower()

# ── CRM: Bitrix24 (входящий вебхук) ──────────────────────────
# URL входящего вебхука вида https://ВАШ-ПОРТАЛ.bitrix24.ru/rest/1/КОД/
# (как создать — см. CRM_SETUP.md). Требует LLM_ENABLED=true (нужна карточка лида).
BITRIX_WEBHOOK_URL: str = os.getenv("BITRIX_WEBHOOK_URL", "")

# Включена ли отправка лидов в CRM. По умолчанию ВКЛЮЧЕНА.
# Если нет BITRIX_WEBHOOK_URL — парсер не падает, а работает без CRM (см. логи).
CRM_ENABLED: bool = os.getenv("CRM_ENABLED", "true").lower() in (
    "1",
    "true",
    "yes",
    "on",
)

# Минимальная категория лида для попадания в CRM (hot/warm/cold/trash).
# По умолчанию заводим в CRM только warm и выше — чтобы база не засорялась.
CRM_MIN_SCORE: str = os.getenv("CRM_MIN_SCORE", "warm").lower()

# ── Каналы, которые слушаем ──────────────────────────────────
# Ссылки в формате https://t.me/...  (Telethon их понимает наравне с @username и id).
# ВАЖНО: аккаунт должен СОСТОЯТЬ в каждом чате/канале — иначе он не читается.
# Каналы, которые не удалось открыть, парсер пропустит с ошибкой в логе и продолжит.
import json
from pathlib import Path

_channels_path = Path(__file__).parent / "channels.json"
if not _channels_path.exists():
    _channels_path = Path(__file__).parent / "channels.example.json"

CHANNELS = json.loads(_channels_path.read_text(encoding="utf-8"))
