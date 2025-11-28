# src/tma_api/tarot_deck.py

from __future__ import annotations

import json
import logging
import random
from functools import lru_cache
from pathlib import Path
from typing import TypedDict, NotRequired, Any

logger = logging.getLogger(__name__)


class TarotCard(TypedDict, total=False):
    """
    Узкий тип под элементы JSON-колоды.

    Поля сделаны опциональными, т.к. структура JSON может расширяться.
    """
    id: NotRequired[int]
    name: NotRequired[str]
    suit: NotRequired[str]
    arcana: NotRequired[str]
    is_reversed: NotRequired[bool]
    image_url: NotRequired[str]
    # допускаем дополнительные ключи без явного описания


# .../project_root, если файл лежит так:
# project_root/
#   data/tarot_deck.json
#   src/tma_api/tarot_deck.py
BASE_DIR = Path(__file__).resolve().parents[2]


@lru_cache
def _load_deck() -> list[TarotCard]:
    """
    Лениво загружаем JSON-колоду с диска и кешируем результат.

    Ожидается структура:
    {
        "cards": [ ... ]
    }
    либо просто список карт в корне.
    """
    deck_path = BASE_DIR / "data" / "tarot_deck.json"
    logger.info("Loading tarot deck from %s", deck_path)

    with deck_path.open("r", encoding="utf-8") as f:
        raw: Any = json.load(f)

    if isinstance(raw, dict) and "cards" in raw:
        cards = raw["cards"]
    else:
        cards = raw

    try:
        size = len(cards)  # type: ignore[arg-type]
    except Exception:
        size = -1

    logger.info("Tarot deck loaded successfully (cards: %s)", size)

    return cards  # type: ignore[return-value]


def draw_random_cards(count: int) -> list[TarotCard]:
    """
    Выбрать случайные карты из колоды без повторов.

    :param count: сколько карт вытянуть
    :raises ValueError: если count > размера колоды (random.sample)
    """
    deck = _load_deck()
    return random.sample(deck, k=count)
