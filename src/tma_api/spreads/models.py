# src/tma_api/spreads/models.py

from __future__ import annotations

from typing import Any, Dict, Literal

from pydantic import BaseModel, Field


# 1. Модели раскладов (для истории и детальных данных)

class CardModel(BaseModel):
    position: int
    name: str
    is_reversed: bool = False


class SpreadListItem(BaseModel):
    id: int
    spread_type: str
    category: str
    created_at: str  # ISO date string
    short_preview: str
    has_questions: bool


class SpreadDetail(BaseModel):
    id: int
    spread_type: str
    category: str
    created_at: str
    cards: list[CardModel]
    interpretation: str | None = None
    question: str | None = None
    questions: list["SpreadQuestionModel"] | None = None


# 2. Модель создания расклада (POST /spreads)

class SpreadCreateIn(BaseModel):
    spread_type: str
    category: str
    question: str | None = None
    mode: Literal["auto", "interactive"]


# 3. Модели интерактивного режима (mode="interactive")

class SpreadSessionStart(BaseModel):
    session_id: str
    status: Literal["awaiting_selection"]
    spread_type: str
    category: str
    total_positions: int
    selected_cards: Dict[int, CardModel] = Field(default_factory=dict)


# 4. Модели выбора карты (interactive)

class SpreadSelectCardIn(BaseModel):
    position: int = Field(..., ge=1)
    choice_index: int = Field(..., ge=1)


# 5. Модели вопросов

class SpreadQuestionCreate(BaseModel):
    """
    Входная модель для POST /spreads/{spread_id}/questions.
    Роутер использует либо question, либо text.
    """
    question: str = Field(..., min_length=1)
    text: str | None = None


class SpreadQuestionModel(BaseModel):
    id: int
    spread_id: int
    user_id: int                     # ← добавлено по ТЗ
    question: str
    answer: str | None
    status: Literal["pending", "ready", "failed"]
    created_at: str
    answered_at: str | None = None


# 6. Модель списка вопросов

class SpreadQuestionsList(BaseModel):
    items: list[SpreadQuestionModel]


# 7. Пагинация (для GET /spreads)

class PaginatedSpreads(BaseModel):
    items: list[SpreadListItem]
    page: int
    total_pages: int
    total_items: int
