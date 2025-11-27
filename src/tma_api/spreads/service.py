# src/tma_api/spreads/service.py

from __future__ import annotations

import logging
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from .models import (
    CardModel,
    SpreadDetail,
    SpreadListItem,
    SpreadQuestionModel,
    SpreadQuestionsList,
)

logger = logging.getLogger(__name__)

# 🔧 In-memory storage

_SPREADS: Dict[int, Dict[str, Any]] = {}
_SPREAD_COUNTER = 1

_QUESTIONS: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
_QUESTION_INDEX: Dict[int, Dict[str, Any]] = {}
_QUESTION_COUNTER = 1

_SESSIONS: Dict[str, Dict[str, Any]] = {}

_ai_interpreter: Any | None = None


# ─────────────────────────────────────
# Utils
# ─────────────────────────────────────

def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _spread_has_questions(s: Dict[str, Any]) -> bool:
    if s.get("question") and str(s["question"]).strip():
        return True
    return len(_QUESTIONS.get((s["user_id"], s["id"]), [])) > 0


def _build_cards(spread_type: str) -> List[CardModel]:
    total = 1 if spread_type == "single" else 3
    return [
        CardModel(
            position=i,
            name=f"Карта {i}",
            is_reversed=(i % 2 == 0),
        )
        for i in range(1, total + 1)
    ]


def _get_ai_interpreter() -> Any | None:
    global _ai_interpreter
    if _ai_interpreter is not None:
        return _ai_interpreter

    try:
        from ...ai_interpreter import AIInterpreter
        _ai_interpreter = AIInterpreter()
    except Exception as e:
        logger.warning("AIInterpreter unavailable: %s", e)
        _ai_interpreter = None

    return _ai_interpreter


def _compute_age(birth_date_val: Any) -> Optional[int]:
    if not birth_date_val:
        return None

    try:
        if isinstance(birth_date_val, str):
            try:
                dt = datetime.fromisoformat(birth_date_val)
            except ValueError:
                dt = datetime.strptime(birth_date_val, "%Y-%m-%d")
            d = dt.date()
        elif isinstance(birth_date_val, datetime):
            d = birth_date_val.date()
        elif isinstance(birth_date_val, date):
            d = birth_date_val
        else:
            return None
    except Exception:
        return None

    today = datetime.utcnow().date()
    return today.year - d.year - ((today.month, today.day) < (d.month, d.day))


def _get_user_ctx(user_id: int) -> Dict[str, Any]:
    profile = None

    try:
        from ...profile_service import ProfileService
        profile = ProfileService().get_profile(user_id=user_id)
    except Exception:
        profile = None

    if profile is None:
        try:
            from ...user_database import get_user_by_id
            profile = get_user_by_id(user_id)
        except Exception:
            profile = None

    name = None
    gender = None
    birth = None

    if isinstance(profile, dict):
        name = profile.get("username") or profile.get("first_name")
        gender = profile.get("gender")
        birth = profile.get("birth_date")
    elif profile:
        name = getattr(profile, "username", None) or getattr(profile, "first_name", None)
        gender = getattr(profile, "gender", None)
        birth = getattr(profile, "birth_date", None)

    return {
        "name": name,
        "gender": gender,
        "age": _compute_age(birth),
    }


# ─────────────────────────────────────
# AI functions (async)
# ─────────────────────────────────────

async def _generate_ai_interpretation(
    spread_type: str,
    category: str,
    cards: List[Dict[str, Any]],
    question: Optional[str],
    user_ctx: Dict[str, Any],
) -> Optional[str]:
    interpreter = _get_ai_interpreter()
    if not interpreter:
        return None

    try:
        # Важно: асинхронный вызов интерпретатора
        result = await interpreter.generate_interpretation(
            spread_type=spread_type,
            category=category,
            cards=cards,
            question=question,
            user_age=user_ctx.get("age"),
            user_gender=user_ctx.get("gender"),
            user_name=user_ctx.get("name"),
        )
        if not result or not result.get("success") or not result.get("text"):
            logger.warning("AI interpretation failed: empty/invalid")
            return None
        return result["text"]
    except Exception as e:
        logger.warning("AI interpretation failed: %s", e)
        return None


async def _generate_ai_answer(
    spread: Dict[str, Any],
    question: str,
    user_ctx: Dict[str, Any],
) -> Optional[str]:
    interpreter = _get_ai_interpreter()
    if not interpreter:
        return None

    try:
        # Важно: асинхронный вызов интерпретатора
        result = await interpreter.generate_question_answer(
            spread_id=spread["id"],
            user_id=spread["user_id"],
            question=question,
            category=spread.get("category"),
            interpretation=spread.get("interpretation"),
            cards=[
                {
                    "name": getattr(c, "name", c["name"]),
                    "is_reversed": getattr(c, "is_reversed", c["is_reversed"]),
                }
                for c in spread.get("cards", [])
            ],
            user_age=user_ctx.get("age"),
            user_gender=user_ctx.get("gender"),
            user_name=user_ctx.get("name"),
        )
        if not result or not result.get("success") or not result.get("text"):
            logger.warning("AI answer failed: empty/invalid")
            return None
        return result["text"]
    except Exception as e:
        logger.warning("AI answer failed: %s", e)
        return None


