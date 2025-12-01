# src/tma_api/profile/postgres_repository.py

import logging
from typing import Any, Dict, Optional

from src.tma_api.db.postgres import get_pg_connection

logger = logging.getLogger(__name__)


class PostgresProfileRepository:
    """
    Репозиторий профилей пользователей на Postgres.

    Методы:
      - get_profile(user_id) -> dict | None
      - upsert_profile(user_id, data) -> dict
    """

    def __init__(self):
        logger.info("PostgresProfileRepository initialized")
        self._init_schema()

    def _init_schema(self):
        """
        Создание таблицы, если её ещё нет.
        """
        sql = """
        CREATE TABLE IF NOT EXISTS tma_profiles (
            user_id    BIGINT PRIMARY KEY,
            username   TEXT,
            first_name TEXT,
            last_name  TEXT,
            birth_date DATE,
            gender     TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
        try:
            with get_pg_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql)
            logger.info("Schema ensured: tma_profiles")
        except Exception:
            logger.exception("Failed to init schema for tma_profiles")

    # ------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------

    def _normalize_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """
        Преобразует строку Postgres в целевой dict.
        """
        if not row:
            return {}

        def iso(val):
            if val is None:
                return None
            return val.isoformat() if hasattr(val, "isoformat") else str(val)

        return {
            "user_id": row.get("user_id"),
            "username": row.get("username"),
            "first_name": row.get("first_name"),
            "last_name": row.get("last_name"),
            "birth_date": iso(row.get("birth_date")),
            "gender": row.get("gender"),
            "created_at": iso(row.get("created_at")),
            "updated_at": iso(row.get("updated_at")),
        }

    # ------------------------------------------------------------
    # Main API
    # ------------------------------------------------------------

    def get_profile(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        SELECT профиль по user_id.
        """
        sql = """
        SELECT
          user_id,
          username,
          first_name,
          last_name,
          birth_date,
          gender,
          created_at,
          updated_at
        FROM tma_profiles
        WHERE user_id = %(user_id)s;
        """

        try:
            with get_pg_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, {"user_id": user_id})
                    row = cur.fetchone()
            if not row:
                return None
            return self._normalize_row(row)
        except Exception:
            logger.exception("get_profile failed for user_id=%s", user_id)
            return None

    def upsert_profile(self, user_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        INSERT ON CONFLICT DO UPDATE.
        Возвращает итоговое состояние профиля как dict.
        """

        # строго как в SQLite-версии
        payload = {
            "user_id": user_id,
            "username": data.get("username"),
            "first_name": data.get("first_name"),
            "last_name": data.get("last_name"),
            "birth_date": data.get("birth_date"),
            "gender": data.get("gender"),
        }

        sql = """
        INSERT INTO tma_profiles (
            user_id, username, first_name, last_name, birth_date, gender
        )
        VALUES (
            %(user_id)s, %(username)s, %(first_name)s, %(last_name)s,
            %(birth_date)s, %(gender)s
        )
        ON CONFLICT (user_id) DO UPDATE SET
            username   = EXCLUDED.username,
            first_name = EXCLUDED.first_name,
            last_name  = EXCLUDED.last_name,
            birth_date = EXCLUDED.birth_date,
            gender     = EXCLUDED.gender,
            updated_at = NOW()
        RETURNING
            user_id,
            username,
            first_name,
            last_name,
            birth_date,
            gender,
            created_at,
            updated_at;
        """

        try:
            with get_pg_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, payload)
                    row = cur.fetchone()
            if not row:
                raise RuntimeError("Upsert returned no row")
            return self._normalize_row(row)
        except Exception:
            logger.exception("upsert_profile failed for user_id=%s", user_id)
            return payload  # минимальный fallback
