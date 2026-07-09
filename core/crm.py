"""
Интеграция с CRM Bitrix24 (входящий вебхук).

На каждый годный лид (после фильтра и LLM-классификации) создаёт сделку-лид
в Bitrix24 методом crm.lead.add. Так лиды не теряются: видна история касаний,
статусы воронки и оценка ещё на входе.

Подключение — через ВХОДЯЩИЙ ВЕБХУК (см. CRM_SETUP.md):
  Bitrix24 → Разработчикам → Другое → Входящий вебхук → права crm.
  Получаешь URL вида https://ВАШ-ПОРТАЛ.bitrix24.ru/rest/1/КОД/
  и кладёшь его в .env как BITRIX_WEBHOOK_URL.

Никакого OAuth — просто POST на {webhook}crm.lead.add.json.
HTTP-клиент — aiohttp (уже стоит как зависимость aiogram).
"""
from __future__ import annotations

import logging

logger = logging.getLogger("parserbot.crm")

# Соответствие нашей категории скоринга и приоритета (для названия/сортировки).
_SCORE_LABEL = {"hot": "🔥HOT", "warm": "🌤WARM", "cold": "❄️COLD", "trash": "⛔TRASH"}


def build_lead_fields(card, channel: str, text: str, link: str | None,
                      sender: dict | None, bl: dict) -> dict:
    """Собрать поля для crm.lead.add из карточки лида.

    Ничего не требует настраивать в Bitrix заранее (только стандартные поля):
      TITLE  — заголовок лида (видно в списке воронки),
      NAME   — имя контакта из Telegram (если есть),
      COMMENTS — полная карточка лида,
      OPPORTUNITY/CURRENCY_ID — ориентир суммы сделки (середина вилки),
      SOURCE_DESCRIPTION — откуда лид (канал + ссылка на сообщение),
      STATUS_ID — NEW (новый лид).
    """
    niches = bl.get("niches", {})
    orders = bl.get("order_types", {})
    clients = bl.get("client_types", {})

    niche_title = niches.get(card.niche, {}).get("title", card.niche)
    order_title = orders.get(card.order_type, {}).get("title", card.order_type)
    client_title = clients.get(card.client_type, {}).get("title", card.client_type)
    label = _SCORE_LABEL.get(card.score, card.score)

    lo, hi = card.price_range_rub
    opportunity = (lo + hi) // 2  # середина вилки как ориентир суммы сделки

    title = f"{label} {order_title} — {card.summary or niche_title}"

    comment_lines = [
        f"Оценка: {card.score} ({card.score_value}/100)",
        f"Ниша: {niche_title}",
        f"Тип клиента: {client_title}",
        f"Тип заказа: {order_title}",
        f"Вилка: {lo:,} – {hi:,} ₽".replace(",", " "),
    ]
    if card.budget_mentioned:
        comment_lines.append(f"Заявленный бюджет: {card.budget_mentioned}")
    if card.deadline_mentioned:
        comment_lines.append(f"Срок: {card.deadline_mentioned}")
    if getattr(card, "hashtags", None):
        comment_lines.append("Теги: " + " ".join(card.hashtags))
    if card.reasons:
        comment_lines.append("Причины: " + ", ".join(card.reasons))
    comment_lines += ["", f"Канал: {channel}"]
    if link:
        comment_lines.append(f"Сообщение: {link}")
    comment_lines += ["", "Текст:", text or "<без текста>"]
    if getattr(card, "draft_reply", ""):
        comment_lines += ["", "Черновик ответа:", card.draft_reply]

    fields: dict = {
        "TITLE": title[:250],
        "COMMENTS": "\n".join(comment_lines),
        "OPPORTUNITY": opportunity,
        "CURRENCY_ID": "RUB",
        "STATUS_ID": "NEW",
        "SOURCE_ID": "OTHER",
        "SOURCE_DESCRIPTION": f"Telegram-парсер · {channel}" + (f" · {link}" if link else ""),
    }

    if sender:
        if sender.get("name"):
            fields["NAME"] = sender["name"]
        if sender.get("username"):
            # Кладём ссылку на профиль в IM-поле, чтобы из карточки можно было написать.
            fields["IM"] = [{"VALUE_TYPE": "OTHER", "VALUE": f"https://t.me/{sender['username']}"}]
            fields["SOURCE_DESCRIPTION"] += f" · @{sender['username']}"

    return fields


class CRM:
    """Обёртка над входящим вебхуком Bitrix24. Один экземпляр на процесс."""

    def __init__(self, webhook_url: str, bl: dict) -> None:
        # Гарантируем завершающий слэш.
        self._base = webhook_url if webhook_url.endswith("/") else webhook_url + "/"
        self._bl = bl
        self._session = None  # ленивая инициализация aiohttp-сессии

    async def _ensure_session(self):
        if self._session is None:
            import aiohttp

            self._session = aiohttp.ClientSession()
        return self._session

    async def push_lead(self, card, channel: str, text: str, link: str | None,
                        sender: dict | None = None) -> int | None:
        """Создать лид в Bitrix24. Возвращает ID лида или None при ошибке."""
        fields = build_lead_fields(card, channel, text, link, sender, self._bl)
        url = self._base + "crm.lead.add.json"
        payload = {"fields": fields, "params": {"REGISTER_SONET_EVENT": "Y"}}
        try:
            session = await self._ensure_session()
            async with session.post(url, json=payload, timeout=20) as resp:
                data = await resp.json(content_type=None)
            if "result" in data:
                lead_id = data["result"]
                logger.info("Лид создан в Bitrix24: ID=%s (%s)", lead_id, card.score)
                return int(lead_id)
            logger.error("Bitrix24 вернул ошибку: %s", data.get("error_description") or data)
            return None
        except Exception as exc:  # noqa: BLE001 — не роняем парсер из-за CRM
            logger.error("Не удалось создать лид в Bitrix24: %s: %s", type(exc).__name__, exc)
            return None

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
