"""
Сборка текста карточки лида для отправки в Telegram-группу.

Формат вынесен сюда, чтобы править его в одном месте, не трогая логику.
Целевой вид (см. ARCHITECTURE.md, раздел 5):

    🧠 НОВЫЙ {lead_label}
    {хэштеги}
    📊 {оценка · тип · цена}      ← техническая строка для тебя (опционально)

    💬 Оригинал:
    «{текст}»

    ✍️ Черновик ответа:
    {draft_reply}

    🔗 Контекст:
    👤 От кого: {имя} ({@username | без @username})
    📍 Чат: {@канал}
    🔗 Перейти: {ссылка}
    ⏰ Время: {ЧЧ:ММ}
"""
from __future__ import annotations

from dataclasses import dataclass

_SCORE_EMOJI = {"hot": "🔥", "warm": "🌤", "cold": "❄️", "trash": "⛔"}


@dataclass
class MessageContext:
    """Контекст сообщения для блока «Контекст» карточки."""

    author_name: str | None = None
    author_username: str | None = None
    channel_title: str | None = None
    channel_username: str | None = None
    link: str | None = None
    time_str: str | None = None


def _ruble(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def render_card(card, ctx: MessageContext, text: str, bl: dict, show_tech_line: bool = True) -> str:
    """Собрать готовый текст карточки лида."""
    orders = bl.get("order_types", {})
    order_title = orders.get(card.order_type, {}).get("title", card.order_type)
    emoji = _SCORE_EMOJI.get(card.score, "•")

    lines: list[str] = [f"🧠 НОВЫЙ {card.lead_label}"]

    if card.hashtags:
        lines.append(" ".join(card.hashtags))

    if show_tech_line:
        lo, hi = card.price_range_rub
        price = f"{_ruble(lo)} – {_ruble(hi)} ₽"
        lines.append(f"📊 {emoji} {card.score} {card.score_value}/100 · {order_title} · {price}")

    lines += ["", "💬 Оригинал:", f"«{text or '<без текста>'}»"]

    if card.draft_reply:
        lines += ["", "✍️ Черновик ответа:", card.draft_reply]

    # Блок контекста
    if ctx.author_username:
        who = f"{ctx.author_name or 'аноним'} (@{ctx.author_username})"
    else:
        who = f"{ctx.author_name or 'аноним'} (без @username)"

    chat = f"@{ctx.channel_username}" if ctx.channel_username else (ctx.channel_title or "—")
    link = ctx.link or "— (приватный чат, прямой ссылки нет)"

    lines += [
        "",
        "🔗 Контекст:",
        f"👤 От кого: {who}",
        f"📍 Чат: {chat}",
        f"🔗 Перейти: {link}",
        f"⏰ Время: {ctx.time_str or '—'}",
    ]

    return "\n".join(lines)
