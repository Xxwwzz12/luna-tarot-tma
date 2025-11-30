# src/tma_api/spreads/postgres_repository.py

import json
import logging
from typing import Any, Dict, List, Tuple

from .repository import SpreadRepository
from src.tma_api.db.postgres import get_pg_connection

logger = logging.getLogger(__name__)


def _to_iso(value: Any) -> str:
    """
    Безопасно привести timestamp/дату к ISO-строке.
    """
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:  # на всякий случай
            return str(value)
    return str(value)


class PostgresSpreadRepository(SpreadRepository):
    def __init__(self) -> None:
        # Пока без пула, на каждую операцию своё подключение.
        logger.info("PostgresSpreadRepository initialized")
        self._init_schema()

    # -------------------------------------------------------------------------
    # Инициализация схемы
    # -------------------------------------------------------------------------
    def _init_schema(self) -> None:
        """
        Создаёт таблицы tma_spreads и tma_spread_questions, если их нет.
        """
        spreads_sql = """
        CREATE TABLE IF NOT EXISTS tma_spreads (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            spread_type TEXT NOT NULL,
            category TEXT NULL,
            user_question TEXT NULL,
            cards_json JSONB NOT NULL,
            interpretation TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL
        );
        """

        questions_sql = """
        CREATE TABLE IF NOT EXISTS tma_spread_questions (
            id SERIAL PRIMARY KEY,
            spread_id INTEGER NOT NULL REFERENCES tma_spreads(id),
            user_id INTEGER NOT NULL,
            question TEXT NOT NULL,
            answer TEXT NULL,
            status TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL
        );
        """

        try:
            with get_pg_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(spreads_sql)
                    cur.execute(questions_sql)
                conn.commit()
            logger.info("PostgresSpreadRepository schema initialized/ensured")
        except Exception as exc:
            logger.exception("Failed to initialize PostgresSpreadRepository schema: %s", exc)
            raise

    # -------------------------------------------------------------------------
    # SpreadRepository interface
    # -------------------------------------------------------------------------
    def save_spread(self, data: dict[str, Any]) -> int:
        """
        Сохраняет расклад в tma_spreads.

        Ожидаемый формат data:
        {
            "user_id": int,
            "spread_type": str,
            "category": str | None,
            "user_question": str | None,
            "cards": list[dict],
            "interpretation": str | None,
            "created_at": str (ISO),
        }
        """
        sql = """
        INSERT INTO tma_spreads (
            user_id, spread_type, category, user_question,
            cards_json, interpretation, created_at
        )
        VALUES (
            %(user_id)s,
            %(spread_type)s,
            %(category)s,
            %(user_question)s,
            %(cards_json)s,
            %(interpretation)s,
            %(created_at)s
        )
        RETURNING id;
        """

        payload: Dict[str, Any] = {
            "user_id": data["user_id"],
            "spread_type": data["spread_type"],
            "category": data.get("category"),
            "user_question": data.get("user_question"),
            # сериализуем карты в JSON-строку; Postgres приведёт к JSONB
            "cards_json": json.dumps(data.get("cards") or [], ensure_ascii=False),
            "interpretation": data.get("interpretation"),
            "created_at": data["created_at"],
        }

        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, payload)
                row = cur.fetchone()
            conn.commit()

        spread_id = int(row["id"])
        logger.debug("Saved spread id=%s for user_id=%s", spread_id, payload["user_id"])
        return spread_id

    def get_spread(self, spread_id: int) -> dict[str, Any] | None:
        """
        Возвращает один расклад по id или None, если не найден.
        """
        sql = """
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
        WHERE id = %(id)s;
        """

        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, {"id": spread_id})
                row = cur.fetchone()

        if row is None:
            logger.debug("Spread id=%s not found", spread_id)
            return None

        cards_raw = row["cards_json"]
        # cards_json хранится как JSONB → dict/list; на всякий случай поддерживаем строку
        if isinstance(cards_raw, str):
            try:
                cards = json.loads(cards_raw)
            except json.JSONDecodeError:
                logger.warning("Failed to decode cards_json for spread id=%s", spread_id)
                cards = []
        else:
            cards = cards_raw

        result: Dict[str, Any] = {
            "id": row["id"],
            "user_id": row["user_id"],
            "spread_type": row["spread_type"],
            "category": row["category"],
            "user_question": row["user_question"],
            "cards": cards,
            "interpretation": row["interpretation"],
            "created_at": _to_iso(row["created_at"]),
        }
        return result

    def list_spreads(
        self,
        user_id: int,
        offset: int,
        limit: int,
    ) -> tuple[int, list[dict[str, Any]]]:
        """
        Возвращает (total, items) для раскладов пользователя.
        """
        count_sql = """
        SELECT COUNT(*) AS total
        FROM tma_spreads
        WHERE user_id = %(user_id)s;
        """

        list_sql = """
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
        WHERE user_id = %(user_id)s
        ORDER BY created_at DESC, id DESC
        OFFSET %(offset)s
        LIMIT %(limit)s;
        """

        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                # total
                cur.execute(count_sql, {"user_id": user_id})
                count_row = cur.fetchone()
                total = int(count_row["total"]) if count_row and count_row["total"] is not None else 0

                # list
                cur.execute(
                    list_sql,
                    {
                        "user_id": user_id,
                        "offset": offset,
                        "limit": limit,
                    },
                )
                rows = cur.fetchall()

        items: List[Dict[str, Any]] = []
        for row in rows:
            cards_raw = row["cards_json"]
            if isinstance(cards_raw, str):
                try:
                    cards = json.loads(cards_raw)
                except json.JSONDecodeError:
                    logger.warning(
                        "Failed to decode cards_json for spread id=%s (list_spreads)", row["id"]
                    )
                    cards = []
            else:
                cards = cards_raw

            items.append(
                {
                    "id": row["id"],
                    "user_id": row["user_id"],
                    "spread_type": row["spread_type"],
                    "category": row["category"],
                    "user_question": row["user_question"],
                    "cards": cards,
                    "interpretation": row["interpretation"],
                    "created_at": _to_iso(row["created_at"]),
                }
            )

        return total, items

    def save_question(self, data: dict[str, Any]) -> int:
        """
        Сохраняет уточняющий вопрос по раскладу.

        Ожидаемый формат data:
        {
            "spread_id": int,
            "user_id": int,
            "question": str,
            "answer": str | None,
            "status": str,
            "created_at": str (ISO),
        }
        """
        sql = """
        INSERT INTO tma_spread_questions (
            spread_id,
            user_id,
            question,
            answer,
            status,
            created_at
        )
        VALUES (
            %(spread_id)s,
            %(user_id)s,
            %(question)s,
            %(answer)s,
            %(status)s,
            %(created_at)s
        )
        RETURNING id;
        """

        payload: Dict[str, Any] = {
            "spread_id": data["spread_id"],
            "user_id": data["user_id"],
            "question": data["question"],
            "answer": data.get("answer"),
            "status": data["status"],
            "created_at": data["created_at"],
        }

        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, payload)
                row = cur.fetchone()
            conn.commit()

        question_id = int(row["id"])
        logger.debug(
            "Saved spread question id=%s for spread_id=%s user_id=%s",
            question_id,
            payload["spread_id"],
            payload["user_id"],
        )
        return question_id

    def list_questions(self, spread_id: int) -> list[dict[str, Any]]:
        """
        Возвращает список уточняющих вопросов по конкретному раскладу.
        """
        sql = """
        SELECT
            id,
            spread_id,
            user_id,
            question,
            answer,
            status,
            created_at
        FROM tma_spread_questions
        WHERE spread_id = %(spread_id)s
        ORDER BY created_at ASC, id ASC;
        """

        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, {"spread_id": spread_id})
                rows = cur.fetchall()

        items: List[Dict[str, Any]] = []
        for row in rows:
            items.append(
                {
                    "id": row["id"],
                    "spread_id": row["spread_id"],
                    "user_id": row["user_id"],
                    "question": row["question"],
                    "answer": row["answer"],
                    "status": row["status"],
                    "created_at": _to_iso(row["created_at"]),
                }
            )

        return items
