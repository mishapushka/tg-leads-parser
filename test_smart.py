"""
Тест «умного» слоя БЕЗ Telegram и БЕЗ CRM.

Берёт несколько примеров сообщений, прогоняет через LLM (провайдер из .env)
и печатает готовую карточку лида в терминал. Нужен только ключ провайдера
(DEEPSEEK_API_KEY или ANTHROPIC_API_KEY) в .env.

Запуск из папки проекта:
    python test_smart.py

Что проверяем:
  * связь с LLM (DeepSeek/Anthropic),
  * классификацию и скоринг,
  * генерацию хэштегов и ЧЕРНОВИКА ОТВЕТА,
  * сборку карточки в нужном формате.
"""
from __future__ import annotations

import asyncio

from config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    DEEPSEEK_API_KEY,
    DEEPSEEK_MODEL,
    LLM_PROVIDER,
    SHOW_TECH_LINE,
)
from core.classifier import Classifier, load_business_logic, load_company_profile
from core.llm import get_provider
from core.render import MessageContext, render_card

# Примеры сообщений (канал, текст). Можно дописывать свои.
SAMPLES = [
    (
        "@mari_vakansii",
        "Добрый вечер! Ищу специалиста для разработки AI-бота, который будет "
        "автоматически отвечать на входящие сообщения на Авито строго по скрипту "
        "и собирать контакты клиентов. Есть готовая база знаний и ТЗ. Нужен не "
        "кнопочный бот, а решение на ИИ с поиском по смыслу.",
    ),
    (
        "@webfrl",
        "Need a landing page for my SaaS, modern design, animations, must look "
        "premium (like awwwards). Budget around $1500. When can you start?",
    ),
    (
        "@frontend_ru",
        "Делаю сайты на заказ, верстка любой сложности, портфолио в личке, пишите!",
    ),
]


async def main() -> None:
    print(f"Провайдер: {LLM_PROVIDER}")
    if LLM_PROVIDER == "deepseek" and not DEEPSEEK_API_KEY:
        print("⛔ Нет DEEPSEEK_API_KEY в .env. Впиши ключ и запусти снова.")
        return
    if LLM_PROVIDER == "anthropic" and not ANTHROPIC_API_KEY:
        print("⛔ Нет ANTHROPIC_API_KEY в .env. Впиши ключ и запусти снова.")
        return

    bl = load_business_logic()
    profile = load_company_profile()
    provider = get_provider(
        LLM_PROVIDER,
        deepseek_key=DEEPSEEK_API_KEY,
        deepseek_model=DEEPSEEK_MODEL,
        anthropic_key=ANTHROPIC_API_KEY,
        anthropic_model=ANTHROPIC_MODEL,
    )
    classifier = Classifier(provider, bl, profile)

    try:
        for channel, text in SAMPLES:
            print("\n" + "=" * 64)
            card = await classifier.classify(text, channel)
            if card is None:
                print("⛔ LLM не вернул результат (см. ошибку выше).")
                continue
            ctx = MessageContext(
                author_name="Тест",
                author_username=None,
                channel_title=channel,
                channel_username=channel.lstrip("@"),
                link=f"https://t.me/{channel.lstrip('@')}/1",
                time_str="12:00",
            )
            print(render_card(card, ctx, text, bl, SHOW_TECH_LINE))
    finally:
        await provider.close()


if __name__ == "__main__":
    asyncio.run(main())
