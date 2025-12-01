# src/tma_api/profile/repository.py

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ProfileRepository:
    """
    SQLite-репозиторий для профиля пользователя.

    Хранит и отдаёт поля:
    - user_id
    - username
    - first_name
    - last_name
    - birth_date
    - gender
    + служебные created_at / updated_at
    """

    def __init__(self, db_path: str = "tma.sqlite3") -> None:
        self._db_path = Path(db_path)
        self._init_schema()

    # -------------------- Внутренние helpers --------------------

    def _get_connection(self) -> sqlite3.Connection:
        """
        Открывает соединение с SQLite и включает row_factory=Row,
        чтобы удобно превращать строки в dict().
        """
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        """
        Создаёт таблицу tma_profiles при первом запуске.

        Важно: таблица содержит все нужные поля профиля:
        user_id, username, first_name, last_name, birth_date, gender.
        """
        logger.info("Initializing tma_profiles schema in SQLite: %s", self._db_path)
        conn = self._get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS tma_profiles (
                        user_id     INTEGER PRIMARY KEY,
                        username    TEXT NULL,
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
          "username": ...,
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
                    username,
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

    def upsert_profile(self, user_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Upsert всех полей профиля в SQLite.

        Формирует payload:

        payload = {
            "user_id": user_id,
            "username": data.get("username"),
            "first_name": data.get("first_name"),
            "last_name": data.get("last_name"),
            "birth_date": data.get("birth_date"),
            "gender": data.get("gender"),
        }

        SQL в стиле:

        INSERT INTO tma_profiles (user_id, username, first_name, last_name, birth_date, gender)
        VALUES (:user_id, :username, :first_name, :last_name, :birth_date, :gender)
        ON CONFLICT(user_id) DO UPDATE SET
            username   = excluded.username,
            first_name = excluded.first_name,
            last_name  = excluded.last_name,
            birth_date = excluded.birth_date,
            gender     = excluded.gender;

        + обновляем updated_at, created_at оставляем как есть.

        Возвращает свежую строку профиля как dict.
        """
        payload = {
            "user_id": user_id,
            "username": data.get("username"),
            "first_name": data.get("first_name"),
            "last_name": data.get("last_name"),
            "birth_date": data.get("birth_date"),
            "gender": data.get("gender"),
        }

        now = datetime.utcnow().isoformat()

        conn = self._get_connection()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO tma_profiles (
                        user_id,
                        username,
                        first_name,
                        last_name,
                        birth_date,
                        gender,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        :user_id,
                        :username,
                        :first_name,
                        :last_name,
                        :birth_date,
                        :gender,
                        :created_at,
                        :updated_at
                    )
                    ON CONFLICT(user_id) DO UPDATE SET
                        username   = excluded.username,
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

        # Возвращаем свежую версию профиля для ProfileService
        profile = self.get_profile(user_id)
        if profile is None:
            # Теоретически не должно случиться, но на всякий случай
            raise RuntimeError(f"Failed to read profile after upsert (user_id={user_id})")

        logger.debug("Profile upserted for user_id=%s: %r", user_id, profile)
        return profile
