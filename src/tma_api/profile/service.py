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
    # Публичный интерфейс
    # --------------------------------------------------------------------- #

    def get_or_create_profile(self, user_id: int, **defaults: Any) -> ProfileModel:
        """
        Получить профиль пользователя или создать "скелет" при отсутствии.

        Возвращает ProfileModel (как и раньше).

        defaults — данные, которые можно использовать при создании
        новой записи (username, first_name, last_name, birth_date, gender).
        """
        raw = self._repo.get_profile(user_id)

        if raw is None:
            # Новая запись — собираем минимальный набор данных из defaults.
            new_data: dict[str, Any] = {
                "user_id": user_id,
                "username": defaults.get("username"),
                "first_name": defaults.get("first_name"),
                "last_name": defaults.get("last_name"),
                "birth_date": defaults.get("birth_date"),
                "gender": defaults.get("gender"),
            }

            # репозиторий сам проставит created_at / updated_at
            raw = self._repo.upsert_profile(user_id, new_data)

        return ProfileModel(**raw)

    def update_profile(self, user_id: int, data: Any) -> ProfileModel:
        """
        Обновить профиль пользователя и вернуть полный ProfileModel.

        Цель по ТЗ:
          1) сохранить изменения в user_db / репозитории;
          2) перечитать профиль (с age, zodiac и т.п.) и вернуть его.

        data может быть:
          - Pydantic-моделью (ProfileUpdateIn и т.п.) с методом .dict();
          - обычным dict.
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

        # 1) сохраняем изменения
        self._repo.upsert_profile(user_id, payload)

        # 2) перечитываем профиль тем же путём, что и для GET /profile
        # (через get_or_create_profile, чтобы вся логика age/zodiac и т.п.
        #  оставалась централизованной)
        return self.get_or_create_profile(user_id)
