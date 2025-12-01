# src/tma_api/profile/repository.py

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ProfileRepository:
    """
    SQLite-репозиторий профиля пользователя.

    Хранит и отдаёт поля:
      - user_id
      - username
      - first_name
      - last_name
      - birth_date
      - gender
      + служебные created_at / updated_at

    Используется ProfileService для:
      - upsert профиля при POST /profile;
      - чтения профиля при GET /profile.
    """

    def __init__(self, db_path: str = "tma.sqlite3") -> None:
        self._db_path = Path(db_path)
        # Держим одно соединение на репозиторий
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    # -------------------- Схема --------------------

    def _init_schema(self) -> None:
        """
        Создаёт таблицу tma_profiles, если её ещё нет.

        ТЗ 6.1:

        CREATE TABLE IF NOT EXISTS tma_profiles (
            user_id    INTEGER PRIMARY KEY,
            username   TEXT NULL,
            first_name TEXT NULL,
            last_name  TEXT NULL,
            birth_date TEXT NULL,
            gender     TEXT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
        logger.info("Initializing tma_profiles schema in SQLite: %s", self._db_path)
        with self._conn as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tma_profiles (
                    user_id    INTEGER PRIMARY KEY,
                    username   TEXT NULL,
                    first_name TEXT NULL,
                    last_name  TEXT NULL,
                    birth_date TEXT NULL,
                    gender     TEXT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    # -------------------- Публичный интерфейс --------------------

    def get_profile(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Вернуть профиль пользователя или None.

        Формат dict — те же поля, что и в таблице:
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
        """
        cur = self._conn.cursor()
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

    def upsert_profile(self, user_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        ТЗ 6.2 — upsert_profile пишет все поля и возвращает свежий профиль.

        Логика:

        now = datetime.utcnow().isoformat()

        payload = {
            "user_id": user_id,
            "username": data.get("username"),
            "first_name": data.get("first_name"),
            "last_name": data.get("last_name"),
            "birth_date": data.get("birth_date"),
            "gender": data.get("gender"),
            "created_at": now,
            "updated_at": now,
        }

        INSERT INTO tma_profiles (
            user_id, username, first_name, last_name,
            birth_date, gender, created_at, updated_at
        ) VALUES (
            :user_id, :username, :first_name, :last_name,
            :birth_date, :gender, :created_at, :updated_at
        )
        ON CONFLICT(user_id) DO UPDATE SET
            username   = excluded.username,
            first_name = excluded.first_name,
            last_name  = excluded.last_name,
            birth_date = excluded.birth_date,
            gender     = excluded.gender,
            updated_at = excluded.updated_at;

        return self.get_profile(user_id)
        """
        now = datetime.utcnow().isoformat()

        payload: Dict[str, Any] = {
            "user_id": user_id,
            "username": data.get("username"),
            "first_name": data.get("first_name"),
            "last_name": data.get("last_name"),
            "birth_date": data.get("birth_date"),
            "gender": data.get("gender"),
            "created_at": now,
            "updated_at": now,
        }

        with self._conn as conn:
            conn.execute(
                """
                INSERT INTO tma_profiles (
                    user_id, username, first_name, last_name,
                    birth_date, gender, created_at, updated_at
                ) VALUES (
                    :user_id, :username, :first_name, :last_name,
                    :birth_date, :gender, :created_at, :updated_at
                )
                ON CONFLICT(user_id) DO UPDATE SET
                    username   = excluded.username,
                    first_name = excluded.first_name,
                    last_name  = excluded.last_name,
                    birth_date = excluded.birth_date,
                    gender     = excluded.gender,
                    updated_at = excluded.updated_at
                """,
                payload,
            )

        profile = self.get_profile(user_id)
        if profile is None:
            # Теоретически сюда не попадём, но на всякий случай явно укажем
            raise RuntimeError(f"Profile for user_id={user_id} not found after upsert")

        logger.debug("Profile upserted for user_id=%s: %r", user_id, profile)
        return profile

    # -------------------- Жизненный цикл --------------------

    def close(self) -> None:
        """Закрыть соединение с БД (на случай явного вызова)."""
        try:
            self._conn.close()
        except Exception:
            logger.exception("Error while closing SQLite connection in ProfileRepository")

    def __del__(self) -> None:
        # На всякий случай закрываем соединение при сборке GC.
        try:
            self._conn.close()
        except Exception:
            # Не логируем агрессивно в __del__, чтобы не шуметь при завершении процесса
            pass
