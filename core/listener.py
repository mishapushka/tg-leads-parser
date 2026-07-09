"""
Листенер Telegram-каналов на Telethon.

Подключается от лица пользователя (по API_ID / API_HASH), подписывается
на события новых сообщений в указанных каналах и на каждое сообщение:
  1. пишет строку в лог,
  2. сохраняет нормализованную запись в data/messages.jsonl (АРХИВ — всё подряд),
  3. прогоняет через слой фильтрации (core.filters),
  4. если включён LLM — классифицирует через Anthropic (core.classifier)
     и шлёт в группу красивую карточку лида (отсекая по минимальной категории);
     если LLM выключен — шлёт сырой текст, как раньше.

Порядок слоёв в handle_message:
    приём → лог → архив → ФИЛЬТР → LLM-классификация → отправка.
"""
from __future__ import annotations

import logging

from telethon import TelegramClient, events
from telethon.utils import get_display_name

from config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    API_HASH,
    API_ID,
    BITRIX_WEBHOOK_URL,
    BOT_TOKEN,
    CHANNELS,
    CRM_ENABLED,
    CRM_MIN_SCORE,
    DEEPSEEK_API_KEY,
    DEEPSEEK_MODEL,
    FILTER_ENABLED,
    FORWARD_TO_GROUP,
    LLM_ENABLED,
    LLM_MIN_SCORE,
    LLM_PROVIDER,
    OUTPUT_CHAT_ID,
    SESSION_PATH,
    SHOW_TECH_LINE,
)
from core.classifier import Classifier, load_business_logic, load_company_profile
from core.crm import CRM
from core.filters import check, load_rules
from core.llm import get_provider
from core.notifier import Notifier
from core.render import MessageContext, render_card
from core.storage import build_record, save_message

logger = logging.getLogger("parserbot.listener")

# Ранг категорий для отсечения по минимальному порогу (выше = горячее).
_SCORE_RANK = {"trash": 0, "cold": 1, "warm": 2, "hot": 3}


def _local_hhmm(dt) -> str:
    """Время сообщения в виде ЧЧ:ММ по локальному часовому поясу машины."""
    try:
        return dt.astimezone().strftime("%H:%M")
    except Exception:  # noqa: BLE001
        return "—"


def create_client() -> TelegramClient:
    """Создать (но ещё не запускать) Telethon-клиент."""
    return TelegramClient(SESSION_PATH, API_ID, API_HASH)


async def _resolve_channels(client: TelegramClient) -> list:
    """Превратить @username в сущности Telegram и проверить доступ."""
    entities = []
    for channel in CHANNELS:
        try:
            entity = await client.get_entity(channel)
            entities.append(entity)
            logger.info("Подписан на канал: %s (%s)", channel, get_display_name(entity))
        except Exception as exc:  # noqa: BLE001 — логируем любую проблему с каналом
            logger.error("Не удалось получить канал %s: %s", channel, exc)
    return entities


def _format_for_group(
    channel_name: str, text: str, link: str | None, matched: list[str]
) -> str:
    """Собрать текст для отправки в группу (режим без LLM — как раньше)."""
    parts = [f"📡 {channel_name}"]
    if matched:
        parts.append(f"🎯 совпало: {', '.join(matched)}")
    parts += ["", text or "<без текста>"]
    if link:
        parts += ["", f"🔗 {link}"]
    return "\n".join(parts)


def _build_link(chat, message_id: int) -> str | None:
    """Ссылка на сообщение, если у чата есть публичный username."""
    username = getattr(chat, "username", None)
    if username:
        return f"https://t.me/{username}/{message_id}"
    return None


async def _sender_info(event: events.NewMessage.Event) -> dict | None:
    """Достать имя/username автора сообщения для карточки контакта в CRM."""
    try:
        sender = await event.get_sender()
    except Exception:  # noqa: BLE001
        return None
    if sender is None:
        return None
    name = get_display_name(sender) or None
    username = getattr(sender, "username", None)
    return {"name": name, "username": username}


