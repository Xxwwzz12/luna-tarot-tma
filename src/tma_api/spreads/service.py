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
from .postgres_repository import PostgresSpreadRepository
from ..tarot_deck import draw_random_cards

logger = logging.getLogger(__name__)

# ВАЖНО:
# Этот модуль НЕ выполняет никакой очистки таблиц/данных при старте.
# Вся долговременная история раскладов/вопросов хранится в репозитории
# (InMemorySpreadRepository — только на время жизни процесса, SQLite/Postgres — в БД).
# Никаких DROP/DELETE при инициализации здесь нет.

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
    """Async-обёртка поверх AIInterpreter.generate_question_answer (для будущего pipeline)."""
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
        Финальный переключатель in-memory → SQLite → Postgres через репозитории.

        Приоритет:
        - если явно передан repo — используем его как есть;
        - иначе читаем TMA_DB_BACKEND / DATABASE_URL и выбираем:
          - backend == "postgres" и есть DATABASE_URL → PostgresSpreadRepository;
          - backend == "sqlite" → SQLiteSpreadRepository(get_connection);
          - иначе → InMemorySpreadRepository.

        Плавный fallback:
        - если Postgres не поднялся → пробуем SQLite, затем память;
        - если SQLite не поднялся → память.
        """
        if repo is not None:
            self._repo = repo
            return

        backend = os.getenv("TMA_DB_BACKEND", "").strip().lower()
        db_url = os.getenv("DATABASE_URL", "").strip()

        # 1) Попытка использовать Postgres
        if backend == "postgres" and db_url:
            try:
                self._repo = PostgresSpreadRepository()
                logger.info(
                    "SpreadService: using PostgresSpreadRepository (DATABASE_URL=%s)",
                    db_url,
                )
                return
            except Exception:
                logger.exception(
                    "Failed to init PostgresSpreadRepository, falling back to SQLite or memory"
                )
                # дальше пробуем SQLite → память

        # 2) Попытка использовать SQLite (явный backend == "sqlite")
        if backend == "sqlite":
            try:
                from src.user_database import get_connection  # type: ignore

                self._repo = SQLiteSpreadRepository(get_connection)
                logger.info("SpreadService: using SQLiteSpreadRepository")
                return
            except Exception:
                logger.exception(
                    "Failed to init SQLiteSpreadRepository, falling back to InMemorySpreadRepository"
                )

        # 3) Финальный fallback — in-memory
        logger.info("SpreadService: using InMemorySpreadRepository")
        self._repo = InMemorySpreadRepository()

    # _build_cards: сервер сам выбирает карты из своей колоды.
    def _build_cards(self, spread_type: str) -> List[Dict[str, Any]]:
        """
        Используем draw_random_cards и берём карты в том виде, как их отдаёт tarot_deck,
        добавляя только is_reversed.

        Контракт:
        - cards — это те же словари, что возвращает tarot_deck (id, code, name, suit, arcana,
          image_url, и любые другие поля);
        - мы НЕ обрезаем структуру до {name, is_reversed};
        - добавляем/переопределяем только флаг is_reversed.
        """
        count = 1 if spread_type == "one" else 3
        raw_cards = draw_random_cards(count)

        cards: List[Dict[str, Any]] = []
        for c in raw_cards:
            card = dict(c)  # копируем все поля как есть
            # случайный перевёрнутый флаг
            card["is_reversed"] = bool(random.getrandbits(1))
            cards.append(card)

        return cards

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

        Контракт с фронтом:
        - backend САМ выбирает карты из своей колоды (через _build_cards);
        - фронтовая карусель — визуальный ритуал, не влияющий на результат POST /spreads;
        - структура запроса от фронта не содержит выбранных карт, только параметры расклада
          (spread_type, category/question);
        - в ответ приходит уже готовый расклад с картами и интерпретацией.

        ВАЖНО:
        - для spread_type == "one" (карта дня) мы жёстко нормализуем значения:
          category = "daily", user_question = None,
          независимо от того, что пришло с фронта;
        - для остальных типов:
          category берём из аргумента category,
          user_question — из аргумента question.
        """
        user_ctx = _get_user_ctx(user_id)

        # 🔒 Жёсткая нормализация "карты дня"
        #
        # Эквивалент ТЗ:
        # if body.spread_type == "one":
        #     category = "daily"
        #     question = None
        # else:
        #     category = body.category
        #     question = body.question
        #
        # Здесь spread_type/category/question — уже "распакованные" поля тела запроса.
        if spread_type == "one":
            normalized_category: Optional[str] = "daily"
            user_question: Optional[str] = None
        else:
            normalized_category = category
            user_question = question

        # Явная обработка ошибок колоды
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
        # Здесь уже работаем только с нормализованной категорией
        effective_category = normalized_category or "general"

        # Структура записи для репозитория:
        # cards — ПОЛНЫЕ словари карт, сохраняем без обрезки.
        record: Dict[str, Any] = {
            # id задаст репозиторий
            "user_id": user_id,
            "spread_type": spread_type,
            "category": effective_category,   # daily/general
            "user_question": user_question,   # вопрос ДО расклада (или None для one)
            "cards": cards_payload,           # полные карточки
            "interpretation": interpretation,
            "created_at": created_at,
        }

        # Сохраняем через репозиторий и получаем id
        spread_id = self._repo.save_spread(record)
        record["id"] = spread_id  # на случай, если repo сам сгенерировал id

        # DEV-лог для дебага истории
        logger.info(
            "Created spread: user_id=%s spread_id=%s spread_type=%s category=%s created_at=%s",
            user_id,
            spread_id,
            spread_type,
            effective_category,
            created_at,
        )

        # ВАЖНО: в API отдаём ПОЛНЫЕ карточки, как в tarot_deck.
        cards_models = [CardModel(**c) for c in cards_payload]

        return SpreadDetail(
            id=spread_id,
            spread_type=spread_type,
            category=effective_category,
            created_at=created_at,
            cards=cards_models,
            interpretation=interpretation,
            question=user_question,
        )

    # Интерактивные сессии — остаются in-memory и не связаны с репозиторием
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
        Возвращает страницу истории раскладов пользователя.

        Источник данных — self._repo.list_spreads(user_id, offset, limit),
        сервис добавляет только:
        - пагинацию;
        - short_preview (первые 140 символов интерпретации);
        - флаг has_questions (по user_question + вопросам в repo);
        - "нормализованную" category для карты дня (daily).
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
            # - one → daily (независимо от того, что лежит в raw.category)
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
        Возвращает детальный расклад по id.

        Только через repo.get_spread(spread_id) и с проверкой владельца:
        - если расклад не найден или принадлежит другому пользователю —
          кидаем ValueError("spread_not_found"), роутер превратит в 404/400.

        ВАЖНО:
        - cards в репозитории должны быть теми же словарями, что вернул tarot_deck;
        - в API отдаём CardModel(**card_dict), без кастомного урезания структуры.
        """
        raw = self._repo.get_spread(spread_id)
        if not raw or raw.get("user_id") != user_id:
            raise ValueError("spread_not_found")

        cards_payload = raw.get("cards") or []

        # Здесь тоже — полные карты Deck → CardModel.
        cards_models = [CardModel(**c) for c in cards_payload]

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
        Вопрос к УЖЕ существующему раскладу.

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
        Список вопросов по раскладу.

        Сначала убеждаемся, что расклад принадлежит пользователю,
        затем берём вопросы через repo.list_questions(spread_id).
        """
        raw_spread = self._repo.get_spread(spread_id)
        if not raw_spread or raw_spread.get("user_id") != user_id:
            raise ValueError("spread_not_found")

        rows = self._repo.list_questions(spread_id)
        # На всякий случай сортируем по created_at от старых к новым
        rows_sorted = sorted(rows, key=lambda r: r.get("created_at") or "")

        items = [SpreadQuestionModel(**row) for row in rows_sorted]
        return SpreadQuestionsList(items=items)
