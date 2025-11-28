from __future__ import annotations  # должна быть первой строкой

import logging
import os
import random
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
from ..tarot_deck import draw_random_cards  # ✅ обновлённый draw_random_cards

logger = logging.getLogger(__name__)

# 🔧 In-memory storage (используются InMemorySpreadRepository)
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
    """Флаг has_questions для списка/деталей раскладов."""
    if s.get("user_question") and str(s["user_question"]).strip():
        return True
    return len(_QUESTIONS.get((s["user_id"], s["id"]), [])) > 0


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
        name = getattr(profile, "username", None) or getattr(
            profile, "first_name", None
        )
        gender = getattr(profile, "gender", None)
        birth = getattr(profile, "birth_date", None)

    return UserContext(
        id=user_id,
        name=name,
        age=_compute_age(birth),
        gender=gender,
    )


def _generate_basic_interpretation(
    spread_type: str,
    category: Optional[str],
    user_question: Optional[str],
) -> str:
    """
    A.4 — базовый fallback, если AI совсем ничего не дал.
    """
    cat = category or "general"
    if user_question:
        return (
            f"Интерпретация расклада ({spread_type}/{cat}) "
            f"с учётом вопроса: {user_question}"
        )
    return f"Интерпретация расклада ({spread_type}/{cat})."


# ─────────────────────────────────────
# Repositories: in-memory & SQLite stub
# ─────────────────────────────────────

class InMemorySpreadRepository:
    """
    In-memory реализация на основе модульных словарей _SPREADS / _QUESTIONS.
    """

    def save_spread(self, record: Dict[str, Any]) -> None:
        _SPREADS[record["id"]] = record

    def list_spreads(self, user_id: int) -> List[Dict[str, Any]]:
        return [s for s in _SPREADS.values() if s["user_id"] == user_id]

    def get_spread(self, user_id: int, spread_id: int) -> Optional[Dict[str, Any]]:
        s = _SPREADS.get(spread_id)
        if not s or s["user_id"] != user_id:
            return None
        return s

    def save_question(self, record: Dict[str, Any]) -> None:
        key = (record["user_id"], record["spread_id"])
        _QUESTIONS.setdefault(key, []).append(record)
        _QUESTION_INDEX[record["id"]] = record

    def list_questions(self, user_id: int, spread_id: int) -> List[Dict[str, Any]]:
        return _QUESTIONS.get((user_id, spread_id), [])


class SQLiteSpreadRepository:
    """
    Заглушка под будущую реализацию через SQLite.
    Сейчас создаётся только если TMA_USE_SQLITE=1,
    но методы пока не реализованы.
    """

    def __init__(self, get_connection):
        self._get_connection = get_connection

    def save_spread(self, record: Dict[str, Any]) -> None:
        raise NotImplementedError("SQLiteSpreadRepository.save_spread is not implemented yet")

    def list_spreads(self, user_id: int) -> List[Dict[str, Any]]:
        raise NotImplementedError("SQLiteSpreadRepository.list_spreads is not implemented yet")

    def get_spread(self, user_id: int, spread_id: int) -> Optional[Dict[str, Any]]:
        raise NotImplementedError("SQLiteSpreadRepository.get_spread is not implemented yet")

    def save_question(self, record: Dict[str, Any]) -> None:
        raise NotImplementedError("SQLiteSpreadRepository.save_question is not implemented yet")

    def list_questions(self, user_id: int, spread_id: int) -> List[Dict[str, Any]]:
        raise NotImplementedError("SQLiteSpreadRepository.list_questions is not implemented yet")


# ─────────────────────────────────────
# AI wrappers
# ─────────────────────────────────────

