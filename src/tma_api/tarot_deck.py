# src/tma_api/tarot_deck.py

from __future__ import annotations

import json
import logging
import random
from functools import lru_cache
from pathlib import Path
from typing import TypedDict, NotRequired, Any
from collections.abc import Iterable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------
# TypedDict под объект карты
# ---------------------------------------------------------
class TarotCard(TypedDict, total=False):
    code: str
    name: NotRequired[str]
    type: NotRequired[str]               # major/minor
    suit: NotRequired[str]
    description: NotRequired[str]
    meaning_upright: dict
    meaning_reversed: dict
    keywords: dict
    image_url: str
    is_reversed: NotRequired[bool]


# ---------------------------------------------------------
# Пути
# ---------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parents[2]
DECK_PATH = BASE_DIR / "data" / "tarot_deck.json"


# ---------------------------------------------------------
# Рекурсивный сбор карт
# ---------------------------------------------------------
def _iter_card_dicts(obj) -> Iterable[dict]:
    if isinstance(obj, dict):
        if "name" in obj and ("type" in obj or "image_url" in obj or "code" in obj or "id" in obj):
            yield obj
        for v in obj.values():
            yield from _iter_card_dicts(v)

    elif isinstance(obj, list):
        for item in obj:
            yield from _iter_card_dicts(item)


# ---------------------------------------------------------
# Нормализация карты (ТЗ 2.1)
# ---------------------------------------------------------
def _normalize_card(raw: dict) -> TarotCard:
    # 1. CODE: сначала code → id → fallback
    code = raw.get("code") or raw.get("id")

    if not code:
        name = str(raw.get("name", "")).strip().lower()
        code = name.replace(" ", "_")
        logger.warning("Card has no code and id, generated fallback code: %s", code)

    # 2. IMAGE_URL: не начинаем со слэша, путь строго как в таблице
    image_url = raw.get("image_url")

    if not image_url:
        card_type = raw.get("type")
        if card_type == "major":
            image_url = f"images/major/{code}.jpg"
        else:
            image_url = f"images/minor/{code}.jpg"

    # 3. meaning*/keywords всегда должны быть dict
    meaning_upright = raw.get("meaning_upright") or {}
    meaning_reversed = raw.get("meaning_reversed") or {}
    keywords = raw.get("keywords") or {}

    return {
        "code": str(code),
        "name": raw.get("name"),
        "type": raw.get("type"),
        "suit": raw.get("suit"),
        "description": raw.get("description"),
        "meaning_upright": meaning_upright,
        "meaning_reversed": meaning_reversed,
        "keywords": keywords,
        "image_url": image_url,
        "is_reversed": raw.get("is_reversed"),
    }


# ---------------------------------------------------------
# Ленивая загрузка JSON
# ---------------------------------------------------------
@lru_cache
def _load_deck() -> list[TarotCard]:
    logger.info("Loading tarot deck from %s", DECK_PATH)

    with DECK_PATH.open("r", encoding="utf-8") as f:
        raw: Any = json.load(f)

    root_obj = raw["cards"] if isinstance(raw, dict) and "cards" in raw else raw

    raw_cards = [c for c in _iter_card_dicts(root_obj)]

    if not raw_cards:
        raise ValueError("No tarot card dicts found in tarot_deck.json")

    # ПРОПУСКАЕМ ВСЕ КАРТЫ ЧЕРЕЗ normalize
    cards = [_normalize_card(c) for c in raw_cards]

    if len(cards) < 3:
        logger.warning(
            "Tarot deck contains only %s cards; spreads may have duplicates.",
            len(cards),
        )

    logger.info("Tarot deck loaded successfully (cards: %s)", len(cards))
    return cards


# ---------------------------------------------------------
# Устойчивый выбор карт
# ---------------------------------------------------------
def draw_random_cards(count: int) -> list[TarotCard]:
    if count <= 0:
        return []

    deck = _load_deck()

    if not deck:
        raise RuntimeError("Tarot deck is empty")

    deck_size = len(deck)

    if deck_size >= count:
        return random.sample(deck, k=count)

    logger.warning(
        "Requested %s cards, but deck has only %s. "
        "Allowing duplicates via random.choices.",
        count,
        deck_size,
    )

    return random.choices(deck, k=count)
