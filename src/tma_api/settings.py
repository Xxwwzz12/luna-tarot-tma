# src/tma_api/settings.py

from functools import lru_cache
import os


@lru_cache
def get_settings():
    """
    Лёгкая обёртка настроек для TMA API.

    Сейчас для tma_api/auth/router важно только TELEGRAM_BOT_TOKEN.
    Возвращаем строку токена — это совместимо с текущей логикой
    get_current_user (там бот-токен просто передаётся в validate_init_data).
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    return token