async def _generate_ai_interpretation(
    spread_type: str,
    category: Optional[str],
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
        return str(result["text"]).strip()
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
        return str(result["text"]).strip()
    except Exception as e:
        logger.warning("AI answer exception: %s", e)
        return None


# ─────────────────────────────────────
# SERVICE
# ─────────────────────────────────────

class SpreadService:
    def __init__(self, repo: Any | None = None):
        """
        C.3 — Переключатель in-memory → SQLite через репозиторий.

        Приоритет:
        - если явно передан repo — используем его;
        - иначе смотрим TMA_USE_SQLITE:
          - "1" → пытаемся создать SQLiteSpreadRepository(get_connection);
          - иначе → InMemorySpreadRepository().
        """
        if repo is not None:
            self._repo = repo
        else:
            use_sqlite = os.getenv("TMA_USE_SQLITE", "0") == "1"
            if use_sqlite:
                try:
                    from src.user_database import get_connection  # type: ignore

                    self._repo = SQLiteSpreadRepository(get_connection)
                    logger.info("SpreadService: using SQLiteSpreadRepository")
                except Exception:
                    logger.warning(
                        "Failed to init SQLiteSpreadRepository, falling back to InMemorySpreadRepository",
                        exc_info=True,
                    )
                    self._repo = InMemorySpreadRepository()
            else:
                self._repo = InMemorySpreadRepository()
                logger.info("SpreadService: using InMemorySpreadRepository")

    # T2.1 — _build_cards как метод сервиса, работающий с обновлённой колодой
    def _build_cards(self, spread_type: str) -> List[Dict[str, Any]]:
        """
        T2.1 — Используем обновлённый draw_random_cards и приводим
        карты к "плоскому" dict-формату, который дальше уходит:
        - в _SPREADS/БД,
        - в AI,
        - в сборку CardModel.
        """
        if spread_type == "one":
            count = 1
        else:
            count = 3

        raw_cards = draw_random_cards(count)

        cards_payload: List[Dict[str, Any]] = []
        for card in raw_cards:
            is_reversed = bool(random.getrandbits(1))

            cards_payload.append(
                {
                    "id": card.get("id"),
                    "name": card.get("name"),
                    "suit": card.get("suit"),
                    "arcana": card.get("type"),  # major/minor
                    "image_url": card.get("image_url"),
                    "is_reversed": is_reversed,
                }
            )

        return cards_payload

    # AUTO-расклад
    async def create_auto_spread(
        self,
        user_id: int,
        spread_type: str,
        category: str | None = None,
        question: str | None = None,
    ) -> SpreadDetail:
        """
        Создать авто-расклад, вызвать AI и сохранить интерпретацию через self._repo.

        - question здесь — «вопрос до расклада» (user_question);
        - для spread_type == "one" считаем это картой дня:
          category="daily", user_question=None.
        """
        global _SPREAD_COUNTER
        spread_id = _SPREAD_COUNTER
        _SPREAD_COUNTER += 1

        user_ctx = _get_user_ctx(user_id)

        # «Вопрос до расклада»
        user_question = question
        normalized_category = category

        # Логика "Карты дня" — one → daily, без вопроса
        if spread_type == "one":
            normalized_category = "daily"
            user_question = None

        # T2.2 — явная обработка ошибок колоды
        try:
            cards_payload = self._build_cards(spread_type)
        except Exception as e:
            logger.exception("Failed to build cards for spread_type=%s: %s", spread_type, e)
            # ValueError → роутер превратит в 400 с нормальным APIError
            raise ValueError(f"tarot_deck_error: {e}") from e

        # Пытаемся получить интерпретацию через AI
        try:
            interpretation = await _generate_ai_interpretation(
                spread_type=spread_type,
                category=normalized_category,
                cards_payload=cards_payload,
                question=user_question,
                user_ctx=user_ctx,
            )
        except Exception:
            interpretation = None

        # A.4 — гарантированный fallback + нормализация
        if not interpretation or not interpretation.strip():
            interpretation = _generate_basic_interpretation(
                spread_type=spread_type,
                category=normalized_category,
                user_question=user_question,
            )
        interpretation = interpretation.strip()

        created_at = _now_iso()
        effective_category = normalized_category or "general"

        # Структура записи — A.5
        record: Dict[str, Any] = {
            "id": spread_id,
            "user_id": user_id,
            "spread_type": spread_type,
            "category": effective_category,   # daily/general
            "user_question": user_question,   # вопрос ДО расклада
            "cards": cards_payload,           # raw-пэйлоад колоды
            "interpretation": interpretation,
            "created_at": created_at,
        }

        # C.3 — сохраняем через репозиторий
        self._repo.save_spread(record)

        # Для ответа API собираем CardModel (минимальный вид)
        cards_models = [
            CardModel(
                position=i + 1,
                name=c.get("name") or "",
                is_reversed=bool(c.get("is_reversed")),
            )
            for i, c in enumerate(cards_payload)
        ]

        return SpreadDetail(
            id=spread_id,
            spread_type=spread_type,
            category=effective_category,
            created_at=created_at,
            cards=cards_models,
            interpretation=interpretation,
            question=user_question,
        )

    # Интерактивные сессии — остаются in-memory
    def create_interactive_session(self, user_id: int, spread_type: str, category: str):
        session_id = str(uuid4())
        total = 1 if spread_type == "one" else 3

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
        """
        C.3 — теперь берём список через repo.list_spreads(user_id),
        а пагинацию/модели строим в сервисе.
        """
        spreads = self._repo.list_spreads(user_id)
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

            # Категория в списке:
            # - one → daily
            # - иначе — сохранённая или general
            if s.get("spread_type") == "one":
                item_category = "daily"
            else:
                item_category = s.get("category") or "general"

            items.append(
                SpreadListItem(
                    id=s["id"],
                    spread_type=s["spread_type"],
                    category=item_category,
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
        """
        C.3 — теперь через repo.get_spread(user_id, spread_id).
        """
        s = self._repo.get_spread(user_id, spread_id)
        if not s:
            return None

        cards_payload = s.get("cards") or []
        cards_models = [
            CardModel(
                position=i + 1,
                name=c.get("name") or "",
                is_reversed=bool(c.get("is_reversed")),
            )
            for i, c in enumerate(cards_payload)
        ]

        return SpreadDetail(
            id=s["id"],
            spread_type=s["spread_type"],
            category=s.get("category") or "general",
            created_at=s["created_at"],
            cards=cards_models,
            interpretation=s.get("interpretation"),
            question=s.get("user_question"),
        )

    # Вопросы
    async def add_spread_question(
        self,
        user_id: int,
        spread_id: int,
        question: str,
    ) -> SpreadQuestionModel:
        """
        Вопрос к УЖЕ существующему раскладу.
        A.6 — question здесь НЕ вопрос до расклада, а уточнение к нему.
        user_question в _SPREADS / БД не трогаем.
        """
        global _QUESTION_COUNTER

        spread = self._repo.get_spread(user_id, spread_id)
        if not spread:
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
            "status": "ready",  # TODO: pipeline pending → AI → ready/failed
            "created_at": _now_iso(),
        }

        # C.3 — сохраняем через репозиторий
        self._repo.save_question(record)

        return SpreadQuestionModel(**record)

    def get_spread_questions(self, user_id: int, spread_id: int):
        """
        C.3 — список вопросов по раскладу через repo.list_questions(...)
        """
        # убедимся, что расклад существует и принадлежит пользователю
        spread = self._repo.get_spread(user_id, spread_id)
        if not spread:
            raise ValueError("Spread not found")

        lst = sorted(
            self._repo.list_questions(user_id, spread_id),
            key=lambda x: x["created_at"],
        )
        return SpreadQuestionsList(items=[SpreadQuestionModel(**q) for q in lst])
