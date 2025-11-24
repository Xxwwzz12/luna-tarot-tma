# src/tma_api/spreads/service.py

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from .models import (
    CardModel,
    SpreadDetail,
    SpreadListItem,
    SpreadQuestionModel,
    SpreadQuestionsList,
)

# 🔧 Временная in-memory "база данных"

_SPREADS: Dict[int, Dict[str, Any]] = {}
_SPREAD_COUNTER: int = 1

_QUESTIONS: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
_QUESTION_INDEX: Dict[int, Dict[str, Any]] = {}
_QUESTION_COUNTER: int = 1

_SESSIONS: Dict[str, Dict[str, Any]] = {}


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _spread_has_questions(spread: Dict[str, Any]) -> bool:
    """Есть ли вопросы к раскладу или непустой question."""
    if spread.get("question") and str(spread["question"]).strip():
        return True

    key = (spread["user_id"], spread["id"])
    return len(_QUESTIONS.get(key, [])) > 0


def _build_cards(spread_type: str) -> List[CardModel]:
    """Простая генерация карт-заглушек."""
    total = 1 if spread_type == "single" else 3
    cards = []
    for pos in range(1, total + 1):
        cards.append(
            CardModel(
                position=pos,
                name=f"Карта {pos}",
                is_reversed=(pos % 2 == 0),
            )
        )
    return cards


