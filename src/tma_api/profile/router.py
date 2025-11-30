# src/tma_api/profile/router.py

from fastapi import APIRouter, Depends

from .service import ProfileService
from .models import ProfileModel, ProfileUpdateIn
from src.tma_api.auth.dependencies import get_current_user
from src.tma_api.common.api_response import APIResponse

router = APIRouter(prefix="/profile", tags=["profile"])

# Сервис сам выберет Postgres / SQLite / UserDatabase по ENV
profile_service = ProfileService()


@router.get("", response_model=APIResponse)
async def get_profile(user: dict = Depends(get_current_user)):
    """
    Возвращает профиль пользователя.
    Контракт остаётся тем же.
    """
    profile = profile_service.get_or_create_profile(
        user_id=user["id"],
        username=user.get("username"),
        first_name=user.get("first_name"),
        last_name=user.get("last_name"),
    )
    return APIResponse.ok(profile)


@router.post("", response_model=APIResponse)
async def update_profile(
    body: ProfileUpdateIn,
    user: dict = Depends(get_current_user),
):
    """
    Обновляет профиль и возвращает актуальный профиль.
    Раньше возвращалось APIResponse.ok(True) — это исправлено.
    """
    profile = profile_service.update_profile(
        user_id=user["id"],
        data=body,
    )
    return APIResponse.ok(profile)
