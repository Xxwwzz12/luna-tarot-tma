# src/tma_api/spreads/sqlite_repository.py

from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Tuple

from .repository import SpreadRepository


class SQLiteSpreadRepository(SpreadRepository):
    """
    Полноценный SQLite-репозиторий для раскладов и вопросов.

    Ожидает фабрику соединений, чтобы можно было подсовывать разные варианты
    (in-memory, файл, обёртки и т.п.):

        conn_factory: Callable[[], sqlite3.Connection]
    """

    def __init__(self, conn_factory):
        self._conn_factory = conn_factory
        self._init_schema()

    # -------------------------------------------------------------------------
    # ИНИЦИАЛИЗАЦИЯ СХЕМЫ
    # -------------------------------------------------------------------------

    def _init_schema(self) -> None:
        conn = self._conn_factory()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS tma_spreads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    spread_type TEXT NOT NULL,
                    category TEXT NULL,
                    user_question TEXT NULL,
                    cards_json TEXT NOT NULL,
                    interpretation TEXT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS tma_spread_questions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    spread_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            conn.commit()
        finally:
            conn.close()

    # -------------------------------------------------------------------------
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # -------------------------------------------------------------------------

    def _get_connection(self) -> sqlite3.Connection:
        """
        Обёртка над фабрикой, чтобы сразу настраивать row_factory.
        """
        conn = self._conn_factory()
        conn.row_factory = sqlite3.Row
        return conn

    def _row_to_spread(self, row) -> dict[str, Any]:
        if row is None:
            return None
        return {
            "id": row["id"],
            "user_id": row["user_id"],
            "spread_type": row["spread_type"],
            "category": row["category"],
            "user_question": row["user_question"],
            "cards": json.loads(row["cards_json"]),
            "interpretation": row["interpretation"],
            "created_at": row["created_at"],
        }

    def _row_to_question(self, row) -> dict[str, Any]:
        if row is None:
            return None
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

    def save_spread(self, data: Dict[str, Any]) -> int:
        """
        Вставка или обновление расклада.

        Ожидаемые ключи в data:
        - id (опц.)
        - user_id
        - spread_type
        - category
        - user_question
        - cards (list[dict]) → сериализуется в cards_json
        - interpretation
        - created_at
        """
        spread_id = data.get("id")
        cards = data.get("cards") or []
        cards_json = json.dumps(cards, ensure_ascii=False)

        if spread_id and spread_id > 0:
            # UPDATE-ветка
            with self._get_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    UPDATE tma_spreads
                    SET
                        user_id = ?,
                        spread_type = ?,
                        category = ?,
                        user_question = ?,
                        cards_json = ?,
                        interpretation = ?,
                        created_at = ?
                    WHERE id = ?
                    """,
                    (
                        data["user_id"],
                        data["spread_type"],
                        data.get("category"),
                        data.get("user_question"),
                        cards_json,
                        data.get("interpretation"),
                        data["created_at"],
                        spread_id,
                    ),
                )
                conn.commit()
            return int(spread_id)

        # INSERT-ветка
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
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
                    data.get("user_question"),
                    cards_json,
                    data.get("interpretation"),
                    data["created_at"],
                ),
            )
            conn.commit()
            new_id = cur.lastrowid
        return int(new_id)

    def get_spread(self, spread_id: int) -> dict[str, Any] | None:
        """
        Получить один расклад по id (без проверки user_id — это делает сервис).
        """
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
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
            row = cur.fetchone()

        if row is None:
            return None
        return self._row_to_spread(row)

    def list_spreads(
        self,
        user_id: int,
        offset: int,
        limit: int,
    ) -> Tuple[int, List[Dict[str, Any]]]:
        """
        Список раскладов пользователя с пагинацией.

        Возвращает (total, items).
        """
        with self._get_connection() as conn:
            cur = conn.cursor()

            # total
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM tma_spreads WHERE user_id = ?",
                (user_id,),
            )
            total_row = cur.fetchone()
            total = int(total_row["cnt"]) if total_row is not None else 0

            # page
            cur.execute(
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
            rows = cur.fetchall()

        items = [self._row_to_spread(r) for r in rows]
        return total, items

    # -------------------------------------------------------------------------
    # QUESTIONS
    # -------------------------------------------------------------------------

    def save_question(self, data: Dict[str, Any]) -> int:
        """
        Вставка или обновление уточняющего вопроса.

        Ожидаемые ключи в data:
        - id (опц.)
        - spread_id
        - user_id
        - question
        - answer
        - status
        - created_at
        """
        question_id = data.get("id")

        if question_id and question_id > 0:
            # UPDATE-ветка
            with self._get_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    UPDATE tma_spread_questions
                    SET
                        spread_id = ?,
                        user_id = ?,
                        question = ?,
                        answer = ?,
                        status = ?,
                        created_at = ?
                    WHERE id = ?
                    """,
                    (
                        data["spread_id"],
                        data["user_id"],
                        data["question"],
                        data.get("answer"),
                        data["status"],
                        data["created_at"],
                        question_id,
                    ),
                )
                conn.commit()
            return int(question_id)

        # INSERT-ветка
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
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
            new_id = cur.lastrowid
        return int(new_id)

    def list_questions(self, spread_id: int) -> List[Dict[str, Any]]:
        """
        Список всех вопросов по раскладу, по возрастанию времени создания.
        """
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
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
            rows = cur.fetchall()

        return [self._row_to_question(r) for r in rows]
