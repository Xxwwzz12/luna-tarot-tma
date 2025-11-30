# src/tma_api/spreads/models.py

from __future__ import annotations

from typing import Dict, Literal

from pydantic import BaseModel, Field


# 1. Модели раскладов (для истории и детальных данных)

class CardModel(BaseModel):
    """
    Модель карты, используемая в SpreadDetail.cards.

    Важно: должна содержать code и image_url,
    чтобы фронт мог отрисовать реальные изображения.
    """
    code: str                  # внутренний код карты (например, "maj_00", "cups_10")
    name: str                  # человекочитаемое название
    is_reversed: bool          # перевёрнута ли карта
    image_url: str             # ссылка на картинку (или fallback)

    # необязательные поля для возможного расширения
    arcana: str | None = None  # major / minor
    suit: str | None = None
    rank: str | None = None


class SpreadListItem(BaseModel):
    id: int
    spread_type: str
    category: str
    created_at: str  # ISO
    short_preview: str | None = None
    has_questions: bool = False
    interpretation: str | None = None


class SpreadDetail(BaseModel):
    id: int
    spread_type: str
    category: str | None
    question: str | None              # первичный вопрос пользователя
    cards: list[CardModel]            # ← теперь обязательно CardModel с image_url/code
    interpretation: str | None = None
    created_at: str
    questions: list["SpreadQuestionModel"] | None = None


# 2. Создание расклада

class SpreadCreateIn(BaseModel):
    """
    Вопрос ДО расклада — вместо категории (только для 3-картного расклада).
    """
    mode: Literal["auto", "interactive"]
    spread_type: Literal["one", "three"]
    category: str | None = None
    question: str | None = None  # вопрос до расклада, вместо категории


# 3. Интерактивный режим

class SpreadSessionStart(BaseModel):
    session_id: str
    status: Literal["awaiting_selection"]
    spread_type: str
    category: str
    total_positions: int
    selected_cards: Dict[int, CardModel] = Field(default_factory=dict)


class SpreadSelectCardIn(BaseModel):
    position: int = Field(..., ge=1)
    choice_index: int = Field(..., ge=1)


# 4. Вопросы

class SpreadQuestionIn(BaseModel):
    question: str  # вопрос по ГОТОВОМУ раскладу


class SpreadQuestionModel(BaseModel):
    id: int
    spread_id: int
    user_id: int
    question: str
    answer: str | None
    status: Literal["pending", "ready", "failed"]
    created_at: str


class SpreadQuestionsList(BaseModel):
    items: list[SpreadQuestionModel]


# 5. Пагинация

class PaginatedSpreads(BaseModel):
    items: list[SpreadListItem]
    page: int
    total_pages: int
    total_items: int
