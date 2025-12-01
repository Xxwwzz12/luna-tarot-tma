# src/tma_api/tarot_deck.py

import json
import logging
import random
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DECK: List[Dict[str, Any]] = []
_CARDS_BY_CODE: Dict[str, Dict[str, Any]] = {}


def _normalize_card(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Нормализуем карту:
    - code: raw.code → raw.id → fallback по name
    - image_url: raw.image_url → images/{type}/{code}.jpg
    - остальные поля приводим к безопасным значениям
    """

    # -----------------------------
    # CODE
    # -----------------------------
    code = raw.get("code") or raw.get("id")
    if not code:
        # fallback: по name
        name = str(raw.get("name", "")).strip().lower()
        code = name.replace(" ", "_") or "unknown_card"
        logger.warning("Card has no code and id, generated fallback code: %s", code)

    # -----------------------------
    # IMAGE_URL
    # -----------------------------
    image_url = raw.get("image_url")
    if not image_url:
        card_type = raw.get("type")
        if card_type == "major":
            image_url = f"images/major/{code}.jpg"
        else:
            image_url = f"images/minor/{code}.jpg"

    # -----------------------------
    # Нормализованный объект
    # -----------------------------
    return {
        "id": raw.get("id"),
        "code": code,
        "name": raw.get("name"),
        "type": raw.get("type"),
        "suit": raw.get("suit"),
        "description": raw.get("description") or "",
        "meaning_upright": raw.get("meaning_upright") or {},
        "meaning_reversed": raw.get("meaning_reversed") or {},
        "keywords": raw.get("keywords") or {},
        "image_url": image_url,
    }


def _load_deck() -> List[Dict[str, Any]]:
    """Читает tarot_deck.json и инициализирует _DECK и _CARDS_BY_CODE."""
    global _DECK, _CARDS_BY_CODE
    if _DECK:
        return _DECK

    base_dir = Path(__file__).resolve().parents[2]
    json_path = base_dir / "data" / "tarot_deck.json"

    logger.info("Loading tarot deck from %s", json_path)

    with json_path.open("r", encoding="utf-8") as f:
        raw_cards = json.load(f)

    # Ожидаем список карточек в JSON
    deck: List[Dict[str, Any]] = []
    for raw in raw_cards:
        deck.append(_normalize_card(raw))

    _DECK = deck
    _CARDS_BY_CODE = {card["code"]: card for card in deck}

    logger.info("Tarot deck loaded successfully (cards: %s)", len(_DECK))
    return _DECK


# ИНИЦИАЛИЗАЦИЯ ПРИ ИМПОРТЕ
_load_deck()


# -------------------------------------------------------------------
# PUBLIC API
# -------------------------------------------------------------------

def get_tarot_deck() -> List[Dict[str, Any]]:
    """
    Возвращает копию полной колоды карт.
    """
    return list(_DECK)


def draw_random_cards(count: int) -> List[Dict[str, Any]]:
    """
    Выбрать случайные карты.
    - count <= 0 → []
    - count >= len(deck) → вернуть всю колоду
    - иначе → random.sample
    """
    if count <= 0:
        return []

    if count >= len(_DECK):
        return list(_DECK)

    return random.sample(_DECK, k=count)


def get_card_by_code(code: str) -> Optional[Dict[str, Any]]:
    """
    Получить карту по её уникальному code (или id, если он использован как code).
    """
    if not code:
        return None
    return _CARDS_BY_CODE.get(code)
