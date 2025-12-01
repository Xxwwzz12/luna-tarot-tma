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
        ТЗ 5.2 / 6.1 — ЖЁСТКИЙ приоритет БД над dev/Telegram.

        Логика:

        1) db_profile = repo.get_profile(user_id)
        2) Если db_profile есть:
             - вообще не смотрим на dev/Telegram;
             - возвращаем ProfileModel ТОЛЬКО из db_profile.
        3) Если db_profile нет:
             - берём tg = _get_telegram_or_dev_profile(...);
             - формируем payload из tg;
             - создаём запись в БД через upsert_profile;
             - перечитываем из БД и возвращаем ProfileModel.
        """
        db_profile = self._repo.get_profile(user_id)

        # 2) В БД уже есть профиль → dev/Telegram не смотрим вообще
        if db_profile is not None:
            return ProfileModel(**db_profile)

        # 3) В БД нет профиля → создаём из dev/Telegram один раз
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

        # ещё раз читаем из БД (на случай, если репозиторий что-то дополнил)
        db_profile = self._repo.get_profile(user_id) or payload
        return ProfileModel(**db_profile)

    def update_profile(self, user_id: int, body: Any) -> ProfileModel:
        """
        ТЗ 5.1 — update_profile обязан писать именно body в репозиторий.

        Логика:

        1) existing = repo.get_profile(user_id) (чтобы сохранить username, если он был);
        2) сформировать payload из body (first_name, last_name, birth_date, gender,
           username при необходимости);
        3) вызвать repo.upsert_profile(user_id, payload);
        4) вернуть self.get_or_create_profile(user_id).

        ВАЖНО:
        - НИГДЕ здесь НЕ трогаем dev/Telegram профиль.
        """
        # 1) читаем текущее состояние из БД (можем вытащить username и прочее)
        existing = self._repo.get_profile(user_id) or {}

        # 2) нормализуем body → dict
        if hasattr(body, "dict"):
            body_data: dict[str, Any] = body.dict(exclude_unset=True)
        elif isinstance(body, dict):
            body_data = dict(body)
        else:
            raise TypeError(
                "update_profile body must be a dict or have a .dict() method"
            )

        # 3) формируем payload именно из body + существующего username
        payload: dict[str, Any] = {
            "user_id": user_id,
            # username берём из existing, чтобы не терять dev/username,
            # если фронт его не редактирует. Но это уже значение ИЗ БД,
            # а не из dev-профиля.
            "username": body_data.get("username", existing.get("username")),
            "first_name": body_data.get("first_name"),
            "last_name": body_data.get("last_name"),
            "birth_date": body_data.get("birth_date"),
            "gender": body_data.get("gender"),
        }

        # 4) сохраняем в БД
        self._repo.upsert_profile(user_id, payload)

        # 5) возвращаем актуальный профиль ИЗ БД
        return self.get_or_create_profile(user_id)
