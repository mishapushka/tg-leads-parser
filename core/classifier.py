"""
LLM-слой: квалификация лида + черновик продающего ответа.

Стоит ПОСЛЕ core.filters. На каждое прошедшее грубый фильтр сообщение делает
ОДИН вызов LLM (через переключаемый провайдер core.llm) и получает:
  * классификацию (ниша, тип клиента, тип заказа, платформа, цена),
  * сигналы для скоринга,
  * хэштеги, заголовок лида (lead_label),
  * ЧЕРНОВИК ОТВЕТА от имени студии (на основе company_profile.json).

Разделение ответственности:
  * LLM — классификация, хэштеги и текст черновика.
  * Python — детерминированный балл (score_value) и категория (hot/warm/cold/trash)
    по правилам scoring из business_logic.json.

Справочники (правятся без кода):
  * business_logic.json — что за лид и сколько стоит;
  * company_profile.json — как студия о себе говорит (тон, услуги, кейсы).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from config import BUSINESS_LOGIC_FILE, COMPANY_PROFILE_FILE
from core.llm import LLMProvider

logger = logging.getLogger("parserbot.classifier")


# ── Карточка лида ─────────────────────────────────────────────
@dataclass
class LeadCard:
    """Результат анализа одного сообщения."""

    is_lead: bool
    lead_label: str = "ЛИД"
    niche: str = "other_it"
    client_type: str = "individual"
    order_type: str = "fix_support"
    platform: str = "web"
    complexity: str = "basic"
    price_range_rub: list[int] = field(default_factory=lambda: [0, 0])
    score: str = "cold"
    score_value: int = 0
    hashtags: list[str] = field(default_factory=list)
    budget_mentioned: str | None = None
    deadline_mentioned: str | None = None
    summary: str = ""
    draft_reply: str = ""
    reasons: list[str] = field(default_factory=list)


# ── Загрузка справочников ─────────────────────────────────────
def load_business_logic() -> dict:
    if not BUSINESS_LOGIC_FILE.exists():
        raise RuntimeError(f"Не найден {BUSINESS_LOGIC_FILE} (business_logic.json).")
    with open(BUSINESS_LOGIC_FILE, encoding="utf-8") as f:
        bl = json.load(f)
    logger.info(
        "Бизнес-логика: %d ниш, %d типов заказов, %d типов клиентов.",
        len(bl.get("niches", {})), len(bl.get("order_types", {})), len(bl.get("client_types", {})),
    )
    return bl


def load_company_profile() -> dict:
    if not COMPANY_PROFILE_FILE.exists():
        logger.warning("Не найден %s — черновик будет обобщённым.", COMPANY_PROFILE_FILE)
        return {}
    with open(COMPANY_PROFILE_FILE, encoding="utf-8") as f:
        profile = json.load(f)
    if profile.get("cases_are_placeholders"):
        logger.info("company_profile.json: кейсы — плейсхолдеры (модель не будет их выдумывать).")
    return profile


# ── Промпт ────────────────────────────────────────────────────
_SYSTEM_PROMPT = """\
Ты — ассистент веб- и мобильного разработчика на рынке СНГ и англоязычном рынке. \
У тебя две роли сразу:
(1) КВАЛИФИКАТОР: по справочнику business_logic.json разложить сообщение по \
категориям (ниша, тип клиента, тип заказа, платформа, цена) и проставить сигналы.
(2) ПРОДАВЕЦ: по профилю company_profile.json написать короткий черновик ответа \
клиенту от имени студии.

Используй ТОЛЬКО ключи из справочников. Отвечай на языке сообщения (русское → \
по-русски, английское → по-английски).

Правила квалификации:
- Если автор предлагает услуги / ищет работу / это крипта-казино-инвестиции / \
«бесплатно/за отзыв» / бюджет ниже минимума — это не лид (signals → trash-флаги).
- Для веба отличай простой одностраничник (simple_signals) от премиум-дизайна \
(premium_signals). Для мобилок по умолчанию Flutter.
- price_range_rub бери из order_types[order_type]; если назван бюджет — скорректируй.
- В signals проставь честные булевы флаги — по ним Python посчитает балл.

Правила черновика ответа (строго следуй company_profile.json → reply_rules):
- Пиши как студия из профиля, в её tone; цепляйся за конкретику из сообщения.
- ВАЖНО: если в профиле cases_are_placeholders=true — НЕ выдумывай названия \
проектов, клиентов и кейсы. Говори о подходе и услугах обобщённо.
- Не обещай точную цену без ТЗ. Заканчивай мягким призывом (созвон/примеры).
- lead_label — короткий ярлык лида заглавными (напр. «B2B AI ЛИД», «ЛЕНДИНГ», \
«МОБИЛЬНОЕ ПРИЛОЖЕНИЕ»). hashtags — 3-5 тегов по теме (напр. ["#ищу","#AI","#бот"]).

