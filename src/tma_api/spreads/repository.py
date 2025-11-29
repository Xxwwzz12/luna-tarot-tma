# src/tma_api/spreads/repository.py

from __future__ import annotations

from typing import Any, Dict, List, Protocol, Tuple


class SpreadRepository(Protocol):
    """
    Абстрактный интерфейс репозитория раскладов.

    Важно: сигнатуры методов синхронизированы с реализациями.
    """

    def save_spread(self, data: dict[str, Any]) -> int:
        """
        Сохранить расклад, вернуть его ID.
        """
        ...

    def get_spread(self, spread_id: int) -> dict[str, Any] | None:
        """
        Получить один расклад по ID (без проверки user_id).
        Проверка "чей расклад" должна быть на уровне сервиса.
        """
        ...

    def list_spreads(
        self,
        user_id: int,
        offset: int,
        limit: int,
    ) -> tuple[int, list[dict[str, Any]]]:
        """
        Вернуть (total, items) по user_id с учётом offset/limit.
        """
        ...

    def save_question(self, data: dict[str, Any]) -> int:
        """
        Сохранить вопрос к раскладу, вернуть его ID.
        """
        ...

    def list_questions(self, spread_id: int) -> list[dict[str, Any]]:
        """
        Вернуть список вопросов по spread_id (без проверки user_id).
        Проверка "чужой вопрос" — на уровне сервиса.
        """
        ...


class InMemorySpreadRepository(SpreadRepository):
    """
    Простая in-memory реализация репозитория.

    Сейчас это по сути инкапсулирует текущий подход с _SPREADS / _QUESTIONS,
    но в одном месте и с понятным интерфейсом. Позже можно заменить или
    дополнить SQL-реализацией.
    """

    def __init__(self) -> None:
        # Хранилище раскладов: spread_id -> dict
        self._spreads: Dict[int, Dict[str, Any]] = {}
        self._spread_index: int = 0

        # Хранилище вопросов: question_id -> dict
        self._questions: Dict[int, Dict[str, Any]] = {}
        self._question_index: int = 0

    # ---- Внутренние helpers ----

    def _next_spread_id(self) -> int:
        self._spread_index += 1
        return self._spread_index

    def _next_question_id(self) -> int:
        self._question_index += 1
        return self._question_index

    # ---- SpreadRepository implementation ----

    def save_spread(self, data: dict[str, Any]) -> int:
        """
        Сохраняем расклад.

        Если id не передан в data — создаём новый, иначе перезаписываем существующий.
        """
        spread_id = data.get("id")
        if not isinstance(spread_id, int):
            spread_id = self._next_spread_id()
            data = {**data, "id": spread_id}

        self._spreads[spread_id] = data
        return spread_id

    def get_spread(self, spread_id: int) -> dict[str, Any] | None:
        return self._spreads.get(spread_id)

    def list_spreads(
        self,
        user_id: int,
        offset: int,
        limit: int,
    ) -> tuple[int, list[dict[str, Any]]]:
        """
        Фильтрация по user_id + простая пагинация.

        Сортируем по created_at (если есть), иначе по id (по убыванию).
        """
        items: List[Dict[str, Any]] = [
            s for s in self._spreads.values() if s.get("user_id") == user_id
        ]

        def _sort_key(item: Dict[str, Any]):
            # created_at ожидается строкой ISO, но здесь можно оставить как есть.
            # Если поля нет — сортируем по id.
            return item.get("created_at") or item.get("id") or 0

        items.sort(key=_sort_key, reverse=True)

        total = len(items)
        if offset < 0:
            offset = 0
        if limit <= 0:
            return total, []

        sliced = items[offset : offset + limit]
        return total, sliced

    def save_question(self, data: dict[str, Any]) -> int:
        """
        Сохраняем вопрос к раскладу.

        Ожидаются поля:
        - spread_id
        - text / question
        - (опционально) created_at и т.п.
        """
        question_id = data.get("id")
        if not isinstance(question_id, int):
            question_id = self._next_question_id()
            data = {**data, "id": question_id}

        self._questions[question_id] = data
        return question_id

    def list_questions(self, spread_id: int) -> list[dict[str, Any]]:
        """
        Возвращаем все вопросы для указанного расклада, по id по возрастанию.
        """
        items: List[Dict[str, Any]] = [
            q for q in self._questions.values() if q.get("spread_id") == spread_id
        ]
        items.sort(key=lambda q: q.get("id") or 0)
        return items


class SQLiteSpreadRepository(SpreadRepository):
    """
    Заглушка под будущую SQL-реализацию.

    Сейчас просто оборачивает InMemorySpreadRepository, чтобы:
    - сигнатуры методов были синхронизированы с Protocol;
    - уже можно было протаскивать этот класс по зависимостям;
    - позже заменить тело методов на реальные SQL-запросы.

    При желании можно будет принять сюда sqlite3.Connection и переписать
    внутреннюю реализацию.
    """

    def __init__(self) -> None:
        # Пока — in-memory внутри, чтобы всё работало.
        self._inner = InMemorySpreadRepository()

    def save_spread(self, data: dict[str, Any]) -> int:
        return self._inner.save_spread(data)

    def get_spread(self, spread_id: int) -> dict[str, Any] | None:
        return self._inner.get_spread(spread_id)

    def list_spreads(
        self,
        user_id: int,
        offset: int,
        limit: int,
    ) -> tuple[int, list[dict[str, Any]]]:
        return self._inner.list_spreads(user_id=user_id, offset=offset, limit=limit)

    def save_question(self, data: dict[str, Any]) -> int:
        return self._inner.save_question(data)

    def list_questions(self, spread_id: int) -> list[dict[str, Any]]:
        return self._inner.list_questions(spread_id)


__all__ = [
    "SpreadRepository",
    "InMemorySpreadRepository",
    "SQLiteSpreadRepository",
]
