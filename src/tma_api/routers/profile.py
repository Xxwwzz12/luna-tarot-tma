# src/tma_api/routers/profile.py
from datetime import datetime
from typing import Optional, Literal, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..api_response import APIResponse, APIError
from ..auth.router import get_current_user


router = APIRouter(
    prefix="/profile",
    tags=["profile"],
)


# In-memory store
_FAKE_PROFILES: Dict[int, Dict[str, Any]] = {}


# -------------------------
# Models
# -------------------------
class ProfileUpdateIn(BaseModel):
    birth_date: Optional[str] = Field(
        default=None,
        description="Дата рождения в формате YYYY-MM-DD",
    )
    gender: Optional[Literal["male", "female", "other"]] = Field(
        default=None,
        description="Пол",
    )


class ProfileOut(BaseModel):
    user_id: int
    username: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    birth_date: Optional[str]
    gender: Optional[str]
    age: Optional[int]
    zodiac: Optional[str]


class ProfileDeleteResult(BaseModel):
    deleted: bool


# -------------------------
# Helpers
# -------------------------
def _parse_iso_date(value: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "validation_error",
                "message": "Неверный формат даты рождения, ожидается YYYY-MM-DD",
                "details": {
                    "field": "birth_date",
                    "expected_format": "YYYY-MM-DD",
                    "value": value,
                },
            },
        )


def _calculate_age(birth_date: datetime) -> int:
    today = datetime.utcnow().date()
    bd = birth_date.date()
    return today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))


def _calculate_zodiac(day: int, month: int) -> str:
    if (month == 12 and day >= 22) or (month == 1 and day <= 19):
        return "♑️ Козерог"
    if (month == 1 and day >= 20) or (month == 2 and day <= 18):
        return "♒️ Водолей"
    if (month == 2 and day >= 19) or (month == 3 and day <= 20):
        return "♓️ Рыбы"
    if (month == 3 and day >= 21) or (month == 4 and day <= 19):
        return "♈️ Овен"
    if (month == 4 and day >= 20) or (month == 5 and day <= 20):
        return "♉️ Телец"
    if (month == 5 and day >= 21) or (month == 6 and day <= 20):
        return "♊️ Близнецы"
    if (month == 6 and day >= 21) or (month == 7 and day <= 22):
        return "♋️ Рак"
    if (month == 7 and day >= 23) or (month == 8 and day <= 22):
        return "♌️ Лев"
    if (month == 8 and day >= 23) or (month == 9 and day <= 22):
        return "♍️ Дева"
    if (month == 9 and day >= 23) or (month == 10 and day <= 22):
        return "♎️ Весы"
    if (month == 10 and day >= 23) or (month == 11 and day <= 21):
        return "♏️ Скорпион"
    if (month == 11 and day >= 22) or (month == 12 and day <= 21):
        return "♐️ Стрелец"
    return "Неизвестно"


def _build_profile_out(current_user: Dict[str, Any]) -> ProfileOut:
    user_id = current_user["id"]
    stored = _FAKE_PROFILES.get(user_id, {})

    birth_date_str = stored.get("birth_date")
    gender = stored.get("gender")

    age = None
    zodiac = None

    if birth_date_str:
        try:
            dt = _parse_iso_date(birth_date_str)
            age = _calculate_age(dt)
            zodiac = _calculate_zodiac(dt.day, dt.month)
        except HTTPException:
            age = None
            zodiac = None

    return ProfileOut(
        user_id=user_id,
        username=current_user.get("username"),
        first_name=current_user.get("first_name"),
        last_name=current_user.get("last_name"),
        birth_date=birth_date_str,
        gender=gender,
        age=age,
        zodiac=zodiac,
    )


# -------------------------
# Endpoints
# -------------------------
@router.get("", response_model=APIResponse)
def get_profile(current_user: Dict[str, Any] = Depends(get_current_user)):
    profile = _build_profile_out(current_user)
    return APIResponse(ok=True, data=profile)


@router.post("", response_model=APIResponse)
def update_profile(
    current_user: Dict[str, Any] = Depends(get_current_user),
    body: ProfileUpdateIn = None,
):
    user_id = current_user["id"]

    birth_date = body.birth_date
    gender = body.gender

    # validate birth date
    if birth_date is not None:
        _ = _parse_iso_date(birth_date)

    # update in-memory
    stored = _FAKE_PROFILES.get(user_id, {})
    if birth_date is not None:
        stored["birth_date"] = birth_date
    if gender is not None:
        stored["gender"] = gender
    _FAKE_PROFILES[user_id] = stored

    # rebuild with age/zodiac
    profile = _build_profile_out(current_user)

    response_data = {
        "user_id": profile.user_id,
        "username": profile.username,
        "first_name": profile.first_name,
        "last_name": profile.last_name,
        "birth_date": profile.birth_date,
        "gender": profile.gender,
        "zodiac": profile.zodiac,
        "age": profile.age,
    }

    return APIResponse(
        ok=True,
        data=response_data,
        error=None,
    )


@router.delete("", response_model=APIResponse)
def delete_profile(current_user: Dict[str, Any] = Depends(get_current_user)):
    user_id = current_user["id"]
    deleted = False

    if user_id in _FAKE_PROFILES:
        del _FAKE_PROFILES[user_id]
        deleted = True

    return APIResponse(ok=True, data=ProfileDeleteResult(deleted=deleted))
