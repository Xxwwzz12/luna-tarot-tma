# src/tma_api/spreads/repository.py

from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Protocol, Tuple


class SpreadRepository(Protocol):
    """
    Абстрактный интерфейс репозитория раскладов.

    Реализации: InMemorySpreadRepository, SQLiteSpreadRepository.
    """

    def save_spread(self, data: dict[str, Any]) -> int:
        """
        Сохранить расклад, вернуть его ID.
        """
        ...

    def get_spread(self, spread_id: int) -> dict[str, Any] | None:
        """
        Получить один расклад по ID (без проверки user_id).
        Проверка принадлежности делается в сервисе.
        """
        ...

    def list_spreads(
        self,
        user_id: int,
        offset: int,
        limit: int,
    ) -> tuple[int, list[dict[str, Any]]]:
        """
        Вернуть (total, items) по user_id с учётом offset/limit.
        """
        ...

    def save_question(self, data: dict[str, Any]) -> int:
        """
        Сохранить вопрос к раскладу, вернуть его ID.
        """
        ...

    def list_questions(self, spread_id: int) -> list[dict[str, Any]]:
        """
        Вернуть список вопросов по spread_id (без проверки user_id).
        Проверка делается в сервисе через get_spread().
        """
        ...


class InMemorySpreadRepository(SpreadRepository):
    """
    Простая in-memory реализация репозитория.

    Нужна как дефолт/заглушка и для локальной разработки без БД.
    """

    def __init__(self) -> None:
        # Хранилище раскладов: spread_id -> dict
        self._spreads: Dict[int, Dict[str, Any]] = {}
        self._spread_index: int = 0

        # Хранилище вопросов: question_id -> dict
        self._questions: Dict[int, Dict[str, Any]] = {}
        self._question_index: int = 0

    # ---- helpers ----

    def _next_spread_id(self) -> int:
        self._spread_index += 1
        return self._spread_index

    def _next_question_id(self) -> int:
        self._question_index += 1
        return self._question_index

    # ---- SpreadRepository implementation ----

    def save_spread(self, data: dict[str, Any]) -> int:
        spread_id = data.get("id")
        if not isinstance(spread_id, int):
            spread_id = self._next_spread_id()
            data = {**data, "id": spread_id}

        self._spreads[spread_id] = data
        return spread_id

    def get_spread(self, spread_id: int) -> dict[str, Any] | None:
        return self._spreads.get(spread_id)

    def list_spreads(
        self,
        user_id: int,
        offset: int,
        limit: int,
    ) -> tuple[int, list[dict[str, Any]]]:
        items: List[Dict[str, Any]] = [
            s for s in self._spreads.values() if s.get("user_id") == user_id
        ]

        def _sort_key(item: Dict[str, Any]):
            return item.get("created_at") or item.get("id") or 0

        items.sort(key=_sort_key, reverse=True)

        total = len(items)
        if offset < 0:
            offset = 0
        if limit <= 0:
            return total, []

        sliced = items[offset : offset + limit]
        return total, sliced

    def save_question(self, data: dict[str, Any]) -> int:
        question_id = data.get("id")
        if not isinstance(question_id, int):
            question_id = self._next_question_id()
            data = {**data, "id": question_id}

        self._questions[question_id] = data
        return question_id

    def list_questions(self, spread_id: int) -> list[dict[str, Any]]:
        items: List[Dict[str, Any]] = [
            q for q in self._questions.values() if q.get("spread_id") == spread_id
        ]
        items.sort(key=lambda q: q.get("id") or 0)
        return items


