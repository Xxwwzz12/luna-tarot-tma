# src/ai_interpreter.py
import asyncio
import random
from typing import Dict, List, Optional, Any
import logging

# Импорты для OpenRouter API
import os
import aiohttp
import json
from openai import AsyncOpenAI

# Импорты конфигурации
from .config import OPENROUTER_CONFIG, TAROT_CONFIG, is_config_loaded

# Настройка логирования
logger = logging.getLogger(__name__)

class AIInterpreter:
    """
    AI-интерпретатор раскладов Таро с интеграцией OpenRouter API
    и резервными механизмами
    """
    
    def __init__(self):
        # Проверка загрузки конфигурации
        if not is_config_loaded():
            logger.error("Конфигурация не загружена! Используются значения по умолчанию.")

        # Инициализация клиента OpenRouter API через конфигурационный класс
       
        self.client = AsyncOpenAI(
            api_key=OPENROUTER_CONFIG.api_key,
            base_url=OPENROUTER_CONFIG.base_url
        )
        self.model = OPENROUTER_CONFIG.model
        self.max_tokens = OPENROUTER_CONFIG.max_tokens
        self.temperature = OPENROUTER_CONFIG.temperature
        self.timeout = OPENROUTER_CONFIG.timeout
        
        # Дополнительные заголовки для OpenRouter 
        self.extra_headers = {
            "HTTP-Referer": "https://tarot-bot-luna.com",  # Можно заменить на ваш сайт
            "X-Title": "Tarot Bot Luna",
        }
        
        # Безопасный доступ к настройкам (для обратной совместимости)
        self.max_retries = 3
        self.retry_delay = 1.0
        self.fallback_enabled = True
        
        # Получение настроек из TAROT_CONFIG с безопасным доступом
        try:
            if isinstance(TAROT_CONFIG, dict):
                self.question_categories = TAROT_CONFIG.get('question_categories', [])
            else:
                self.question_categories = getattr(TAROT_CONFIG, 'question_categories', [])
        except Exception:
            self.question_categories = []
            logger.warning("Категории вопросов не найдены в конфигурации")
        
        logger.info(f"OpenRouter Interpreter инициализирован с моделью: {self.model}")

    async def generate_interpretation(self, spread_data: Dict, question_category: str, user_context: Optional[Dict] = None) -> str:
        """Генерация интерпретации через OpenRouter API"""
        # Детальное логирование начала процесса
        try:
            logger.info(f"Starting AI interpretation for {len(spread_data['cards'])} cards")
        except Exception:
            logger.info("Starting AI interpretation")
        logger.info(f"Spread type: {spread_data.get('spread_type')} , Question category: {question_category}")
        
        # Логируем информацию о картах
        try:
            card_names = [f"{card.name}{' (reversed)' if card.is_reversed else ''}" 
                         for card in spread_data['cards']]
            logger.debug(f"Cards in spread: {', '.join(card_names)}")
        except Exception:
            logger.debug("Could not log card names (structure unexpected)")
        
        # Проверяем допустимость категории вопроса
        if question_category not in self.question_categories:
            logger.warning(f"Категория '{question_category}' не найдена в конфигурации")
        
        try:
            # Создаем промпт
            prompt = self._create_prompt(spread_data, question_category, user_context)
            logger.debug(f"Создан промпт длиной {len(prompt)} символов")
            logger.debug(f"Prompt preview: {prompt[:200]}...")
            
            # Логируем вызов AI
            logger.info(f"Отправка запроса к OpenRouter, модель: {self.model}")
            
            # Вызов OpenRouter API 
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system", 
                        "content": """Ты мудрый и эмпатичный таролог. Дай развернутую и вдохновляющую интерпретацию расклада карт Таро. 
                        Учитывай значения выпавших карт, их положение (прямое/перевернутое), заданную категорию вопроса и взаимосвязи между картами в раскладе.
                        Будь внимателен к контексту и дай практические советы."""
                    },
                    {
                        "role": "user", 
                        "content": prompt
                    }
                ],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                timeout=self.timeout,
                extra_headers=self.extra_headers
            )
            
            # Логируем успешный ответ
            logger.info("Успешно получена интерпретация от OpenRouter")
            ai_response = response.choices[0].message.content
            logger.debug(f"AI response length: {len(ai_response)} characters")
            logger.debug(f"AI response preview: {ai_response[:200]}...")
            
            # Форматируем ответ
            formatted_response = self._format_response(ai_response, question_category)
            logger.info("AI response formatted successfully")
            
            return formatted_response
            
        except Exception as e:
            # Детальное логирование ошибок
            logger.error(f"OpenRouter API error: {e}", exc_info=True)
            logger.error(f"Fallback enabled: {self.fallback_enabled}")
            
            if self.fallback_enabled:
                logger.info("Using fallback interpretation")
                return self._generate_fallback_interpretation(spread_data, question_category)
            else:
                logger.error("Fallback disabled, returning error message")
                return "В настоящее время я не могу сгенерировать интерпретацию. Пожалуйста, попробуйте позже."

    def _create_prompt(self, spread_data: Dict, category: str, user_context: Optional[Dict] = None) -> str:
        """Создание промпта для OpenRouter"""
        logger.debug(f"Creating prompt for spread: {spread_data.get('spread_type')}, category: {category}")
        
        # Получаем карты и позиции напрямую из spread_data
        cards = spread_data.get('cards', [])
        positions = spread_data.get('positions', [])
        
        # Описание позиций расклада
        positions_desc = " → ".join([f"{i+1}. {pos}" for i, pos in enumerate(positions)])
        
        # Детальное описание карт
        cards_description = self._build_cards_description(cards, positions)
        
        # Базовые значения для контекста
        base_meanings = self._extract_base_meanings(cards)
        
        # Контекст пользователя если есть
        user_context_str = ""
        if user_context:
            user_context_str = f"""
КОНТЕКСТ ПОЛЬЗОВАТЕЛЯ:
- Предыдущие расклады: {user_context.get('previous_readings', 'неизвестно')}
- Темы вопросов: {', '.join(user_context.get('question_themes', []))}
- Уровень опыта: {user_context.get('experience_level', 'неизвестно')}
"""
            logger.debug("User context included in prompt")
        
        prompt = f"""Ты — эмпатичный таролог с многолетним опытом. Проанализируй этот расклад и дай поддерживающую интерпретацию.

РАСКЛАД: {spread_data.get('spread_type', 'расклад')}
КАТЕГОРИЯ ВОПРОСА: {category}
ПОЗИЦИИ РАСКЛАДА: {positions_desc}

ВЫПАВШИЕ КАРТЫ:
{cards_description}

БАЗОВЫЕ ЗНАЧЕНИЯ КАРТ:
{base_meanings}
{user_context_str}

ИНСТРУКЦИИ ДЛЯ ИНТЕРПРЕТАЦИИ:
1. Начни с общего впечатления от расклада
2. Проанализируй каждую позицию и карту в ней, учитывая перевернутые карты
3. Покажи взаимодействие между картами и общую динамику
4. Учитывай категорию вопроса ({category}) в интерпретации
5. Будь поддерживающим, но честным - предлагай insights, а не предсказания
6. Заверши практическим советом или выводом
7. Используй естественный, эмпатичный тон как опытный таролог

ОТВЕТ (на русском):"""
        
        return prompt

    def _build_cards_description(self, cards: List, positions: List[str] = None) -> str:
        """Создает описание карт для промпта"""
        descriptions = []
        for i, card in enumerate(cards):
            # card теперь объект TarotCard, а не словарь
            position = positions[i] if positions and i < len(positions) else f"Позиция {i+1}"
            
            # Используем методы TarotCard для получения данных
            card_meaning = card.get_meaning()
            
            card_description = f"- {position}: {card.name}"
            if card.is_reversed:
                card_description += " (Перевернутая)"
            
            card_description += f"\n  Описание: {card.description}\n"
            
            # Добавляем ключевые слова
            keywords = card_meaning.get('keywords', [])
            if keywords:
                card_description += f"  Ключевые слова: {', '.join(keywords)}\n"
            
            descriptions.append(card_description)
        
        return "\n".join(descriptions)

    def _extract_base_meanings(self, cards: List) -> str:
        """Извлечение базовых значений карт"""
        meanings = []
        for i, card in enumerate(cards):
            # card теперь объект TarotCard
            card_meaning = card.get_meaning()
            
            meaning = card_meaning.get('meaning', '')
            reversal_text = "перевернутая " if card.is_reversed else ""
            meanings.append(f"- {card.name} ({reversal_text}): {meaning}")
        
        return "\n".join(meanings)

    def _format_response(self, ai_response: str, question_category: str) -> str:
        """Форматирование ответа AI в стиль таролога"""
        logger.debug("Formatting AI response")
        
        response = ai_response.strip() if ai_response else ""
        
        # Добавляем эмодзи в зависимости от категории
        try:
            if isinstance(TAROT_CONFIG, dict):
                category_emojis = TAROT_CONFIG.get('category_emojis')
            else:
                category_emojis = getattr(TAROT_CONFIG, 'category_emojis', None)
        except Exception:
            category_emojis = None

        if not category_emojis:
            category_emojis = {
                'любовь': '💖',
                'работа': '💼',
                'финансы': '💰',
                'здоровье': '🌿',
                'развитие': '🌟',
                'будущее': '🔮'
            }
        
        emoji = category_emojis.get(question_category, '✨')
        
        # Убедимся, что ответ начинается с заголовка
        if response and not response.startswith(('✨', '💫', '🌟', '📖', '💖')):
            lines = response.split('\n')
            if lines and len(lines[0].strip()) > 0:
                lines[0] = f"{emoji} {lines[0]}"
            response = '\n'.join(lines)
        
        # Добавляем поддерживающее заключение если его нет
        supportive_endings = [
            "Помните, что карты показывают потенциал развития, а не предопределенное будущее.",
            "Прислушайтесь к своей интуиции при принятии решений.",
            "Это возможность для роста и лучшего понимания себя."
        ]
        
        has_supportive_ending = any(
            ending.lower() in response.lower() for ending in supportive_endings
        ) if response else False
        
        if not has_supportive_ending:
            response = (response + f"\n\n💫 {supportive_endings[0]}") if response else f"{emoji} {supportive_endings[0]}"
        
        logger.debug("Response formatting completed")
        return response

    def _generate_fallback_interpretation(self, spread_data: Dict, question_category: str) -> str:
        """Генерация резервной интерпретации когда AI недоступен"""
        cards = spread_data.get('cards', [])
        spread_type = spread_data.get('spread_type', 'расклад')
        
        fallback_text = f"🔮 {spread_type.capitalize()}\n"
        fallback_text += f"📋 Категория: {question_category}\n\n"
        
        for i, card in enumerate(cards):
            card_meaning = card.get_meaning()
            position = spread_data.get('positions', [])[i] if i < len(spread_data.get('positions', [])) else f"Карта {i+1}"
            
            fallback_text += f"• {position}: {card.name}"
            if card.is_reversed:
                fallback_text += " (Перевернутая)"
            fallback_text += "\n"
            
            # Добавляем краткое значение
            meaning = card_meaning.get('meaning', '')
            if meaning:
                fallback_text += f"  Значение: {meaning}\n"
            
            fallback_text += "\n"
        
        fallback_text += "💫 Это базовая интерпретация. Для более детального анализа попробуйте позже, когда AI будет доступен."
        
        return fallback_text

# Пример использования
async def example_usage():
    """Пример использования AI интерпретатора"""
    
    # Проверка загрузки конфигурации
    if not is_config_loaded():
        logger.error("Конфигурация не загружена!")
        return
    
    # Создаем интерпретатор
    interpreter = AIInterpreter()
    
    # Использование настроек из config.py
    logger.info(f"Модель: {interpreter.model}")
    logger.info(f"Доступные категории: {interpreter.question_categories}")

if __name__ == "__main__":
    asyncio.run(example_usage())