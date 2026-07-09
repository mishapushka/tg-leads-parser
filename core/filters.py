"""
Слой фильтрации сообщений.

Решает, отправлять ли пойманное сообщение дальше (в группу / позже в LLM).
Правила берутся из файла filters.json рядом с проектом — его можно править
без изменения кода (шаг к будущему «конструктору»).

Логика проверки (по порядку):
  1. Длина: слишком короткие сообщения отсекаем (мусор вроде «kf», «test»).
  2. Стоп-слова: если встретилось любое — отбрасываем (напр. «ищу работу»).
  3. Ключевые слова: пропускаем дальше, только если есть хотя бы одно.
     (Если список keywords пуст — пропускаем всё.)

ВАЖНО про сопоставление: слово ищется ПО ГРАНИЦЕ СЛОВА (с его начала),
а не как любая подстрока. Поэтому:
  * «разработ» ловит «разработчик / разработка / разработать» (это суффиксы);
  * но «правки» НЕ срабатывает внутри «Справки», а «ставк» — внутри «доставка».
Регистр не важен. В keywords пиши корни слов.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from config import FILTERS_FILE

logger = logging.getLogger("parserbot.filters")

# Правила по умолчанию — на случай, если filters.json отсутствует или битый.
DEFAULT_RULES: dict = {
    "min_length": 15,
    "keywords": [],
    "stop_words": [],
}


@dataclass
class FilterResult:
    """Результат проверки одного сообщения."""

    passed: bool
    matched: list[str] = field(default_factory=list)  # какие ключевые слова совпали
    reason: str = ""  # человекочитаемая причина решения


def _compile(words: list[str]) -> list[tuple[str, re.Pattern]]:
    """Скомпилировать слова в regex-шаблоны с привязкой к началу слова."""
    patterns = []
    for w in words:
        # \b перед словом = совпадение только с начала слова (суффиксы разрешены).
        patterns.append((w, re.compile(r"\b" + re.escape(w), re.IGNORECASE | re.UNICODE)))
    return patterns


def load_rules() -> dict:
    """Прочитать правила из filters.json (с подстановкой значений по умолчанию)."""
    if FILTERS_FILE.exists():
        try:
            with open(FILTERS_FILE, encoding="utf-8") as f:
                data = json.load(f)
            rules = {**DEFAULT_RULES, **data}
            logger.info(
                "Правила фильтрации загружены: %d ключевых слов, %d стоп-слов, min_length=%s",
                len(rules.get("keywords", [])),
                len(rules.get("stop_words", [])),
                rules.get("min_length"),
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Не удалось прочитать %s (%s). Использую правила по умолчанию.",
                FILTERS_FILE,
                exc,
            )
            rules = dict(DEFAULT_RULES)
    else:
        logger.warning("Файл %s не найден — использую правила по умолчанию.", FILTERS_FILE)
        rules = dict(DEFAULT_RULES)

    # Предкомпиляция шаблонов (один раз при загрузке).
    rules["_kw_patterns"] = _compile(rules.get("keywords", []))
    rules["_sw_patterns"] = _compile(rules.get("stop_words", []))
    return rules


def check(text: str, rules: dict) -> FilterResult:
    """Проверить текст по правилам и вернуть результат."""
    clean = (text or "").strip()

    min_length = int(rules.get("min_length", 0))
    if len(clean) < min_length:
        return FilterResult(False, reason=f"слишком коротко (<{min_length})")

    for word, pattern in rules.get("_sw_patterns", []):
        if pattern.search(clean):
            return FilterResult(False, reason=f"стоп-слово: {word!r}")

    kw_patterns = rules.get("_kw_patterns", [])
    if not kw_patterns:
        return FilterResult(True, reason="ключевые слова не заданы — пропускаю всё")

    matched = [word for word, pattern in kw_patterns if pattern.search(clean)]
    if matched:
        return FilterResult(True, matched=matched, reason="совпадение по ключевым словам")

    return FilterResult(False, reason="нет совпадений по ключевым словам")
