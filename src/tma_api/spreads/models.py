# src/tma_api/spreads/models.py

from __future__ import annotations

from typing import Dict, Literal
from pydantic import BaseModel, Field


# 1. Модели карт и раскладов

class CardModel(BaseModel):
    """
    Модель карты, используемая в SpreadDetail.cards.
    """
    code: str                 # внутренний код карты (совпадает с tarot_deck.json)
    name: str                 # человекочитаемое название
    is_reversed: bool         # перевёрнута ли карта
    image_url: str            # итоговая ссылка на картинку

    # дополнительные (необязательные) атрибуты
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
    # первичный вопрос пользователя ДО расклада (только для three)
    question: str | None
    cards: list[CardModel]
    interpretation: str | None = None
    created_at: str
    # вопросы ПО уже готовому раскладу (опционально)
    questions: list["SpreadQuestionModel"] | None = None


# 2. Создание расклада (POST /spreads)

class SpreadCreateIn(BaseModel):
    """
    Входная модель для POST /spreads.

    Смысл полей:

    mode:
      - "auto"        — карты выбирает backend сам (по правилам/вероятностям);
      - "interactive" — карты выбирает пользователь и передаёт их в cards.

    spread_type:
      - "one"   — «Карта дня»;
      - "three" — «Прошлое / Настоящее / Будущее».

    category:
      - используется ТОЛЬКО для spread_type="three" без вопроса;
      - для spread_type="one" игнорируется — backend всегда подставляет "daily".

    question:
      - используется для spread_type="three" ВМЕСТО категории (свой вопрос до расклада);
      - для spread_type="one" игнорируется (должно быть null / не задаётся).

    cards:
      - используется ТОЛЬКО для mode="interactive";
      - список code карт (строки) в том порядке, как их выбрал пользователь;
      - для spread_type="one" длина должна быть ровно 1;
      - для spread_type="three" длина должна быть ровно 3;
      - для mode="auto" либо не передаётся, либо должна быть None (полностью игнорируется).

    Важно:
      - для трёхкартного расклада category и question взаимоисключающие:
        либо категория, либо свой вопрос, но не оба сразу.
      - «Карта дня» всегда имеет category="daily" и НЕ использует question.
    """

    mode: Literal["auto", "interactive"]
    spread_type: Literal["one", "three"]

    category: str | None = None      # категория для 3-картного авто-расклада
    question: str | None = None      # вопрос ВМЕСТО категории (только для three)
    cards: list[str] | None = None   # коды выбранных карт (interactive; len=1 или 3)


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
    # Вопрос по уже готовому раскладу (POST /spreads/{spread_id}/questions)
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
