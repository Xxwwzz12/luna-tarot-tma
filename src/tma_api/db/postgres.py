# src/tma_api/db/postgres.py

import logging
import os
from typing import Optional
from urllib.parse import urlparse

import psycopg
from psycopg.rows import dict_row

logger = logging.getLogger(__name__)

# Читаем один раз при импорте
DATABASE_URL: str = os.getenv("DATABASE_URL", "").strip()

# Флаг, чтобы не спамить логами
_LOGGED_DB_URL: bool = False


def _mask_db_url(url: str) -> str:
    """
    Возвращает "обрезанный" вариант DATABASE_URL без пароля:
    scheme://user@host:port/dbname

    Если распарсить не удалось — возвращает "<invalid DATABASE_URL>".
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return "<invalid DATABASE_URL>"

    scheme = parsed.scheme or "postgresql"
    user = parsed.username or ""
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    path = parsed.path or ""

    # На всякий случай, если вообще ничего нет
    if not any([user, host, path]):
        return "<invalid DATABASE_URL>"

    # query/params обычно не чувствительные, но для простоты не логируем
    return f"{scheme}://{user}@{host}{port}{path}"


def _log_db_url_once() -> None:
    """
    Логирует безопасный вариант DATABASE_URL только один раз за жизнь процесса.
    Не выводит пароль и query-параметры.
    """
    global _LOGGED_DB_URL

    if _LOGGED_DB_URL:
        return

    if not DATABASE_URL:
        logger.warning(
            "DATABASE_URL is empty; Postgres connectivity for tma_api is disabled."
        )
        _LOGGED_DB_URL = True
        return

    safe_url = _mask_db_url(DATABASE_URL)
    logger.info("Using Postgres DATABASE_URL: %s", safe_url)
    _LOGGED_DB_URL = True


def get_pg_connection() -> psycopg.Connection:
    """
    Возвращает sync-подключение к Postgres с row_factory=dict_row.
    Используется репозиторием (PostgresSpreadRepository).

    Подключается по DATABASE_URL из ENV.
    Если DATABASE_URL не задан — бросает RuntimeError.
    """
    if not DATABASE_URL:
        # Логируем один раз, чтобы было видно причину
        _log_db_url_once()
        raise RuntimeError("DATABASE_URL is not set for Postgres")

    # Логируем безопасный URL (без пароля) при первом обращении
    _log_db_url_once()

    conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    return conn
