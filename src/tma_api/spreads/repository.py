# src/tma_api/spreads/repository.py

from __future__ import annotations

from typing import Protocol, Any, Iterable, Tuple, List, Dict


class SpreadRepository(Protocol):
    """
    Абстрактный репозиторий раскладов и вопросов.

    Отличия по контракту:

    - get_spread / list_questions НЕ принимают user_id — проверка владельца лежит на сервисе.
    - list_spreads делает пагинацию по user_id и возвращает (total, items).
    """

    def save_spread(self, data: Dict[str, Any]) -> int:
        """Сохранить расклад. Вернуть id."""
        ...

    def get_spread(self, spread_id: int) -> Dict[str, Any] | None:
        """Получить расклад по id или None."""
        ...

    def list_spreads(
        self, user_id: int, offset: int, limit: int
    ) -> Tuple[int, List[Dict[str, Any]]]:
        """
        Вернуть (total_items, items) для раскладов пользователя.

        offset / limit — параметры пагинации.
        """
        ...

    def save_question(self, data: Dict[str, Any]) -> int:
        """Сохранить уточняющий вопрос. Вернуть id."""
        ...

    def list_questions(self, spread_id: int) -> List[Dict[str, Any]]:
        """Вернуть список вопросов по id расклада."""
        ...


class InMemorySpreadRepository(SpreadRepository):
    """
    Простая in-memory реализация для dev-режима и тестов.

    Хранит данные в локальных словарях процесса.
    """

    def __init__(self) -> None:
        self._spreads: Dict[int, Dict[str, Any]] = {}
        self._questions: Dict[int, Dict[str, Any]] = {}
        self._spread_counter: int = 0
        self._question_counter: int = 0

    # --- Расклады ---

    def save_spread(self, data: Dict[str, Any]) -> int:
        spread_id = int(data.get("id") or 0)
        if spread_id > 0 and spread_id in self._spreads:
            # update
            stored = self._spreads[spread_id].copy()
            stored.update(data)
            stored["id"] = spread_id
            self._spreads[spread_id] = stored
            return spread_id

        # insert
        self._spread_counter += 1
        spread_id = self._spread_counter
        stored = data.copy()
        stored["id"] = spread_id
        self._spreads[spread_id] = stored
        return spread_id

    def get_spread(self, spread_id: int) -> Dict[str, Any] | None:
        return self._spreads.get(spread_id)

    def list_spreads(
        self, user_id: int, offset: int, limit: int
    ) -> Tuple[int, List[Dict[str, Any]]]:
        # фильтруем по user_id
        items = [
            s
            for s in self._spreads.values()
            if int(s.get("user_id") or 0) == int(user_id)
        ]

        # сортировка: сначала по created_at DESC, затем по id DESC
        def _sort_key(s: Dict[str, Any]):
            return (
                s.get("created_at") or "",
                int(s.get("id") or 0),
            )

        items.sort(key=_sort_key, reverse=True)

        total = len(items)
        if offset < 0:
            offset = 0
        if limit <= 0:
            page_items = items[offset:]
        else:
            page_items = items[offset : offset + limit]

        return total, page_items

    # --- Вопросы ---

    def save_question(self, data: Dict[str, Any]) -> int:
        qid = int(data.get("id") or 0)
        if qid > 0 and qid in self._questions:
            stored = self._questions[qid].copy()
            stored.update(data)
            stored["id"] = qid
            self._questions[qid] = stored
            return qid

        self._question_counter += 1
        qid = self._question_counter
        stored = data.copy()
        stored["id"] = qid
        self._questions[qid] = stored
        return qid

    def list_questions(self, spread_id: int) -> List[Dict[str, Any]]:
        items = [
            q
            for q in self._questions.values()
            if int(q.get("spread_id") or 0) == int(spread_id)
        ]

        # сортируем по времени ASC, потом по id ASC
        def _sort_key(q: Dict[str, Any]):
            return (
                q.get("created_at") or "",
                int(q.get("id") or 0),
            )

        items.sort(key=_sort_key)
        return items


class SQLiteSpreadRepository(SpreadRepository):
    """
    Обёртка над реальной SQLite-реализацией.

    Нужна, чтобы:

    - сервис импортировал её из одного места: src.tma_api.spreads.repository;
    - избежать жёсткого циклического импорта между repository.py и sqlite_repository.py.

    Внутри лениво создаём экземпляр настоящего репозитория.
    """

    def __init__(self, conn_factory) -> None:
        # Ленивая загрузка, чтобы не словить цикл импортов на уровне модулей
        from .sqlite_repository import SQLiteSpreadRepository as _Impl

        self._inner: SpreadRepository = _Impl(conn_factory)

    def save_spread(self, data: Dict[str, Any]) -> int:
        return self._inner.save_spread(data)

    def get_spread(self, spread_id: int) -> Dict[str, Any] | None:
        return self._inner.get_spread(spread_id)

    def list_spreads(
        self, user_id: int, offset: int, limit: int
    ) -> Tuple[int, List[Dict[str, Any]]]:
        return self._inner.list_spreads(user_id, offset, limit)

    def save_question(self, data: Dict[str, Any]) -> int:
        return self._inner.save_question(data)

    def list_questions(self, spread_id: int) -> List[Dict[str, Any]]:
        return self._inner.list_questions(spread_id)


__all__ = [
    "SpreadRepository",
    "InMemorySpreadRepository",
    "SQLiteSpreadRepository",
]