Верни СТРОГО валидный JSON без текста вокруг, по схеме:
{
  "is_lead": bool,
  "lead_label": "строка заглавными",
  "niche": "<ключ niches>",
  "client_type": "<ключ client_types>",
  "order_type": "<ключ order_types>",
  "platform": "web" | "mobile",
  "complexity": "basic" | "medium" | "premium" | "minor",
  "price_range_rub": [min, max],
  "hashtags": ["#тег", ...],
  "budget_mentioned": "строка" | null,
  "deadline_mentioned": "строка" | null,
  "summary": "одно предложение: кто и что хочет",
  "draft_reply": "черновик ответа клиенту",
  "signals": {
    "direct_request": bool, "budget_mentioned": bool, "deadline_mentioned": bool,
    "niche_match": bool, "client_business_or_marketer_or_startup": bool,
    "order_value_medium_plus": bool, "is_executor_offering_services": bool,
    "crypto_casino_invest": bool, "free_or_for_review": bool,
    "below_min_budget": bool, "individual_microbudget": bool,
    "no_specifics_chitchat": bool
  },
  "reasons": ["короткая причина", ...]
}
"""


def _build_user_prompt(channel: str, text: str, bl: dict, profile: dict) -> str:
    return (
        f"Канал: {channel}\n"
        f'Сообщение:\n"""\n{text}\n"""\n\n'
        f"business_logic.json:\n{json.dumps(bl, ensure_ascii=False)}\n\n"
        f"company_profile.json:\n{json.dumps(profile, ensure_ascii=False)}\n\n"
        f"Верни карточку лида в формате JSON."
    )


# ── Скоринг на стороне Python ─────────────────────────────────
def _score(signals: dict, bl: dict) -> tuple[int, str]:
    scoring = bl.get("scoring", {})
    positive = scoring.get("positive", {})
    negative = scoring.get("negative", {})

    hard_kill = ("is_executor_offering_services", "crypto_casino_invest",
                 "free_or_for_review", "below_min_budget")
    if any(signals.get(k) for k in hard_kill):
        return 0, "trash"

    value = 0
    for key, weight in positive.items():
        if signals.get(key):
            value += weight
    for key, weight in negative.items():
        if signals.get(key):
            value += weight
    value = max(0, min(100, value))

    cats = scoring.get("categories", {})
    ordered = sorted(cats.items(), key=lambda kv: kv[1].get("min_score", 0), reverse=True)
    for name, meta in ordered:
        if value >= meta.get("min_score", 0):
            return value, name
    return value, "trash"


def _coerce_price(order_type: str, raw, bl: dict) -> list[int]:
    if isinstance(raw, list) and len(raw) == 2 and all(isinstance(x, (int, float)) for x in raw):
        return [int(raw[0]), int(raw[1])]
    ot = bl.get("order_types", {}).get(order_type, {})
    pr = ot.get("price_range_rub", [0, 0])
    return [int(pr[0]), int(pr[1])]


def _extract_json(text: str) -> dict:
    """Достать JSON из ответа модели (на случай code-fence или мусора вокруг)."""
    s = text.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1] if "```" in s[3:] else s
        s = s.lstrip("json").strip().strip("`").strip()
    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end != -1:
        s = s[start : end + 1]
    return json.loads(s)


# ── Классификатор ─────────────────────────────────────────────
class Classifier:
    """Обёртка: провайдер LLM + справочники. Один экземпляр на процесс."""

    def __init__(self, provider: LLMProvider, bl: dict, profile: dict) -> None:
        self._provider = provider
        self._bl = bl
        self._profile = profile

    async def classify(self, text: str, channel: str) -> LeadCard | None:
        """Проанализировать сообщение. None — если LLM не смог (роняем мягко)."""
        try:
            raw = await self._provider.complete(
                _SYSTEM_PROMPT,
                _build_user_prompt(channel, text, self._bl, self._profile),
                json=True,
            )
            data = _extract_json(raw)
        except Exception as exc:  # noqa: BLE001 — не роняем парсер из-за LLM
            logger.error("LLM-анализ не удался: %s: %s", type(exc).__name__, exc)
            return None

        signals = data.get("signals", {}) or {}
        score_value, score = _score(signals, self._bl)
        order_type = data.get("order_type", "fix_support")

        return LeadCard(
            is_lead=bool(data.get("is_lead", False)),
            lead_label=data.get("lead_label", "ЛИД"),
            niche=data.get("niche", "other_it"),
            client_type=data.get("client_type", "individual"),
            order_type=order_type,
            platform=data.get("platform", "web"),
            complexity=data.get("complexity", "basic"),
            price_range_rub=_coerce_price(order_type, data.get("price_range_rub"), self._bl),
            score=score,
            score_value=score_value,
            hashtags=data.get("hashtags", []) or [],
            budget_mentioned=data.get("budget_mentioned"),
            deadline_mentioned=data.get("deadline_mentioned"),
            summary=data.get("summary", ""),
            draft_reply=data.get("draft_reply", ""),
            reasons=data.get("reasons", []) or [],
        )
