# src/utils/formatters.py
import re
from datetime import datetime

def format_date(date_string: str) -> str:
    """Форматирование даты в читаемый вид"""
    if not date_string:
        return "Дата недоступна"
    
    try:
        # Пробуем разные форматы дат
        formats = ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d.%m.%Y %H:%M:%S']
        for fmt in formats:
            try:
                dt = datetime.strptime(date_string, fmt)
                return dt.strftime('%d.%m.%Y в %H:%M')
            except ValueError:
                continue
        return date_string
    except Exception:
        return date_string

def format_gender(gender: str) -> str:
    """Форматирование пола для отображения"""
    gender_map = {
        'male': 'Мужской ♂️',
        'female': 'Женский ♀️',
        'other': 'Другой'
    }
    return gender_map.get(gender, 'не указан')

def format_spread_type(spread_type: str) -> str:
    """
    Преобразование типа расклада в читаемый формат
    
    Args:
        spread_type: Внутренний тип расклада (single, three, one_card, etc.)
        
    Returns:
        str: Локализованное название расклада
    """
    spread_type_map = {
        'single': '1 карта',
        'three': '3 карты', 
        'three_card': '3 карты',
        'one_card': '1 карта',
        'three_card_spread': '3 карты', 
        'single_card': '1 карта',
        'celtic_cross': 'Кельтский крест',
        'relationship': 'Отношения',
        'career': 'Карьера'
    }
    
    # Нормализация входных данных
    if spread_type:
        normalized_type = spread_type.lower().strip()
        return spread_type_map.get(normalized_type, spread_type)
    
    return 'Неизвестный расклад'

def format_spread_for_display(spread_data, spread_number: int = 1) -> str:
    """Форматирование расклада для отображения"""
    spread_type = format_spread_type(spread_data['spread_type'])
    category = spread_data.get('category', 'Общий вопрос')
    created_at = format_date(spread_data.get('created_at', ''))
    
    # Форматируем карты
    cards_list = spread_data.get('cards', [])
    if cards_list and isinstance(cards_list, list) and len(cards_list) > 0:
        cards_preview = ", ".join(cards_list[:3])
        if len(cards_list) > 3:
            cards_preview += f" ... (+{len(cards_list) - 3})"
    else:
        cards_preview = "информация недоступна"
    
    entry_text = (
        f"<b>{spread_number}. {spread_type}</b>\n"
        f"📋 Категория: {category}\n"
        f"📅 Дата: {created_at}\n"
        f"🎴 Карты: {cards_preview}\n"
    )
    
    # Проверяем наличие интерпретации
    interpretation = spread_data.get('interpretation')
    if interpretation and len(interpretation) > 10:
        entry_text += "💫 Есть интерпретация\n"
    else:
        entry_text += "❌ Нет интерпретации\n"
    
    return entry_text