def register_handlers(
    client: TelegramClient,
    entities: list,
    notifier: Notifier | None,
    rules: dict | None,
    classifier: Classifier | None,
    business_logic: dict | None,
    crm: CRM | None,
) -> None:
    """Навесить обработчик новых сообщений на список каналов."""

    min_rank = _SCORE_RANK.get(LLM_MIN_SCORE, 2)      # порог для отправки в группу
    crm_min_rank = _SCORE_RANK.get(CRM_MIN_SCORE, 2)  # порог для попадания в CRM

    @client.on(events.NewMessage(chats=entities))
    async def handle_message(event: events.NewMessage.Event) -> None:
        message = event.message
        chat = await event.get_chat()
        channel_name = get_display_name(chat) or str(event.chat_id)
        text = message.message or ""

        # 1) Лог
        preview = text.replace("\n", " ")
        if len(preview) > 200:
            preview = preview[:200] + "…"
        logger.info("[%s] #%s: %s", channel_name, message.id, preview or "<без текста>")

        # 2) Архив: сохраняем ВСЁ, независимо от фильтра
        record = build_record(
            channel=channel_name,
            channel_id=event.chat_id,
            message_id=message.id,
            sender_id=message.sender_id,
            text=text,
            raw_date=message.date,
        )
        save_message(record)

        # 3) Фильтрация (грубый отсев не-заказов)
        matched: list[str] = []
        if rules is not None:
            result = check(text, rules)
            matched = result.matched
            if not result.passed:
                logger.debug("  ⨯ отфильтровано: %s", result.reason)
                return  # дальше не идём — в группу не шлём

        # Без получателей (ни группы, ни CRM) — дальше идти незачем.
        if notifier is None and crm is None:
            return

        link = _build_link(chat, message.id)

        # 4) LLM-анализ (если включён и доступен): классификация + черновик ответа
        if classifier is not None and business_logic is not None:
            card = await classifier.classify(text, channel_name)
            if card is None:
                # LLM не ответил — мягкий откат: шлём сырой текст в группу, лид не теряем.
                logger.warning("  LLM не дал результат — шлю сырой текст.")
                if notifier is not None:
                    await notifier.send(_format_for_group(channel_name, text, link, matched))
                return

            rank = _SCORE_RANK.get(card.score, 0)
            if rank < min(min_rank, crm_min_rank):
                logger.debug("  ⨯ ниже порогов (%s): %s", card.score, card.summary)
                return

            # Автор сообщения — для блока «Контекст» карточки и контакта в CRM.
            sender = await _sender_info(event)

            # 4a) В группу — красивая карточка с черновиком ответа.
            if notifier is not None and rank >= min_rank:
                ctx = MessageContext(
                    author_name=sender.get("name") if sender else None,
                    author_username=sender.get("username") if sender else None,
                    channel_title=channel_name,
                    channel_username=getattr(chat, "username", None),
                    link=link,
                    time_str=_local_hhmm(message.date),
                )
                await notifier.send(render_card(card, ctx, text, business_logic, SHOW_TECH_LINE))
                logger.info("  → группа: лид %s (%s/100): %s", card.score, card.score_value, card.summary)

            # 4b) В CRM — если проходит свой порог.
            if crm is not None and rank >= crm_min_rank:
                await crm.push_lead(card, channel_name, text, link, sender)
            return

        # 5) Без LLM — пересылка сырого текста (как раньше); в CRM не шлём (нет карточки).
        if notifier is not None:
            await notifier.send(_format_for_group(channel_name, text, link, matched))
            logger.info("  → отправлено в группу%s", f" (🎯 {', '.join(matched)})" if matched else "")


async def run() -> None:
    """Точка входа корутины: подключиться и слушать до остановки."""
    client = create_client()
    # start() при первом запуске спросит номер телефона и код из Telegram
    # прямо в консоли (окно Run в PyCharm). Если уже есть .session — войдёт молча.
    await client.start()

    me = await client.get_me()
    logger.info("Авторизован как: %s (id=%s)", get_display_name(me), me.id)

    # Готовим отправителя в группу (если включено и заданы токен + chat_id).
    notifier: Notifier | None = None
    if FORWARD_TO_GROUP:
        if BOT_TOKEN and OUTPUT_CHAT_ID:
            notifier = Notifier(BOT_TOKEN, OUTPUT_CHAT_ID)
            logger.info("Пересылка в группу включена (chat_id=%s).", OUTPUT_CHAT_ID)
        else:
            logger.warning(
                "FORWARD_TO_GROUP=true, но не заданы TELEGRAM_BOT_TOKEN/OUTPUT_CHAT_ID "
                "в .env — пересылка отключена."
            )

    # Загружаем правила фильтрации (None = фильтр выключен, шлём всё).
    rules: dict | None = None
    if FILTER_ENABLED:
        rules = load_rules()
    else:
        logger.info("Фильтрация ВЫКЛЮЧЕНА (FILTER_ENABLED=false) — пересылаю всё подряд.")

    # Поднимаем LLM-слой (None = выключен). Провайдер (deepseek/anthropic) — из .env.
    classifier: Classifier | None = None
    business_logic: dict | None = None
    provider = None
    if LLM_ENABLED:
        try:
            provider = get_provider(
                LLM_PROVIDER,
                deepseek_key=DEEPSEEK_API_KEY,
                deepseek_model=DEEPSEEK_MODEL,
                anthropic_key=ANTHROPIC_API_KEY,
                anthropic_model=ANTHROPIC_MODEL,
            )
            business_logic = load_business_logic()
            profile = load_company_profile()
            classifier = Classifier(provider, business_logic, profile)
            logger.info("LLM-слой включён (провайдер=%s, порог=%s).", LLM_PROVIDER, LLM_MIN_SCORE)
        except Exception as exc:  # noqa: BLE001
            logger.error("Не удалось поднять LLM-слой (%s) — работаю без него.", exc)
            classifier, business_logic, provider = None, None, None

    # Поднимаем CRM-интеграцию (None = выключена). Нужна карточка лида от LLM.
    crm: CRM | None = None
    if CRM_ENABLED:
        if not BITRIX_WEBHOOK_URL:
            logger.warning("CRM_ENABLED=true, но не задан BITRIX_WEBHOOK_URL — работаю без CRM.")
        elif classifier is None or business_logic is None:
            logger.warning("CRM включена, но LLM-слой выключен — без карточки лида в CRM не пишем.")
        else:
            crm = CRM(BITRIX_WEBHOOK_URL, business_logic)
            logger.info("CRM Bitrix24 включена (порог=%s).", CRM_MIN_SCORE)

    entities = await _resolve_channels(client)
    if not entities:
        logger.error("Нет ни одного доступного канала. Останавливаюсь.")
        if notifier is not None:
            await notifier.close()
        if crm is not None:
            await crm.close()
        if provider is not None:
            await provider.close()
        return

    register_handlers(client, entities, notifier, rules, classifier, business_logic, crm)
    logger.info("Слушаю %d каналов. Нажми Ctrl+C для остановки.", len(entities))

    try:
        await client.run_until_disconnected()
    finally:
        if notifier is not None:
            await notifier.close()
        if crm is not None:
            await crm.close()
        if provider is not None:
            await provider.close()