class SQLiteSpreadRepository(SpreadRepository):
    """
    SQLite-реализация SpreadRepository.

    ТЗ 9.1:
      - история раскладов только по конкретному user_id (WHERE user_id = ?)

    ТЗ 9.2:
      - вопросы только по конкретному spread_id (WHERE spread_id = ?)
      - контроль принадлежности расклада пользователю делается в сервисе.
    """

    def __init__(self, db_path: str = "tma.sqlite3") -> None:
        self._db_path = db_path

    # ---- helpers ----

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ---- SpreadRepository implementation ----

    def save_spread(self, data: dict[str, Any]) -> int:
        """
        Примитивный upsert в таблицу spreads.

        Ожидается таблица с хотя бы этими полями:
        - id INTEGER PRIMARY KEY
        - user_id INTEGER NOT NULL
        - spread_type TEXT NOT NULL
        - category TEXT NULL
        - question TEXT NULL
        - cards_json TEXT NULL
        - interpretation TEXT NULL
        - created_at TEXT NULL
        - updated_at TEXT NULL
        """
        with self._get_conn() as conn:
            cur = conn.cursor()
            spread_id = data.get("id")

            if spread_id is None:
                cols = list(data.keys())
                cols_sql = ", ".join(cols)
                placeholders = ", ".join([f":{c}" for c in cols])
                sql = f"INSERT INTO spreads ({cols_sql}) VALUES ({placeholders})"
                cur.execute(sql, data)
                spread_id = int(cur.lastrowid)
            else:
                cols = [k for k in data.keys() if k != "id"]
                set_sql = ", ".join([f"{c} = :{c}" for c in cols])
                sql = f"UPDATE spreads SET {set_sql} WHERE id = :id"
                cur.execute(sql, data)

            return spread_id  # type: ignore[return-value]

    def get_spread(self, spread_id: int) -> dict[str, Any] | None:
        """
        Получаем расклад по id (без фильтра по user_id — это на стороне сервиса).
        """
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM spreads WHERE id = ? LIMIT 1",
                (spread_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return dict(row)

    def list_spreads(
        self,
        user_id: int,
        offset: int,
        limit: int,
    ) -> tuple[int, list[dict[str, Any]]]:
        """
        ТЗ 9.1 — история раскладов только для конкретного пользователя.

        Никаких SELECT * FROM spreads ORDER BY ... без WHERE user_id = ?.

        Здесь ДВА запроса:
        - COUNT(*) по user_id
        - SELECT * по user_id с ORDER BY и LIMIT/OFFSET
        """
        if offset < 0:
            offset = 0
        if limit <= 0:
            return 0, []

        with self._get_conn() as conn:
            cur = conn.cursor()

            # total только по этому user_id
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM spreads WHERE user_id = ?",
                (user_id,),
            )
            row = cur.fetchone()
            total = int(row["cnt"] if row and "cnt" in row.keys() else 0)

            # сами элементы
            cur.execute(
                """
                SELECT *
                FROM spreads
                WHERE user_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                (user_id, limit, offset),
            )
            rows = cur.fetchall()
            items = [dict(r) for r in rows]

        return total, items

    def save_question(self, data: dict[str, Any]) -> int:
        """
        Upsert в таблицу spread_questions.

        Ожидается таблица, например:
        - id INTEGER PRIMARY KEY
        - spread_id INTEGER NOT NULL
        - question TEXT NOT NULL
        - answer TEXT NULL
        - created_at TEXT NULL
        - updated_at TEXT NULL
        """
        with self._get_conn() as conn:
            cur = conn.cursor()
            question_id = data.get("id")

            if question_id is None:
                cols = list(data.keys())
                cols_sql = ", ".join(cols)
                placeholders = ", ".join([f":{c}" for c in cols])
                sql = (
                    f"INSERT INTO spread_questions ({cols_sql}) "
                    f"VALUES ({placeholders})"
                )
                cur.execute(sql, data)
                question_id = int(cur.lastrowid)
            else:
                cols = [k for k in data.keys() if k != "id"]
                set_sql = ", ".join([f"{c} = :{c}" for c in cols])
                sql = "UPDATE spread_questions SET {set_sql} WHERE id = :id"
                sql = f"UPDATE spread_questions SET {set_sql} WHERE id = :id"
                cur.execute(sql, data)

            return question_id  # type: ignore[return-value]

    def list_questions(self, spread_id: int) -> list[dict[str, Any]]:
        """
        ТЗ 9.2 — вопросы только по конкретному раскладу.

        SELECT *
        FROM spread_questions
        WHERE spread_id = ?
        ORDER BY created_at ASC, id ASC

        Проверка принадлежности расклада пользователю — в сервисе.
        """
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT *
                FROM spread_questions
                WHERE spread_id = ?
                ORDER BY created_at ASC, id ASC
                """,
                (spread_id,),
            )
            rows = cur.fetchall()
            return [dict(r) for r in rows]


__all__ = [
    "SpreadRepository",
    "InMemorySpreadRepository",
    "SQLiteSpreadRepository",
]
