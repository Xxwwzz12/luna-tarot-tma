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
    id: NotRequired[int]
    name: NotRequired[str]
    type: NotRequired[str]              # major/minor
    suit: NotRequired[str]
    description: NotRequired[str]
    meaning_upright: NotRequired[str]
    meaning_reversed: NotRequired[str]
    keywords: NotRequired[list[str]]
    image_url: NotRequired[str]
    is_reversed: NotRequired[bool]


# ---------------------------------------------------------
# Пути
# ---------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parents[2]
DECK_PATH = BASE_DIR / "data" / "tarot_deck.json"


# ---------------------------------------------------------
# Рекурсивный парсер объектов-карт (T1.3)
# ---------------------------------------------------------
def _iter_card_dicts(obj) -> Iterable[dict]:
    """
    Рекурсивно обходит структуру (dict/list)
    и собирает все объекты, которые "похожи" на карту:
      - есть "name"
      - есть хотя бы один из: "image_url", "type", "id"
    """
    if isinstance(obj, dict):
        # Похожа на карту? Считаем картой
        if "name" in obj and ("image_url" in obj or "type" in obj or "id" in obj):
            yield obj

        # И продолжаем углубляться
        for v in obj.values():
            yield from _iter_card_dicts(v)

    elif isinstance(obj, list):
        for item in obj:
            yield from _iter_card_dicts(item)

    # Всё остальное (строки, числа и т.п.) игнорируем


# ---------------------------------------------------------
# Ленивая загрузка JSON с рекурсивным разбором (T1.3)
# ---------------------------------------------------------
@lru_cache
def _load_deck() -> list[TarotCard]:
    logger.info("Loading tarot deck from %s", DECK_PATH)

    with DECK_PATH.open("r", encoding="utf-8") as f:
        raw: Any = json.load(f)

    # Если есть ключ "cards" — работаем с ним, иначе со всем JSON
    if isinstance(raw, dict) and "cards" in raw:
        root_obj = raw["cards"]
    else:
        root_obj = raw

    # Рекурсивно собираем все карточные dict
    cards = [c for c in _iter_card_dicts(root_obj)]

    if not cards:
        raise ValueError("No tarot card dicts found in tarot_deck.json")

    if len(cards) < 3:
        logger.warning(
            "Tarot deck contains only %s cards; spreads may have duplicates.",
            len(cards),
        )

    logger.info("Tarot deck loaded successfully (cards: %s)", len(cards))
    return cards  # type: ignore[return-value]


# ---------------------------------------------------------
# Устойчивый выбор карт (T1.2, без изменений)
# ---------------------------------------------------------
def draw_random_cards(count: int) -> list[TarotCard]:
    """
    Надёжное поведение для любой длины колоды.
    """
    if count <= 0:
        return []

    deck = _load_deck()

    if not deck:
        raise RuntimeError("Tarot deck is empty")

    deck_size = len(deck)

    if deck_size >= count:
        return random.sample(deck, k=count)

    # Деградация: карт меньше, чем нужно → выбираем с повторами
    logger.warning(
        "Requested %s cards, but deck has only %s. "
        "Allowing duplicates via random.choices.",
        count,
        deck_size,
    )

    return random.choices(deck, k=count)
