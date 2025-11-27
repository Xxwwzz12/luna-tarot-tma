# src/ai_prompts.py
from __future__ import annotations

from typing import List, Dict, Optional


BASE_TAROT_SYSTEM_PROMPT = """
Ты — профессиональный русскоязычный таролог с большим опытом.

🚨 ВАЖНЫЕ ПРАВИЛА:
1. Отвечай ТОЛЬКО на русском языке.
2. Не используй английские слова, кроме общеупотребимых имён собственных.
3. Не пиши технические детали, JSON, списки ключ-значение и подобные структуры.
4. Пиши живым, человечным языком, как опытный таролог, объясняющий расклад клиенту.
5. Избегай категоричных предсказаний смерти, заболеваний и других пугающих прогнозов.
""".strip()


def build_profile_context(
    user_age: Optional[int] = None,
    user_gender: Optional[str] = None,
    user_name: Optional[str] = None,
) -> str:
    """
    Собирает текстовый контекст профиля пользователя для подмешивания в промпты.

    Если нет ни возраста, ни пола, ни имени — возвращает пустую строку.
    """
    if user_age is None and not user_gender and not user_name:
        return ""

    # Пол → человек / мужчина / женщина
    gender_label = "человек"
    if user_gender:
        gender_lower = user_gender.lower()
        if gender_lower == "male":
            gender_label = "мужчина"
        elif gender_lower == "female":
            gender_label = "женщина"

    # Возраст → «молодой», «в расцвете сил», «зрелый», «опытный»
    age_phrase = None
    if isinstance(user_age, int) and user_age > 0:
        if user_age < 25:
            age_phrase = "молодой"
        elif 25 <= user_age <= 35:
            age_phrase = "в расцвете сил"
        elif 36 <= user_age <= 50:
            age_phrase = "зрелый"
        else:
            age_phrase = "опытный"

    lines: List[str] = [
        "Учитывай следующие данные о пользователе при интерпретации, "
        "но НЕ упоминай их прямо в тексте:"
    ]

    if user_name:
        lines.append(f"- Имя: {user_name}")

    if user_gender:
        lines.append(f"- Пол: {gender_label}")

    if isinstance(user_age, int) and user_age > 0:
        if age_phrase:
            lines.append(f"- Возраст: {user_age} лет ({age_phrase})")
        else:
            lines.append(f"- Возраст: {user_age} лет")

    lines.append(
        "Используй эти данные для тонкой настройки интерпретации, но не указывай их явно."
    )

    return "\n".join(lines)


def _get_spread_name(spread_type: str, cards: List[Dict]) -> str:
    """Внутренний хелпер для человеческого названия расклада."""
    st = (spread_type or "").lower().strip()

    if st in {"one", "single", "card"} or len(cards) == 1:
        return "Карта дня"

    if st in {"three", "3"} or len(cards) == 3:
        return "Расклад «Прошлое–Настоящее–Будущее»"

    # Фолбэк на случай других типов
    return "Таро-расклад"


def _build_cards_text(spread_type: str, cards: List[Dict]) -> str:
    """
    Собирает текст по картам для промпта.

    Ожидается формат карт:
    {
        "name": str,
        "is_reversed": bool,
        # опционально:
        "position": str,
    }
    """
    if not cards:
        return "нет данных по картам"

    st = (spread_type or "").lower().strip()

    # Одна карта — просто список без позиций
    if st in {"one", "single", "card"} or len(cards) == 1:
        lines: List[str] = []
        for card in cards:
            name = card.get("name") or "Неизвестная карта"
            is_reversed = bool(card.get("is_reversed"))
            orientation = "перевернутая" if is_reversed else "прямая"
            lines.append(f"• {name} ({orientation})")
        return "\n".join(lines)

    # Несколько карт — добавляем позиции
    default_positions = ["Прошлое", "Настоящее", "Будущее"]
    lines = []

    for idx, card in enumerate(cards):
        name = card.get("name") or "Неизвестная карта"
        is_reversed = bool(card.get("is_reversed"))
        orientation = "перевернутая" if is_reversed else "прямая"

        position = card.get("position")
        if not position:
            if idx < len(default_positions):
                position = default_positions[idx]
            else:
                position = f"Позиция {idx + 1}"

        lines.append(f"• {position}: {name} ({orientation})")

    return "\n".join(lines)


def build_spread_interpretation_prompt(
    spread_type: str,
    cards: List[Dict],
    question_category: str,
    profile_context: str = "",
) -> str:
    """
    Построение промпта для первичной интерпретации расклада.
    """
    spread_name = _get_spread_name(spread_type, cards)
    cards_text = _build_cards_text(spread_type, cards)

    # Аккуратно вставляем контекст профиля, если он есть
    profile_block = ""
    if profile_context:
        profile_block = profile_context.strip() + "\n\n"

    category_text = question_category or "общий"

    prompt_parts = [
        "Ты — профессиональный русскоязычный таролог с 20-летним стажем.",
        "",
        "🚨 ВАЖНЫЕ ПРАВИЛА ЯЗЫКА:",
        "1. Отвечай ТОЛЬКО на русском языке.",
        "2. Не используй английские слова, кроме общеупотребимых имён собственных.",
        "3. Пиши живым, человечным, разговорным языком, как опытный таролог, объясняющий расклад клиенту.",
        "4. Избегай категоричных предсказаний смерти, тяжёлых заболеваний и других пугающих прогнозов.",
        "5. Не используй технические форматы (JSON, списки ключ-значение и т.п.).",
        "",
        profile_block.rstrip(),  # может быть пустым
        f"Тип расклада: {spread_name}",
        f"Категория вопроса: {category_text}",
        "",
        "Карты в раскладе:",
        cards_text,
        "",
        "Начни интерпретацию на русском языке:",
    ]

    # Уберём возможные пустые строки от profile_block
    prompt = "\n".join(line for line in prompt_parts if line != "" or profile_block)
    return prompt.strip()


def build_question_answer_prompt(
    spread_type: str,
    category: str,
    cards_text: str,
    interpretation_text: str,
    question: str,
    profile_context: str = "",
) -> str:
    """
    Построение промпта для ответа на дополнительный вопрос по уже сделанному раскладу.
    """
    spread_name = _get_spread_name(spread_type, [])

    profile_block = ""
    if profile_context:
        profile_block = profile_context.strip() + "\n\n"

    category_text = category or "общий"
    question_clean = (question or "").strip()
    interpretation_clean = (interpretation_text or "").strip()
    cards_clean = (cards_text or "").strip() or "нет подробного описания карт"

    prompt_lines = [
        "Ты — опытный таролог. Ответь на вопрос пользователя по предыдущему раскладу.",
        "",
        profile_block.rstrip(),  # может быть пустым
        f'Вопрос пользователя: "{question_clean}"',
        "",
        "Информация о раскладе:",
        f"- Тип: {spread_name}",
        f"- Категория: {category_text}",
        f"- Карты: {cards_clean}",
        f"- Исходная интерпретация: {interpretation_clean}",
        "",
        "Ответ (только на русском языке):",
    ]

    prompt = "\n".join(line for line in prompt_lines if line != "" or profile_block)
    return prompt.strip()


__all__ = [
    "BASE_TAROT_SYSTEM_PROMPT",
    "build_profile_context",
    "build_spread_interpretation_prompt",
    "build_question_answer_prompt",
]
