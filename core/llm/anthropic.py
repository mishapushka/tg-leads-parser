"""
Провайдер Anthropic (Claude).

У Anthropic нет отдельного «json-режима», поэтому строгий JSON просим в промпте,
а на стороне классификатора ответ парсится устойчиво (срезаем ```-обёртки и
берём содержимое {...}).

Ключ: ANTHROPIC_API_KEY. Модель: из ANTHROPIC_MODEL.
"""
from __future__ import annotations

import logging

from .base import LLMProvider

logger = logging.getLogger("parserbot.llm.anthropic")


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model: str) -> None:
        from anthropic import AsyncAnthropic

        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model

    async def complete(self, system: str, user: str, *, json: bool = True) -> str:
        # json-флаг тут не используется (нет строгого режима) — формат задаём в промпте.
        resp = await self._client.messages.create(
            model=self._model,
            max_tokens=1200,
            temperature=0,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in resp.content if block.type == "text")

    async def close(self) -> None:
        # У AsyncAnthropic явного close не требуется; оставляем для единообразия.
        return None
