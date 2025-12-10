# src/tma_api/tarot_deck.py

import json
import logging
import random
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DECK: List[Dict[str, Any]] = []
_CARDS_BY_CODE: Dict[str, Dict[str, Any]] = {}


def _slugify(value: str) -> str:
    """
    Простейший slugify: оставляем только a-z0-9 и заменяем всё остальное на "_".
    """
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = value.strip("_")
    return value or "card"


def _normalize_card(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Нормализуем карту:
    - image_url: из JSON или по type + code,
    - остальные поля приводим к безопасным значениям.
    Предполагается, что поле code уже выставлено в _load_deck().
    """
    code = str(raw.get("code", ""))  # к этому моменту уже должен быть не пустым

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


def _is_probably_card(obj: Any) -> bool:
    """
    Эвристика: похоже ли это на объект карты Таро.
    """
    if not isinstance(obj, dict):
        return False

    has_name_or_id = "name" in obj or "id" in obj
    has_tarot_field = any(
        key in obj for key in ("image_url", "meaning_upright", "meaning_reversed")
    )
    return bool(has_name_or_id and has_tarot_field)


def _collect_cards(node: Any, cards: List[Dict[str, Any]]) -> None:
    """
    Рекурсивно обходит структуру JSON и собирает все объекты-карты.
    Поддерживает:
    - список карт [ {...}, {...}, ... ]
    - любые вложенные словари/объекты вида { "major_arcana": [...], "minor_arcana": ... }
    """
    if isinstance(node, list):
        for item in node:
            _collect_cards(item, cards)
    elif isinstance(node, dict):
        if _is_probably_card(node):
            cards.append(node)
        else:
            for v in node.values():
                _collect_cards(v, cards)
    # всё остальное (строки, числа и т.п.) игнорируем


def _load_deck() -> None:
    """
    Загружает колоду из data/tarot_deck.json в _DECK и _CARDS_BY_CODE.

    Поддерживает два основных варианта структуры JSON:
    - список карт: [ {...}, {...}, ... ]
    - словарь/вложенная структура: { "major_arcana": [...], "minor_arcana": [...], ... }

    Рекурсивно собирает все объекты, "похожие на карту", гарантирует наличие code
    и строит индекс по code.
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

    # Рекурсивно собираем все объекты, похожие на карты
    raw_cards: List[Dict[str, Any]] = []
    _collect_cards(data, raw_cards)

    if not raw_cards:
        logger.error("No tarot cards found in tarot_deck.json")
        _DECK = []
        _CARDS_BY_CODE = {}
        return

    # Гарантируем наличие code у каждой карты
    for obj in raw_cards:
        raw_code = obj.get("code")
        raw_id = obj.get("id")

        if raw_code is not None:
            code = str(raw_code)
        elif raw_id is not None:
            code = str(raw_id)
        else:
            name = str(obj.get("name", "")).strip().lower() or "card"
            code = _slugify(name)
            logger.warning(
                "Card has no code and id, generated fallback code: %s",
                code,
            )

        obj["code"] = code

    # Нормализуем и собираем индекс по code
    deck: List[Dict[str, Any]] = []
    cards_by_code: Dict[str, Dict[str, Any]] = {}

    for idx, raw in enumerate(raw_cards):
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

    logger.info(
        "Tarot deck loaded: %d cards, %d codes",
        len(_DECK),
        len(_CARDS_BY_CODE),
    )


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
