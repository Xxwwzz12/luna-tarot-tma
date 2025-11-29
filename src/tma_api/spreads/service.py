from __future__ import annotations  # должна быть первой строкой

import logging
import os
import random
from dataclasses import dataclass
from datetime import datetime, date
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .models import (
    CardModel,
    SpreadDetail,
    SpreadListItem,
    SpreadQuestionModel,
    SpreadQuestionsList,
)
from .repository import (
    SpreadRepository,
    InMemorySpreadRepository,
    SQLiteSpreadRepository,
)
from ..tarot_deck import draw_random_cards  # обновлённый draw_random_cards

logger = logging.getLogger(__name__)

# Интерактивные сессии остаются чисто in-memory
_SESSIONS: Dict[str, Dict[str, Any]] = {}

_ai_interpreter: Any | None = None


# ─────────────────────────────────────
# Utils
# ─────────────────────────────────────

def _now_iso() -> str:
    return datetime.utcnow().isoformat()


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
    """Пытаемся достать профиль мягко (ProfileService → user_database)."""
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
    """Базовый fallback, если AI ничего не дал."""
    cat = category or "general"
    if user_question:
        return (
            f"Интерпретация расклада ({spread_type}/{cat}) "
            f"с учётом вопроса: {user_question}"
        )
    return f"Интерпретация расклада ({spread_type}/{cat})."


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


async def _generate_ai_interpretation(
    spread_type: str,
    category: Optional[str],
    cards_payload: List[Dict[str, Any]],
    question: Optional[str],
    user_ctx: UserContext,
) -> Optional[str]:
    """Async-обёртка поверх AIInterpreter.generate_interpretation."""
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
    """Async-обёртка поверх AIInterpreter.generate_question_answer (пока не используется)."""
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


def _spread_has_questions(repo: SpreadRepository, spread: Dict[str, Any]) -> bool:
    """
    Флаг has_questions:

    - true, если есть user_question (вопрос до расклада),
    - или если есть хотя бы один записанный вопрос по раскладу.
    """
    if spread.get("user_question") and str(spread["user_question"]).strip():
        return True
    try:
        questions = repo.list_questions(spread["id"])
    except Exception:
        return False
    return len(questions) > 0


# ─────────────────────────────────────
# SERVICE
# ─────────────────────────────────────

class SpreadService:
    def __init__(self, repo: SpreadRepository | None = None):
        """
        ТЗ 23.4 — финальный переключатель in-memory → SQLite.

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
                    logger.exception(
                        "Failed to init SQLiteSpreadRepository, falling back to InMemorySpreadRepository"
                    )
                    self._repo = InMemorySpreadRepository()
            else:
                logger.info("SpreadService: using InMemorySpreadRepository")
                self._repo = InMemorySpreadRepository()

    # T2.1 — _build_cards как метод сервиса, работающий с обновлённой колодой
    def _build_cards(self, spread_type: str) -> List[Dict[str, Any]]:
        """
        Используем обновлённый draw_random_cards и приводим
        карты к "плоскому" dict-формату, который дальше уходит:
        - в репозиторий (_repo.save_spread),
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
            logger.exception(
                "Failed to build cards for spread_type=%s: %s", spread_type, e
            )
            # ValueError → роутер превратит в 400 с понятным APIError
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

        # Гарантированный fallback + нормализация
        if not interpretation or not interpretation.strip():
            interpretation = _generate_basic_interpretation(
                spread_type=spread_type,
                category=normalized_category,
                user_question=user_question,
            )
        interpretation = interpretation.strip()

        created_at = _now_iso()
        effective_category = normalized_category or "general"

        # Структура записи для репозитория
        record: Dict[str, Any] = {
            # id задаст репозиторий
            "user_id": user_id,
            "spread_type": spread_type,
            "category": effective_category,   # daily/general
            "user_question": user_question,   # вопрос ДО расклада
            "cards": cards_payload,           # raw-пэйлоад колоды
            "interpretation": interpretation,
            "created_at": created_at,
        }

        # 4.2 — сохраняем через репозиторий и получаем id
        spread_id = self._repo.save_spread(record)
        record["id"] = spread_id  # на случай, если repo сам сгенерировал id

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
        4.3 — список через repo.list_spreads(user_id, offset, limit),
        а пагинация/модели строятся в сервисе.
        """
        if limit <= 0:
            limit = 10
        page = max(page, 1)
        offset = (page - 1) * limit

        total_items, items_raw = self._repo.list_spreads(
            user_id=user_id,
            offset=offset,
            limit=limit,
        )
        total_pages = max((total_items + limit - 1) // limit, 1)

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
                    has_questions=_spread_has_questions(self._repo, s),
                    interpretation=interpretation,
                )
            )

        return {
            "items": items,
            "page": page,
            "total_pages": total_pages,
            "total_items": total_items,
        }

    # Алиас для совместимости
    def get_spreads_list(self, user_id: int, page: int = 1, limit: int = 10):
        return self.get_spreads(user_id=user_id, page=page, limit=limit)

    # Детальный расклад
    def get_spread(self, user_id: int, spread_id: int) -> SpreadDetail:
        """
        4.4 — только через repo.get_spread(spread_id) и проверку владельца.
        """
        raw = self._repo.get_spread(spread_id)
        if not raw or raw.get("user_id") != user_id:
            raise ValueError("spread_not_found")

        cards_payload = raw.get("cards") or []
        cards_models = [
            CardModel(
                position=i + 1,
                name=c.get("name") or "",
                is_reversed=bool(c.get("is_reversed")),
            )
            for i, c in enumerate(cards_payload)
        ]

        return SpreadDetail(
            id=raw["id"],
            spread_type=raw["spread_type"],
            category=raw.get("category") or "general",
            created_at=raw["created_at"],
            cards=cards_models,
            interpretation=raw.get("interpretation"),
            question=raw.get("user_question"),
        )

    # Вопросы
    async def add_spread_question(
        self,
        user_id: int,
        spread_id: int,
        question: str,
    ) -> SpreadQuestionModel:
        """
        4.5 — Вопрос к УЖЕ существующему раскладу.

        Здесь question — уточнение к раскладу (не вопрос до расклада).
        Ответ и статус на этом этапе: answer=None, status="pending".
        """
        # Проверяем, что расклад существует и принадлежит user_id
        raw_spread = self._repo.get_spread(spread_id)
        if not raw_spread or raw_spread.get("user_id") != user_id:
            raise ValueError("spread_not_found")

        created_at = _now_iso()
        record: Dict[str, Any] = {
            "spread_id": spread_id,
            "user_id": user_id,
            "question": question,
            "answer": None,
            "status": "pending",
            "created_at": created_at,
        }

        qid = self._repo.save_question(record)
        record["id"] = qid

        return SpreadQuestionModel(**record)

    def get_spread_questions(self, user_id: int, spread_id: int) -> SpreadQuestionsList:
        """
        4.5 — сначала убеждаемся, что расклад не чужой,
        затем берём список вопросов через repo.list_questions(spread_id).
        """
        raw_spread = self._repo.get_spread(spread_id)
        if not raw_spread or raw_spread.get("user_id") != user_id:
            raise ValueError("spread_not_found")

        rows = self._repo.list_questions(spread_id)
        # На всякий случай сортируем по created_at от старых к новым
        rows_sorted = sorted(rows, key=lambda r: r.get("created_at") or "")

        items = [SpreadQuestionModel(**row) for row in rows_sorted]
        return SpreadQuestionsList(items=items)
