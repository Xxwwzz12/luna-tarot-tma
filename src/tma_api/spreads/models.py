# src/tma_api/spreads/models.py

from __future__ import annotations

from typing import Dict, Literal
from pydantic import BaseModel, Field


# 1. Модели карт и раскладов

class CardModel(BaseModel):
    """
    Модель карты, используемая в SpreadDetail.cards.
    """
    code: str
    name: str
    is_reversed: bool
    image_url: str

    arcana: str | None = None
    suit: str | None = None
    rank: str | None = None


class SpreadListItem(BaseModel):
    id: int
    spread_type: str
    category: str
    created_at: str
    short_preview: str | None = None
    has_questions: bool = False
    interpretation: str | None = None


class SpreadDetail(BaseModel):
    id: int
    spread_type: str
    category: str | None
    question: str | None                     # первичный вопрос пользователя (до расклада)
    cards: list[CardModel]
    interpretation: str | None = None
    created_at: str
    questions: list["SpreadQuestionModel"] | None = None


# 2. Создание расклада (POST /spreads)

class SpreadCreateIn(BaseModel):
    """
    Входная модель для POST /spreads.

    Правила:

    • spread_type="one":
        - category -> backend сам подставляет "daily" (если не пришла)
        - question игнорируется (должно быть None)

    • spread_type="three":
        - category — готовая тема ДЛЯ авто-расклада
        - question — свой вопрос пользователя ДО расклада (вместо категории)
        - одновременно присылать category и question НЕЛЬЗЯ
    """

    mode: Literal["auto", "interactive"]
    spread_type: Literal["one", "three"]
    category: str | None = None       # категория для 3-картного авто-расклада
    question: str | None = None       # вопрос ВМЕСТО категории (только для 3-карт)


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


# 4. Вопросы к ГОТОВОМУ раскладу

class SpreadQuestionIn(BaseModel):
    question: str


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
