# src/tma_api/tarot_deck.py

from __future__ import annotations

import json
import logging
import random
from functools import lru_cache
from pathlib import Path
from typing import TypedDict, NotRequired, Any, List

logger = logging.getLogger(__name__)


# --------------------------------------------
# TypedDict под карту из JSON
# --------------------------------------------
class TarotCard(TypedDict, total=False):
    id: NotRequired[int]
    name: NotRequired[str]
    type: NotRequired[str]              # major / minor
    suit: NotRequired[str]
    description: NotRequired[str]
    meaning_upright: NotRequired[str]
    meaning_reversed: NotRequired[str]
    keywords: NotRequired[List[str]]
    image_url: NotRequired[str]
    is_reversed: NotRequired[bool]      # Не обязателен в JSON


# --------------------------------------------
# Пути
# --------------------------------------------
BASE_DIR = Path(__file__).resolve().parents[2]
DECK_PATH = BASE_DIR / "data" / "tarot_deck.json"


# --------------------------------------------
# Ленивый универсальный парсер структуры JSON
# --------------------------------------------
@lru_cache
def _load_deck() -> list[TarotCard]:
    """
    Загружает таро-колоду из JSON в одном из форматов:

    Формат №1:
        { "cards": [ {...}, ... ] }

    Формат №2:
        [ {...}, {...}, ... ]

    Формат №3:
        { "0": {...}, "1": {...}, "shut": {...}, ... }

    Если структура неизвестна → ValueError.
    """

    logger.info("Loading tarot deck from %s", DECK_PATH)

    with DECK_PATH.open("r", encoding="utf-8") as f:
        raw: Any = json.load(f)

    cards: list[TarotCard]

    # Формат №1
    if isinstance(raw, dict) and "cards" in raw:
        if isinstance(raw["cards"], list):
            cards = raw["cards"]  # type: ignore[assignment]
        else:
            raise ValueError("JSON key 'cards' exists but is not a list")

    # Формат №2
    elif isinstance(raw, list):
        cards = raw  # type: ignore[assignment]

    # Формат №3 (словарь без 'cards')
    elif isinstance(raw, dict):
        # Берём все значения
        values = list(raw.values())
        # Значения должны быть dict/карты
        if not all(isinstance(v, dict) for v in values):
            raise ValueError(
                "Unsupported tarot deck JSON mapping: some values are not dicts"
            )
        cards = values  # type: ignore[assignment]

    # Неподдерживаемый тип
    else:
        raise ValueError(f"Unsupported tarot deck JSON structure: {type(raw)}")

    # Логирование результата
    size = len(cards)
    logger.info("Tarot deck loaded successfully (cards: %s)", size)

    if size < 3:
        logger.warning(
            "Tarot deck contains only %s cards; some spreads may duplicate cards.",
            size,
        )

    return cards


# --------------------------------------------
# Устойчивый выбор карт
# --------------------------------------------
def draw_random_cards(count: int) -> list[TarotCard]:
    """
    Нормально работает при любой длине колоды:
    - count <= 0 → []
    - len(deck) >= count → random.sample
    - len(deck) < count → предупреждение + random.choices (допускаются повторы)
    """
    if count <= 0:
        return []

    deck = _load_deck()

    if not deck:
        raise RuntimeError("Tarot deck is empty")

    deck_size = len(deck)

    if deck_size >= count:
        return random.sample(deck, k=count)

    # Деградация: карт меньше, чем надо — выбираем с повторами
    logger.warning(
        "Requested %s cards, but deck has only %s. "
        "Allowing duplicates via random.choices.",
        count,
        deck_size,
    )

    return random.choices(deck, k=count)
