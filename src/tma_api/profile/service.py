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
    Профиль-сервис TMA API.

    Главный принцип:
    - БД — источник истины.
    - Telegram/dev-профиль используется только как fallback для пустых полей.
    """

    def __init__(self, repo: Any | None = None) -> None:
        backend = os.getenv("TMA_DB_BACKEND", "").strip().lower()
        db_url = os.getenv("DATABASE_URL", "").strip()

        if repo is not None:
            self._repo = repo
            logger.info("ProfileService: using injected repository %s", type(repo).__name__)
            return

        if backend == "postgres" and db_url:
            try:
                self._repo = PostgresProfileRepository()
                logger.info("ProfileService: using PostgresProfileRepository")
                return
            except Exception:
                logger.exception("Failed to init PostgresProfileRepository, falling back to UserDatabase")

        # fallback / default
        self._repo = UserDatabase()
        logger.info("ProfileService: using UserDatabase (default/fallback)")

    # ------------------------------------------------------------------ #
    # internal
    # ------------------------------------------------------------------ #

    def _get_telegram_or_dev_profile(self, defaults: dict[str, Any]) -> dict[str, Any]:
        """
        Формируем "сырой Telegram/dev профиль":
        username, first_name, last_name, birth_date, gender
        (birth_date, gender — редко приходят, но оставляем на будущее).
        """
        return {
            "username": defaults.get("username"),
            "first_name": defaults.get("first_name"),
            "last_name": defaults.get("last_name"),
            "birth_date": defaults.get("birth_date"),
            "gender": defaults.get("gender"),
        }

    # ------------------------------------------------------------------ #
    # public
    # ------------------------------------------------------------------ #

    def get_or_create_profile(self, user_id: int, **defaults: Any) -> ProfileModel:
        """
        Логика по ТЗ:

        1) Читаем БД:
             db_profile = {...} или {}

        2) Получаем Telegram/dev-профиль:
             tg = {...}

        3) Схема сборки итоговых значений:
             username   = db.username   or tg.username
             first_name = db.first_name or tg.first_name
             last_name  = db.last_name  or tg.last_name
             birth_date = db.birth_date or tg.birth_date
             gender     = db.gender     or tg.gender

        4) Если db_profile пустой — создаём новую запись в БД,
           используя tg-данные, чтобы затем БД стала источником истины.

        5) Всегда возвращаем ProfileModel.
        """
        db_profile: dict[str, Any] = self._repo.get_profile(user_id) or {}
        tg = self._get_telegram_or_dev_profile(defaults)

        # Итоговые значения (БД имеет приоритет)
        username = db_profile.get("username") or tg.get("username")
        first_name = db_profile.get("first_name") or tg.get("first_name")
        last_name = db_profile.get("last_name") or tg.get("last_name")
        birth_date = db_profile.get("birth_date") or tg.get("birth_date")
        gender = db_profile.get("gender") or tg.get("gender")

        # Если профиля в БД ещё нет — создаём его, используя tg-данные
        if not db_profile:
            payload = {
                "user_id": user_id,
                "username": username,
                "first_name": first_name,
                "last_name": last_name,
                "birth_date": birth_date,
                "gender": gender,
            }
            raw = self._repo.upsert_profile(user_id, payload)
            return ProfileModel(**raw)

        # Если есть — просто возвращаем объединённые данные (но БД доминирует)
        combined = {
            "user_id": user_id,
            "username": username,
            "first_name": first_name,
            "last_name": last_name,
            "birth_date": birth_date,
            "gender": gender,
            "created_at": db_profile.get("created_at"),
            "updated_at": db_profile.get("updated_at"),
        }

        return ProfileModel(**combined)

    # ------------------------------------------------------------------ #

    def update_profile(self, user_id: int, data: Any) -> ProfileModel:
        """
        Обновление профиля с возвращением ПОЛНОГО результата.
        Логика по ТЗ:

        1) нормализуем data в dict;
        2) добавляем user_id;
        3) сохраняем в БД через upsert_profile;
        4) return self.get_or_create_profile(user_id) — чтобы вернуть
           поля age, zodiac и 100% актуальный профиль.
        """
        if hasattr(data, "dict"):
            payload: dict[str, Any] = data.dict(exclude_unset=True)
        elif isinstance(data, dict):
            payload = dict(data)
        else:
            raise TypeError("update_profile data must be a dict or Pydantic model")

        payload["user_id"] = user_id

        self._repo.upsert_profile(user_id, payload)

        # ОБЯЗАТЕЛЬНО: возвращаем собранный профиль (БД + tg fallback)
        return self.get_or_create_profile(user_id)
