#!/usr/bin/env python3
"""
Тестовый скрипт для проверки импортов после рефакторинга
"""

import sys
import os

# Добавляем src в путь для импорта
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_imports():
    """Тестирование всех импортов"""
    print("🔍 Тестирование импортов...")
    
    try:
        # Основные модули
        from src import config, tarot_engine, user_database, ai_interpreter, keyboards
        print("✅ Основные модули: OK")
        
        # Сервисы
        from src.services import CardService, AIService, ProfileService, HistoryService
        print("✅ Сервисы: OK")
        
        # Обработчики
        from src.handlers import CommandHandlers, CallbackHandlers, MessageHandlers, ErrorHandlers
        print("✅ Обработчики: OK")
        
        # Утилиты
        from src.utils import format_date, format_gender, validate_birth_date
        print("✅ Утилиты: OK")
        
        # Модели
        from src.models import UserContext, SpreadData, ProfileData
        print("✅ Модели: OK")
        
        # Главный бот
        from src.bot_main import TarotBot
        print("✅ Главный бот: OK")
        
        print("\n🎉 Все импорты успешны! Архитектура работает корректно.")
        return True
        
    except ImportError as e:
        print(f"❌ Ошибка импорта: {e}")
        return False
    except Exception as e:
        print(f"❌ Неожиданная ошибка: {e}")
        return False

if __name__ == "__main__":
    test_imports()