# src/services/ai_service.py
import logging
import asyncio
import time
import re
import os
import html
from datetime import datetime
import traceback
from typing import Dict, List, Optional, Tuple, Any, Union

# Настройка логгера для предотвращения дублирования
logger = logging.getLogger(__name__)
logger.propagate = False

# Добавляем обработчик только если его еще нет
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# Конфигурация валидации
MIN_RESPONSE_LENGTH = 50
MIN_CYRILLIC_RATIO = 0.8  # ужесточаем проверку: требуем >=80% кириллицы
FALLBACK_ACCEPT_MIN = 10
TELEGRAM_MAX_MESSAGE = 4096
TELEGRAM_SAFE_LIMIT = 3900

SYSTEM_PROMPT = (
    "Вы — опытный таролог и копирайтер на русском языке. Всегда отвечайте на русском. "
    "Не используйте английские слова, латиницу, нечитаемые фрагменты или сырые JSON-метки. "
    "Формат ответа: заголовок (одно предложение), затем 3 раздела: Прошлое / Настоящее / Будущее. "
    "Каждый раздел — 2–4 предложения, эмпатичный, понятный, без технических подробностей. "
    "Итог — одно короткое позитивное резюме (1-2 предложения). Не используйте HTML-теги сами — мы будем экранировать вывод."
)

USER_PROMPT_TEMPLATE = (
    "Вход: spread_type={spread_type}, cards={cards}\n"
    "Контекст: пол={gender}, возраст={age}, вопрос=\"{question}\"\n"
    "Требование: выдайте текст строго на русском, без англ. слов, длина ~800-1400 знаков."
)

