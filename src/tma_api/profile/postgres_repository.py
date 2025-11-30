# src/tma_api/profile/postgres_repository.py

import logging
from datetime import date, datetime
from typing import Any, Dict, Optional

from src.tma_api.db.postgres import get_pg_connection

logger = logging.getLogger(__name__)


class PostgresProfileRepository:
    """
    Хранилище профиля пользователя в Postgres.

    Методы:
      - get_profile(user_id) -> dict | None
      - upsert_profile(user_id, data) -> dict
    """

    def __init__(self) -> None:
        logger.info("PostgresProfileRepository initialized")
        self._init_schema()

    def _init_schema(self) -> None:
        """
        Создаёт таблицу профилей, если её ещё нет.
        """
        create_sql = """
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
                    cur.execute(create_sql)
            logger.info("PostgresProfileRepository: schema ensured (tma_profiles)")
        except Exception:
            logger.exception("PostgresProfileRepository: failed to init schema")

    def _row_to_profile_dict(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """
        Приводит строку БД к целевому dict-формату.
        """
        if row is None:
            return {}

        birth_date_val: Optional[date] = row.get("birth_date")
        created_at_val: Any = row.get("created_at")
        updated_at_val: Any = row.get("updated_at")

        def _iso_or_none(value: Any) -> Optional[str]:
            if value is None:
                return None
            if isinstance(value, (datetime, date)):
                return value.isoformat()
            # На всякий случай — если драйвер вернул строку
            return str(value)

        return {
            "user_id": row.get("user_id"),
            "username": row.get("username"),
            "first_name": row.get("first_name"),
            "last_name": row.get("last_name"),
            "birth_date": birth_date_val.isoformat() if birth_date_val else None,
            "gender": row.get("gender"),
            "created_at": _iso_or_none(created_at_val),
            "updated_at": _iso_or_none(updated_at_val),
        }

    def get_profile(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Возвращает профиль пользователя или None, если записи нет.
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
        WHERE user_id = %s
        """

        try:
            with get_pg_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (user_id,))
                    row = cur.fetchone()
            if not row:
                return None
            # row_factory=dict_row → row уже dict-подобный
            return self._row_to_profile_dict(row)
        except Exception:
            logger.exception("PostgresProfileRepository.get_profile: failed (user_id=%s)", user_id)
            return None

    def upsert_profile(self, user_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Вставляет или обновляет профиль и возвращает итоговое состояние.
        """
        # Разрешённые поля для записи/обновления
        username = data.get("username")
        first_name = data.get("first_name")
        last_name = data.get("last_name")
        gender = data.get("gender")

        birth_date_raw = data.get("birth_date")
        birth_date_val: Optional[date] = None

        if birth_date_raw:
            if isinstance(birth_date_raw, date):
                birth_date_val = birth_date_raw
            else:
                try:
                    # Ожидаем формат "YYYY-MM-DD"
                    birth_date_val = date.fromisoformat(str(birth_date_raw))
                except Exception:
                    logger.warning(
                        "PostgresProfileRepository.upsert_profile: invalid birth_date '%s' for user_id=%s",
                        birth_date_raw,
                        user_id,
                    )
                    birth_date_val = None

        params = {
            "user_id": user_id,
            "username": username,
            "first_name": first_name,
            "last_name": last_name,
            "birth_date": birth_date_val,
            "gender": gender,
        }

        sql = """
        INSERT INTO tma_profiles (
            user_id,
            username,
            first_name,
            last_name,
            birth_date,
            gender,
            created_at,
            updated_at
        ) VALUES (
            %(user_id)s,
            %(username)s,
            %(first_name)s,
            %(last_name)s,
            %(birth_date)s,
            %(gender)s,
            NOW(),
            NOW()
        )
        ON CONFLICT (user_id) DO UPDATE
        SET
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
                    cur.execute(sql, params)
                    row = cur.fetchone()
            if not row:
                raise RuntimeError("Upsert profile returned no row")

            profile = self._row_to_profile_dict(row)
            logger.info(
                "PostgresProfileRepository.upsert_profile: profile saved for user_id=%s",
                user_id,
            )
            return profile
        except Exception:
            logger.exception(
                "PostgresProfileRepository.upsert_profile: failed to save profile for user_id=%s",
                user_id,
            )
            # На всякий случай возвращаем минимальный словарь;
            # сервис выше по стеку может решить, что с этим делать.
            return {
                "user_id": user_id,
                "username": username,
                "first_name": first_name,
                "last_name": last_name,
                "birth_date": birth_date_val.isoformat() if birth_date_val else None,
                "gender": gender,
                "created_at": None,
                "updated_at": None,
            }