# ─────────────────────────────────────
# SERVICE
# ─────────────────────────────────────

class SpreadService:
    def __init__(self):
        pass

    # 1) AUTO-расклад с AI-интерпретацией
    async def create_auto_spread(
        self,
        user_id: int,
        spread_type: str,
        category: str,
        question: Optional[str] = None,
    ) -> SpreadDetail:

        global _SPREAD_COUNTER
        spread_id = _SPREAD_COUNTER
        _SPREAD_COUNTER += 1

        cards = _build_cards(spread_type)
        cards_payload = [{"name": c.name, "is_reversed": c.is_reversed} for c in cards]

        user_ctx = _get_user_ctx(user_id)

        try:
            interp = await _generate_ai_interpretation(
                spread_type=spread_type,
                category=category,
                cards=cards_payload,
                question=question,
                user_ctx=user_ctx,
            )
        except Exception:
            interp = None

        if not interp:
            interp = (
                f"Интерпретация расклада ({spread_type}/{category})"
                + (f" с вопросом: {question}" if question else ".")
            )

        created_at = _now_iso()

        _SPREADS[spread_id] = {
            "id": spread_id,
            "user_id": user_id,
            "spread_type": spread_type,
            "category": category,
            "created_at": created_at,
            "cards": cards,
            "interpretation": interp,
            "question": question,
        }

        return SpreadDetail(
            id=spread_id,
            spread_type=spread_type,
            category=category,
            created_at=created_at,
            cards=cards,
            interpretation=interp,
            question=question,
        )

    # 2) Вопросы к раскладу (AI-ответы)
    async def add_spread_question(
        self,
        user_id: int,
        spread_id: int,
        question: str,
    ) -> SpreadQuestionModel:

        global _QUESTION_COUNTER

        spread = _SPREADS.get(spread_id)
        if not spread or spread["user_id"] != user_id:
            raise ValueError("Spread not found")

        user_ctx = _get_user_ctx(user_id)

        try:
            answer = await _generate_ai_answer(spread, question, user_ctx)
        except Exception:
            answer = None

        if not answer:
            answer = (
                "Это базовый ответ без подключения AI. "
                f"Ваш вопрос: «{question}»."
            )

        qid = _QUESTION_COUNTER
        _QUESTION_COUNTER += 1

        record = {
            "id": qid,
            "spread_id": spread_id,
            "user_id": user_id,
            "question": question,
            "answer": answer,
            "status": "ready",  # TODO: pipeline ('pending' → AI → 'ready' / 'failed')
            "created_at": _now_iso(),
        }

        key = (user_id, spread_id)
        _QUESTIONS.setdefault(key, []).append(record)
        _QUESTION_INDEX[qid] = record

        return SpreadQuestionModel(**record)

    def get_spread_questions(self, user_id: int, spread_id: int) -> SpreadQuestionsList:
        spread = _SPREADS.get(spread_id)
        if not spread or spread["user_id"] != user_id:
            raise ValueError("Spread not found")

        raw = sorted(
            _QUESTIONS.get((user_id, spread_id), []),
            key=lambda x: x["created_at"],
        )

        return SpreadQuestionsList(
            items=[SpreadQuestionModel(**q) for q in raw]
        )

    # 3) Список раскладов (основной метод)
    def get_spreads(
        self,
        user_id: int,
        page: int = 1,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """
        Основной метод для получения списка раскладов с пагинацией.
        """
        spreads = [s for s in _SPREADS.values() if s["user_id"] == user_id]
        spreads.sort(key=lambda s: s["created_at"], reverse=True)

        total_items = len(spreads)
        if limit <= 0:
            limit = 10

        total_pages = max((total_items + limit - 1) // limit, 1)
        page = max(page, 1)
        offset = (page - 1) * limit

        items_raw = spreads[offset : offset + limit]

        items: List[SpreadListItem] = []
        for s in items_raw:
            preview = (s.get("interpretation") or "")[:140]
            items.append(
                SpreadListItem(
                    id=s["id"],
                    spread_type=s["spread_type"],
                    category=s["category"],
                    created_at=s["created_at"],
                    short_preview=preview,
                    has_questions=_spread_has_questions(s),
                )
            )

        return {
            "items": items,
            "page": page,
            "total_pages": total_pages,
            "total_items": total_items,
        }

    # 4) Алиас для совместимости с роутером TMA
    def get_spreads_list(
        self,
        user_id: int,
        page: int = 1,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """
        Алиас для совместимости с роутером TMA.
        Старое имя метода, теперь просто прокидывает в get_spreads.
        """
        return self.get_spreads(user_id=user_id, page=page, limit=limit)