class AIService:
    def __init__(self, user_db, ai_interpreter):
        self.user_db = user_db
        self.ai_interpreter = ai_interpreter

        # Circuit-breaker метрики
        self.model_failures: Dict[str, Dict] = {}
        self.model_successes: Dict[str, int] = {}
        self.model_last_used: Dict[str, float] = {}
        self.model_permanent_failures: set = set()  # Для 404 ошибок
        self.model_temp_backoff: Dict[str, float] = {}  # model -> next_retry_timestamp

        # Конфигурация
        self.max_consecutive_failures = 3
        self.circuit_breaker_timeout = 300

        # Настройка списков моделей: primary -> пытаемся в первую очередь, fallback -> запас
        base_models = getattr(self.ai_interpreter, 'model_list', None)
        if base_models and isinstance(base_models, (list, tuple)) and len(base_models) > 1:
            # Простейшая стратегия: первые 3 — primary, остальные — fallback
            self.primary_models = list(base_models[:3])
            self.fallback_models = list(base_models[3:])
        else:
            # Дефолтный порядок (можно переопределить извне)
            self.primary_models = [
                'anthropic/claude-3-sonnet',
                'meta-llama/llama-3-70b-instruct',
                'anthropic/claude-3-haiku'
            ]
            self.fallback_models = [
                'openai/gpt-3.5-turbo',
                'google/gemini-pro',
                'microsoft/wizardlm-2'
            ]

        # Лог OpenRouter
        self.openrouter_key = os.getenv('OPENROUTER_KEY')
        if not self.openrouter_key:
            logger.warning("🔑 OPENROUTER_KEY не установлен. Использую бесплатные модели с лимитами.")
        else:
            logger.info("🔑 OPENROUTER_KEY обнаружен — OpenRouter будет использоваться для поддерживаемых моделей.")

    # ------------------------ Санитизация и разбиение ------------------------
    def sanitize_ai_text_for_telegram(self, text: str) -> str:
        """
        Экранирует текст для безопасной отправки в Telegram с использованием парсера HTML.
        Возвращает обёрнутый <pre>...<pre> текст (без автоматической разбивки).
        """
        if text is None:
            return ""
        
        # Экранируем HTML-символы
        escaped = html.escape(text)
        
        # Обрезаем до безопасного лимита Telegram
        if len(escaped) <= TELEGRAM_SAFE_LIMIT:
            return f"<pre>{escaped}</pre>"
        
        # Для длинных текстов caller должен разбивать на порции
        return escaped

    def split_text_into_chunks(self, text: str, max_chunk: int = TELEGRAM_SAFE_LIMIT) -> List[str]:
        """
        Разбивает текст на чанки, пытаясь резать по границам параграфов/строк.
        Возвращает список строк, каждая <= max_chunk (в символах).
        """
        if not text:
            return []

        if len(text) <= max_chunk:
            return [text]

        chunks = []
        current_chunk = ""
        
        # Разбиваем на параграфы, сохраняя разделители
        paragraphs = re.split(r'(\n\n+)', text)
        
        for paragraph in paragraphs:
            # Если добавление параграфа не превышает лимит
            if len(current_chunk) + len(paragraph) <= max_chunk:
                current_chunk += paragraph
            else:
                # Если текущий чанк не пустой, сохраняем его
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = ""
                
                # Если параграф сам по себе слишком длинный, разбиваем по строкам
                if len(paragraph) > max_chunk:
                    lines = paragraph.split('\n')
                    for line in lines:
                        if len(current_chunk) + len(line) + 1 <= max_chunk:
                            current_chunk += line + '\n'
                        else:
                            if current_chunk:
                                chunks.append(current_chunk.strip())
                            current_chunk = line + '\n' if len(line) + 1 <= max_chunk else line[:max_chunk]
                else:
                    current_chunk = paragraph
        
        # Добавляем последний чанк
        if current_chunk:
            chunks.append(current_chunk.strip())
            
        return chunks

    async def send_sanitized_message(self, bot, chat_id: int, text: str) -> bool:
        """
        Безопасно отправляет сообщение в Telegram с автоматическим разбиением на чанки.
        Возвращает True если отправка успешна, False при ошибке.
        """
        try:
            chunks = self.split_text_into_chunks(text)
            for chunk in chunks:
                safe_text = self.sanitize_ai_text_for_telegram(chunk)
                # Если текст все еще слишком длинный после санитизации, обрезаем
                if len(safe_text) > TELEGRAM_MAX_MESSAGE:
                    safe_text = safe_text[:TELEGRAM_MAX_MESSAGE - 100] + "...</pre>"
                
                await bot.send_message(chat_id, safe_text, parse_mode='HTML')
                # Небольшая задержка между сообщениями чтобы не спамить
                await asyncio.sleep(0.5)
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка отправки сообщения в Telegram: {str(e)}")
            return False

    # ------------------------ Извлечение/валидация текста ------------------------
    def _extract_text_from_response(self, response: Any) -> str:
        """
        Безопасно извлекает текст из различных форматов ответов AI.
        Поддерживает: str, dict (OpenAI format), list
        """
        if response is None:
            return ""

        # Если это строка - возвращаем как есть
        if isinstance(response, str):
            return response.strip()

        # Если это словарь - ищем текстовые поля
        if isinstance(response, dict):
            # Пробуем разные возможные ключи в порядке приоритета
            text_keys = ['choices', 'message', 'content', 'text', 'response', 'answer']

            for key in text_keys:
                if key in response:
                    extracted = self._extract_text_from_response(response[key])
                    if extracted:
                        return extracted

            # Если не нашли стандартных ключей, пробуем найти любую строку в значениях
            for value in response.values():
                if isinstance(value, str) and len(value.strip()) > 10:
                    return value.strip()

        # Если это список - обрабатываем каждый элемент
        if isinstance(response, list):
            texts = []
            for item in response:
                extracted = self._extract_text_from_response(item)
                if extracted:
                    texts.append(extracted)
            return " ".join(texts) if texts else ""

        # Если это другой тип - пробуем преобразовать в строку
        try:
            text = str(response).strip()
            return text if len(text) > 10 else ""
        except:
            return ""

    def _is_response_valid(self, text: str) -> Tuple[bool, str]:
        """
        Проверяет валидность ответа AI.
        Возвращает (is_valid, reason)
        Усиленная проверка: доля кириллицы >= MIN_CYRILLIC_RATIO и отсутствие опасных html-токенов
        """
        if not text or not isinstance(text, str):
            return False, 'empty_or_not_string'

        t = text.strip()

        # Проверка длины
        if len(t) < MIN_RESPONSE_LENGTH:
            return False, f'too_short_{len(t)}'

        # Подсчет кириллических символов
        cyrillic_count = sum(1 for ch in t if '\u0400' <= ch <= '\u04FF')
        total_chars = len(t)

        if total_chars == 0:
            return False, 'empty_after_strip'

        cyrillic_ratio = cyrillic_count / total_chars

        # Проверка доли кириллицы (строгая)
        if cyrillic_ratio < MIN_CYRILLIC_RATIO:
            return False, f'low_cyrillic_ratio_{cyrillic_ratio:.2f}'

        # Проверка на английские отказы и латиницу
        lower = t.lower()
        english_refusals = [
            "i cannot", "i'm sorry", "as an ai", "i am not able",
            "cannot fulfill", "unable to", "not appropriate", "i'm an ai",
            "as a language model", "i'm a language model"
        ]
        if any(refusal in lower for refusal in english_refusals):
            return False, 'contains_english_refusal'

        # Проверка на подозрительные символы/теги
        forbidden_patterns = [
            r'<[^>]+>',  # HTML теги
            r'\{.*?\}',  # JSON-подобные структуры
            r'\[.*?\]',  # Квадратные скобки с содержимым
            r'https?://',  # URL
            r'www\.',  # URL без протокола
            r'\\[a-z_]+',  # Бэклеш-команды
        ]
        
        for pattern in forbidden_patterns:
            if re.search(pattern, t, re.IGNORECASE):
                return False, 'contains_forbidden_tokens'

        return True, 'valid'

    def _calculate_candidate_score(self, text: str, validation_reason: str) -> float:
        """
        Рассчитывает оценку кандидата для выбора лучшего fallback.
        Чем выше оценка - тем лучше кандидат.
        """
        score = 0.0
        length = len(text.strip())

        # Базовый счет за длину
        score += min(length / 1000.0, 1.0)  # Нормализуем длину до 1.0

        # Улучшаем за хорошую кириллицу
        cyrillic_count = sum(1 for ch in text if '\u0400' <= ch <= '\u04FF')
        total_chars = max(1, len(text))
        cyrillic_ratio = cyrillic_count / total_chars
        score += cyrillic_ratio * 1.0

        # Штрафы за разные типы проблем
        if 'low_cyrillic_ratio' in validation_reason:
            try:
                ratio = float(validation_reason.split('_')[-1])
                score += ratio * 0.3  # Частичный штраф
            except:
                score += 0.2
        elif 'too_short' in validation_reason:
            try:
                actual_length = int(validation_reason.split('_')[-1])
                score += (actual_length / MIN_RESPONSE_LENGTH) * 0.2
            except:
                score += 0.05
        elif 'contains_english_refusal' in validation_reason or 'contains_forbidden' in validation_reason:
            score *= 0.1  # Серьезный штраф за отказы и запрещенные токены

        return score

    # ------------------------ Логика выбора моделей и обработки ошибок ------------------------
    def _get_available_models(self) -> List[str]:
        """
        Получение списка доступных моделей с учетом circuit-breaker, temp backoff и правильным порядком
        Сначала primary, затем fallback.
        """
        base_models = self.primary_models + self.fallback_models
        available_models = []
        current_time = time.time()

        for model in base_models:
            # Пропускаем permanently failed модели
            if model in self.model_permanent_failures:
                continue

            # Проверяем временный backoff (после 429)
            if model in self.model_temp_backoff:
                next_try = self.model_temp_backoff[model]
                if current_time < next_try:
                    logger.debug(f"🚫 Модель {model} временно в backoff до {datetime.fromtimestamp(next_try).strftime('%H:%M:%S')}")
                    continue
                else:
                    # Снимаем backoff по истечении времени
                    del self.model_temp_backoff[model]

            # Проверяем circuit-breaker по количеству неудач
            if model in self.model_failures:
                failures_info = self.model_failures[model]
                if (failures_info['count'] >= self.max_consecutive_failures and
                        current_time - failures_info['last_failure'] < self.circuit_breaker_timeout):
                    logger.debug(f"🚫 Модель {model} временно заблокирована circuit-breaker")
                    continue

            available_models.append(model)

        logger.info(f"🔧 Доступно моделей: {len(available_models)} из {len(base_models)}")
        if available_models:
            logger.debug(f"🔧 Порядок моделей: {[m.split('/')[-1] for m in available_models]}")

        if not self.openrouter_key and len(available_models) < len(base_models):
            logger.warning("🔑 Установите OPENROUTER_KEY для доступа к большему количеству моделей и снятия лимитов")

        return available_models

    def _classify_error(self, error: Exception) -> str:
        """
        Классификация ошибок для лучшей обработки
        """
        error_msg = str(error).lower()

        if '404' in error_msg or 'not found' in error_msg:
            return "model_not_found_404"
        elif '429' in error_msg or 'too many requests' in error_msg or 'rate limit' in error_msg:
            return "rate_limit_429"
        elif 'timeout' in error_msg or 'timed out' in error_msg:
            return "timeout"
        elif '503' in error_msg or '502' in error_msg or 'service unavailable' in error_msg:
            return "service_unavailable"
        elif '401' in error_msg or 'unauthorized' in error_msg:
            return "auth_error"
        elif 'api' in error_msg or 'openrouter' in error_msg:
            return "api_error"
        else:
            return "unknown_error"

    def _handle_model_error(self, model: str, error_type: str, error_message: str):
        """Обработка ошибок модели с учётом 404/429"""
        if error_type == "model_not_found_404":
            self.model_permanent_failures.add(model)
            logger.error(f"💥 Модель {model} не найдена (404). Добавлена в permanent failures.")
        elif error_type == "rate_limit_429":
            # Exponential backoff на основе количества неудач
            failures = self.model_failures.get(model, {}).get('count', 0)
            base_backoff = 60  # секунды
            backoff = min(3600, base_backoff * (2 ** max(0, failures - 1)))
            next_try = time.time() + backoff
            self.model_temp_backoff[model] = next_try
            logger.warning(f"⏳ Модель {model} превысила лимит (429). Backoff {backoff}s, next_try={datetime.fromtimestamp(next_try).strftime('%H:%M:%S')}")
            self._record_failure(model, error_type)
        elif error_type == "auth_error":
            self.model_permanent_failures.add(model)
            logger.error(f"🔐 Модель {model} требует авторизации (401). Добавлена в permanent failures.")
        else:
            # Другие ошибки
            self._record_failure(model, error_type)

    def _record_success(self, model: str):
        """Запись успешного выполнения модели"""
        self.model_successes[model] = self.model_successes.get(model, 0) + 1

        # Сброс счетчика ошибок при успехе
        if model in self.model_failures:
            del self.model_failures[model]
        
        # Сброс временного backoff при успехе
        if model in self.model_temp_backoff:
            del self.model_temp_backoff[model]

    def _record_failure(self, model: str, failure_type: str):
        """Запись неудачи модели"""
        if model not in self.model_failures:
            self.model_failures[model] = {"count": 0, "last_failure": time.time(), "types": []}

        self.model_failures[model]["count"] += 1
        self.model_failures[model]["last_failure"] = time.time()
        self.model_failures[model]["types"].append(failure_type)

        # Лимитируем историю типов ошибок
        if len(self.model_failures[model]["types"]) > 10:
            self.model_failures[model]["types"] = self.model_failures[model]["types"][-5:]

    # ------------------------ Генерация интерпретации ------------------------
    async def generate_ai_interpretation(self, spread_cards, spread_type, category, user_id, chat_id, bot, spread_id=None, user_name=None, question=None):
        """Генерация AI-интерпретации с улучшенной обработкой ошибок и метриками"""
        if not self.ai_interpreter:
            logger.warning("OpenRouter interpreter not available")
            return None

        # Получаем данные пользователя
        user_profile = self.user_db.get_user_profile(user_id)
        user_age, user_gender = self._extract_user_profile_data(user_profile)

        if not user_name and user_profile:
            user_name = user_profile.get('first_name', 'друг')

        logger.info(f"🎯 Запуск AI-интерпретации: user_id={user_id}, spread_type={spread_type}, cards={len(spread_cards)}")

        # Получаем доступные модели с учетом circuit-breaker
        available_models = self._get_available_models()
        if not available_models:
            logger.error("❌ Все модели временно заблокированы circuit-breaker/backoff")
            fallback_result = self._handle_complete_failure(spread_type, spread_cards, category, user_name, "all_models_circuit_broken")
            # Отправляем fallback пользователю
            if bot and chat_id:
                await self.send_sanitized_message(bot, chat_id, fallback_result)
            return fallback_result

        # Подготавливаем prompt
        cards_repr = str([f"{card.get('position', 'unknown')}: {card.get('name', 'unknown')} (reversed: {card.get('is_reversed', False)})" 
                         for card in spread_cards])
        user_prompt = USER_PROMPT_TEMPLATE.format(
            spread_type=spread_type, 
            cards=cards_repr, 
            gender=user_gender or 'unknown', 
            age=user_age or 'unknown', 
            question=question or 'нет вопроса'
        )

        # Основной цикл перебора моделей
        interpretation, successful_model = await self._try_models_sequence(
            available_models, spread_type, spread_cards, category,
            user_age, user_gender, user_name, user_id,
            system_prompt=SYSTEM_PROMPT, user_prompt=user_prompt
        )

        # Обработка результатов
        if interpretation:
            await self._handle_success(interpretation, successful_model, spread_id, user_id)
            # Отправляем пользователю безопасно разбитые части
            if bot and chat_id:
                await self.send_sanitized_message(bot, chat_id, interpretation)
            return interpretation
        else:
            fallback_result = self._handle_complete_failure(spread_type, spread_cards, category, user_name, "all_models_failed")
            if bot and chat_id:
                await self.send_sanitized_message(bot, chat_id, fallback_result)
            return fallback_result

    async def _try_models_sequence(self, models: List[str], spread_type: str, spread_cards: list,
                                 category: str, user_age: Optional[int], user_gender: Optional[str],
                                 user_name: str, user_id: int, system_prompt: Optional[str] = None, user_prompt: Optional[str] = None):
        """Последовательный перебор моделей с улучшенной обработкой ответов"""
        failure_reasons = {}
        candidates = []  # (text, model, length, validation_reason, score)
        valid_candidate_found = False

        for model_index, model in enumerate(models, 1):
            model_name = model.split('/')[-1]

            # Пропускаем permanently failed модели
            if model in self.model_permanent_failures:
                logger.debug(f"🚫 Пропускаем permanently failed модель: {model}")
                continue

            # Если модель в temp backoff — пропускаем
            if model in self.model_temp_backoff and time.time() < self.model_temp_backoff[model]:
                logger.debug(f"⏳ Пропускаем {model} из-за temp backoff")
                continue

            logger.info(f"🔄 Попытка {model_index}/{len(models)}: {model_name}")

            start_time = time.time()
            raw_response = None
            error_type = None

            try:
                # Попробуем передать system/user prompts, если интерпретатор их поддерживает
                try:
                    raw_response = await self.ai_interpreter.generate_interpretation(
                        spread_type=spread_type,
                        cards=spread_cards,
                        category=category,
                        user_age=user_age,
                        user_gender=user_gender,
                        user_name=user_name,
                        model=model,
                        system_prompt=system_prompt,
                        user_prompt=user_prompt
                    )
                except TypeError as te:
                    # FALLBACK: если метод не принимает system_prompt/user_prompt/model - пробуем менее параметризованную версию
                    if "unexpected keyword argument" in str(te):
                        logger.debug(f"AIInterpreter.generate_interpretation не поддерживает часть параметров ({te}) — пробую с минимальным набором")
                        raw_response = await self.ai_interpreter.generate_interpretation(
                            spread_type=spread_type,
                            cards=spread_cards,
                            category=category,
                            user_age=user_age,
                            user_gender=user_gender,
                            user_name=user_name
                        )
                    else:
                        raise

            except Exception as e:
                error_type = self._classify_error(e)
                failure_reasons[model] = f"{error_type}: {str(e)}"
                self._handle_model_error(model, error_type, str(e))

            # Обработка ответа
            if raw_response is not None:
                response_time = time.time() - start_time
                self.model_last_used[model] = time.time()

                # Извлекаем текст из ответа
                extracted_text = self._extract_text_from_response(raw_response)

                # Логируем сырой ответ для диагностики (DEBUG)
                logger.debug(f"📝 RAW (model={model}): {extracted_text[:200]!r}...")

                # Валидация ответа
                is_valid, validation_reason = self._is_response_valid(extracted_text)

                if is_valid:
                    # Успешная генерация
                    self._record_success(model)
                    logger.info(f"✅ Модель {model_name} успешна за {response_time:.2f}с, длина: {len(extracted_text)}")
                    valid_candidate_found = True
                    return extracted_text, model
                else:
                    # Всегда добавляем в кандидаты если достаточно длинный, даже с проблемами
                    if len(extracted_text.strip()) >= FALLBACK_ACCEPT_MIN:
                        score = self._calculate_candidate_score(extracted_text, validation_reason)
                        candidates.append((extracted_text, model, len(extracted_text.strip()), validation_reason, score))
                        logger.debug(f"🟡 Модель {model} добавлена в кандидаты: {validation_reason}, длина={len(extracted_text.strip())}, score={score:.2f}")

                    failure_reasons[model] = f"validation_failed: {validation_reason}"
                    self._record_failure(model, "validation_failed")
                    logger.warning(f"❌ Model {model} validation failed: {validation_reason}")

            else:
                # raw_response is None - ошибка уже записана
                response_time = time.time() - start_time
                if error_type:
                    logger.warning(f"❌ Модель {model} ошибка: {error_type}, время: {response_time:.2f}с")

        # Логируем список кандидатов как DEBUG
        if candidates:
            logger.debug(f"📋 Fallback кандидаты: {[(c[1], c[2], c[3], f'score:{c[4]:.2f}') for c in candidates]}")

        # Fallback логика: выбираем лучшего кандидата
        if candidates and not valid_candidate_found:
            candidates.sort(key=lambda x: x[4], reverse=True)
            best_text, best_model, best_length, validation_reason, best_score = candidates[0]

            logger.info(f"⚠️ Выбран fallback-кандидат от {best_model} (длина={best_length}, score={best_score:.2f}, причина={validation_reason})")
            self._record_success(best_model)
            return best_text, f"{best_model}_fallback_accepted"

        # Полный провал
        logger.error(f"📊 Все модели не справились: {failure_reasons}")
        return None, None

    # ------------------------ Сохранение/фолбек и misc ------------------------
    async def _handle_success(self, interpretation: str, model: str, spread_id: Optional[int], user_id: int):
        """Обработка успешной генерации"""
        model_name = model.split('/')[-1]
        logger.info(f"🎉 УСПЕХ: модель {model_name} сгенерировала интерпретацию {len(interpretation)} символов")

        # Сохранение в БД
        if spread_id:
            logger.info(f"💾 Сохранение интерпретации для расклада {spread_id}")
            success = self.user_db.update_interpretation(spread_id, interpretation)
            if success:
                logger.info(f"💾 Интерпретация успешно сохранена для расклада {spread_id}")
            else:
                logger.error(f"❌ Ошибка сохранения интерпретации для расклада {spread_id}")

    def _handle_complete_failure(self, spread_type: str, cards: list, category: str, user_name: str, reason: str):
        """Обработка полного отказа всех моделей"""
        logger.error(f"💥 ПОЛНЫЙ ОТКАЗ: {reason}. Использую fallback.")

        interpretation = self._generate_fallback_interpretation(spread_type, cards, category, user_name)
        logger.info(f"🔄 Fallback интерпретация: {len(interpretation)} символов")

        return interpretation

    def _generate_fallback_interpretation(self, spread_type: str, cards: list, category: str, user_name: str) -> str:
        """Генерация fallback интерпретации"""
        card_descriptions = []
        for i, card in enumerate(cards):
            if isinstance(card, dict):
                card_name = card.get('name', 'Неизвестная карта')
                position = card.get('position', f'Позиция {i+1}')
                reversed_status = "перевернута" if card.get('is_reversed', False) else "прямая"
                card_descriptions.append(f"• {position}: {card_name} ({reversed_status})")
            else:
                card_descriptions.append(f"• Карта {i+1}: {card}")

        cards_text = "\n".join(card_descriptions)

        if spread_type == "one_card":
            card = cards[0]
            card_name = card['name'] if isinstance(card, dict) else card
            interpretation = (
                f"{user_name}, карта **{card_name}** указывает на важные энергии в вашей жизни. "
                f"Эта карта связана с категорией **{category}** и может говорить о новых возможностях "
                f"или вызовах, которые вам предстоит рассмотреть."
            )
        elif spread_type == "three_cards":
            interpretation = (
                f"{user_name}, ваш расклад **Три Карты** показывает:\n\n"
                f"{cards_text}\n\n"
                f"В контексте **{category}** этот расклад раскрывает различные аспекты вашей ситуации. "
                f"Первая карта говорит о прошлом влиянии, вторая - о текущей ситуации, "
                f"третья - о возможном будущем развитии событий."
            )
        else:
            interpretation = (
                f"{user_name}, ваш расклад **{spread_type}** показывает:\n\n"
                f"{cards_text}\n\n"
                f"В контексте **{category}** этот расклад раскрывает различные аспекты вашей ситуации. "
                f"Каждая карта вносит свой уникальный вклад в общую картину."
            )

        interpretation += "\n\n🔮 *Базовая интерпретация (AI временно недоступен)*"
        return interpretation

    def get_metrics(self) -> Dict:
        """Получение метрик для мониторинга"""
        return {
            "successes": self.model_successes.copy(),
            "failures": {k: v.copy() for k, v in self.model_failures.items()},
            "last_used": self.model_last_used.copy(),
            "permanent_failures": list(self.model_permanent_failures),
            "temp_backoff": self.model_temp_backoff.copy()
        }

    # ------------------------ Доп. генерация ответа на вопрос ------------------------
    async def generate_answer_for_spread_question(self, spread_id: int, question: str, user_id: int, chat_id: int, bot):
        """Генерация ответа на вопрос по сохраненному раскладу"""
        if not self.ai_interpreter:
            logger.warning("OpenRouter interpreter not available for question answering")
            return None

        try:
            # Получаем данные расклада из базы данных
            spread_data = self.user_db.get_spread(spread_id)
            if not spread_data:
                logger.error(f"❌ Расклад с ID {spread_id} не найден")
                return None

            # Получаем карты расклада
            spread_cards = spread_data.get('cards', [])
            spread_type = spread_data.get('spread_type', 'unknown')
            category = spread_data.get('category', 'general')
            original_interpretation = spread_data.get('interpretation', '')

            # Получаем данные пользователя
            user_profile = self.user_db.get_user_profile(user_id)
            user_age, user_gender = self._extract_user_profile_data(user_profile)
            user_name = user_profile.get('first_name', 'друг') if user_profile else 'друг'

            logger.info(f"🎯 Генерация ответа на вопрос по раскладу {spread_id}: "
                       f"user_id={user_id}, spread_type={spread_type}, cards={len(spread_cards)}, "
                       f"question_length={len(question)}")

            available_models = self._get_available_models()
            if not available_models:
                logger.error("❌ Все модели временно заблокированы circuit-breaker/backoff")
                fallback_answer = self._generate_fallback_answer(question, user_name)
                if bot and chat_id:
                    await self.send_sanitized_message(bot, chat_id, fallback_answer)
                return fallback_answer

            # Подготавливаем prompt для вопроса
            cards_repr = str([f"{card.get('position', 'unknown')}: {card.get('name', 'unknown')}" for card in spread_cards])
            user_prompt = USER_PROMPT_TEMPLATE.format(
                spread_type=spread_type, 
                cards=cards_repr, 
                gender=user_gender or 'unknown', 
                age=user_age or 'unknown', 
                question=question
            )

            answer, successful_model = await self._try_models_sequence_for_question(
                available_models, spread_id, spread_cards, spread_type, category,
                original_interpretation, question, user_age, user_gender, user_name, user_id,
                user_prompt=user_prompt
            )

            if answer:
                logger.info(f"✅ Ответ на вопрос успешно сгенерирован моделью {successful_model}, длина: {len(answer)}")
                # Отправляем безопасно
                if bot and chat_id:
                    await self.send_sanitized_message(bot, chat_id, answer)
                return answer
            else:
                logger.warning("❌ Не удалось сгенерировать ответ на вопрос")
                fallback_answer = self._generate_fallback_answer(question, user_name)
                if bot and chat_id:
                    await self.send_sanitized_message(bot, chat_id, fallback_answer)
                return fallback_answer

        except Exception as e:
            logger.error(f"💥 Ошибка генерации ответа на вопрос по раскладу: {str(e)}")
            logger.debug(f"🔍 Детали ошибки: {traceback.format_exc()}")
            fallback_answer = self._generate_fallback_answer(question, 'друг')
            if bot and chat_id:
                await self.send_sanitized_message(bot, chat_id, fallback_answer)
            return fallback_answer

    async def _try_models_sequence_for_question(self, models: List[str], spread_id: int, spread_cards: list,
                                              spread_type: str, category: str, original_interpretation: str,
                                              question: str, user_age: Optional[int], user_gender: Optional[str],
                                              user_name: str, user_id: int, user_prompt: Optional[str] = None):
        """Последовательный перебор моделей для ответа на вопрос"""
        failure_reasons = {}
        candidates = []  # (text, model, length, validation_reason, score)
        valid_candidate_found = False

        for model_index, model in enumerate(models, 1):
            model_name = model.split('/')[-1]

            # Пропускаем permanently failed модели
            if model in self.model_permanent_failures:
                logger.debug(f"🚫 Пропускаем permanently failed модель: {model}")
                continue

            # Пропускаем временно заблокированные модели
            if model in self.model_temp_backoff and time.time() < self.model_temp_backoff[model]:
                logger.debug(f"⏳ Пропускаем {model} из-за temp backoff")
                continue

            logger.info(f"🔄 Попытка {model_index}/{len(models)} для вопроса: {model_name}")

            start_time = time.time()
            raw_response = None
            error_type = None

            try:
                try:
                    raw_response = await self.ai_interpreter.generate_question_answer(
                        spread_id=spread_id,
                        user_id=user_id,
                        question=question,
                        user_age=user_age,
                        user_gender=user_gender,
                        user_name=user_name,
                        model=model,
                        user_prompt=user_prompt
                    )
                except TypeError:
                    # FALLBACK: если метод не принимает model/user_prompt
                    raw_response = await self.ai_interpreter.generate_question_answer(
                        spread_id=spread_id,
                        user_id=user_id,
                        question=question,
                        user_age=user_age,
                        user_gender=user_gender,
                        user_name=user_name
                    )

            except Exception as e:
                error_type = self._classify_error(e)
                failure_reasons[model] = f"{error_type}: {str(e)}"
                self._handle_model_error(model, error_type, str(e))

            # Обработка ответа
            if raw_response is not None:
                response_time = time.time() - start_time
                self.model_last_used[model] = time.time()

                extracted_text = self._extract_text_from_response(raw_response)
                logger.debug(f"📝 RAW (model={model}): {extracted_text[:200]!r}...")

                is_valid, validation_reason = self._is_response_valid(extracted_text)

                if is_valid:
                    self._record_success(model)
                    logger.info(f"✅ Модель {model_name} сгенерировала ответ за {response_time:.2f}с, длина: {len(extracted_text)}")
                    valid_candidate_found = True
                    return extracted_text, model
                else:
                    if len(extracted_text.strip()) >= FALLBACK_ACCEPT_MIN:
                        score = self._calculate_candidate_score(extracted_text, validation_reason)
                        candidates.append((extracted_text, model, len(extracted_text.strip()), validation_reason, score))
                        logger.debug(f"🟡 Модель {model} добавлена в кандидаты: {validation_reason}, длина={len(extracted_text.strip())}, score={score:.2f}")

                    failure_reasons[model] = f"validation_failed: {validation_reason}"
                    self._record_failure(model, "validation_failed")
                    logger.warning(f"❌ Model {model} validation failed: {validation_reason}")

            else:
                response_time = time.time() - start_time
                if error_type:
                    logger.warning(f"❌ Модель {model} не справилась с вопросом: {error_type}, время: {response_time:.2f}с")

        if candidates:
            logger.debug(f"📋 Fallback кандидаты для вопроса: {[(c[1], c[2], c[3], f'score:{c[4]:.2f}') for c in candidates]}")

        if candidates and not valid_candidate_found:
            candidates.sort(key=lambda x: x[4], reverse=True)
            best_text, best_model, best_length, validation_reason, best_score = candidates[0]

            logger.info(f"⚠️ Выбран fallback-кандидат от {best_model} для вопроса (длина={best_length}, score={best_score:.2f}, причина={validation_reason})")
            self._record_success(best_model)
            return best_text, f"{best_model}_fallback_accepted"

        logger.error(f"📊 Статистика неудач при ответе на вопрос: {failure_reasons}")
        return None, None

    def _generate_fallback_answer(self, question: str, user_name: str) -> str:
        """Генерация fallback ответа на вопрос"""
        answer = (
            f"{user_name}, на основании вашего вопроса:\n\n"
            f"\"{question}\"\n\n"
            f"Я рекомендую вам внимательно изучить интерпретацию вашего расклада. "
            f"Каждая карта содержит глубокий символизм, который может пролить свет на вашу ситуацию. "
            f"Обратите внимание на взаимосвязи между картами и их позициями в раскладе.\n\n"
            f"🔮 *Для более детального анализа рекомендуется обратиться к опытному тарологу*"
        )
        logger.info(f"🔄 Использован fallback ответ на вопрос, длина: {len(answer)}")
        return answer

    def _extract_user_profile_data(self, user_profile):
        """Извлечение данных профиля пользователя"""
        user_age = None
        user_gender = None

        if user_profile and user_profile.get('birth_date'):
            try:
                birth_date_str = user_profile.get('birth_date')
                if '.' in birth_date_str:
                    birth_date = datetime.strptime(birth_date_str, '%d.%m.%Y')
                else:
                    birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d')

                today = datetime.now()
                user_age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
                logger.info(f"🎯 Расчет возраста: {birth_date_str} -> {user_age} лет")
            except Exception as e:
                logger.error(f"❌ Ошибка расчета возраста: {e}")

        if user_profile and user_profile.get('gender'):
            user_gender = user_profile.get('gender')
            logger.info(f"🎯 Получен пол: {user_gender}")

        return user_age, user_gender