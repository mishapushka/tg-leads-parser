"""
Фабрика LLM-провайдеров.

get_provider() читает имя провайдера (из .env → LLM_PROVIDER) и возвращает
готовый экземпляр. Конкретные классы импортируются лениво — нужен только тот
пакет, чей провайдер выбран.
"""
from __future__ import annotations

from .base import LLMProvider


def get_provider(
    name: str,
    *,
    deepseek_key: str = "",
    deepseek_model: str = "deepseek-v4-flash",
    anthropic_key: str = "",
    anthropic_model: str = "claude-3-5-sonnet-latest",
) -> LLMProvider:
    """Вернуть провайдера по имени ('deepseek' | 'anthropic')."""
    name = (name or "deepseek").lower()

    if name == "deepseek":
        if not deepseek_key:
            raise RuntimeError("LLM_PROVIDER=deepseek, но не задан DEEPSEEK_API_KEY.")
        from .deepseek import DeepSeekProvider

        return DeepSeekProvider(deepseek_key, deepseek_model)

    if name == "anthropic":
        if not anthropic_key:
            raise RuntimeError("LLM_PROVIDER=anthropic, но не задан ANTHROPIC_API_KEY.")
        from .anthropic import AnthropicProvider

        return AnthropicProvider(anthropic_key, anthropic_model)

    raise RuntimeError(f"Неизвестный LLM_PROVIDER: {name!r}. Допустимо: deepseek | anthropic.")


__all__ = ["LLMProvider", "get_provider"]
