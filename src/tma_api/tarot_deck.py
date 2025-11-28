# src/tma_api/tarot_deck.py

from __future__ import annotations

import json
import random
from functools import lru_cache
from pathlib import Path
from typing import TypedDict, NotRequired, Any


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
    # (json.load вернёт dict[str, Any], TypedDict с total=False это допускает)


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
    base_dir = Path(__file__).resolve().parent.parent
    deck_path = base_dir / "tarot_engine" / "data" / "tarot_deck.json"

    with deck_path.open("r", encoding="utf-8") as f:
        raw: Any = json.load(f)

    if isinstance(raw, dict) and "cards" in raw:
        return raw["cards"]  # type: ignore[return-value]

    # fallback: если в корне уже список
    return raw  # type: ignore[return-value]


def draw_random_cards(count: int) -> list[TarotCard]:
    """
    Выбрать случайные карты из колоды без повторов.

    :param count: сколько карт вытянуть
    :raises ValueError: если count > размера колоды (random.sample)
    """
    deck = _load_deck()
    return random.sample(deck, k=count)