class SpreadService:
    def __init__(self):
        pass

    # ───────────────────────────────────────────────
    # 1. AUTO расклады
    # ───────────────────────────────────────────────

    def create_auto_spread(
        self,
        user_id: int,
        spread_type: str,
        category: str,
        question: str | None = None,
    ) -> SpreadDetail:
        global _SPREAD_COUNTER

        spread_id = _SPREAD_COUNTER
        _SPREAD_COUNTER += 1

        cards = _build_cards(spread_type)

        if question:
            interpretation = (
                f"Интерпретация расклада ({spread_type}/{category}) "
                f"с учётом вопроса: {question}"
            )
        else:
            interpretation = f"Интерпретация расклада ({spread_type}/{category})."

        created_at = _now_iso()

        db_spread = {
            "id": spread_id,
            "user_id": user_id,
            "spread_type": spread_type,
            "category": category,
            "created_at": created_at,
            "cards": cards,
            "interpretation": interpretation,
            "question": question,
        }

        _SPREADS[spread_id] = db_spread

        return SpreadDetail(
            id=spread_id,
            spread_type=spread_type,
            category=category,
            created_at=created_at,
            cards=cards,
            interpretation=interpretation,
            question=question,
        )

    # ───────────────────────────────────────────────
    # 2. Интерактивные сессии
    # ───────────────────────────────────────────────

    def create_interactive_session(self, user_id: int, spread_type: str, category: str):
        session_id = str(uuid4())
        total_positions = 1 if spread_type == "single" else 3

        session = {
            "session_id": session_id,
            "user_id": user_id,
            "spread_type": spread_type,
            "category": category,
            "total_positions": total_positions,
            "selected_cards": {},
            "current_position": 1,
            "status": "awaiting_selection",
        }

        _SESSIONS[session_id] = session
        return session

    def select_card(
        self,
        session_id: str,
        position: int,
        choice_index: int,
    ):
        session = _SESSIONS.get(session_id)
        if not session:
            return None

        if session["status"] != "awaiting_selection":
            return None

        total = session["total_positions"]
        if position < 1 or position > total:
            return None

        session["selected_cards"][position] = {
            "position": position,
            "name": f"Карта {choice_index}",
            "is_reversed": (choice_index % 2 == 0),
        }

        if len(session["selected_cards"]) < total:
            session["current_position"] = position + 1
            return session

        # Все карты выбраны
        session["status"] = "completed"

        cards = [
            CardModel(
                position=c["position"],
                name=c["name"],
                is_reversed=c["is_reversed"],
            )
            for _, c in sorted(session["selected_cards"].items())
        ]

        spread_detail = self.create_auto_spread(
            user_id=session["user_id"],
            spread_type=session["spread_type"],
            category=session["category"],
            question=None,
        )

        db_spread = _SPREADS[spread_detail.id]
        db_spread["cards"] = cards
        db_spread["interpretation"] = (
            f"Интерпретация интерактивного расклада: "
            f"{session['spread_type']}/{session['category']}"
        )

        return {
            "session": session,
            "spread": SpreadDetail(
                id=db_spread["id"],
                spread_type=db_spread["spread_type"],
                category=db_spread["category"],
                created_at=db_spread["created_at"],
                cards=db_spread["cards"],
                interpretation=db_spread["interpretation"],
                question=db_spread.get("question"),
            ),
        }

    # ───────────────────────────────────────────────
    # 3. Список раскладов
    # ───────────────────────────────────────────────

    def get_spreads_list(self, user_id: int, page: int, limit: int):
        spreads = [s for s in _SPREADS.values() if s["user_id"] == user_id]
        spreads.sort(key=lambda s: s["created_at"], reverse=True)

        total_items = len(spreads)
        limit = limit or 10
        total_pages = max((total_items + limit - 1) // limit, 1)
        page = max(page, 1)

        start = (page - 1) * limit
        items_raw = spreads[start : start + limit]

        items = []
        for s in items_raw:
            items.append(
                SpreadListItem(
                    id=s["id"],
                    spread_type=s["spread_type"],
                    category=s["category"],
                    created_at=s["created_at"],
                    short_preview=(s["interpretation"] or "")[:140],
                    has_questions=_spread_has_questions(s),
                )
            )

        return {
            "items": items,
            "page": page,
            "total_pages": total_pages,
            "total_items": total_items,
        }

    # ───────────────────────────────────────────────
    # 4. Детальный расклад
    # ───────────────────────────────────────────────

    def get_spread(self, user_id: int, spread_id: int):
        s = _SPREADS.get(spread_id)
        if not s or s["user_id"] != user_id:
            return None

        return SpreadDetail(
            id=s["id"],
            spread_type=s["spread_type"],
            category=s["category"],
            created_at=s["created_at"],
            cards=s["cards"],
            interpretation=s["interpretation"],
            question=s["question"],
        )

    # ───────────────────────────────────────────────
    # 5. Вопросы (новый интерфейс: модели SpreadQuestion*)
    # ───────────────────────────────────────────────

    def add_spread_question(
        self,
        user_id: int,
        spread_id: int,
        question: str,
    ) -> SpreadQuestionModel:
        """Создать вопрос к раскладу (с фиксом статуса)."""

        global _QUESTION_COUNTER

        spread = _SPREADS.get(spread_id)
        if not spread or spread["user_id"] != user_id:
            raise ValueError("Spread not found")

        question_id = _QUESTION_COUNTER
        _QUESTION_COUNTER += 1

        record = {
            "id": question_id,
            "spread_id": spread_id,
            "user_id": user_id,
            "question": question,
            "answer": f"Заглушка: ответ на вопрос '{question}'",
            "status": "ready",  # TODO: позже заменить на pipeline ('pending' → AI → 'ready' / 'failed') 
            "created_at": _now_iso(),
        }

        key = (user_id, spread_id)
        _QUESTIONS.setdefault(key, []).append(record)
        _QUESTION_INDEX[question_id] = record

        return SpreadQuestionModel(**record)

    def get_spread_questions(self, user_id: int, spread_id: int) -> SpreadQuestionsList:
        spread = _SPREADS.get(spread_id)
        if not spread or spread["user_id"] != user_id:
            raise ValueError("Spread not found")

        items = [
            SpreadQuestionModel(**q)
            for q in sorted(
                _QUESTIONS.get((user_id, spread_id), []),
                key=lambda q: q["created_at"],
            )
        ]

        return SpreadQuestionsList(items=items)

    # ───────────────────────────────────────────────
    # 6. Старый интерфейс (dict) — совместимость
    # ───────────────────────────────────────────────

    def create_question(self, user_id: int, spread_id: int, text: str):
        try:
            q = self.add_spread_question(user_id, spread_id, text)
        except ValueError:
            return None

        return {
            "id": q.id,
            "user_id": q.user_id,
            "spread_id": q.spread_id,
            "text": q.question,
            "answer": q.answer,
            "status": q.status,
            "created_at": q.created_at,
        }

    def get_questions(self, user_id: int, spread_id: int):
        try:
            qs = self.get_spread_questions(user_id, spread_id).items
        except ValueError:
            return []

        return [
            {
                "id": q.id,
                "user_id": q.user_id,
                "spread_id": q.spread_id,
                "text": q.question,
                "answer": q.answer,
                "status": q.status,
                "created_at": q.created_at,
            }
            for q in qs
        ]

    def get_question(self, user_id: int, question_id: int):
        rec = _QUESTION_INDEX.get(question_id)
        if not rec or rec["user_id"] != user_id:
            return None

        return {
            "id": rec["id"],
            "user_id": rec["user_id"],
            "spread_id": rec["spread_id"],
            "text": rec["question"],
            "answer": rec["answer"],
            "status": rec["status"],
            "created_at": rec["created_at"],
        }
