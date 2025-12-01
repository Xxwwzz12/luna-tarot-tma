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
    - Dev/Telegram-профиль используется только один раз:
      при первичном создании записи, когда профиля в БД ещё нет.
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

        В реальном коде defaults обычно берутся из initData/dev-хедеров
        на уровне роутера/авторизации.
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
        ТЗ 5.1 / 5.2 — жёсткий приоритет БД над dev/Telegram.

        Логика:

        1) db_profile = repo.get_profile(user_id)
        2) Если db_profile есть:
             - НИЧЕГО из dev/Telegram не используем.
             - return ProfileModel(**db_profile)
        3) Если db_profile нет:
             - tg = _get_telegram_or_dev_profile(...)
             - payload из tg
             - repo.upsert_profile(user_id, payload)
             - created = repo.get_profile(user_id)
             - return ProfileModel(**created)
        """
        db_profile = self._repo.get_profile(user_id)

        # 2) Профиль уже есть в БД → dev/Telegram игнорируем полностью
        if db_profile:
            return ProfileModel(**db_profile)

        # 3) Профиля нет → создаём из dev/Telegram один раз
        tg = self._get_telegram_or_dev_profile(defaults)

        payload: dict[str, Any] = {
            "user_id": user_id,
            "username": tg.get("username"),
            "first_name": tg.get("first_name"),
            "last_name": tg.get("last_name"),
            "birth_date": tg.get("birth_date"),
            "gender": tg.get("gender"),
        }

        self._repo.upsert_profile(user_id, payload)
        created = self._repo.get_profile(user_id) or payload
        return ProfileModel(**created)

    def update_profile(self, user_id: int, body: Any) -> ProfileModel:
        """
        ТЗ 5.1 — update_profile обязан писать именно body в репозиторий.

        Логика:

        1) existing = repo.get_profile(user_id) or {}  — чтобы, например,
           не потерять username, если фронт его не отправляет;
        2) payload собираем ИЗ body (first_name, last_name, birth_date, gender,
           username при необходимости), НИГДЕ не трогаем dev/Telegram;
        3) repo.upsert_profile(user_id, payload);
        4) updated = repo.get_profile(user_id);
           return ProfileModel(**updated).
        """
        existing = self._repo.get_profile(user_id) or {}

        # нормализуем body → dict
        if hasattr(body, "dict"):
            body_data: dict[str, Any] = body.dict(exclude_unset=True)
        elif isinstance(body, dict):
            body_data = dict(body)
        else:
            raise TypeError(
                "update_profile body must be a dict or have a .dict() method"
            )

        payload: dict[str, Any] = {
            "user_id": user_id,
            # username берём из существующей записи, если фронт его не прислал
            "username": body_data.get("username", existing.get("username")),
            "first_name": body_data.get("first_name"),
            "last_name": body_data.get("last_name"),
            "birth_date": body_data.get("birth_date"),
            "gender": body_data.get("gender"),
        }

        self._repo.upsert_profile(user_id, payload)
        updated = self._repo.get_profile(user_id) or payload
        return ProfileModel(**updated)
