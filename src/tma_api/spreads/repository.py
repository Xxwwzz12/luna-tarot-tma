# src/tma_api/spreads/repository.py

from __future__ import annotations

import sqlite3
from typing import Any, Dict, List, Protocol, Tuple


class SpreadRepository(Protocol):
    """
    Абстрактный интерфейс репозитория раскладов.

    Важно: сигнатуры синхронизированы со всеми реализациями.
    """

    def save_spread(self, data: dict[str, Any]) -> int:
        """
        Сохранить расклад, вернуть его ID.
        """
        ...

    def get_spread(self, spread_id: int) -> dict[str, Any] | None:
        """
        Получить один расклад по ID (без проверки user_id).
        Проверка "чей расклад" должна быть на уровне сервиса.
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
        Проверка "чужой вопрос" — на уровне сервиса.
        """
        ...


class InMemorySpreadRepository(SpreadRepository):
    """
    Простая in-memory реализация репозитория.

    Сейчас это по сути инкапсулирует текущий подход с _SPREADS / _QUESTIONS,
    но в одном месте и с понятным интерфейсом. Позже можно заменить или
    дополнить SQL-реализацией.
    """

    def __init__(self) -> None:
        # Хранилище раскладов: spread_id -> dict
        self._spreads: Dict[int, Dict[str, Any]] = {}
        self._spread_index: int = 0

        # Хранилище вопросов: question_id -> dict
        self._questions: Dict[int, Dict[str, Any]] = {}
        self._question_index: int = 0

    # ---- Внутренние helpers ----

    def _next_spread_id(self) -> int:
        self._spread_index += 1
        return self._spread_index

    def _next_question_id(self) -> int:
        self._question_index += 1
        return self._question_index

    # ---- SpreadRepository implementation ----

    def save_spread(self, data: dict[str, Any]) -> int:
        """
        Сохраняем расклад.

        Если id не передан в data — создаём новый, иначе перезаписываем существующий.
        """
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
        """
        Фильтрация по user_id + простая пагинация.

        Сортируем по created_at (если есть), иначе по id (по убыванию).
        """
        items: List[Dict[str, Any]] = [
            s for s in self._spreads.values() if s.get("user_id") == user_id
        ]

        def _sort_key(item: Dict[str, Any]):
            # created_at ожидается строкой ISO, но здесь можно оставить как есть.
            # Если поля нет — сортируем по id.
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
        """
        Сохраняем вопрос к раскладу.

        Ожидаются поля:
        - spread_id
        - text / question
        - (опционально) created_at и т.п.
        """
        question_id = data.get("id")
        if not isinstance(question_id, int):
            question_id = self._next_question_id()
            data = {**data, "id": question_id}

        self._questions[question_id] = data
        return question_id

    def list_questions(self, spread_id: int) -> list[dict[str, Any]]:
        """
        Возвращаем все вопросы для указанного расклада, по id по возрастанию.
        """
        items: List[Dict[str, Any]] = [
            q for q in self._questions.values() if q.get("spread_id") == spread_id
        ]
        items.sort(key=lambda q: q.get("id") or 0)
        return items


class SQLiteSpreadRepository(SpreadRepository):
    """
    SQLite-реализация SpreadRepository.

    ВАЖНО по ТЗ 7.1:
    - list_spreads делает SELECT только по текущему user_id:
      SELECT * FROM spreads WHERE user_id = ? ORDER BY created_at DESC, id DESC
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

        Ожидается, что таблица содержит как минимум:
        id INTEGER PRIMARY KEY,
        user_id INTEGER,
        spread_type TEXT,
        category TEXT,
        question TEXT,
        cards_json TEXT,
        interpretation TEXT,
        created_at TEXT,
        updated_at TEXT
        (часть полей может быть NULL).

        Здесь мы не навязываем жёсткую схему: берём ключи data как список колонок.
        """
        with self._get_conn() as conn:
            cur = conn.cursor()
            spread_id = data.get("id")

            if spread_id is None:
                # INSERT
                cols = list(data.keys())
                placeholders = ", ".join([f":{c}" for c in cols])
                cols_sql = ", ".join(cols)
                sql = f"INSERT INTO spreads ({cols_sql}) VALUES ({placeholders})"
                cur.execute(sql, data)
                spread_id = int(cur.lastrowid)
            else:
                # UPDATE по id
                cols = [k for k in data.keys() if k != "id"]
                set_sql = ", ".join([f"{c} = :{c}" for c in cols])
                sql = f"UPDATE spreads SET {set_sql} WHERE id = :id"
                cur.execute(sql, data)

            return spread_id  # type: ignore[return-value]

    def get_spread(self, spread_id: int) -> dict[str, Any] | None:
        """
        SELECT * FROM spreads WHERE id = ? LIMIT 1
        """
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM spreads WHERE id = ? LIMIT 1", (spread_id,))
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
        ВАЖНО: фильтрация по user_id.

        Было (плохо):
            SELECT * FROM spreads ORDER BY created_at DESC

        Стало:
            SELECT * FROM spreads
            WHERE user_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ? OFFSET ?

        Для total считаем только строки этого пользователя.
        """
        if offset < 0:
            offset = 0
        if limit <= 0:
            return 0, []

        with self._get_conn() as conn:
            cur = conn.cursor()

            # total
            cur.execute(
                "SELECT COUNT(*) AS cnt FROM spreads WHERE user_id = ?",
                (user_id,),
            )
            row = cur.fetchone()
            total = int(row["cnt"] if row and "cnt" in row.keys() else 0)

            # items
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
        Примитивный upsert в таблицу вопросов.

        Ожидается таблица, например:
        spread_questions (
            id INTEGER PRIMARY KEY,
            spread_id INTEGER NOT NULL,
            question TEXT NOT NULL,
            answer TEXT,
            created_at TEXT,
            updated_at TEXT
        )
        """
        with self._get_conn() as conn:
            cur = conn.cursor()
            question_id = data.get("id")

            if question_id is None:
                cols = list(data.keys())
                placeholders = ", ".join([f":{c}" for c in cols])
                cols_sql = ", ".join(cols)
                sql = (
                    f"INSERT INTO spread_questions ({cols_sql}) "
                    f"VALUES ({placeholders})"
                )
                cur.execute(sql, data)
                question_id = int(cur.lastrowid)
            else:
                cols = [k for k in data.keys() if k != "id"]
                set_sql = ", ".join([f"{c} = :{c}" for c in cols])
                sql = f"UPDATE spread_questions SET {set_sql} WHERE id = :id"
                cur.execute(sql, data)

            return question_id  # type: ignore[return-value]

    def list_questions(self, spread_id: int) -> list[dict[str, Any]]:
        """
        SELECT * FROM spread_questions WHERE spread_id = ? ORDER BY created_at, id.

        Т.е. возвращаем только вопросы конкретного расклада. Проверка "чужой"
        расклад/вопрос делается в сервисе (по user_id в самом раскладе).
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
