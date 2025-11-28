from __future__ import annotations  # MUST be the first line

import logging
from dataclasses import dataclass
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
    """Флаг has_questions."""
    if s.get("question") and str(s["question"]).strip():
        return True
    return len(_QUESTIONS.get((s["user_id"], s["id"]), [])) > 0


def _build_cards(spread_type: str) -> List[CardModel]:
    """Простая заглушка выбора карт."""
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
    """Singleton AIInterpreter."""
    global _ai_interpreter
    if _ai_interpreter is not None:
        return _ai_interpreter

    try:
        from ...ai_interpreter import AIInterpreter  # type: ignore
        _ai_interpreter = AIInterpreter()
    except Exception as e:
        logger.warning("AIInterpreter unavailable for TMA: %s", e)
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


@dataclass
class UserContext:
    id: int
    name: Optional[str]
    age: Optional[int]
    gender: Optional[str]


def _get_user_ctx(user_id: int) -> UserContext:
    """Пытаемся достать профиль мягко."""
    profile: Any = None

    try:
        from ...profile_service import ProfileService  # type: ignore
        profile = ProfileService().get_profile(user_id=user_id)
    except Exception:
        profile = None

    if profile is None:
        try:
            from ...user_database import get_user_by_id  # type: ignore
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

    return UserContext(
        id=user_id,
        name=name,
        age=_compute_age(birth),
        gender=gender,
    )


# ─────────────────────────────────────
# AI wrappers
# ─────────────────────────────────────

async def _generate_ai_interpretation(
    spread_type: str,
    category: str,
    cards_payload: List[Dict[str, Any]],
    question: Optional[str],
    user_ctx: UserContext,
) -> Optional[str]:

    interpreter = _get_ai_interpreter()
    if not interpreter:
        return None

    try:
        result = await interpreter.generate_interpretation(
            spread_type=spread_type,
            cards=cards_payload,
            category=category,
            question=question,
            user_age=user_ctx.age,
            user_gender=user_ctx.gender,
            user_name=user_ctx.name,
        )
        if not result or not result.get("success") or not result.get("text"):
            logger.warning("AI interpretation failed: empty")
            return None
        return result["text"].strip()
    except Exception as e:
        logger.warning("AI interpretation exception: %s", e)
        return None


async def _generate_ai_answer(
    spread: Dict[str, Any],
    question: str,
    user_ctx: UserContext,
) -> Optional[str]:

    interpreter = _get_ai_interpreter()
    if not interpreter:
        return None

    try:
        result = await interpreter.generate_question_answer(
            spread_id=spread["id"],
            user_id=user_ctx.id,
            question=question,
            user_age=user_ctx.age,
            user_gender=user_ctx.gender,
            user_name=user_ctx.name,
        )
        if not result or not result.get("success") or not result.get("text"):
            logger.warning("AI answer failed: empty")
            return None
        return result["text"].strip()
    except Exception as e:
        logger.warning("AI answer exception: %s", e)
        return None


# ─────────────────────────────────────
# SERVICE
# ─────────────────────────────────────

