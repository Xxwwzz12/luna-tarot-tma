# src/tma_api/spreads/sqlite_repository.py

from __future__ import annotations

import json
import sqlite3
from typing import Any, Callable, Iterable, Optional, Tuple, List

from .repository import SpreadRepository


class SQLiteSpreadRepository(SpreadRepository):
    """
    Реализация SpreadRepository поверх SQLite.

    Ожидает фабрику соединений, чтобы не завязываться на конкретный способ
    инициализации БД (in-memory / файл / пул и т.п.).

    conn_factory: Callable[[], sqlite3.Connection]
    """

    def __init__(self, conn_factory: Callable[[], sqlite3.Connection]) -> None:
        self._conn_factory = conn_factory

    # -------------------------------------------------------------------------
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # -------------------------------------------------------------------------

    def _get_connection(self) -> sqlite3.Connection:
        conn = self._conn_factory()
        # Удобнее работать через dict-like доступ к полям
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _row_to_spread(row: sqlite3.Row) -> dict[str, Any]:
        """
        Маппинг строки tma_spreads в dict в формате, удобном сервису.

        ВАЖНО:
        - user_question из БД → поле "question" в доменной модели;
        - cards_json (TEXT) → "cards": list[dict].
        """
        cards_raw = row["cards_json"] if "cards_json" in row.keys() else "[]"
        try:
            cards = json.loads(cards_raw) if cards_raw else []
        except json.JSONDecodeError:
            cards = []

        return {
            "id": row["id"],
            "user_id": row["user_id"],
            "spread_type": row["spread_type"],
            "category": row["category"],
            # в API/моделях поле называется question, а не user_question
            "question": row["user_question"],
            "cards": cards,
            "interpretation": row["interpretation"],
            "created_at": row["created_at"],
        }

    @staticmethod
    def _row_to_question(row: sqlite3.Row) -> dict[str, Any]:
        """
        Маппинг строки tma_spread_questions в dict.
        """
        return {
            "id": row["id"],
            "spread_id": row["spread_id"],
            "user_id": row["user_id"],
            "question": row["question"],
            "answer": row["answer"],
            "status": row["status"],
            "created_at": row["created_at"],
        }

    # -------------------------------------------------------------------------
    # SPREADS
    # -------------------------------------------------------------------------

    def save_spread(self, data: dict[str, Any]) -> int:
        """
        Сохранение расклада в tma_spreads.

        Ожидаемый формат data (минимальный):
        {
            "user_id": int,
            "spread_type": "one" | "three",
            "category": str | None,
            "question": str | None,        # вопрос ПЕРЕД раскладом
            "cards": list[dict],           # JSON-список карт
            "interpretation": str | None,
            "created_at": str,             # ISO-строка
        }

        Возвращает id вставленной записи.
        """
        cards = data.get("cards") or []
        cards_json = json.dumps(cards, ensure_ascii=False)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO tma_spreads (
                    user_id,
                    spread_type,
                    category,
                    user_question,
                    cards_json,
                    interpretation,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["user_id"],
                    data["spread_type"],
                    data.get("category"),
                    # question из доменной модели кладём в user_question
                    data.get("question"),
                    cards_json,
                    data.get("interpretation"),
                    data["created_at"],
                ),
            )
            conn.commit()
            spread_id = int(cursor.lastrowid)
        return spread_id

    def get_spread(self, spread_id: int) -> Optional[dict[str, Any]]:
        """
        Получить один расклад по id.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    id,
                    user_id,
                    spread_type,
                    category,
                    user_question,
                    cards_json,
                    interpretation,
                    created_at
                FROM tma_spreads
                WHERE id = ?
                """,
                (spread_id,),
            )
            row = cursor.fetchone()

        if row is None:
            return None
        return self._row_to_spread(row)

    def list_spreads(
        self,
        user_id: int,
        offset: int,
        limit: int,
    ) -> Tuple[int, List[dict[str, Any]]]:
        """
        Список раскладов пользователя с пагинацией.

        Возвращает (total, items), где:
        - total: общее количество раскладов пользователя;
        - items: список dict'ов, отсортированных по created_at DESC, id DESC.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Считаем общее количество для пагинации
            cursor.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM tma_spreads
                WHERE user_id = ?
                """,
                (user_id,),
            )
            total_row = cursor.fetchone()
            total = int(total_row["cnt"]) if total_row is not None else 0

            # Получаем страницу
            cursor.execute(
                """
                SELECT
                    id,
                    user_id,
                    spread_type,
                    category,
                    user_question,
                    cards_json,
                    interpretation,
                    created_at
                FROM tma_spreads
                WHERE user_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                (user_id, limit, offset),
            )
            rows = cursor.fetchall()

        items = [self._row_to_spread(r) for r in rows]
        return total, items

    # -------------------------------------------------------------------------
    # QUESTIONS
    # -------------------------------------------------------------------------

    def save_question(self, data: dict[str, Any]) -> int:
        """
        Сохранение уточняющего вопроса по раскладу в tma_spread_questions.

        Ожидаемый формат data (минимальный):
        {
            "spread_id": int,
            "user_id": int,
            "question": str,
            "answer": str | None,
            "status": str,        # "pending" / "ready" / "failed"
            "created_at": str,    # ISO-строка
        }

        Возвращает id вставленной записи.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO tma_spread_questions (
                    spread_id,
                    user_id,
                    question,
                    answer,
                    status,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    data["spread_id"],
                    data["user_id"],
                    data["question"],
                    data.get("answer"),
                    data["status"],
                    data["created_at"],
                ),
            )
            conn.commit()
            question_id = int(cursor.lastrowid)
        return question_id

    def list_questions(self, spread_id: int) -> List[dict[str, Any]]:
        """
        Список вопросов по конкретному раскладу.

        Возвращает list[dict], отсортированный по created_at ASC, id ASC.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    id,
                    spread_id,
                    user_id,
                    question,
                    answer,
                    status,
                    created_at
                FROM tma_spread_questions
                WHERE spread_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (spread_id,),
            )
            rows = cursor.fetchall()

        return [self._row_to_question(r) for r in rows]
