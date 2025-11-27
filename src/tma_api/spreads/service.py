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

# 🔧 Временная in-memory "база данных"

_SPREADS: Dict[int, Dict[str, Any]] = {}
_SPREAD_COUNTER: int = 1

_QUESTIONS: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
_QUESTION_INDEX: Dict[int, Dict[str, Any]] = {}
_QUESTION_COUNTER: int = 1

_SESSIONS: Dict[str, Dict[str, Any]] = {}

# Ленивый singleton для AIInterpreter
_ai_interpreter: Any | None = None


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _spread_has_questions(spread: Dict[str, Any]) -> bool:
    """Есть ли вопросы к раскладу или непустой question."""
    if spread.get("question") and str(spread["question"]).strip():
        return True

    key = (spread["user_id"], spread["id"])
    return len(_QUESTIONS.get(key, [])) > 0


def _build_cards(spread_type: str) -> List[CardModel]:
    """Генерация карточек (заглушки для AUTO-режима)."""
    total = 1 if spread_type == "single" else 3
    cards = [
        CardModel(
            position=i,
            name=f"Карта {i}",
            is_reversed=(i % 2 == 0),
        )
        for i in range(1, total + 1)
    ]
    return cards


def _get_ai_interpreter() -> Any | None:
    """Ленивый singleton AIInterpreter."""
    global _ai_interpreter

    if _ai_interpreter is not None:
        return _ai_interpreter

    try:
        from ...ai_interpreter import AIInterpreter  # type: ignore

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
    years = today.year - d.year - ((today.month, today.day) < (d.month, d.day))
    return max(years, 0)


def _get_user_context(user_id: int) -> Dict[str, Any]:
    """Пытаемся достать профиль пользователя для AI (мягко, без падений)."""
    profile = None

    # Вариант 1: ProfileService
    try:
        from ...profile_service import ProfileService  # type: ignore

        svc = ProfileService()
        profile = svc.get_profile(user_id=user_id)
    except Exception:
        profile = None

    # Вариант 2: user_database
    if profile is None:
        try:
            from ...user_database import get_user_by_id  # type: ignore

            profile = get_user_by_id(user_id)
        except Exception:
            profile = None

    name = None
    gender = None
    birth_date = None

    if isinstance(profile, dict):
        name = profile.get("username") or profile.get("first_name")
        gender = profile.get("gender")
        birth_date = profile.get("birth_date")
    elif profile is not None:
        try:
            name = getattr(profile, "username", None) or getattr(
                profile, "first_name", None
            )
            gender = getattr(profile, "gender", None)
            birth_date = getattr(profile, "birth_date", None)
        except Exception:
            pass

    age = _compute_age(birth_date)

    return {
        "name": name,
        "age": age,
        "gender": gender,
    }


async def _generate_ai_interpretation(
    spread_type: str,
    category: str,
    cards_payload: List[Dict[str, Any]],
    question: Optional[str],
    user_ctx: Dict[str, Any],
) -> str:
    """
    Первый слой интеграции AI для интерпретации расклада.
    ASYNC-версия: вызывается с await внутри create_auto_spread.
    """
    if question:
        fallback = (
            f"Интерпретация расклада ({spread_type}/{category}) "
            f"с учётом вопроса: {question}"
        )
    else:
        fallback = f"Интерпретация расклада ({spread_type}/{category})."

    ai = _get_ai_interpreter()
    if not ai:
        return fallback

    try:
        # generate_interpretation может быть синхронным — просто вызываем его из async-контекста
        text = ai.generate_interpretation(
            spread_type=spread_type,
            category=category,
            cards=cards_payload,
            question=question,
            user_name=user_ctx.get("name"),
            user_age=user_ctx.get("age"),
            user_gender=user_ctx.get("gender"),
        )
        if not text or not isinstance(text, str):
            raise ValueError("empty AI interpretation")
        return text.strip()
    except Exception as e:
        logger.warning("AI interpretation failed, using fallback: %s", e)
        return fallback


async def _generate_ai_answer(
    spread: Dict[str, Any],
    question: str,
    user_ctx: Dict[str, Any],
) -> str:
    """
    Первый слой интеграции AI для ответов на вопросы к раскладу.
    ASYNC-версия: вызывается с await внутри add_spread_question.
    """
    cards_payload = [
        {
            "name": getattr(c, "name", c["name"]),
            "is_reversed": getattr(c, "is_reversed", c["is_reversed"]),
        }
        for c in spread.get("cards", [])
    ]

    fallback = (
        "Это базовый ответ без подключения основного AI. "
        f"Ваш вопрос: «{question}». Опирайтесь на общую интерпретацию расклада."
    )

    ai = _get_ai_interpreter()
    if not ai:
        return fallback

    try:
        text = ai.generate_question_answer(
            spread_id=spread["id"],
            user_id=spread["user_id"],
            question=question,
            category=spread.get("category"),
            interpretation=spread.get("interpretation"),
            cards=cards_payload,
            user_name=user_ctx.get("name"),
            user_age=user_ctx.get("age"),
            user_gender=user_ctx.get("gender"),
        )
        if not text or not isinstance(text, str):
            raise ValueError("empty AI answer")
        return text.strip()
    except Exception as e:
        logger.warning("AI question-answer failed, using fallback: %s", e)
        return fallback


