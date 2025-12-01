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
    - БД — источник истины.
    - Telegram/dev-профиль используется ТОЛЬКО как источник начальных значений,
      когда записи в БД ещё нет.
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
        Получить профиль пользователя или создать его, если записи ещё нет.

        ВАЖНО:

        - Если запись в БД уже существует → возвращаем ProfileModel,
          построенный ИСКЛЮЧИТЕЛЬНО по данным БД.

        - Если записи нет:
            * берём Telegram/dev-профиль из defaults;
            * создаём профиль в БД через upsert_profile;
            * возвращаем ProfileModel по данным БД.

        Таким образом:
        - после первого создания БД становится единственным источником истины;
        - dev/Telegram-профиль больше не участвует в слиянии данных.
        """
        # 1) Пробуем взять профиль из БД
        db_profile = self._repo.get_profile(user_id)

        if db_profile:
            # БД уже есть → просто оборачиваем в модель
            return ProfileModel(**db_profile)

        # 2) В БД ничего нет — инициализируем профиль из Telegram/dev
        tg = self._get_telegram_or_dev_profile(defaults)

        payload: dict[str, Any] = {
            "user_id": user_id,
            "username": tg.get("username"),
            "first_name": tg.get("first_name"),
            "last_name": tg.get("last_name"),
            "birth_date": tg.get("birth_date"),
            "gender": tg.get("gender"),
        }

        # создаём / upsert-им профиль в БД
        raw = self._repo.upsert_profile(user_id, payload)
        return ProfileModel(**raw)

    def update_profile(self, user_id: int, data: Any) -> ProfileModel:
        """
        Обновить профиль пользователя через БД и вернуть полный ProfileModel.

        Логика:

        1) нормализуем payload в dict;
        2) проставляем user_id;
        3) сохраняем в репозитории через upsert_profile;
        4) возвращаем get_or_create_profile(user_id), который уже читает
           данные ТОЛЬКО из БД (dev/Telegram — только для первичного create).
        """
        # 1) нормализация входных данных
        if hasattr(data, "dict"):
            payload: dict[str, Any] = data.dict(exclude_unset=True)
        elif isinstance(data, dict):
            payload = dict(data)
        else:
            raise TypeError(
                "update_profile data must be a dict or have a .dict() method"
            )

        # user_id — источник истины
        payload["user_id"] = user_id

        # 2–3) сохраняем в БД
        self._repo.upsert_profile(user_id, payload)

        # 4) возвращаем актуальный профиль ИЗ БД
        return self.get_or_create_profile(user_id)
