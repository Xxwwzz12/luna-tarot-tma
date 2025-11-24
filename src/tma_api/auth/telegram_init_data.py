# src/tma_api/auth/telegram_init_data.py

import hmac
import hashlib
import json
import urllib.parse
from typing import Dict, Any
from fastapi import HTTPException, status


UNAUTHORIZED_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid Telegram initData",
)


def _raise_unauthorized() -> None:
    """
    Вспомогательная функция, чтобы в одном месте задать форму ошибки.
    """
    # Отдельная функция нужна, чтобы избежать копипасты и при этом
    # не создавать новый объект исключения каждый раз (опционально).
    raise UNAUTHORIZED_EXCEPTION


def parse_init_data(raw_init_data: str) -> Dict[str, str]:
    """
    Парсит строку initData вида:
    query_id=AAH...&user=%7B%22id%22%3A12345%2C...%7D&auth_date=...&hash=...

    Требования:
    - не менять порядок полей (dict в Python 3.7+ сохраняет порядок вставки);
    - не удалять и не сортировать поля при парсинге;
    - percent-decode только значений, не ключей;
    - при дублирующихся ключах — считаем initData невалидным.
    """
    try:
        if not raw_init_data:
            _raise_unauthorized()

        data: Dict[str, str] = {}

        # Разбираем вручную, чтобы не декодировать ключи
        pairs = raw_init_data.split("&")
        for pair in pairs:
            if not pair:
                continue

            if "=" in pair:
                key, value = pair.split("=", 1)
            else:
                key, value = pair, ""

            # Нельзя декодировать ключи, только значения
            decoded_value = urllib.parse.unquote_plus(value)

            if key in data:
                # Дубликат ключа — считаем initData невалидным
                _raise_unauthorized()

            data[key] = decoded_value

        if not data:
            _raise_unauthorized()

        return data
    except HTTPException:
        # Уже правильно оформленная ошибка
        raise
    except Exception:
        _raise_unauthorized()


def calculate_check_string(data_dict: Dict[str, Any]) -> str:
    """
    Формирует check_string по правилам Telegram:

    1. Исключаем ключ 'hash'.
    2. Упорядочиваем оставшиеся ключи по алфавиту.
    3. Каждый параметр в формате "key=value".
    4. Склеиваем параметры через '\n'.

    Пример:
        auth_date=168...
        query_id=AAH...
        user={"id":12345,...}
    """
    try:
        # Исключаем hash
        items = [
            (k, v)
            for k, v in data_dict.items()
            if k != "hash"
        ]

        # Сортировка по алфавиту по ключам
        items.sort(key=lambda item: item[0])

        # Формируем строки "key=value"
        lines = [f"{key}={value}" for key, value in items]
        return "\n".join(lines)
    except Exception:
        _raise_unauthorized()


def validate_init_data(raw_init_data: str, bot_token: str) -> Dict[str, Any]:
    """
    Главная функция валидации initData.

    Шаги:
    1. Парсит raw initData → dict.
    2. Извлекает hash.
    3. Строит check_string.
    4. Вычисляет секрет:
       secret_key = hashlib.sha256(f"WebAppData{bot_token}".encode()).digest()
    5. Считает HMAC-SHA256 от check_string.
    6. Сравнивает calculated_hash с hash из initData.
       При несовпадении — Unauthorized.
    7. Парсит поле user (JSON-строка) и возвращает user (dict).

    Все ошибки — HTTPException 401 с detail "Invalid Telegram initData".
    """
    try:
        if not bot_token:
            _raise_unauthorized()

        data = parse_init_data(raw_init_data)

        received_hash = data.get("hash")
        if not received_hash:
            _raise_unauthorized()

        check_string = calculate_check_string(data)

        # Секретный ключ по спецификации Telegram WebApp
        secret_key = hashlib.sha256(
            f"WebAppData{bot_token}".encode("utf-8")
        ).digest()

        calculated_hash = hmac.new(
            secret_key,
            msg=check_string.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()

        # Используем безопасное сравнение
        if not hmac.compare_digest(calculated_hash, received_hash):
            _raise_unauthorized()

        user_raw = data.get("user")
        if not user_raw:
            _raise_unauthorized()

        user = json.loads(user_raw)

        if not isinstance(user, dict):
            _raise_unauthorized()

        return user

    except HTTPException:
        # Уже нормализованная ошибка 401
        raise
    except Exception:
        _raise_unauthorized()
