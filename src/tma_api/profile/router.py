# src/tma_api/profile/router.py

from fastapi import APIRouter, Depends

from .service import ProfileService
from .models import ProfileModel, ProfileUpdateIn  # имена моделей предполагаемы из текущего кода
from src.tma_api.auth.dependencies import get_current_user

router = APIRouter(prefix="/profile", tags=["profile"])

# Один инстанс сервиса на модуль — внутри он сам решает, какой репозиторий использовать
profile_service = ProfileService()


@router.get("", response_model=ProfileModel)
async def get_profile(user: dict = Depends(get_current_user)) -> ProfileModel:
    """
    Возвращает профиль текущего пользователя.

    Контракт не меняется:
    - тот же URL: GET /profile
    - тот же JSON, что и раньше (user_id, username, name, age, zodiac, и т.д.).
    """
    # Если профиль ещё не заведён — создаём по данным из Telegram (id, username, и т.п.)
    profile = profile_service.get_or_create_profile(
        user_id=user["id"],
        username=user.get("username"),
        first_name=user.get("first_name"),
        last_name=user.get("last_name"),
    )
    return profile


@router.post("", response_model=ProfileModel)
async def update_profile(
    body: ProfileUpdateIn,
    user: dict = Depends(get_current_user),
) -> ProfileModel:
    """
    Обновляет профиль текущего пользователя.

    Контракт не меняется:
    - тот же URL: POST /profile
    - тот же payload (ProfileUpdateIn должен соответствовать старой схеме)
    - тот же JSON в ответе (ProfileModel).
    """
    profile = profile_service.update_profile(user_id=user["id"], data=body)
    return profile