class SpreadService:
    def __init__(self):
        pass

    # ───────────────────────────────
    # 1. AUTO РАСКЛАД + AI интерпретация (ASYNC)
    # ───────────────────────────────
    async def create_auto_spread(
        self,
        user_id: int,
        spread_type: str,
        category: str,
        question: str | None = None,
    ) -> SpreadDetail:
        """
        Создать расклад в авто-режиме.
        Ждём _generate_ai_interpretation через await.
        """
        global _SPREAD_COUNTER
        spread_id = _SPREAD_COUNTER
        _SPREAD_COUNTER += 1

        cards = _build_cards(spread_type)
        user_ctx = _get_user_context(user_id)

        cards_payload = [{"name": c.name, "is_reversed": c.is_reversed} for c in cards]

        try:
            interpretation = await _generate_ai_interpretation(
                spread_type=spread_type,
                category=category,
                cards_payload=cards_payload,
                question=question,
                user_ctx=user_ctx,
            )
        except Exception as e:
            logger.warning("AI interpretation wrapper failed: %s", e)
            # fallback прямо здесь, чтобы точно не упасть
            if question:
                interpretation = (
                    f"Интерпретация расклада ({spread_type}/{category}) "
                    f"с учётом вопроса: {question}"
                )
            else:
                interpretation = (
                    f"Интерпретация расклада ({spread_type}/{category})."
                )

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

        spread = SpreadDetail(
            id=spread_id,
            spread_type=spread_type,
            category=category,
            created_at=created_at,
            cards=cards,
            interpretation=interpretation,
            question=question,
        )
        return spread

    # ───────────────────────────────
    # 2. Интерактивные сессии (пока sync)
    # ───────────────────────────────
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

    def select_card(self, session_id: str, position: int, choice_index: int):
        session = _SESSIONS.get(session_id)
        if not session:
            return None

        if session["status"] != "awaiting_selection":
            return None

        total = session["total_positions"]
        if not (1 <= position <= total):
            return None

        session["selected_cards"][position] = {
            "position": position,
            "name": f"Карта {choice_index}",
            "is_reversed": (choice_index % 2 == 0),
        }

        if len(session["selected_cards"]) < total:
            session["current_position"] = position + 1
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

        # Здесь оставляем более простой текст, без отдельного AI-вызова
        # (основная интерпретация уже сделана выше для auto-расклада).
        spread_detail = SpreadDetail(
            id=-1,
            spread_type=session["spread_type"],
            category=session["category"],
            created_at=_now_iso(),
            cards=cards,
            interpretation=(
                f"Интерпретация интерактивного расклада: "
                f"{session['spread_type']}/{session['category']}"
            ),
            question=None,
        )

        return {
            "session": session,
            "spread": spread_detail,
        }

    # ───────────────────────────────
    # 3. Список раскладов
    # ───────────────────────────────
    def get_spreads_list(self, user_id: int, page: int, limit: int):
        spreads = [s for s in _SPREADS.values() if s["user_id"] == user_id]
        spreads.sort(key=lambda s: s["created_at"], reverse=True)

        total = len(spreads)
        limit = max(limit, 1)
        total_pages = max((total + limit - 1) // limit, 1)
        page = max(page, 1)

        start = (page - 1) * limit
        items_raw = spreads[start : start + limit]

        items: List[SpreadListItem] = []
        for s in items_raw:
            preview = (s["interpretation"] or "")[:140]
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
            "total_items": total,
        }

    # ───────────────────────────────
    # 4. Детальный расклад
    # ───────────────────────────────
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

    # ───────────────────────────────
    # 5. Вопросы (новый интерфейс: SpreadQuestion*, с AI-ответами, ASYNC)
    # ───────────────────────────────
    async def add_spread_question(
        self,
        user_id: int,
        spread_id: int,
        question: str,
    ) -> SpreadQuestionModel:
        """
        Создать вопрос к раскладу.
        Ждём _generate_ai_answer через await.
        """
        global _QUESTION_COUNTER

        spread = _SPREADS.get(spread_id)
        if not spread or spread["user_id"] != user_id:
            raise ValueError("Spread not found")

        user_ctx = _get_user_context(user_id)

        try:
            answer = await _generate_ai_answer(spread, question, user_ctx)
        except Exception as e:
            logger.warning("AI answer wrapper failed: %s", e)
            answer = (
                "Это базовый ответ без подключения основного AI. "
                f"Ваш вопрос: «{question}». Опирайтесь на общие тенденции расклада."
            )

        question_id = _QUESTION_COUNTER
        _QUESTION_COUNTER += 1

        record: Dict[str, Any] = {
            "id": question_id,
            "spread_id": spread_id,
            "user_id": user_id,
            "question": question,
            "answer": answer,
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

        lst = sorted(
            _QUESTIONS.get((user_id, spread_id), []),
            key=lambda q: q["created_at"],
        )

        items = [SpreadQuestionModel(**q) for q in lst]
        return SpreadQuestionsList(items=items)

    # ───────────────────────────────
    # 6. Старый интерфейс (dict) — совместимость
    # ───────────────────────────────
    async def create_question(self, user_id: int, spread_id: int, text: str):
        """
        Старый метод, теперь просто async-обёртка над add_spread_question.
        """
        try:
            q = await self.add_spread_question(user_id, spread_id, text)
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
