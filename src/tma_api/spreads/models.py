# src/tma_api/spreads/models.py

from __future__ import annotations

from typing import Dict, Literal

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
    short_preview: str | None = None
    has_questions: bool = False
    interpretation: str | None = None


class SpreadDetail(BaseModel):
    id: int
    spread_type: str
    category: str | None
    question: str | None  # первичный вопрос пользователя, если был
    cards: list[CardModel]
    interpretation: str | None = None
    created_at: str
    # опционально: вопросы по уже готовому раскладу
    questions: list["SpreadQuestionModel"] | None = None


# 2. Модель создания расклада (POST /spreads)

class SpreadCreateIn(BaseModel):
    """
    Входная модель для POST /spreads.

    mode:
      - "auto" — сразу генерируем расклад и интерпретацию;
      - "interactive" — интерактивный выбор карт.

    spread_type:
      - "one"   — 1 карта;
      - "three" — 3 карты.

    category:
      - категория для 3-картного авто-расклада (если нет собственного вопроса).

    question:
      - вопрос ДО расклада, вместо категории, только для 3-картного расклада.
    """
    mode: Literal["auto", "interactive"]
    spread_type: Literal["one", "three"]
    category: str | None = None
    question: str | None = None  # вопрос до расклада, вместо категории (только для 3-карт)


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

class SpreadQuestionIn(BaseModel):
    """
    Вопрос по УЖЕ ГОТОВОМУ раскладу (POST /spreads/{spread_id}/questions).
    """
    question: str


class SpreadQuestionModel(BaseModel):
    id: int
    spread_id: int
    user_id: int
    question: str
    answer: str | None
    status: Literal["pending", "ready", "failed"]
    created_at: str


# 6. Модель списка вопросов

class SpreadQuestionsList(BaseModel):
    items: list[SpreadQuestionModel]


# 7. Пагинация (для GET /spreads)

class PaginatedSpreads(BaseModel):
    items: list[SpreadListItem]
    page: int
    total_pages: int
    total_items: int
