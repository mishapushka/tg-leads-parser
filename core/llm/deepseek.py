"""
Провайдер DeepSeek.

API DeepSeek совместим с OpenAI, поэтому используем пакет `openai` с другим
base_url. Модель по умолчанию — deepseek-v4-flash (быстро/дёшево, для объёма);
для более качественных ответов можно deepseek-v4-pro.

Ключ: DEEPSEEK_API_KEY. base_url: https://api.deepseek.com
"""
from __future__ import annotations

import logging

from .base import LLMProvider

logger = logging.getLogger("parserbot.llm.deepseek")

_BASE_URL = "https://api.deepseek.com"


class DeepSeekProvider(LLMProvider):
    def __init__(self, api_key: str, model: str) -> None:
        # Импорт здесь, чтобы отсутствие пакета не роняло проект, когда выбран др. провайдер.
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key, base_url=_BASE_URL)
        self._model = model

    async def complete(self, system: str, user: str, *, json: bool = True) -> str:
        kwargs: dict = {}
        if json:
            # DeepSeek поддерживает строгий json-режим, как OpenAI.
            kwargs["response_format"] = {"type": "json_object"}
        resp = await self._client.chat.completions.create(
            model=self._model,
            temperature=0,
            max_tokens=1200,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            **kwargs,
        )
        return resp.choices[0].message.content or ""

    async def close(self) -> None:
        await self._client.close()
