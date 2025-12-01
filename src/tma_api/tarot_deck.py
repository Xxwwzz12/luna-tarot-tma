# src/tma_api/tarot_deck.py

import json
import logging
import random
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DECK: List[Dict[str, Any]] = []
_CARDS_BY_CODE: Dict[str, Dict[str, Any]] = {}


def _normalize_card(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Нормализуем карту:
    - code: raw.code → raw.id → fallback по name (со warning-логом),
    - image_url: из JSON или по type + code,
    - остальные поля приводим к безопасным значениям.
    """
    code = raw.get("code") or raw.get("id")
    if not code:
        name = str(raw.get("name", "")).strip().lower()
        code = name.replace(" ", "_") or "unknown_card"
        logger.warning(
            "Card has no code and id, generated fallback code: %s", code
        )

    # гарантируем, что code — строка (важно, если id был числом)
    code = str(code)

    image_url = raw.get("image_url")
    if not image_url:
        card_type = raw.get("type")
        if card_type == "major":
            image_url = f"images/major/{code}.jpg"
        else:
            image_url = f"images/minor/{code}.jpg"

    return {
        "id": raw.get("id"),
        "code": code,
        "name": raw.get("name") or "",
        "type": raw.get("type"),
        "suit": raw.get("suit"),
        "description": raw.get("description") or "",
        "meaning_upright": raw.get("meaning_upright") or {},
        "meaning_reversed": raw.get("meaning_reversed") or {},
        "keywords": raw.get("keywords") or {},
        "image_url": image_url,
    }


def _load_deck() -> None:
    """
    Загружает колоду из data/tarot_deck.json в _DECK и _CARDS_BY_CODE.

    Поддерживает два варианта структуры JSON:
    1) Список карт: [ { ... }, { ... }, ... ]
    2) Словарь карт: { "0": { ... }, "1": { ... }, ... }
    """
    global _DECK, _CARDS_BY_CODE

    project_root = Path(__file__).resolve().parents[2]
    deck_path = project_root / "data" / "tarot_deck.json"

    logger.info("Loading tarot deck from %s", deck_path)

    if not deck_path.exists():
        logger.error("Tarot deck file not found: %s", deck_path)
        _DECK = []
        _CARDS_BY_CODE = {}
        return

    try:
        with deck_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to load tarot deck JSON: %s", exc)
        _DECK = []
        _CARDS_BY_CODE = {}
        return

    # Приводим к списку raw-карт
    items: list[dict[str, Any]] = []

    if isinstance(data, list):
        # ожидаемый вариант: список объектов
        for idx, raw in enumerate(data):
            if not isinstance(raw, dict):
                logger.warning(
                    "Tarot deck item at index %s is not an object, skipping: %r",
                    idx,
                    raw,
                )
                continue
            items.append(raw)
    elif isinstance(data, dict):
        # альтернативный вариант: словарь id -> объект карты
        for key, raw in data.items():
            if not isinstance(raw, dict):
                logger.warning(
                    "Tarot deck item for key %r is not an object, skipping: %r",
                    key,
                    raw,
                )
                continue
            items.append(raw)
    else:
        logger.error(
            "Tarot deck JSON must be a list or dict of objects, got %s",
            type(data).__name__,
        )
        _DECK = []
        _CARDS_BY_CODE = {}
        return

    deck: list[dict[str, Any]] = []
    cards_by_code: dict[str, dict[str, Any]] = {}

    for idx, raw in enumerate(items):
        card = _normalize_card(raw)
        code = card["code"]
        if code in cards_by_code:
            logger.warning(
                "Duplicate tarot card code %s at index %s, overriding previous",
                code,
                idx,
            )
        deck.append(card)
        cards_by_code[code] = card

    _DECK = deck
    _CARDS_BY_CODE = cards_by_code

    logger.info("Tarot deck loaded successfully (cards: %s)", len(_DECK))


# Инициализация при импорте модуля
_load_deck()


def get_tarot_deck() -> List[Dict[str, Any]]:
    """
    Возвращает полный список карт (копию).
    """
    return list(_DECK)


def draw_random_cards(count: int) -> List[Dict[str, Any]]:
    """
    Возвращает случайные карты из колоды.
    """
    if count <= 0:
        return []
    if count >= len(_DECK):
        return list(_DECK)
    return random.sample(_DECK, k=count)


def get_card_by_code(code: str) -> Optional[Dict[str, Any]]:
    """
    Получить карту по её code (или id из JSON).

    Используется интерактивным раскладом: фронт присылает codes,
    мы поднимаем из загруженной колоды.
    """
    if not code:
        return None
    return _CARDS_BY_CODE.get(code)
