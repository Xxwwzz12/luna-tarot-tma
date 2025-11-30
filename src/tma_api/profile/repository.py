# src/tma_api/profile/repository.py

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ProfileRepository:
    """
    Простой SQLite-репозиторий для профиля пользователя.

    Задачи:
    - хранить first_name / last_name / birth_date / gender в таблице профиля;
    - при GET /profile отдавать те же поля без переименований.
    """

    def __init__(self, db_path: str = "tma.sqlite3") -> None:
        # Путь до файла БД можно будет пробросить из настроек/ENV
        self._db_path = Path(db_path)
        self._init_schema()

    # -------------------- Внутренние helpers --------------------

    def _get_connection(self) -> sqlite3.Connection:
        """
        Открывает соединение с SQLite и включает row_factory, чтобы
        можно было удобно превращать строки в dict.
        """
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        """
        Создаёт таблицу tma_profiles, если её ещё нет.

        Важно: таблица обязательно содержит поля first_name / last_name /
        birth_date / gender, как требует ТЗ.
        """
        logger.info("Initializing tma_profiles schema in SQLite: %s", self._db_path)
        conn = self._get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tma_profiles (
                        user_id     INTEGER PRIMARY KEY,
                        first_name  TEXT NULL,
                        last_name   TEXT NULL,
                        birth_date  TEXT NULL,
                        gender      TEXT NULL,
                        created_at  TEXT NOT NULL,
                        updated_at  TEXT NOT NULL
                    )
                    """
                )
        finally:
            conn.close()

    # -------------------- Публичный интерфейс --------------------

    def get_profile(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Вернуть профиль пользователя в виде dict:

        {
          "user_id": ...,
          "first_name": ...,
          "last_name": ...,
          "birth_date": ...,
          "gender": ...,
          "created_at": ...,
          "updated_at": ...,
        }

        Если записи нет — вернуть None.
        """
        conn = self._get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                    user_id,
                    first_name,
                    last_name,
                    birth_date,
                    gender,
                    created_at,
                    updated_at
                FROM tma_profiles
                WHERE user_id = ?
                """,
                (user_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None

            return dict(row)
        finally:
            conn.close()

    def upsert_profile(self, user_id: int, data: Dict[str, Any]) -> None:
        """
        Сохранить профиль пользователя.

        По ТЗ upsert_profile обязан писать в поля:
        first_name / last_name / birth_date / gender.

        payload = {
            "user_id": user_id,
            "first_name": data.get("first_name"),
            "last_name": data.get("last_name"),
            "birth_date": data.get("birth_date"),
            "gender": data.get("gender"),
        }

        Остальные поля (created_at / updated_at) заполняются здесь же.
        """
        payload = {
            "user_id": user_id,
            "first_name": data.get("first_name"),
            "last_name": data.get("last_name"),
            "birth_date": data.get("birth_date"),
            "gender": data.get("gender"),
        }

        now = datetime.utcnow().isoformat()

        conn = self._get_connection()
        try:
            with conn:
                # INSERT ... ON CONFLICT(user_id) DO UPDATE — классический upsert
                conn.execute(
                    """
                    INSERT INTO tma_profiles (
                        user_id,
                        first_name,
                        last_name,
                        birth_date,
                        gender,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        :user_id,
                        :first_name,
                        :last_name,
                        :birth_date,
                        :gender,
                        :created_at,
                        :updated_at
                    )
                    ON CONFLICT(user_id) DO UPDATE SET
                        first_name = excluded.first_name,
                        last_name  = excluded.last_name,
                        birth_date = excluded.birth_date,
                        gender     = excluded.gender,
                        updated_at = excluded.updated_at
                    """,
                    {
                        **payload,
                        "created_at": now,
                        "updated_at": now,
                    },
                )
        finally:
            conn.close()

        logger.debug("Profile upserted for user_id=%s: %r", user_id, payload)
