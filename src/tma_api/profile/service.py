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

    Публичный интерфейс:
      - get_or_create_profile(user_id: int, ...) -> ProfileModel
      - update_profile(user_id: int, data: Any) -> ProfileModel

    Источник хранения:
      - PostgresProfileRepository при TMA_DB_BACKEND=postgres и наличии DATABASE_URL
      - UserDatabase во всех остальных случаях.
    """

    def __init__(self, repo: Any | None = None) -> None:
        """
        Инициализация репозитория профиля.

        repo:
          - если передан явно — используем как есть (например, в тестах);
          - иначе:
              * при TMA_DB_BACKEND=postgres и наличии DATABASE_URL —
                PostgresProfileRepository;
              * иначе — UserDatabase (текущая SQLite/файловая реализация).
        """
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

        # default / fallback путь — старая реализация через UserDatabase
        self._repo = UserDatabase()
        logger.info("ProfileService: using UserDatabase (default/fallback)")

    # --------------------------------------------------------------------- #
    # Внутренние хелперы
    # --------------------------------------------------------------------- #

    def _get_telegram_or_dev_profile(self, defaults: dict[str, Any]) -> dict[str, Any]:
        """
        Условный "Telegram / dev профиль".

        По сути — то, что мы можем извлечь из initData или dev-хедеров
        и уже пробросили в get_or_create_profile через **defaults.
        """
        return {
            "username": defaults.get("username"),
            "first_name": defaults.get("first_name"),
            "last_name": defaults.get("last_name"),
        }

    # --------------------------------------------------------------------- #
    # Публичный интерфейс
    # --------------------------------------------------------------------- #

    def get_or_create_profile(self, user_id: int, **defaults: Any) -> ProfileModel:
        """
        Получить профиль пользователя или создать его, аккуратно объединив:

          - данные из БД (db_profile)
          - "сырой" Telegram/dev профиль (tg_profile из initData/headers)

        Правило объединения:

          first_name = db.first_name or tg.first_name
          last_name  = db.last_name  or tg.last_name
          username   = db.username   or tg.username
          birth_date = db.birth_date           # только из БД
          gender     = db.gender               # только из БД
        """
        # 1) Берём, что есть в БД (или пустой dict) и "телеграм-профиль"
        db_profile: dict[str, Any] = self._repo.get_profile(user_id) or {}
        tg_profile: dict[str, Any] = self._get_telegram_or_dev_profile(defaults)

        # 2) Собираем итоговые значения с приоритетом БД
        username = db_profile.get("username") or tg_profile.get("username")
        first_name = db_profile.get("first_name") or tg_profile.get("first_name")
        last_name = db_profile.get("last_name") or tg_profile.get("last_name")
        birth_date = db_profile.get("birth_date")
        gender = db_profile.get("gender")

        # 3а) Если в БД ещё нет записи — создаём новую, сразу скомбинировав данные
        if not db_profile:
            new_data: dict[str, Any] = {
                "user_id": user_id,
                "username": username,
                "first_name": first_name,
                "last_name": last_name,
                "birth_date": birth_date,
                "gender": gender,
            }
            raw = self._repo.upsert_profile(user_id, new_data)
            return ProfileModel(**raw)

        # 3б) Если запись есть — по желанию можем "дополнить" её тем,
        # что приехало из Telegram/dev (но НЕ трогаем birth_date/gender).
        updated = dict(db_profile)
        changed = False

        for field, value in (
            ("username", username),
            ("first_name", first_name),
            ("last_name", last_name),
        ):
            if value is not None and updated.get(field) != value:
                updated[field] = value
                changed = True

        if changed:
            raw = self._repo.upsert_profile(user_id, updated)
        else:
            raw = db_profile

        return ProfileModel(**raw)

    def update_profile(self, user_id: int, data: Any) -> ProfileModel:
        """
        Обновить профиль пользователя и вернуть ПОЛНЫЙ ProfileModel.

        Логика по ТЗ:

          1) нормализуем data в dict,
          2) добавляем user_id,
          3) сохраняем в репозиторий через upsert_profile,
          4) обязательно делаем return self.get_or_create_profile(user_id),
             чтобы на выходе были все производные поля (age, zodiac и т.п.)
             + актуальное слияние с Telegram/dev-профилем при необходимости.
        """
        # 1) нормализуем payload → dict
        if hasattr(data, "dict"):
            payload: dict[str, Any] = data.dict(exclude_unset=True)
        elif isinstance(data, dict):
            payload = dict(data)
        else:
            raise TypeError(
                "update_profile data must be a dict or have a .dict() method"
            )

        # user_id всегда берём из аргумента, не даём перезаписать его из payload
        payload["user_id"] = user_id

        # 2) сохраняем изменения
        self._repo.upsert_profile(user_id, payload)

        # 3–4) перечитываем профиль тем же путём, что и для GET /profile
        # (через get_or_create_profile, где уже есть логика объединения
        #  с Telegram/dev-профилем и расчёт производных полей).
        return self.get_or_create_profile(user_id)
