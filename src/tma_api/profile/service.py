# src/tma_api/profile/service.py

import logging
import os
from typing import Any

from src.user_database import UserDatabase

from .models import ProfileModel
from .postgres_repository import PostgresProfileRepository

logger = logging.getLogger(__name__)


class ProfileService:
    """
    Сервис профиля для TMA API.

    Принципы:
    - БД — единственный источник истины.
    - Dev/Telegram-профиль используется только для первичного создания записи,
      когда профиля в БД ещё нет.
    """

    def __init__(self, repo: Any | None = None) -> None:
        backend = os.getenv("TMA_DB_BACKEND", "").strip().lower()
        db_url = os.getenv("DATABASE_URL", "").strip()

        if repo is not None:
            self._repo = repo
            logger.info(
                "ProfileService: using injected repository %s",
                type(repo).__name__,
            )
            return

        if backend == "postgres" and db_url:
            try:
                self._repo = PostgresProfileRepository()
                logger.info("ProfileService: using PostgresProfileRepository")
                return
            except Exception:
                logger.exception(
                    "Failed to init PostgresProfileRepository, falling back to UserDatabase"
                )

        # fallback / default
        self._repo = UserDatabase()
        logger.info("ProfileService: using UserDatabase (default/fallback)")

    # ------------------------------------------------------------------ #
    # internal helpers
    # ------------------------------------------------------------------ #

    def _get_telegram_or_dev_profile(self, defaults: dict[str, Any]) -> dict[str, Any]:
        """
        Собирает "сырой" Telegram/dev-профиль из того,
        что пришло в get_or_create_profile через **defaults.

        По сути это данные, извлечённые из initData или dev-хедеров
        (username, first_name, last_name, birth_date, gender).
        """
        return {
            "username": defaults.get("username"),
            "first_name": defaults.get("first_name"),
            "last_name": defaults.get("last_name"),
            "birth_date": defaults.get("birth_date"),
            "gender": defaults.get("gender"),
        }

    # ------------------------------------------------------------------ #
    # public API
    # ------------------------------------------------------------------ #

    def get_or_create_profile(self, user_id: int, **defaults: Any) -> ProfileModel:
        """
        ТЗ 6.1 — жёсткий приоритет БД над dev/Telegram.

        Алгоритм:

        1) Читаем БД:
             db_profile = self._repo.get_profile(user_id)

        2) Если db_profile есть (не None):
             - НЕ используем dev/Telegram вообще.
             - Собираем ProfileModel только из db_profile.

        3) Если db_profile отсутствует:
             - получаем tg = self._get_telegram_or_dev_profile(...);
             - формируем payload из tg-данных;
             - делаем db_profile = self._repo.upsert_profile(user_id, payload);
             - возвращаем ProfileModel по db_profile.
        """
        db_profile = self._repo.get_profile(user_id)

        # 2) Запись в БД уже есть → dev/Telegram игнорируем, возвращаем только БД
        if db_profile is not None:
            return ProfileModel(**db_profile)

        # 3) Записи в БД нет → инициализируем из dev/Telegram-профиля
        tg = self._get_telegram_or_dev_profile(defaults)

        payload: dict[str, Any] = {
            "user_id": user_id,
            "username": tg.get("username"),
            "first_name": tg.get("first_name"),
            "last_name": tg.get("last_name"),
            "birth_date": tg.get("birth_date"),
            "gender": tg.get("gender"),
        }

        db_profile = self._repo.upsert_profile(user_id, payload)
        return ProfileModel(**db_profile)

    def update_profile(self, user_id: int, body: Any) -> ProfileModel:
        """
        ТЗ 6.1 — update_profile:

        1) Сформировать payload из body (first_name, last_name, birth_date,
           gender, username при необходимости);
        2) вызвать self._repo.upsert_profile(user_id, payload);
        3) вернуть self.get_or_create_profile(user_id) — который уже не трогает
           dev-профиль, т.к. запись в БД появилась.
        """
        # 1) нормализуем body → dict
        if hasattr(body, "dict"):
            payload: dict[str, Any] = body.dict(exclude_unset=True)
        elif isinstance(body, dict):
            payload = dict(body)
        else:
            raise TypeError(
                "update_profile body must be a dict or have a .dict() method"
            )

        # user_id всегда берём из аргумента
        payload["user_id"] = user_id

        # 2) сохраняем в БД
        self._repo.upsert_profile(user_id, payload)

        # 3) возвращаем актуальный профиль ИЗ БД
        return self.get_or_create_profile(user_id)
