import aiohttp
import json
import logging
import asyncio
import re
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from .config import OPENROUTER_CONFIG

# ✅ НАСТРОЙКА ЛОГГЕРА: предотвращаем дублирование
logger = logging.getLogger(__name__)
logger.propagate = False  # ✅ ЗАПРЕТ ДУБЛИРОВАНИЯ ЛОГОВ

class AIInterpreter:
    def __init__(self):
        self.api_key = OPENROUTER_CONFIG.api_key
        
        # ✅ ПРАВИЛЬНЫЙ ПОРЯДОК МОДЕЛЕЙ: meta-llama первой, deepseek в конце
        self.model_list = [
            "meta-llama/llama-3.3-70b-instruct",   # ✅ СТАБИЛЬНАЯ ОСНОВНАЯ МОДЕЛЬ
            "google/gemma-2-9b-it:free",           # Бесплатная резервная
            "qwen/qwen-2-7b-instruct:free",        # Бесплатная резервная
            "microsoft/wizardlm-2-8x22b:free",     # Резервная мощная
            "deepseek/deepseek-r1:free"            # ✅ ПЕРЕМЕЩЕНА В КОНЕЦ (проблемы с rate-limit)
        ]
        
        # ✅ ЗАЩИТА ОТ EDGE-CASES: гарантируем что model_list не пустой
        self.model_list = self.model_list or []
        if not self.model_list:
            logger.error("🚨 CRITICAL: model_list is empty! Using fallback meta-llama")
            self.model_list = ["meta-llama/llama-3.3-70b-instruct"]
        
        # ✅ ЛОГИРОВАНИЕ ВЫСОКОГО УРОВНЯ: только порядок моделей
        model_names = [m.split('/')[-1] for m in self.model_list]
        logger.info(f"🔧 AIInterpreter model_list order: {model_names}")
        
        self.base_url = OPENROUTER_CONFIG.base_url
        self.max_tokens = OPENROUTER_CONFIG.max_tokens
        self.temperature = 1.0
        
        # ✅ PER-MODEL ТАЙМАУТЫ
        self.request_timeout = getattr(OPENROUTER_CONFIG, 'timeout', 60)  # Базовый таймаут 60 секунд
        self.per_model_timeout = {
            "meta-llama/llama-3.3-70b-instruct": 90,  # 90 секунд для тяжелой модели
            "microsoft/wizardlm-2-8x22b:free": 90,    # 90 секунд для большой модели
        }
        
        # ✅ УСОВЕРШЕНСТВОВАННАЯ КОНФИГУРАЦИЯ RETRY/BACKOFF
        self.max_retries = 2
        self.base_backoff = 1.5
        self.backoff_multiplier = 1.5
        self.max_backoff = 3.0  # ✅ МАКСИМАЛЬНАЯ ЗАДЕРЖКА 3 СЕКУНДЫ
        
        logger.info(f"⏱️ Request timeout: base={self.request_timeout}s, meta-llama=90s")
        logger.info(f"🔄 Retry config: {self.max_retries} attempts, backoff: {self.base_backoff}→{self.max_backoff}s")
        
        # Circuit breaker state
        self._model_failures = {}
        self._model_cooldown_until = {}
        self._model_cooldown_duration = 300
        
        # Session cache for successful models
        self._preferred_models = {}
        self._preferred_model_ttl = 1800
        
        self._validate_parameters()
        self.prompt_cache = {}
        self.cache_size = 50
        
        logger.info(f"✅ AI Interpreter initialized with {len(self.model_list)} models")

    def _validate_parameters(self):
        """Валидация параметров"""
        if not (0 <= self.temperature <= 2):
            logger.warning(f"⚠️ Invalid temperature {self.temperature}, clamping to 1.0")
            self.temperature = 1.0
        
        if self.max_tokens > 4000:
            logger.warning(f"⚠️ High max_tokens {self.max_tokens}, clamping to 4000")
            self.max_tokens = 4000

    def _get_request_timeout(self, model: str) -> int:
        """✅ ПОЛУЧЕНИЕ ТАЙМАУТА ДЛЯ КОНКРЕТНОЙ МОДЕЛИ"""
        return self.per_model_timeout.get(model, self.request_timeout)

    def _calculate_backoff(self, attempt: int) -> float:
        """✅ РАСЧЕТ BACKOFF С ОГРАНИЧЕНИЕМ МАКСИМУМА"""
        backoff = self.base_backoff * (self.backoff_multiplier ** attempt)
        return min(backoff, self.max_backoff)

    async def generate_interpretation(self,
                                    spread_type: str,
                                    cards: list,
                                    category: str,
                                    user_age: int = None,
                                    user_gender: str = None,
                                    user_name: str = None,
                                    user_id: Optional[int] = None,
                                    model: str = None) -> Dict[str, Any]:
        """
        Генерация интерпретации расклада
        
        Returns:
            Dict с результатом: {success, text, model, error}
        """
        try:
            logger.info(f"🎯 Generating interpretation for {len(cards)} cards, category: {category}")
            
            # ✅ DEBUG: логируем порядок моделей только при необходимости
            if logger.isEnabledFor(logging.DEBUG):
                model_names = [m.split('/')[-1] for m in self.model_list]
                logger.debug(f"🔧 Current model_list order: {model_names}")
            
            profile_context = self._build_profile_context(user_age, user_gender, user_name)
            spread_data = {
                'spread_type': spread_type,
                'cards': cards
            }
            
            prompt = self._build_prompt(spread_data, category, profile_context)
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"📝 Prompt length: {len(prompt)} characters")
            
            # ✅ ЕСЛИ ПЕРЕДАНА КОНКРЕТНАЯ МОДЕЛЬ - ИСПОЛЬЗУЕМ ТОЛЬКО ЕЁ
            if model:
                logger.info(f"🎯 Using specific model: {model}")
                
                # Проверяем, не в cooldown ли модель
                if self._is_model_in_cooldown(model):
                    logger.warning(f"⏸️ Model {model} is in cooldown")
                    return {
                        "success": False,
                        "text": None,
                        "model": model,
                        "error": f"Model {model} is temporarily unavailable"
                    }
                
                result = await self._make_llm_request(
                    model=model,
                    spread_data=spread_data,
                    question_category=category,
                    profile_context=profile_context
                )
                
                if result["success"] and self._is_valid_interpretation(result["text"]):
                    logger.info(f"✅ SUCCESS with model {model}")
                    self._record_model_success(model)
                    
                    cleaned_response = self._clean_response(result["text"])
                    final_response = self._clean_ai_response(cleaned_response)
                    
                    return {
                        "success": True,
                        "text": final_response,
                        "model": model,
                        "error": None
                    }
                else:
                    logger.warning(f"❌ Model {model} failed: {result.get('error', 'Unknown error')}")
                    self._record_model_failure(model)
                    return result
            
            # ✅ СТАНДАРТНАЯ ЛОГИКА С КЭШЕМ И CIRCUIT BREAKER
            return await self._generate_with_fallback(
                spread_data=spread_data,
                category=category,
                profile_context=profile_context,
                user_id=user_id
            )
            
        except Exception as e:
            logger.error(f"❌ Unexpected error in generate_interpretation: {e}")
            return {
                "success": False,
                "text": None,
                "model": model,
                "error": f"Unexpected error: {str(e)}"
            }

    async def _generate_with_fallback(self, 
                                    spread_data: Dict, 
                                    category: str, 
                                    profile_context: str,
                                    user_id: Optional[int] = None) -> Dict[str, Any]:
        """Стандартная логика с кэшем и circuit breaker"""
        preferred_model = self._get_preferred_model(user_id)
        models_to_try = self.model_list.copy()
        
        # ✅ ЗАПРЕТ НА ПЕРЕМЕЩЕНИЕ DEEPSEEK В НАЧАЛО
        if preferred_model and preferred_model in models_to_try and preferred_model != "deepseek/deepseek-r1:free":
            models_to_try.remove(preferred_model)
            models_to_try.insert(0, preferred_model)
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"🎯 Starting with preferred model: {preferred_model}")

        # Перебор моделей с circuit breaker
        for i, model in enumerate(models_to_try, 1):
            if self._is_model_in_cooldown(model):
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"⏸️ Skipping model in cooldown: {model}")
                continue
                
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"🔄 Trying model {i}/{len(models_to_try)}: {model}")
            
            result = await self._make_llm_request(
                model=model,
                spread_data=spread_data,
                question_category=category,
                profile_context=profile_context
            )
            
            if result["success"] and self._is_valid_interpretation(result["text"]):
                logger.info(f"✅ SUCCESS with model {model}")
                
                # ✅ ЗАПРЕТ НА КЭШИРОВАНИЕ DEEPSEEK
                if model != "deepseek/deepseek-r1:free":
                    self._set_preferred_model(user_id, model)
                
                self._record_model_success(model)
                
                cleaned_response = self._clean_response(result["text"])
                final_response = self._clean_ai_response(cleaned_response)
                
                return {
                    "success": True,
                    "text": final_response,
                    "model": model,
                    "error": None
                }
            else:
                logger.warning(f"❌ Model {model} failed: {result.get('error', 'Unknown error')}")
                self._record_model_failure(model)
                continue
        
        # Все модели не сработали
        logger.error("❌ All AI models failed to generate interpretation")
        fallback_text = self._generate_basic_interpretation(spread_data, category)
        
        return {
            "success": False,
            "text": fallback_text,
            "model": None,
            "error": "All models failed to generate valid interpretation"
        }

    async def _make_llm_request(self, model: str, prompt: Optional[str] = None, 
                               spread_data: Optional[Dict] = None, 
                               question_category: Optional[str] = None,
                               profile_context: str = "") -> Dict[str, Any]:
        """✅ УСОВЕРШЕНСТВОВАННЫЙ МЕТОД ЗАПРОСА"""
        
        if prompt is None:
            if spread_data is None or question_category is None:
                return {
                    "success": False,
                    "text": None,
                    "model": model,
                    "error": "Missing required parameters for prompt generation"
                }
            prompt = self._build_prompt(spread_data, question_category, profile_context)
        
        system_prompt = """
Ты - профессиональный русскоязычный таролог. Твоя задача - давать точные и полезные интерпретации раскладов Таро.

🚨 ВАЖНЫЕ ПРАВИЛА ЯЗЫКА:
1. ОТВЕЧАЙ ТОЛЬКО НА РУССКОМ ЯЗЫКЕ
2. НЕ ИСПОЛЬЗУЙ АНГЛИЙСКИЕ, КИТАЙСКИЕ ИЛИ ДРУГИЕ СИМВОЛЫ
3. ПИШИ ГРАМОТНО И ПОЛНОСТЬЮ НА РУССКОМ ЯЗЫКЕ
4. Все термины должны быть переведены на русский
5. Запрещены любые вставки на других языках

Твой ответ должен быть ЕСТЕСТВЕННЫМ, ГРАМОТНЫМ и ПОЛЕЗНЫМ - только на русском языке.
"""
        
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt.strip()
                },
                {
                    "role": "user", 
                    "content": prompt
                }
            ],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": False
        }
        
        payload = self._validate_payload(payload)
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://tarot-bot-luna.com",
            "X-Title": "Tarot Bot Luna"
        }
        
        # ✅ УСОВЕРШЕНСТВОВАННЫЙ BACKOFF С ОГРАНИЧЕНИЕМ
        for attempt in range(self.max_retries):
            start_time = time.time()
            try:
                timeout_seconds = self._get_request_timeout(model)
                timeout = aiohttp.ClientTimeout(total=timeout_seconds)
                
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"📤 Sending request to {model}, attempt {attempt + 1}, timeout: {timeout_seconds}s")
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                        timeout=timeout
                    ) as response:
                        
                        end_time = time.time()
                        elapsed = end_time - start_time
                        response_headers = dict(response.headers)
                        
                        # ✅ DEBUG: логируем метаданные ответа
                        if logger.isEnabledFor(logging.DEBUG):
                            logger.debug(f"📨 Response (model={model}) status={response.status} time={elapsed:.1f}s")
                            logger.debug(f"🔧 Response headers: {response_headers}")
                        
                        if response.status == 200:
                            raw_body = await response.text()
                            
                            # ✅ DEBUG: логируем сырое тело ответа
                            if logger.isEnabledFor(logging.DEBUG):
                                logger.debug(f"📄 Raw response body (model={model}): {raw_body[:2000]!r}")
                            
                            try:
                                result = json.loads(raw_body)
                                interpretation = result['choices'][0]['message']['content'].strip()
                                
                                # ✅ INFO: только высокоуровневая информация
                                logger.info(f"✅ SUCCESS: {model} responded in {elapsed:.1f}s, len={len(interpretation)}")
                                
                                return {
                                    "success": True,
                                    "text": interpretation,
                                    "model": model,
                                    "error": None
                                }
                            except (json.JSONDecodeError, KeyError, IndexError) as e:
                                logger.error(f"❌ Failed to parse response from {model}: {str(e)}")
                                return {
                                    "success": False,
                                    "text": None,
                                    "model": model,
                                    "error": f"Failed to parse API response: {str(e)}"
                                }
                        
                        else:
                            error_text = await response.text()
                            end_time = time.time()
                            elapsed = end_time - start_time
                            
                            logger.error(f"❌ API Error {response.status} for {model}: {error_text}")
                            
                            if response.status == 429:
                                retry_after = response_headers.get('Retry-After')
                                wait_time = self._calculate_backoff(attempt)
                                
                                if retry_after:
                                    try:
                                        wait_time = min(int(retry_after), self.max_backoff)
                                        if logger.isEnabledFor(logging.DEBUG):
                                            logger.debug(f"⏰ Using Retry-After header: {wait_time} seconds")
                                    except ValueError:
                                        logger.warning(f"⚠️ Invalid Retry-After header: {retry_after}")
                                
                                logger.warning(f"⏳ Rate limit hit for {model}. Waiting {wait_time:.1f} seconds...")
                                await asyncio.sleep(wait_time)
                                continue
                            
                            return {
                                "success": False,
                                "text": None,
                                "model": model,
                                "error": f"API returned status {response.status}: {error_text[:200]}"
                            }
                            
            except asyncio.TimeoutError:
                end_time = time.time()
                elapsed = end_time - start_time
                timeout_setting = self._get_request_timeout(model)
                
                logger.warning(f"⏰ Request timeout (model={model}) after {elapsed:.1f}s (timeout setting: {timeout_setting}s)")
                
                if attempt == self.max_retries - 1:
                    return {
                        "success": False,
                        "text": None,
                        "model": model,
                        "error": f"Timeout after {self.max_retries} attempts"
                    }
                
                wait_time = self._calculate_backoff(attempt)
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"⏳ Waiting {wait_time:.1f}s before retry after timeout...")
                await asyncio.sleep(wait_time)
                
            except Exception as e:
                end_time = time.time()
                elapsed = end_time - start_time
                
                logger.error(f"❌ Model {model} error on attempt {attempt + 1}: {str(e)}")
                
                if attempt == self.max_retries - 1:
                    return {
                        "success": False,
                        "text": None,
                        "model": model,
                        "error": f"Exception after {self.max_retries} attempts: {str(e)}"
                    }
                
                wait_time = self._calculate_backoff(attempt)
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"⏳ Waiting {wait_time:.1f}s before retry after exception...")
                await asyncio.sleep(wait_time)
        
        return {
            "success": False,
            "text": None,
            "model": model,
            "error": f"All {self.max_retries} attempts failed"
        }

    def _validate_payload(self, payload: Dict) -> Dict:
        """Защитная валидация payload перед запросом"""
        validated_payload = payload.copy()
        
        temp = validated_payload.get('temperature', self.temperature)
        if not (0 <= temp <= 2):
            logger.warning(f"🚨 Invalid temperature {temp}, clamping to 1.0")
            validated_payload['temperature'] = 1.0
        
        tokens = validated_payload.get('max_tokens', self.max_tokens)
        if tokens > 4000:
            logger.warning(f"🚨 High max_tokens {tokens}, clamping to 4000")
            validated_payload['max_tokens'] = 4000
        
        return validated_payload

    def _is_model_in_cooldown(self, model: str) -> bool:
        """Circuit breaker: Проверка cooldown для модели"""
        if model not in self._model_cooldown_until:
            return False
        
        cooldown_until = self._model_cooldown_until[model]
        if time.time() < cooldown_until:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"🔒 Model {model} in cooldown until {datetime.fromtimestamp(cooldown_until)}")
            return True
        
        del self._model_cooldown_until[model]
        if model in self._model_failures:
            del self._model_failures[model]
        return False

    def _record_model_failure(self, model: str):
        """Circuit breaker: Запись неудачи"""
        current_failures = self._model_failures.get(model, 0) + 1
        self._model_failures[model] = current_failures
        
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"📉 Model {model} failure count: {current_failures}")
        
        if current_failures >= 3:
            cooldown_until = time.time() + self._model_cooldown_duration
            self._model_cooldown_until[model] = cooldown_until
            logger.warning(f"🚨 Model {model} entering cooldown until {datetime.fromtimestamp(cooldown_until)}")

    def _record_model_success(self, model: str):
        """Circuit breaker: Сброс счетчика неудач"""
        if model in self._model_failures:
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"🔄 Resetting failure count for model {model}")
            del self._model_failures[model]

    def _get_preferred_model(self, user_id: Optional[int] = None) -> Optional[str]:
        """Кэш успешных моделей: Получение предпочтительной модели"""
        if not user_id:
            return None
            
        if user_id in self._preferred_models:
            model, expiry_ts = self._preferred_models[user_id]
            if time.time() < expiry_ts and not self._is_model_in_cooldown(model):
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"🎯 Using preferred model {model} for user {user_id}")
                return model
            else:
                del self._preferred_models[user_id]
        
        return None

    def _set_preferred_model(self, user_id: Optional[int], model: str):
        """Кэш успешных моделей: Сохранение предпочтительной модели"""
        if user_id:
            expiry_ts = time.time() + self._preferred_model_ttl
            self._preferred_models[user_id] = (model, expiry_ts)
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"💾 Cached preferred model {model} for user {user_id}")

    def _contains_english_text(self, text: str) -> bool:
        """Валидация языка: Проверка на наличие английского текста"""
        if not text:
            return False
        
        english_word_pattern = re.compile(r'\b[a-zA-Z]{3,}\b')
        english_words = english_word_pattern.findall(text)
        
        if len(english_words) >= 2:
            logger.warning(f"🚨 Detected English words in response: {english_words[:3]}")
            return True
        
        return False

    def _is_valid_interpretation(self, interpretation: str) -> bool:
        """Усиленная валидация ответа с проверкой языка"""
        if not interpretation or len(interpretation.strip()) < 50:
            logger.warning("❌ Invalid interpretation: too short")
            return False
        
        interpretation_lower = interpretation.lower()
        
        forbidden_phrases = [
            "provide me with more context", "could you please provide", 
            "what would you like me to do", "i need more information",
            "please provide", "tell me more", "какую задачу",
            "что вы хотите", "пожалуйста, предоставьте", "уточните, пожалуйста",
            "как таролог, я", "в качестве таролога", "согласно картам таро"
        ]
        
        for phrase in forbidden_phrases:
            if phrase in interpretation_lower:
                logger.warning(f"❌ Invalid interpretation - contains forbidden phrase: {phrase}")
                return False
        
        if self._contains_english_text(interpretation):
            logger.warning("❌ Invalid interpretation - contains English text")
            return False
        
        if interpretation_lower.count('?') > 2:
            logger.warning("❌ Invalid interpretation - too many questions")
            return False
            
        if len(interpretation.split()) < 30:
            logger.warning("❌ Invalid interpretation - too few words")
            return False
        
        return True

    def _build_profile_context(self, user_age: int = None, user_gender: str = None, user_name: str = None):
        """Построение контекста профиля для промпта"""
        profile_context = ""
        
        if user_age or user_gender or user_name:
            profile_context = "Учитывай следующие данные о пользователе при интерпретации, но НЕ упоминай их прямо в тексте:\n"
            
            if user_name:
                profile_context += f"- Имя: {user_name}\n"
            
            if user_gender:
                gender_display = {
                    'male': 'мужчина',
                    'female': 'женщина', 
                    'other': 'человек'
                }.get(user_gender, 'человек')
                profile_context += f"- Пол: {gender_display}\n"
            
            if user_age:
                if user_age < 25:
                    age_group = "молодой"
                elif user_age < 35:
                    age_group = "в расцвете сил" 
                elif user_age < 50:
                    age_group = "зрелый"
                else:
                    age_group = "опытный"
                
                profile_context += f"- Возраст: {user_age} лет ({age_group})\n"
            
            profile_context += "\nИспользуй эти данные для тонкой настройки интерпретации, но не указывай их явно.\n\n"
        
        return profile_context

    def _build_prompt(self, spread_data: Dict, question_category: str, profile_context: str = "") -> str:
        """Построение промпта"""
        cards = spread_data.get('cards', [])
        card_names = []
        for card in cards:
            if isinstance(card, dict):
                card_names.append(card['name'])
            else:
                card_names.append(card.name)
                
        cache_key = f"{question_category}:{','.join(card_names)}"
        if profile_context:
            cache_key += f":profile_{hash(profile_context)}"
        
        if cache_key in self.prompt_cache:
            return self.prompt_cache[cache_key]
        
        spread_type = spread_data.get('spread_type', 'unknown')
        spread_name = "Карта дня" if spread_type == '1 карта' or len(cards) == 1 else "Расклад Прошлое-Настоящее-Будущее"
        
        cards_text = ""
        if spread_type == '1 карта' or len(cards) == 1:
            card = cards[0]
            if isinstance(card, dict):
                card_name = card['name']
                is_reversed = card.get('is_reversed', False)
            else:
                card_name = card.name
                is_reversed = getattr(card, 'is_reversed', False)
            position_text = "перевернутая" if is_reversed else "прямая"
            cards_text = f"• {card_name} ({position_text})"
        else:
            positions = spread_data.get('positions', ["Прошлое", "Настоящее", "Будущее"])
            for i, card in enumerate(cards):
                if isinstance(card, dict):
                    card_name = card['name']
                    is_reversed = card.get('is_reversed', False)
                else:
                    card_name = card.name
                    is_reversed = getattr(card, 'is_reversed', False)
                position = positions[i] if i < len(positions) else f"Позиция {i+1}"
                position_text = "перевернутая" if is_reversed else "прямая"
                cards_text += f"• {position}: {card_name} ({position_text})\n"
    
        prompt = f"""
Ты — профессиональный русскоязычный таролог с 20-летним стажем.

🚨 ВАЖНЫЕ ПРАВИЛА ЯЗЫКА:
• ОТВЕЧАЙ ТОЛЬКО НА РУССКОМ ЯЗЫКЕ
• НЕ ИСПОЛЬЗУЙ АНГЛИЙСКИЕ, КИТАЙСКИЕ ИЛИ ДРУГИЕ СИМВОЛЫ
• ПИШИ ГРАМОТНО И ПОЛНОСТЬЮ НА РУССКОМ ЯЗЫКЕ

{profile_context}

Тип расклада: {spread_name}
Категория вопроса: {question_category}

Карты в раскладе:
{cards_text}

Начни интерпретацию на русском языке:
"""
        
        if len(self.prompt_cache) >= self.cache_size:
            oldest_key = next(iter(self.prompt_cache))
            del self.prompt_cache[oldest_key]
        
        self.prompt_cache[cache_key] = prompt
        return prompt

    def _clean_ai_response(self, text: str) -> str:
        """Очистка AI-ответа от англицизмов"""
        if not text:
            return text
        
        corrections = {
            'responsable': 'ответственный',
            'stable': 'стабильный', 
            'energy': 'энергия',
            'card': 'карта',
            'spread': 'расклад',
            'upright': 'прямая',
            'reversed': 'перевернутая',
            'tarot': 'таро',
            'reading': 'гадание',
            'interpretation': 'толкование',
            'advice': 'совет',
            'guidance': 'руководство',
            'message': 'послание',
        }
        
        for wrong, correct in corrections.items():
            text = text.replace(wrong, correct)
            text = text.replace(wrong.capitalize(), correct.capitalize())
        
        return text

    def _clean_response(self, response: str) -> str:
        """Очистка и форматирование ответа"""
        if not response:
            return response
            
        clean_phrases = [
            "Конечно, вот интерпретация:",
            "Вот интерпретация вашего расклада:",
            "Интерпретация карт:",
            "Вот что говорят карта:",
            "Карты показывают:",
            "На основе вашего расклада:",
        ]
        
        for phrase in clean_phrases:
            response = response.replace(phrase, "")
        
        response = response.strip()
        
        if len(response) > 2000:
            response = response[:2000] + "..."
        
        return response

    def _generate_basic_interpretation(self, spread_data: dict, question_category: str) -> str:
        """Локальный fallback"""
        cards = spread_data['cards']
        spread_type = spread_data['spread_type']
        
        if spread_type == '1 карта':
            card = cards[0]
            
            if isinstance(card, dict):
                card_name = card['name']
                is_reversed = card.get('is_reversed', False)
            else:
                card_name = card.name
                is_reversed = getattr(card, 'is_reversed', False)
            
            interpretation = f"✨ {card_name} ({'перевернутая' if is_reversed else 'прямая'})\n\n"
            interpretation += f"В контексте {question_category} эта карта указывает на важный аспект твоей жизни."
            
        else:
            positions = spread_data.get('positions', ["Прошлое", "Настоящее", "Будущее"])
            interpretation = "🔮 Расклад показывает связь между разными этапами:\n\n"
            
            for i, card in enumerate(cards):
                if isinstance(card, dict):
                    card_name = card['name']
                else:
                    card_name = card.name
                    
                position = positions[i] if i < len(positions) else f"Позиция {i+1}"
                interpretation += f"• {position}: {card_name}\n"
                
            interpretation += f"\nОбщая тенденция в сфере {question_category}."
        
        interpretation += "\n\nДля более детальной интерпретации попробуй сделать расклад еще раз."
        return interpretation

    async def generate_question_answer(self, spread_id: int, user_id: int, question: str, 
                                     user_age: int = None, user_gender: str = None, 
                                     user_name: str = None) -> Dict[str, Any]:
        """Генерация ответа на вопрос по раскладу"""
        logger.info(f"🎯 Generating answer for question: {question}")
        
        try:
            spread_data = self._get_spread_data(spread_id, user_id)
            if not spread_data:
                return {
                    "success": False,
                    "text": None,
                    "model": None,
                    "error": f"Spread {spread_id} for user {user_id} not found"
                }
            
            profile_context = self._build_profile_context(user_age, user_gender, user_name)
            cards_text = self._format_cards_text(spread_data)
            interpretation_text = spread_data.get('interpretation', 'Интерпретация не сгенерирована')
            category = spread_data.get('category', 'общая тема')
            spread_type = spread_data.get('spread_type', 'unknown')
            
            prompt = f"""
Ты — опытный таролог. Ответь на вопрос пользователя по предыдущему раскладу.

{profile_context}

Вопрос пользователя: "{question}"

Информация о раскладе:
- Тип: {spread_type}
- Категория: {category}
- Карты: {cards_text}
- Исходная интерпретация: {interpretation_text}

Ответ (только на русском языке):
"""
            
            preferred_model = self._get_preferred_model(user_id)
            models_to_try = self.model_list.copy()
            
            if preferred_model and preferred_model in models_to_try:
                models_to_try.remove(preferred_model)
                models_to_try.insert(0, preferred_model)

            for i, model in enumerate(models_to_try, 1):
                if self._is_model_in_cooldown(model):
                    continue
                    
                if logger.isEnabledFor(logging.DEBUG):
                    logger.debug(f"🔄 Trying model {i}/{len(models_to_try)} for question: {model}")
                
                result = await self._make_llm_request(model, prompt=prompt)
                
                if result["success"] and self._is_valid_interpretation(result["text"]):
                    logger.info(f"✅ SUCCESS with model {model} for question")
                    
                    if model != "deepseek/deepseek-r1:free":
                        self._set_preferred_model(user_id, model)
                    
                    self._record_model_success(model)
                    
                    cleaned_response = self._clean_response(result["text"])
                    final_response = self._clean_ai_response(cleaned_response)
                    
                    return {
                        "success": True,
                        "text": final_response,
                        "model": model,
                        "error": None
                    }
                else:
                    logger.warning(f"❌ Model {model} failed for question: {result.get('error', 'Unknown error')}")
                    self._record_model_failure(model)
                    continue
            
            logger.error("❌ All models failed for question answering")
            return {
                "success": False,
                "text": "К сожалению, я не могу ответить на ваш вопрос прямо сейчас. Пожалуйста, попробуйте позже.",
                "model": None,
                "error": "All models failed"
            }
            
        except Exception as e:
            logger.error(f"❌ Critical error in generate_question_answer: {e}")
            return {
                "success": False,
                "text": None,
                "model": None,
                "error": f"Critical error: {str(e)}"
            }

    def _format_cards_text(self, spread_data: Dict) -> str:
        """Форматирование текста карт для промпта"""
        cards = spread_data.get('cards', [])
        if isinstance(cards, str):
            try:
                cards = json.loads(cards)
            except:
                cards = []
        
        spread_type = spread_data.get('spread_type', 'unknown')
        cards_text = ""
        
        if spread_type == '1 карта' or len(cards) == 1:
            card = cards[0] if cards else "Неизвестная карта"
            if isinstance(card, dict):
                card_name = card.get('name', 'Неизвестная карта')
            else:
                card_name = str(card)
            cards_text = f"• {card_name}"
        else:
            positions = ["Прошлое", "Настоящее", "Будущее"]
            for i, card in enumerate(cards):
                if i < len(positions):
                    position = positions[i]
                else:
                    position = f"Позиция {i+1}"
                
                if isinstance(card, dict):
                    card_name = card.get('name', 'Неизвестная карта')
                else:
                    card_name = str(card)
                cards_text += f"• {position}: {card_name}\n"
        
        return cards_text

    def _get_spread_data(self, spread_id: int, user_id: int):
        """Получение данных расклада из базы данных"""
        try:
            from src.user_database import UserDatabase
            user_db = UserDatabase()
            
            history = user_db.get_user_history_by_spread_id(user_id, spread_id)
            
            if history:
                return history[0] if isinstance(history, list) and len(history) > 0 else history
            else:
                return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения данных расклада {spread_id} для пользователя {user_id}: {e}")
            return None