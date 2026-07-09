"""
Базовый интерфейс LLM-провайдера.

Классификатору всё равно, кто внутри (DeepSeek, Anthropic, …) — он зовёт
provider.complete(system, user). Добавить нового провайдера = новый файл,
реализующий этот интерфейс.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Контракт провайдера: один метод генерации ответа."""

    @abstractmethod
    async def complete(self, system: str, user: str, *, json: bool = True) -> str:
        """Вернуть текстовый ответ модели.

        system — системная инструкция, user — запрос пользователя.
        json=True — попросить модель ответить валидным JSON (если провайдер
        поддерживает строгий json-режим — включить его).
        Возвращает строку (при json=True — строку с JSON внутри).
        """
        raise NotImplementedError

    async def close(self) -> None:
        """Закрыть сетевые ресурсы провайдера (по умолчанию ничего не делает)."""
        return None
