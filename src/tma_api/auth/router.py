# src/tma_api/auth/router.py

import logging
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..settings import get_settings
from ..api_response import APIResponse, APIError
from .telegram_init_data import validate_init_data

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)

UserDict = Dict[str, Any]


class TelegramAuthRequest(BaseModel):
    init_data: str = Field(..., alias="initData")

    class Config:
        allow_population_by_field_name = True


class TelegramAuthResponse(BaseModel):
    user: UserDict
    token: Optional[str] = None


async def get_current_user(
    request: Request,
    bot_token: Any = Depends(get_settings),  # подпись сохранена
) -> UserDict:
    # 1) DEV режим (TMA_DEV_MODE=1)
    dev_mode = os.getenv("TMA_DEV_MODE") == "1"
    if dev_mode:
        dev_user_id = request.headers.get("X-Dev-User-Id")
        dev_username = request.headers.get("X-Dev-Username")

        if dev_user_id:
            return {
                "id": int(dev_user_id),
                "first_name": "Dev",
                "last_name": "User",
                "username": dev_username or "dev_user",
            }

        return {
            "id": 123,
            "first_name": "Dev",
            "last_name": "User",
            "username": "dev_user",
        }

    # 2) PROD-режим — читаем initData
    raw_init_data: Optional[str] = request.headers.get("X-Telegram-Init-Data")

    # опционально — поддержка JSON-тела
    if not raw_init_data:
        try:
            body = await request.json()
        except Exception:
            body = None
        if isinstance(body, dict):
            raw_init_data = body.get("initData") or body.get("init_data")

    if not raw_init_data:
        raise HTTPException(status_code=401, detail="X-Telegram-Init-Data header missing")

    # Универсальное получение bot_token
    settings = get_settings()
    if isinstance(settings, str):
        bot_token_value = settings
    else:
        bot_token_value = getattr(settings, "TELEGRAM_BOT_TOKEN", None)

    if not bot_token_value:
        raise HTTPException(status_code=500, detail="TELEGRAM_BOT_TOKEN is not configured")

    user = validate_init_data(raw_init_data, bot_token_value)
    return user


@router.post(
    "/telegram",
    response_model=APIResponse,
    summary="Авторизация пользователя через Telegram initData",
)
async def auth_telegram(
    payload: TelegramAuthRequest,
    settings: Any = Depends(get_settings),
) -> APIResponse:
    raw_init_data = payload.init_data

    if isinstance(settings, str):
        bot_token_value = settings
    else:
        bot_token_value = getattr(settings, "TELEGRAM_BOT_TOKEN", None)

    if not bot_token_value:
        raise HTTPException(status_code=500, detail="TELEGRAM_BOT_TOKEN is not configured")

    try:
        user = validate_init_data(raw_init_data, bot_token_value)
    except HTTPException as exc:
        raise exc
    except Exception:
        logger.exception("Unexpected error in /auth/telegram")
        raise HTTPException(status_code=500, detail="Internal server error")

    response_data = TelegramAuthResponse(user=user, token=None)

    return APIResponse(ok=True, data=response_data.dict(), error=None)
