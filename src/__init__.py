"""
Пакет AI-Таролога 'Луна'
"""

from . import config
from . import tarot_engine
from . import user_database
from . import ai_interpreter
from . import keyboards
from . import bot_main
from .bot_main import TarotBot  # ← ДОБАВЛЕНО

__all__ = [
    'config',
    'tarot_engine',
    'user_database', 
    'ai_interpreter',
    'keyboards',
    'bot_main',
    'TarotBot'  # ← ДОБАВЛЕНО
]

__version__ = '1.0.0'
__author__ = 'AI Tarot Luna Team'