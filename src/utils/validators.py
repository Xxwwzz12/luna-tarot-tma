# src/utils/validators.py
import re
from datetime import datetime
import logging

# Настройка логгера для модуля
logger = logging.getLogger(__name__)

def validate_birth_date(birth_date_str: str) -> tuple:
    """Валидация даты рождения"""
    logger.info(f"🔍 Валидация даты рождения: {birth_date_str}")
    
    if not re.match(r'^\d{2}\.\d{2}\.\d{4}$', birth_date_str):
        error_message = "Неверный формат даты. Используйте ДД.ММ.ГГГГ (например: 15.05.1990)"
        logger.warning(f"❌ Валидация даты не пройдена: {birth_date_str} - {error_message}")
        return False, error_message
    
    try:
        birth_date = datetime.strptime(birth_date_str, '%d.%m.%Y')
        today = datetime.now()
        
        # Проверяем что дата не в будущем
        if birth_date > today:
            error_message = "Дата рождения не может быть в будущем."
            logger.warning(f"❌ Валидация даты не пройдена: {birth_date_str} - {error_message}")
            return False, error_message
            
        # Проверяем что возраст разумный
        age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
        if age > 150:
            error_message = "Пожалуйста, проверьте дату рождения. Возраст не должен превышать 150 лет."
            logger.warning(f"❌ Валидация даты не пройдена: {birth_date_str} - {error_message}")
            return False, error_message
            
        logger.info(f"✅ Дата рождения валидирована: {birth_date_str} -> {birth_date}")
        return True, birth_date
        
    except ValueError:
        error_message = "Неверная дата. Пожалуйста, введите существующую дату в формате ДД.ММ.ГГГГ"
        logger.warning(f"❌ Валидация даты не пройдена: {birth_date_str} - {error_message}")
        return False, error_message

def validate_question_text(question: str) -> tuple:
    """Валидация текста вопроса"""
    logger.info(f"🔍 Валидация вопроса: {question[:50]}...")  # Логируем первые 50 символов
    
    if len(question) < 5:
        error_message = "Вопрос слишком короткий. Пожалуйста, сформулируйте более развернутый вопрос."
        logger.warning(f"❌ Валидация вопроса не пройдена: {error_message}")
        return False, error_message
    
    if len(question) > 500:
        error_message = "Вопрос слишком длинный. Пожалуйста, сформулируйте вопрос короче (до 500 символов)."
        logger.warning(f"❌ Валидация вопроса не пройдена: {error_message}")
        return False, error_message
    
    logger.info(f"✅ Вопрос валидирован (длина: {len(question)} символов)")
    return True, ""

def validate_category(category: str) -> bool:
    """Валидация категории"""
    logger.info(f"🔍 Валидация категории: {category}")
    
    valid_categories = [
        'Любовь и отношения',
        'Карьера и работа', 
        'Финансы и богатство',
        'Отношения',
        'Личностный рост',
        'Общий вопрос'
    ]
    
    is_valid = category in valid_categories
    if is_valid:
        logger.info(f"✅ Категория валидирована: {category}")
    else:
        logger.warning(f"❌ Неизвестная категория: {category}")
    
    return is_valid