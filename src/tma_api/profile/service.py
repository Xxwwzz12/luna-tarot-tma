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

    Важно: публичный интерфейс остаётся прежним:
      - get_or_create_profile(user_id: int, ...) -> ProfileModel
      - update_profile(user_id: int, ...) -> ProfileModel

    Внутри меняется только источник хранения:
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
                # Если не смогли поднять Postgres — логируем и
                # падаем обратно на UserDatabase, чтобы не ломать прод.
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

        Интерфейс метода остаётся тем же: первый аргумент — user_id,
        остальные параметры как и раньше (username, first_name, last_name и т.п.)
        передаются как именованные аргументы, и используются только при
        создании новой записи.

        Возвращает ProfileModel (как и раньше).
        """
        raw = self._repo.get_profile(user_id)

        if raw is None:
            # Новая запись — собираем минимальный набор данных из defaults.
            new_data: dict[str, Any] = {
                "user_id": user_id,
                # эти ключи безопасны: если чего-то нет в defaults,
                # просто запишется None
                "username": defaults.get("username"),
                "first_name": defaults.get("first_name"),
                "last_name": defaults.get("last_name"),
                "birth_date": defaults.get("birth_date"),
                "gender": defaults.get("gender"),
            }

            # репозиторий сам проставит created_at / updated_at
            raw = self._repo.upsert_profile(user_id, new_data)

        # На этом уровне мы работаем только с "сырыми" dict,
        # а преобразование в Pydantic-модель оставляем ProfileModel.
        return ProfileModel(**raw)

    def update_profile(self, user_id: int, payload: Any) -> ProfileModel:
        """
        Обновить профиль пользователя.

        Интерфейс сохраняем максимально гибким, чтобы не ломать существующий
        код в роутере:

        - payload может быть:
            * Pydantic-моделью (ProfileUpdateIn и т.п.) с методом .dict();
            * обычным dict.
        """
        # Унифицируем payload → dict с учётом exclude_unset, если это Pydantic.
        if hasattr(payload, "dict"):
            # Pydantic BaseModel: используем только переданные поля.
            data: dict[str, Any] = payload.dict(exclude_unset=True)
        elif isinstance(payload, dict):
            data = dict(payload)
        else:
            raise TypeError(
                "update_profile payload must be a dict or have a .dict() method"
            )

        # user_id — источник истины, не даём перезаписать его из payload.
        data["user_id"] = user_id

        raw = self._repo.upsert_profile(user_id, data)
        return ProfileModel(**raw)
