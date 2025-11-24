#!/usr/bin/env python3
"""
Главный файл для запуска AI-Таролога "Луна"
"""

import sys
import os
import logging

# Добавляем текущую директорию в путь для импортов
sys.path.append(os.path.dirname(__file__))

# ✅ НАСТРОЙКА ЛОГИРОВАНИЯ ДО ИМПОРТА ДРУГИХ МОДУЛЕЙ
# Это важно чтобы настройка применилась ко всем импортируемым модулям

# Настройка базового логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

# ✅ УМЕНЬШАЕМ УРОВЕНЬ ЛОГИРОВАНИЯ ДЛЯ ШУМНЫХ БИБЛИОТЕК
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

# ✅ СОХРАНЯЕМ НАШИ ЛОГИ НА УРОВНЕ INFO
logging.getLogger("src").setLevel(logging.INFO)
logging.getLogger("root").setLevel(logging.INFO)

# Теперь импортируем наш бот после настройки логирования
from src.bot_main import TarotBot

if __name__ == '__main__':
    # Создаем логгер для main
    logger = logging.getLogger(__name__)
    logger.info("🚀 Запуск AI-Таролога 'Луна'...")
    
    try:
        bot = TarotBot()
        bot.main()  # Теперь это синхронный вызов
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при запуске бота: {e}")
        sys.exit(1)