class SpreadService:
    def __init__(self):
        pass

    # AUTO-расклад
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
            interpretation = await _generate_ai_interpretation(
                spread_type=spread_type,
                category=category,
                cards_payload=cards_payload,
                question=question,
                user_ctx=user_ctx,
            )
        except Exception:
            interpretation = None

        if not interpretation:
            if question:
                interpretation = (
                    f"Интерпретация расклада ({spread_type}/{category}) "
                    f"с вопросом: {question}"
                )
            else:
                interpretation = f"Интерпретация расклада ({spread_type}/{category})."

        created_at = _now_iso()

        _SPREADS[spread_id] = {
            "id": spread_id,
            "user_id": user_id,
            "spread_type": spread_type,
            "category": category,
            "created_at": created_at,
            "cards": cards,
            "interpretation": interpretation,
            "question": question,
        }

        return SpreadDetail(
            id=spread_id,
            spread_type=spread_type,
            category=category,
            created_at=created_at,
            cards=cards,
            interpretation=interpretation,
            question=question,
        )

    # Интерактивные сессии — как было
    def create_interactive_session(self, user_id: int, spread_type: str, category: str):
        session_id = str(uuid4())
        total = 1 if spread_type == "single" else 3

        session = {
            "session_id": session_id,
            "user_id": user_id,
            "spread_type": spread_type,
            "category": category,
            "total_positions": total,
            "selected_cards": {},
            "current_position": 1,
            "status": "awaiting_selection",
        }
        _SESSIONS[session_id] = session
        return session

    def select_card(self, session_id: str, pos: int, choice: int):
        session = _SESSIONS.get(session_id)
        if not session:
            return None

        if session["status"] != "awaiting_selection":
            return None

        total = session["total_positions"]
        if not (1 <= pos <= total):
            return None

        session["selected_cards"][pos] = {
            "position": pos,
            "name": f"Карта {choice}",
            "is_reversed": (choice % 2 == 0),
        }

        if len(session["selected_cards"]) < total:
            session["current_position"] = pos + 1
            return session

        session["status"] = "completed"

        cards = [
            CardModel(
                position=v["position"],
                name=v["name"],
                is_reversed=v["is_reversed"],
            )
            for _, v in sorted(session["selected_cards"].items())
        ]

        interpretation = (
            f"Интерактивный расклад: {session['spread_type']}/{session['category']}"
        )

        return {
            "session": session,
            "spread": SpreadDetail(
                id=-1,
                spread_type=session["spread_type"],
                category=session["category"],
                created_at=_now_iso(),
                cards=cards,
                interpretation=interpretation,
                question=None,
            ),
        }

    # Список раскладов
    def get_spreads(
        self,
        user_id: int,
        page: int = 1,
        limit: int = 10,
    ) -> Dict[str, Any]:

        spreads = [s for s in _SPREADS.values() if s["user_id"] == user_id]
        spreads.sort(key=lambda s: s["created_at"], reverse=True)

        total = len(spreads)
        if limit <= 0:
            limit = 10

        total_pages = max((total + limit - 1) // limit, 1)
        page = max(page, 1)
        offset = (page - 1) * limit

        items_raw = spreads[offset : offset + limit]

        items: List[SpreadListItem] = []

        for s in items_raw:
            interpretation = s.get("interpretation") or ""
            short_preview = (
                interpretation[:140].rstrip() if interpretation else None
            )

            items.append(
                SpreadListItem(
                    id=s["id"],
                    spread_type=s["spread_type"],
                    category=s.get("category") or "general",
                    created_at=s["created_at"],
                    short_preview=short_preview,
                    has_questions=_spread_has_questions(s),
                    interpretation=interpretation,
                )
            )

        return {
            "items": items,
            "page": page,
            "total_pages": total_pages,
            "total_items": total,
        }

    # Алиас для совместимости
    def get_spreads_list(self, user_id: int, page: int = 1, limit: int = 10):
        return self.get_spreads(user_id=user_id, page=page, limit=limit)

    # Детальный расклад
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
            question=s.get("question"),
        )

    # Вопросы
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
                "Это базовый ответ без AI. "
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
            "status": "ready",
            "created_at": _now_iso(),
        }

        key = (user_id, spread_id)
        _QUESTIONS.setdefault(key, []).append(record)
        _QUESTION_INDEX[qid] = record

        return SpreadQuestionModel(**record)

    def get_spread_questions(self, user_id: int, spread_id: int):
        spread = _SPREADS.get(spread_id)
        if not spread or spread["user_id"] != user_id:
            raise ValueError("Spread not found")

        lst = sorted(
            _QUESTIONS.get((user_id, spread_id), []),
            key=lambda x: x["created_at"],
        )
        return SpreadQuestionsList(items=[SpreadQuestionModel(**q) for q in lst])
