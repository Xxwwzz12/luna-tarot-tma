# src/services/card_service.py
import logging
import os
import tempfile
import asyncio
import uuid
import html
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Union, Tuple
from PIL import Image, ImageOps
from telegram import InputMediaPhoto
from telegram.error import BadRequest

# Добавляем импорт для модели сессии
try:
    from src.models.user_context import InteractiveSession
except ImportError:
    # Fallback если модель еще не создана
    class InteractiveSession:
        def __init__(self, session_id, user_id, spread_type, category, selected_cards=None, 
                     current_position=1, created_at=None, chat_id=None, context=None, bot=None):
            self.session_id = session_id
            self.user_id = user_id
            self.spread_type = spread_type
            self.category = category
            self.selected_cards = selected_cards or {}
            self.current_position = current_position
            self.created_at = created_at or datetime.now()
            self.status = 'pending'
            self.chat_id = chat_id
            self.context = context
            self.bot = bot
            # 🔧 ГАРАНТИРУЕМ наличие флагов
            self.ai_executed = False
            self.saved_spread_id = None
            # 🆕 НОВЫЕ АТРИБУТЫ ДЛЯ СОХРАНЕНИЯ ID СООБЩЕНИЙ
            self.interface_message_id = None  # ID сообщения с интерфейсом выбора карт
            self.result_message_id = None     # ID финального сообщения с результатом
            self.ai_generating_message_id = None  # ID сообщения "Генерирую AI..."

logger = logging.getLogger(__name__)

class CardService:
    def __init__(self, user_db, tarot_engine, ai_service=None):
        self.user_db = user_db
        self.tarot_engine = tarot_engine
        self.ai_service = ai_service
        
        # Инициализация системы сессий
        self.active_sessions: Dict[str, InteractiveSession] = {}
        self._session_lock = asyncio.Lock()
        
        # 🆕 ЕДИНЫЙ ИСТОЧНИК ИСТИНЫ ДЛЯ completed_sessions
        self.completed_sessions: Dict[str, float] = {}  # session_id -> timestamp
        self.completed_sessions_lock = asyncio.Lock()
        
        logger.info(f"🎯 CardService получил ai_service: {ai_service is not None}")
        
        # 🔧 ПРОВЕРКА СОВМЕСТИМОСТИ API ПРИ ИНИЦИАЛИЗАЦИИ
        self._verify_api_compatibility()

    def __getattr__(self, name):
        """
        Safety alias: если метод неожиданно отсутствует, даём диагностическое сообщение.
        """
        # Список ключевых методов, которые ожидают обработчики
        expected_methods = {
            'send_card_selection_interface': 'send_card_selection_interface',
            'start_interactive_spread': 'start_interactive_spread', 
            'complete_interactive_spread': 'complete_interactive_spread',
            'process_card_selection': 'process_card_selection'
        }
        
        if name in expected_methods:
            # Детальная диагностика
            available_methods = [m for m in dir(self) if not m.startswith('_')]
            logger.error(f"🚨 КРИТИЧЕСКАЯ ОШИБКА: Метод {name} отсутствует в CardService!")
            logger.error(f"🔍 Ожидаемые методы: {list(expected_methods.keys())}")
            logger.error(f"🔍 Доступные методы: {available_methods}")
            logger.error(f"🔍 Тип card_service: {type(self)}")
            logger.error(f"🔍 ai_service доступен: {hasattr(self, 'ai_service') and self.ai_service is not None}")
            
            raise AttributeError(
                f"Метод {name} отсутствует в CardService. "
                f"Проверьте импорт/инициализацию сервиса (тип: {type(self)}). "
                f"Доступные методы: {available_methods}"
            )
        
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    def _verify_api_compatibility(self):
        """Проверяет, что все ожидаемые методы доступны"""
        expected_methods = [
            'send_card_selection_interface',
            'start_interactive_spread', 
            'complete_interactive_spread',
            'process_card_selection'
        ]
        
        for method in expected_methods:
            if not hasattr(self, method):
                logger.error(f"🚨 КРИТИЧЕСКАЯ ОШИБКА СОВМЕСТИМОСТИ: Метод {method} отсутствует!")
                return False
        
        logger.info("✅ Проверка совместимости API CardService пройдена")
        return True

    # ==================== API ДЛЯ completed_sessions ====================

    async def add_completed_session(self, session_id: str):
        """🆕 ДОБАВЛЕНИЕ СЕССИИ В ЗАВЕРШЕННЫЕ"""
        async with self.completed_sessions_lock:
            self.completed_sessions[session_id] = time.time()
            logger.debug(f"✅ Сессия {session_id} добавлена в completed_sessions")

    async def is_session_completed(self, session_id: str) -> bool:
        """🆕 ПРОВЕРКА ЗАВЕРШЕННОСТИ СЕССИИ"""
        async with self.completed_sessions_lock:
            if session_id in self.completed_sessions:
                completion_time = self.completed_sessions[session_id]
                current_time = time.time()
                if current_time - completion_time < 3600:  # 1 час в секундах
                    return True
                else:
                    # Удаляем устаревшую сессию
                    del self.completed_sessions[session_id]
                    logger.debug(f"🧹 Удалена устаревшая completed_session: {session_id}")
            return False

    async def cleanup_old_completed_sessions(self, ttl_seconds: int = 3600):
        """🆕 ОЧИСТКА УСТАРЕВШИХ СЕССИЙ"""
        async with self.completed_sessions_lock:
            now = time.time()
            to_remove = []
            for session_id, timestamp in self.completed_sessions.items():
                if now - timestamp > ttl_seconds:
                    to_remove.append(session_id)
            
            for session_id in to_remove:
                del self.completed_sessions[session_id]
            
            if to_remove:
                logger.debug(f"🧹 Очищено {len(to_remove)} устаревших completed_sessions")

    # ==================== УНИФИЦИРОВАННЫЕ МЕТОДЫ РЕДАКТИРОВАНИЯ/ОТПРАВКИ ====================

    async def _safe_edit_or_send_message(self, bot, chat_id: int, message_id: Optional[int], 
                                       text: str, reply_markup=None, parse_mode='HTML') -> Tuple[str, Optional[int]]:
        """
        🆕 УЛУЧШЕННАЯ БЕЗОПАСНАЯ ОТПРАВКА/РЕДАКТИРОВАНИЕ СООБЩЕНИЯ
        Возвращает: (статус, message_id)
        """
        try:
            if message_id:
                # Пытаемся отредактировать существующее сообщение
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
                logger.debug(f"✅ Сообщение {message_id} отредактировано")
                return ('edited', message_id)
            else:
                # Отправляем новое сообщение
                sent_message = await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
                new_message_id = sent_message.message_id
                logger.debug(f"📤 Новое сообщение отправлено: {new_message_id}")
                return ('sent', new_message_id)
                
        except BadRequest as e:
            error_msg = str(e)
            if "Message is not modified" in error_msg:
                logger.debug(f"⚠️ Сообщение {message_id} не требует изменений")
                return ('not_modified', message_id)
            elif "Message to edit not found" in error_msg or "Message can't be edited" in error_msg:
                logger.warning(f"⚠️ Не удалось отредактировать сообщение {message_id}: {e}")
                # Отправляем новое сообщение
                sent_message = await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
                new_message_id = sent_message.message_id
                logger.debug(f"📤 Новое сообщение отправлено вместо редактирования: {new_message_id}")
                return ('sent_new', new_message_id)
            else:
                logger.error(f"❌ Ошибка редактирования сообщения {message_id}: {e}")
                # Пробуем отправить новое сообщение как fallback
                try:
                    sent_message = await bot.send_message(
                        chat_id=chat_id,
                        text=text,
                        reply_markup=reply_markup,
                        parse_mode=parse_mode
                    )
                    new_message_id = sent_message.message_id
                    return ('sent_fallback', new_message_id)
                except Exception as send_error:
                    logger.error(f"💥 Критическая ошибка отправки сообщения: {send_error}")
                    return ('error', None)
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка при работе с сообщением {message_id}: {e}")
            # Fallback: отправляем новое сообщение
            try:
                sent_message = await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
                new_message_id = sent_message.message_id
                return ('sent_fallback', new_message_id)
            except Exception as send_error:
                logger.error(f"💥 Критическая ошибка отправки сообщения: {send_error}")
                return ('error', None)

    async def _safe_delete_message(self, bot, chat_id: int, message_id: Optional[int]) -> bool:
        """
        🆕 БЕЗОПАСНОЕ УДАЛЕНИЕ СООБЩЕНИЯ
        """
        if not message_id:
            return False
            
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
            logger.debug(f"✅ Сообщение {message_id} удалено")
            return True
        except BadRequest as e:
            if "Message to delete not found" in str(e):
                logger.debug(f"⚠️ Сообщение {message_id} уже удалено")
                return True
            else:
                logger.warning(f"⚠️ Не удалось удалить сообщение {message_id}: {e}")
                return False
        except Exception as e:
            logger.error(f"❌ Ошибка удаления сообщения {message_id}: {e}")
            return False

    # ==================== МЕТОДЫ ИНТЕРАКТИВНЫХ РАСКЛАДОВ ====================

    async def start_interactive_spread(self, user_id: int, spread_type: str, category: str, 
                                     chat_id: int = None, context=None, bot=None) -> str:
        """Создает новую сессию интерактивного выбора карт"""
        try:
            async with self._session_lock:
                # Нормализация spread_type
                if spread_type in ('three_card', 'three_cards', 'three'):
                    normalized_spread_type = 'three'
                elif spread_type in ('single', 'one_card', 'one'):
                    normalized_spread_type = 'single'
                else:
                    normalized_spread_type = spread_type
                
                logger.debug(f"🔄 Нормализация spread_type: '{spread_type}' -> '{normalized_spread_type}'")
                
                # 🆕 ОЧИСТКА УСТАРЕВШИХ completed_sessions ПЕРЕД НОВЫМ РАСКЛАДОМ
                await self.cleanup_old_completed_sessions()
                
                # Очищаем устаревшие сессии этого пользователя
                await self._cleanup_user_sessions(user_id)
                
                session_id = str(uuid.uuid4())[:8]
                
                # Определяем bot объект
                effective_bot = bot
                if effective_bot is None and context is not None and hasattr(context, 'bot'):
                    effective_bot = context.bot
                
                # 🔧 ГАРАНТИРУЕМ правильную инициализацию сессии
                session = InteractiveSession(
                    session_id=session_id,
                    user_id=user_id,
                    spread_type=normalized_spread_type,
                    category=category,
                    selected_cards={},
                    current_position=1,
                    created_at=datetime.now(),
                    chat_id=chat_id,
                    context=context,
                    bot=effective_bot
                )
                
                # 🔧 ЯВНО УСТАНАВЛИВАЕМ флаги - ai_executed ТОЛЬКО false при старте
                session.ai_executed = False
                session.status = 'pending'
                session.saved_spread_id = None
                # 🆕 ИНИЦИАЛИЗИРУЕМ ID сообщений
                session.interface_message_id = None
                session.result_message_id = None
                session.ai_generating_message_id = None
                
                self.active_sessions[session_id] = session
                
                logger.info(f"🆕 Создана сессия {session_id} для пользователя {user_id}, "
                          f"тип: {normalized_spread_type}, категория: {category}, статус: {session.status}")
                
                return session_id
                
        except Exception as e:
            logger.error(f"❌ Ошибка создания сессии для пользователя {user_id}: {e}")
            raise

    async def process_card_selection(self, session_id: str, position: int, selected_number: int,
                                   user_id: int = None, chat_id: int = None, 
                                   context: Any = None, bot: Any = None) -> Dict[str, Any]:
        """
        Обрабатывает выбор номера карты пользователем
        🔧 ИСПРАВЛЕНИЕ: НЕ добавляем в completed_sessions до полного завершения расклада
        """
        try:
            async with self._session_lock:
                if session_id not in self.active_sessions:
                    return {
                        'success': False,
                        'status': 'error',
                        'message': 'Сессия не найдена',
                        'completed': False,
                        'session': None,
                        'session_id': session_id,
                        'spread_type': None
                    }
                
                session = self.active_sessions[session_id]
                
                # 🔧 ГАРАНТИРУЕМ наличие атрибутов
                self._ensure_session_attributes(session)
                
                # 🆕 ПРОВЕРКА ЗАВЕРШЕННЫХ СЕССИЙ ЧЕРЕЗ API
                if await self.is_session_completed(session_id):
                    logger.warning(f"⚠️ Попытка обработки карты для завершенной сессии {session_id}")
                    return {
                        'success': False,
                        'status': 'already_completed',
                        'message': 'Расклад уже завершен',
                        'completed': True,
                        'session': session,
                        'session_id': session_id,
                        'spread_type': session.spread_type
                    }
                
                # 🔧 ПРОВЕРКА СТАТУСА СЕССИИ
                if session.status == 'completed':
                    logger.warning(f"⚠️ Попытка обработки карты для завершенной сессии {session_id}")
                    return {
                        'success': False,
                        'status': 'already_completed', 
                        'message': 'Расклад уже завершен',
                        'completed': True,
                        'session': session,
                        'session_id': session_id,
                        'spread_type': session.spread_type
                    }
            
                # Обновляем параметры сессии если нужно
                if session.chat_id is None and chat_id is not None:
                    session.chat_id = chat_id
                if session.context is None and context is not None:
                    session.context = context
                if session.bot is None and bot is not None:
                    session.bot = bot
            
                # Проверяем соответствие позиции
                if position != session.current_position:
                    return {
                        'success': False,
                        'status': 'error',
                        'message': f'Неверная позиция. Ожидалась позиция {session.current_position}',
                        'completed': False,
                        'session': session,
                        'current_position': session.current_position,
                        'session_id': session_id,
                        'spread_type': session.spread_type
                    }
            
                # Генерируем карту
                card = await self._draw_single_card_with_engine(session.category)
                if not card:
                    return {
                        'success': False,
                        'status': 'error',
                        'message': 'Не удалось сгенерировать карту',
                        'completed': False,
                        'session': session,
                        'session_id': session_id,
                        'spread_type': session.spread_type
                    }
            
                # Сохраняем карту в сессию
                session.selected_cards[position] = card
                logger.debug(f"✅ Карта выбрана для сессии {session_id}, позиция {position}: {card.get('name', 'Unknown')}")
            
                # Подсчет выбранных карт
                valid_selected_cards = {k: v for k, v in session.selected_cards.items() if v is not None}
                selected_count = len(valid_selected_cards)
            
                # Определяем статус завершения
                if session.spread_type == 'single':
                    result_status = 'completed'
                    progress = f"{selected_count}/1"
                    completed = True
                    next_position = None
                else:  # 'three'
                    if selected_count >= 3:
                        result_status = 'completed'
                        progress = f"{selected_count}/3"
                        completed = True
                        next_position = None
                    else:
                        result_status = 'in_progress'
                        progress = f"{selected_count}/3"
                        completed = False
                        next_position = position + 1
            
                # 🔧 ОБНОВЛЯЕМ СТАТУС СЕССИИ - НЕ добавляем в completed_sessions здесь!
                if session.status == 'pending' and not completed:
                    session.status = 'in_progress'
                    logger.info(f"🔄 Сессия {session_id} перешла в статус: in_progress")
                elif completed:
                    session.status = 'completed'
                    logger.info(f"🔄 Сессия {session_id} перешла в статус: completed")
                    # 🔧 ИСПРАВЛЕНИЕ: НЕ добавляем в completed_sessions до полного завершения расклада
                    # completed_sessions будет добавлен только в complete_interactive_spread
            
                # Стандартизированный результат
                result = {
                    'success': True,
                    'session': session,
                    'session_id': session_id,
                    'spread_type': session.spread_type,
                    'message': f'Карта "{card["name"]}" успешно выбрана для позиции {position}',
                    'card': card,
                    'current_position': position,
                    'status': result_status,
                    'completed': completed,
                    'next_position': next_position,
                    'progress': progress,
                    'selected_count': selected_count,
                    'total_required': 1 if session.spread_type == 'single' else 3
                }
            
                # Обновляем позицию если не завершено
                if not completed:
                    session.current_position = next_position
            
                logger.debug(f"📊 Статус сессии {session_id}: {result_status}, прогресс: {progress}")
            
                return result
                    
        except Exception as e:
            logger.error(f"❌ Ошибка обработки выбора карты для сессии {session_id}: {e}")
            return {
                'success': False,
                'status': 'error',
                'message': f'Внутренняя ошибка: {str(e)}',
                'completed': False,
                'session': None,
                'session_id': session_id,
                'spread_type': None
            }

    async def send_card_selection_interface(self, update, context, session_id: str, position: int = 1):
        """
        🔧 УЛУЧШЕННАЯ ВЕРСИЯ: Отправляет интерфейс выбора карты с сохранением message_id
        """
        try:
            # 🆕 ПРОВЕРКА СЕССИИ ЧЕРЕЗ API
            if await self.is_session_completed(session_id):
                logger.warning(f"⚠️ Попытка отправки интерфейса для завершенной сессии {session_id}")
                if getattr(update, "callback_query", None):
                    await update.callback_query.edit_message_text("Этот расклад уже завершен. Начни новый расклад.")
                else:
                    chat_id = update.effective_chat.id if update and getattr(update, "effective_chat", None) else None
                    if chat_id and context and hasattr(context, 'bot'):
                        await context.bot.send_message(
                            chat_id=chat_id, 
                            text="Этот расклад уже завершен. Начни новый расклад."
                        )
                return

            # Получаем сессию
            session = await self.get_session(session_id)
            if not session:
                await self._send_session_not_found(update, context)
                return

            # 🔧 ГАРАНТИРУЕМ наличие атрибутов
            self._ensure_session_attributes(session)

            # Определяем позицию
            effective_position = position if position is not None else session.current_position
            if effective_position is None:
                effective_position = 1

            # Текст сообщения
            if session.spread_type == 'single':
                message_text = "🎴 Выбери карту интуитивно:\n[1️⃣]-[5️⃣] - твой выбор определит карту"
                total_positions = 1
            else:
                position_names = {1: "прошлого", 2: "настоящего", 3: "будущего"}
                message_text = f"🎴 Выбери карту {effective_position}/3:\n[1️⃣]-[5️⃣] - карта {position_names.get(effective_position, str(effective_position))}"
                total_positions = 3

            # Создаем клавиатуру
            keyboard = await self._create_selection_keyboard(session_id, effective_position, total_positions)

            # 🆕 ОТПРАВЛЯЕМ/РЕДАКТИРУЕМ СООБЩЕНИЕ С СОХРАНЕНИЕМ message_id
            await self._send_interface_message_with_save(update, context, session, message_text, keyboard, effective_position)

        except Exception as e:
            logger.error(f"❌ Критическая ошибка отправки интерфейса для сессии {session_id}: {e}")
            await self._send_interface_error(update, context)

    async def _send_interface_message_with_save(self, update, context, session, message_text, keyboard, position):
        """
        🆕 УНИФИЦИРОВАННАЯ ОТПРАВКА ИНТЕРФЕЙСА С СОХРАНЕНИЕМ message_id
        """
        try:
            effective_bot = context.bot if context and hasattr(context, 'bot') else session.bot
            chat_id = session.chat_id
            
            if not chat_id:
                # Пытаемся получить chat_id из update
                if update and getattr(update, "effective_chat", None):
                    chat_id = update.effective_chat.id
                else:
                    logger.error(f"❌ Не удалось определить chat_id для сессии {session.session_id}")
                    return

            # 🆕 ИСПОЛЬЗУЕМ БЕЗОПАСНОЕ РЕДАКТИРОВАНИЕ/ОТПРАВКУ
            current_message_id = session.interface_message_id
            
            if getattr(update, "callback_query", None):
                # Для callback_query пробуем отредактировать существующее сообщение
                try:
                    await update.callback_query.edit_message_text(
                        text=message_text,
                        reply_markup=keyboard
                    )
                    # Сохраняем ID сообщения из callback_query
                    new_message_id = update.callback_query.message.message_id
                    session.interface_message_id = new_message_id
                    logger.debug(f"✅ Интерфейс отредактирован через callback: {new_message_id}")
                except BadRequest as e:
                    if "Message is not modified" in str(e):
                        logger.debug(f"⚠️ Сообщение интерфейса не требует изменений")
                        # message_id остается прежним
                    else:
                        logger.warning(f"⚠️ Не удалось отредактировать через callback: {e}")
                        # Отправляем новое сообщение
                        sent_message = await effective_bot.send_message(
                            chat_id=chat_id,
                            text=message_text,
                            reply_markup=keyboard
                        )
                        session.interface_message_id = sent_message.message_id
                        logger.debug(f"📤 Новый интерфейс отправлен: {sent_message.message_id}")
            else:
                # Для обычного сообщения используем безопасный метод
                status, new_message_id = await self._safe_edit_or_send_message(
                    bot=effective_bot,
                    chat_id=chat_id,
                    message_id=current_message_id,
                    text=message_text,
                    reply_markup=keyboard
                )
                
                if new_message_id and new_message_id != current_message_id:
                    session.interface_message_id = new_message_id
                    logger.debug(f"💾 Сохранен interface_message_id: {new_message_id} для сессии {session.session_id}")

            logger.debug(f"📤 Интерфейс выбора карт отправлен, позиция {position}")

        except Exception as e:
            logger.error(f"❌ Ошибка отправки интерфейса для сессии {session.session_id}: {e}")
            # Fallback: пробуем отправить простое сообщение
            try:
                chat_id = session.chat_id or (update.effective_chat.id if update and getattr(update, "effective_chat", None) else None)
                if chat_id and effective_bot:
                    sent_message = await effective_bot.send_message(
                        chat_id=chat_id,
                        text=message_text,
                        reply_markup=keyboard
                    )
                    session.interface_message_id = sent_message.message_id
                    logger.debug(f"📤 Fallback интерфейс отправлен: {sent_message.message_id}")
            except Exception as fallback_error:
                logger.error(f"💥 Критическая ошибка fallback отправки: {fallback_error}")

    async def complete_interactive_spread(self, session_id: str, bot=None, chat_id: int = None, context=None) -> Dict[str, Any]:
        """
        🔧 УЛУЧШЕННАЯ ВЕРСИЯ: Завершает расклад с гарантированной идемпотентностью и сохранением message_id
        """
        try:
            async with self._session_lock:
                if session_id not in self.active_sessions:
                    logger.warning(f"⚠️ Попытка завершения несуществующей сессии: {session_id}")
                    return {
                        'status': 'error',
                        'message': 'Сессия не найдена'
                    }
            
                session = self.active_sessions[session_id]
                
                # 🔧 ГАРАНТИРУЕМ наличие атрибутов
                self._ensure_session_attributes(session)
                
                # 🔧 СТРОГАЯ ПРОВЕРКА ИДЕМПОТЕНТНОСТИ
                if session.status == "completed" and session.ai_executed:
                    logger.warning(f"⚠️ Попытка повторного завершения сессии {session_id} с выполненным AI")
                    return {
                        'status': 'already_completed',
                        'message': 'Расклад уже завершен и AI-интерпретация выполнена',
                        'spread_id': session.saved_spread_id
                    }
                
                # 🆕 ПРОВЕРКА ЧЕРЕЗ API
                if await self.is_session_completed(session_id):
                    logger.warning(f"⚠️ Сессия {session_id} уже завершена (проверка через completed_sessions)")
                    return {
                        'status': 'already_completed',
                        'message': 'Расклад уже завершен',
                        'spread_id': session.saved_spread_id
                    }
            
                # Собираем карты
                valid_cards = {k: v for k, v in session.selected_cards.items() if v is not None}
                cards = [valid_cards[i] for i in sorted(valid_cards.keys())]
            
                if not cards:
                    logger.error(f"❌ Нет валидных карт в сессии {session_id}")
                    return {
                        'status': 'error',
                        'message': 'Нет выбранных карт для завершения расклада'
                    }
            
                # Определяем bot и chat_id
                target_bot, target_chat_id = await self._resolve_bot_and_chat_id(session, bot, chat_id, context)
                if not target_bot or not target_chat_id:
                    return {
                        'status': 'error',
                        'message': 'Не удалось определить бота или chat_id для отправки сообщений'
                    }
            
                # Сохраняем расклад в БД
                spread_id = self.user_db.add_spread_to_history(
                    user_id=session.user_id,
                    username=f"user_{session.user_id}",
                    spread_type=session.spread_type,
                    category=session.category,
                    cards=cards,
                    interpretation=None
                )
                session.saved_spread_id = spread_id
            
                logger.info(f"💾 Расклад сохранен в БД: spread_id={spread_id}")
            
                # Отправляем заголовок и карты
                spread_title = self._generate_spread_title(session.spread_type, session.category)
                await target_bot.send_message(chat_id=target_chat_id, text=spread_title, parse_mode='HTML')
            
                try:
                    await self._send_card_images_with_chat_id(
                        spread_cards=cards,
                        spread_type=session.spread_type, 
                        bot=target_bot,
                        chat_id=target_chat_id
                    )
                except Exception as e:
                    logger.error(f"❌ Ошибка отправки картинок: {e}")
                    await self._send_fallback_card_description_with_chat_id(
                        bot=target_bot,
                        chat_id=target_chat_id,
                        spread_cards=cards,
                        spread_type=session.spread_type
                    )
            
                # 🔧 УЛУЧШЕННАЯ ЛОГИКА AI С ГАРАНТИЕЙ ИДЕМПОТЕНТНОСТИ
                interpretation = None
                if self.ai_service and not session.ai_executed:
                    interpretation = await self._execute_ai_interpretation_safely(
                        session, cards, spread_id, target_bot, target_chat_id
                    )
                else:
                    logger.debug(f"⚠️ AI-сервис пропущен: ai_service={self.ai_service is not None}, ai_executed={session.ai_executed}")
            
                # 🆕 ЭКРАНИРОВАНИЕ HTML ПРИ ОТПРАВКЕ AI-ИНТЕРПРЕТАЦИИ
                if interpretation:
                    safe_interpretation = html.escape(interpretation)
                    interpretation_text = (
                        "💫 <b>Интерпретация:</b>\n\n"
                        f"<pre>{safe_interpretation}</pre>\n\n"
                        "✨ <i>Интерпретация создана с помощью AI</i>"
                    )
                    await target_bot.send_message(
                        chat_id=target_chat_id,
                        text=interpretation_text,
                        parse_mode='HTML'
                    )
                else:
                    no_ai_text = (
                        "❌ <b>AI-интерпретация временно недоступна</b>\n\n"
                        "🤖 В данный момент сервис AI-интерпретации не работает.\n"
                        "🔮 Вы можете посмотреть значение карт в классических источниках.\n\n"
                        "🔄 Попробуйте сделать расклад позже."
                    )
                    await target_bot.send_message(
                        chat_id=target_chat_id,
                        text=no_ai_text,
                        parse_mode='HTML'
                    )
            
                # 🆕 ОТПРАВЛЯЕМ ФИНАЛЬНОЕ СООБЩЕНИЕ С СОХРАНЕНИЕМ message_id
                final_text = "✅ <b>Расклад завершен!</b>\n\n🔮 Расклад сохранен в вашей истории."
                keyboard = await self._create_interpretation_keyboard(spread_id)
                
                # Используем безопасную отправку/редактирование
                status, result_message_id = await self._safe_edit_or_send_message(
                    bot=target_bot,
                    chat_id=target_chat_id,
                    message_id=session.interface_message_id,  # Пытаемся отредактировать интерфейс
                    text=final_text,
                    reply_markup=keyboard,
                    parse_mode='HTML'
                )
                
                # Сохраняем ID финального сообщения
                if result_message_id:
                    session.result_message_id = result_message_id
                    logger.debug(f"💾 Сохранен result_message_id: {result_message_id} для сессии {session.session_id}")
            
                # 🔧 ФИНАЛИЗИРУЕМ СЕССИЮ - ТОЛЬКО ЗДЕСЬ добавляем в completed_sessions
                session.status = 'completed'
                
                # 🆕 ДОБАВЛЯЕМ В completed_sessions ЧЕРЕЗ API
                await self.add_completed_session(session_id)
                
                # Удаляем сессию из активных
                del self.active_sessions[session_id]
                
                # 🔧 ФИНАЛЬНОЕ СУММАРИ ЛОГИРОВАНИЕ
                logger.info(f"✅ Интерактивный расклад завершен {session_id}, saved_as={spread_id}, ai_executed={session.ai_executed}")
                logger.debug("Full session state: %s", {k: v for k, v in session.__dict__.items() if k != 'context'})
            
                return {
                    'status': 'success',
                    'spread_id': spread_id,
                    'message': 'Расклад успешно завершен',
                    'cards': cards,
                    'interpretation': interpretation,
                    'spread_type': session.spread_type,
                    'category': session.category,
                    'session_id': session_id
                }
            
        except Exception as e:
            logger.error(f"💥 Критическая ошибка в complete_interactive_spread для сессии {session_id}: {e}")
            return {
                'status': 'error',
                'message': str(e)
            }

    # ==================== ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ====================

    def _ensure_session_attributes(self, session: InteractiveSession):
        """Гарантирует наличие обязательных атрибутов сессии"""
        if not hasattr(session, 'ai_executed'):
            session.ai_executed = False
        if not hasattr(session, 'saved_spread_id'):
            session.saved_spread_id = None
        if not hasattr(session, 'status'):
            session.status = 'pending'
        # 🆕 ГАРАНТИРУЕМ НАЛИЧИЕ АТРИБУТОВ СООБЩЕНИЙ
        if not hasattr(session, 'interface_message_id'):
            session.interface_message_id = None
        if not hasattr(session, 'result_message_id'):
            session.result_message_id = None
        if not hasattr(session, 'ai_generating_message_id'):
            session.ai_generating_message_id = None

    async def _execute_ai_interpretation_safely(self, session: InteractiveSession, cards: list, 
                                              spread_id: str, target_bot, target_chat_id: int) -> Optional[str]:
        """
        🔧 БЕЗОПАСНОЕ ВЫПОЛНЕНИЕ AI: Гарантирует идемпотентность и правильную установку флагов
        """
        try:
            # 🔧 УСТАНАВЛИВАЕМ ФЛАГ ПЕРЕД ВЫЗОВОМ AI для блокировки повторных вызовов
            session.ai_executed = True
            logger.debug(f"🔒 Флаг ai_executed установлен для сессии {session.session_id} перед вызовом AI")

            # 🆕 СОХРАНЯЕМ ID СООБЩЕНИЯ О ГЕНЕРАЦИИ
            generating_msg = await target_bot.send_message(
                chat_id=target_chat_id, 
                text="🔄 Генерирую AI-интерпретацию...",
                parse_mode='HTML'
            )
            session.ai_generating_message_id = generating_msg.message_id
            logger.debug(f"💾 Сохранен ai_generating_message_id: {generating_msg.message_id}")

            # Нормализуем тип расклада для AI
            spread_type_mapping = {'single': 'one_card', 'three': 'three_cards'}
            ai_spread_type = spread_type_mapping.get(session.spread_type, session.spread_type)

            logger.debug(f"🎯 Вызов AI-сервиса для расклада {spread_id}")

            interpretation = await self.ai_service.generate_ai_interpretation(
                spread_cards=cards,
                spread_type=ai_spread_type,
                category=session.category,
                user_id=session.user_id,
                chat_id=target_chat_id,
                bot=target_bot,
                spread_id=spread_id
            )

            # 🆕 БЕЗОПАСНОЕ УДАЛЕНИЕ УВЕДОМЛЕНИЯ О ГЕНЕРАЦИИ
            await self._safe_delete_message(target_bot, target_chat_id, session.ai_generating_message_id)
            session.ai_generating_message_id = None

            if interpretation:
                logger.debug(f"✅ AI-интерпретация успешно сгенерирована для расклада {spread_id}")
                await self.user_db.update_spread_interpretation(spread_id, interpretation)
                # 🔧 ai_executed остается True - успешное выполнение
                return interpretation
            else:
                logger.warning(f"⚠️ AI-сервис вернул пустую интерпретацию для расклада {spread_id}")
                # 🔧 СБРАСЫВАЕМ ФЛАГ ПРИ НЕУДАЧЕ - можно попробовать снова
                session.ai_executed = False
                logger.debug(f"🔄 Флаг ai_executed сброшен для сессии {session.session_id} из-за пустой интерпретации")
                return None

        except Exception as e:
            logger.exception(f"❌ Ошибка генерации AI-интерпретации для расклада {spread_id}")
            # 🆕 БЕЗОПАСНОЕ УДАЛЕНИЕ УВЕДОМЛЕНИЯ ПРИ ОШИБКЕ
            await self._safe_delete_message(target_bot, target_chat_id, session.ai_generating_message_id)
            session.ai_generating_message_id = None
            
            # 🔧 СБРАСЫВАЕМ ФЛАГ ПРИ ОШИБКЕ - можно попробовать снова
            session.ai_executed = False
            logger.debug(f"🔄 Флаг ai_executed сброшен для сессии {session.session_id} из-за ошибки AI")
            return None

    async def get_session(self, session_id: str) -> Optional[InteractiveSession]:
        """
        🔧 УЛУЧШЕННАЯ ВЕРСИЯ: Потокобезопасное получение сессии с гарантией атрибутов
        """
        async with self._session_lock:
            session = self.active_sessions.get(session_id)
            if session:
                self._ensure_session_attributes(session)
            return session

    async def _create_selection_keyboard(self, session_id: str, position: int, total_positions: int):
        """Создает клавиатуру для выбора карты"""
        try:
            from ..keyboards import get_card_selection_keyboard
            return get_card_selection_keyboard(session_id, position, total_positions)
        except Exception as e:
            logger.error(f"❌ Ошибка создания клавиатуры: {e}")
            from telegram import InlineKeyboardMarkup, InlineKeyboardButton
            return InlineKeyboardMarkup([[
                InlineKeyboardButton("1️⃣", callback_data=f"card_choice:{session_id}:{position}:1"),
                InlineKeyboardButton("2️⃣", callback_data=f"card_choice:{session_id}:{position}:2"),
                InlineKeyboardButton("3️⃣", callback_data=f"card_choice:{session_id}:{position}:3"),
                InlineKeyboardButton("4️⃣", callback_data=f"card_choice:{session_id}:{position}:4"),
                InlineKeyboardButton("5️⃣", callback_data=f"card_choice:{session_id}:{position}:5")
            ]])

    async def _create_interpretation_keyboard(self, spread_id: str):
        """Создает клавиатуру для интерпретации"""
        try:
            from ..keyboards import get_interpretation_keyboard
            return get_interpretation_keyboard(spread_id)
        except Exception as e:
            logger.error(f"❌ Ошибка создания клавиатуры интерпретации: {e}")
            from telegram import InlineKeyboardMarkup, InlineKeyboardButton
            return InlineKeyboardMarkup([
                [InlineKeyboardButton("💭 Задать вопрос", callback_data=f"ask_question_{spread_id}")],
                [InlineKeyboardButton("📊 Детали расклада", callback_data=f"details_{spread_id}")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
            ])

    async def _resolve_bot_and_chat_id(self, session, bot, chat_id, context):
        """Определяет bot и chat_id для отправки сообщений"""
        target_bot = bot or session.bot
        if target_bot is None and context is not None and hasattr(context, 'bot'):
            target_bot = context.bot
        
        target_chat_id = chat_id or session.chat_id
        
        if not target_bot or not target_chat_id:
            logger.error(f"❌ Не удалось определить бота или chat_id: bot={target_bot is not None}, chat_id={target_chat_id}")
        
        return target_bot, target_chat_id

    async def _send_session_not_found(self, update, context):
        """Отправляет сообщение о не найденной сессии"""
        if getattr(update, "callback_query", None):
            await update.callback_query.edit_message_text("Сессия устарела. Начни расклад заново.")
        else:
            chat_id = update.effective_chat.id if update and getattr(update, "effective_chat", None) else None
            if chat_id and context and hasattr(context, 'bot'):
                await context.bot.send_message(chat_id=chat_id, text="Сессия устарела. Начни расклад заново.")

    async def _send_interface_error(self, update, context):
        """Отправляет сообщение об ошибке интерфейса"""
        if getattr(update, "callback_query", None):
            await update.callback_query.edit_message_text("Ошибка при создании интерфейса выбора. Попробуйте еще раз.")
        else:
            chat_id = update.effective_chat.id if update and getattr(update, "effective_chat", None) else None
            if chat_id and context and hasattr(context, 'bot'):
                await context.bot.send_message(chat_id=chat_id, text="Ошибка при создании интерфейса выбора. Попробуйте еще раз.")

    # ==================== СУЩЕСТВУЮЩИЕ МЕТОДЫ ====================

    async def _draw_single_card_with_engine(self, category: str) -> dict:
        """Генерирует одну случайную карту используя self.tarot_engine"""
        try:
            if self.tarot_engine is None:
                logger.error("❌ Tarot engine не инициализирован")
                return None
            
            # Используем self.tarot_engine для генерации одной карты
            cards, _ = self.tarot_engine.generate_spread('one_card', category)
            if cards and len(cards) > 0:
                logger.debug(f"✅ Сгенерирована карта: {cards[0].get('name', 'Unknown')}")
                return cards[0]
            
            logger.error("❌ Не удалось сгенерировать карту через tarot_engine")
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка генерации карты для категории {category} через tarot_engine: {e}")
            # Fallback: возвращаем mock-карту только в случае ошибки
            return {
                'name': 'Шут',
                'image_url': 'assets/cards/fool.jpg',
                'position': 'upright',
                'keywords': {'upright': ['невинность', 'новое начало', 'свобода']},
                'description': 'Карта новых начинаний и невинности'
            }

    async def _cleanup_user_sessions(self, user_id: int):
        """Очищает все сессии пользователя (предотвращает дублирование)"""
        try:
            sessions_to_remove = []
            for session_id, session in self.active_sessions.items():
                if session.user_id == user_id:
                    sessions_to_remove.append(session_id)
            
            for session_id in sessions_to_remove:
                del self.active_sessions[session_id]
                
            if sessions_to_remove:
                logger.debug(f"🧹 Очищено {len(sessions_to_remove)} предыдущих сессий пользователя {user_id}")
        except Exception as e:
            logger.error(f"❌ Ошибка очистки сессий пользователя {user_id}: {e}")

    async def cleanup_expired_sessions(self):
        """Очищает сессии старше 1 часа"""
        try:
            async with self._session_lock:
                now = datetime.now()
                expired_sessions = []
                
                for session_id, session in self.active_sessions.items():
                    if now - session.created_at > timedelta(hours=1):
                        expired_sessions.append(session_id)
                
                for session_id in expired_sessions:
                    del self.active_sessions[session_id]
                
                if expired_sessions:
                    logger.info(f"🧹 Очищено {len(expired_sessions)} устаревших сессий")
                    
                return len(expired_sessions)
                
        except Exception as e:
            logger.error(f"❌ Ошибка очистки устаревших сессий: {e}")
            return 0

    async def cancel_session(self, session_id: str) -> bool:
        """Отменяет и удаляет сессию"""
        try:
            async with self._session_lock:
                if session_id in self.active_sessions:
                    # 🆕 БЕЗОПАСНОЕ УДАЛЕНИЕ СООБЩЕНИЙ ИНТЕРФЕЙСА
                    session = self.active_sessions[session_id]
                    if session.bot and session.chat_id:
                        await self._safe_delete_message(session.bot, session.chat_id, session.interface_message_id)
                        await self._safe_delete_message(session.bot, session.chat_id, session.ai_generating_message_id)
                    
                    del self.active_sessions[session_id]
                    logger.info(f"❌ Сессия отменена: {session_id}")
                    return True
                return False
        except Exception as e:
            logger.error(f"❌ Ошибка отмены сессии {session_id}: {e}")
            return False

    async def get_session_stats(self) -> dict:
        """Возвращает статистику по активным сессиям"""
        async with self._session_lock:
            now = datetime.now()
            active_count = len(self.active_sessions)
            
            # Статистика по типам раскладов
            spread_types = {}
            for session in self.active_sessions.values():
                # 🔧 ИСПРАВЛЕНИЕ: Гарантируем наличие атрибута ai_executed
                if not hasattr(session, 'ai_executed'):
                    session.ai_executed = False
                
                spread_type = session.spread_type
                spread_types[spread_type] = spread_types.get(spread_type, 0) + 1
            
            return {
                'total_sessions': active_count,
                'spread_types': spread_types,
                'oldest_session': min([s.created_at for s in self.active_sessions.values()]) if self.active_sessions else None
            }

    def _generate_spread_title(self, spread_type: str, category: str) -> str:
        """Генерирует заголовок расклада"""
        type_names = {
            'single': '🔮 Расклад одной карты',
            'three': '🔮 Расклад трёх карт'
        }
        spread_name = type_names.get(spread_type, '🔮 Расклад')
        return f"{spread_name}\n📋 Категория: {category}\n"

    def _process_card_image(self, project_root, card):
        """Обработка изображения карты - переворачивание если нужно"""
        original_path = os.path.join(project_root, card['image_url'])
        position = card.get('position', 'upright')
        
        # Если карта прямая - возвращаем оригинальный путь
        if position == 'upright':
            return original_path
        
        # Если карта перевернутая - создаем перевернутое изображение
        try:
            with Image.open(original_path) as img:
                # Переворачиваем изображение на 180 градусов
                rotated_img = img.rotate(180)
                
                # Создаем временный файл
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
                rotated_img.save(temp_file.name, 'JPEG', quality=95)
                
                logger.debug(f"🔄 Изображение перевернуто: {card['name']}")
                return temp_file.name
                
        except Exception as e:
            logger.error(f"❌ Ошибка переворота изображения {card['name']}: {e}")
            return original_path

    def _generate_card_caption(self, card, spread_type, index=0, positions=None):
        """Генерация подписи для карты"""
        position = card.get('position', 'upright')
        
        if spread_type == "single":
            caption = f"🎴 <b>Карта дня: {card['name']}</b>\n"
            caption += f"📏 Положение: {'🔼 Прямое' if position == 'upright' else '🔽 Перевернутое'}\n"
        else:
            pos_name = positions[index] if positions and index < len(positions) else f"Карта {index+1}"
            caption = f"🎴 <b>{pos_name}: {card['name']}</b>\n"
            caption += f"📏 Положение: {'🔼 Прямое' if position == 'upright' else '🔽 Перевернутоe'}\n"
        
        # Добавляем ключевые слова если они есть
        keywords = card.get('keywords', {}).get(position, [])
        if keywords:
            caption += f"🔑 Ключевые слова: {', '.join(keywords[:5])}"
        
        return caption

    async def _send_card_images_with_chat_id(self, spread_cards, spread_type, bot, chat_id: int):
        """Улучшенная отправка изображений карт с использованием chat_id"""
        try:
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            
            if spread_type == "single":
                media_group = []
                for i, card in enumerate(spread_cards):
                    image_path = self._process_card_image(project_root, card)
                    
                    caption = self._generate_card_caption(card, spread_type, i)
                    
                    if os.path.exists(image_path):
                        with open(image_path, 'rb') as photo_file:
                            media_group.append(InputMediaPhoto(
                                media=photo_file,
                                caption=caption,
                                parse_mode='HTML'
                            ))
                    
                    # Очищаем временные файлы
                    if image_path != os.path.join(project_root, card['image_url']):
                        try:
                            os.unlink(image_path)
                        except:
                            pass
                
                if media_group:
                    await bot.send_media_group(chat_id=chat_id, media=media_group)
                    
            else:  # 'three'
                positions = ["🕰 Прошлое", "⚡ Настоящее", "🔮 Будущее"]
                for i, card in enumerate(spread_cards):
                    image_path = self._process_card_image(project_root, card)
                    
                    caption = self._generate_card_caption(card, spread_type, i, positions)
                    
                    if os.path.exists(image_path):
                        with open(image_path, 'rb') as photo_file:
                            await bot.send_photo(
                                chat_id=chat_id,
                                photo=photo_file,
                                caption=caption,
                                parse_mode='HTML'
                            )
                    
                    # Очищаем временные файлы
                    if image_path != os.path.join(project_root, card['image_url']):
                        try:
                            os.unlink(image_path)
                        except:
                            pass
                    
                    # Небольшая пауза между сообщениями
                    await asyncio.sleep(0.5)
                
        except Exception as e:
            logger.error(f"❌ Ошибка отправки изображений: {e}")
            raise

    async def _send_fallback_card_description_with_chat_id(self, bot, chat_id: int, spread_cards, spread_type):
        """Отправка текстового описания карт при ошибке изображений с использованием chat_id"""
        if spread_type == "single":
            fallback_text = "🎴 <b>Карта дня:</b>\n"
            for card in spread_cards:
                position = card.get('position', 'upright')
                fallback_text += f"\n🃏 <b>{card['name']}</b> ({'🔼 Прямое' if position == 'upright' else '🔽 Перевернутое'})"
        else:  # 'three'
            positions = ["Прошлое", "Настоящее", "Будущее"]
            fallback_text = "🎴 <b>Расклад из 3 карт:</b>\n"
            for i, card in enumerate(spread_cards):
                position = card.get('position', 'upright')
                pos_name = positions[i] if i < len(positions) else f"Карта {i+1}"
                fallback_text += f"\n🃏 <b>{pos_name}: {card['name']}</b> ({'🔼 Прямое' if position == 'upright' else '🔽 Перевернутое'})"
        
        await bot.send_message(
            chat_id=chat_id,
            text=fallback_text,
            parse_mode='HTML'
        )

    def generate_basic_interpretation(self, cards, spread_type):
        """🔧 ИСПРАВЛЕННАЯ базовая интерпретация с нормализованными типами"""
        
        # 🔧 NORMALIZE: Преобразуем для отображения пользователю
        spread_type_mapping = {
            'single': '1 карта',
            'three': '3 карты'
        }
        user_spread_type = spread_type_mapping.get(spread_type, spread_type)
        
        basic_text = f"📊 <b>Ваш расклад:</b> {user_spread_type}\n\n"
        
        # 🔧 NORMALIZE: Используем нормализованные типы
        if spread_type == 'three':
            positions = ["🕰️ Прошлое", "🌅 Настоящее", "🔮 Будущее"]
            
            for i, card in enumerate(cards):
                if i < len(positions):
                    basic_text += f"<b>{positions[i]}:</b> "
                card_name = card.get('name', 'Неизвестная карта')
                position = card.get('position', 'upright')
                orientation = '🔼 Прямая' if position == 'upright' else '🔽 Перевернутая'
                basic_text += f"🃏 {card_name} ({orientation})\n"
                
        else:  # single
            for card in cards:
                card_name = card.get('name', 'Неизвестная карта')
                position = card.get('position', 'upright')
                orientation = '🔼 Прямая' if position == 'upright' else '🔽 Перевернутая'
                basic_text += f"🎴 {card_name} ({orientation})\n"
        
        basic_text += "\n🔮 <i>AI-интерпретация временно недоступна. Попробуйте позже.</i>"
        return basic_text

    async def _send_card_images(self, message, spread_cards, spread_type, bot):
        """Улучшенная отправка изображений карт с переворачиванием и отдельными подписями"""
        
        try:
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            
            # Для одной карты отправляем медиагруппой с подписью
            if spread_type == "one_card":
                media_group = []
                for i, card in enumerate(spread_cards):
                    image_path = self._process_card_image(project_root, card)
                    
                    caption = self._generate_card_caption(card, spread_type, i)
                    
                    if os.path.exists(image_path):
                        with open(image_path, 'rb') as photo_file:
                            # Для одной карты - подпись в медиагруппе
                            media_group.append(InputMediaPhoto(
                                media=photo_file,
                                caption=caption,
                                parse_mode='HTML'
                            ))
                    
                    # Очищаем временные файлы
                    if image_path != os.path.join(project_root, card['image_url']):
                        try:
                            os.unlink(image_path)
                        except:
                            pass
                
                if media_group:
                    await message.reply_media_group(media=media_group)
                    
            else:  # three_card - отправляем каждую карту отдельным сообщением
                positions = ["🕰 Прошлое", "⚡ Настоящее", "🔮 Будущее"]
                for i, card in enumerate(spread_cards):
                    image_path = self._process_card_image(project_root, card)
                    
                    caption = self._generate_card_caption(card, spread_type, i, positions)
                    
                    if os.path.exists(image_path):
                        with open(image_path, 'rb') as photo_file:
                            await bot.send_photo(
                                chat_id=message.chat_id,
                                photo=photo_file,
                                caption=caption,
                                parse_mode='HTML'
                            )
                    
                    # Очищаем временные файлы
                    if image_path != os.path.join(project_root, card['image_url']):
                        try:
                            os.unlink(image_path)
                        except:
                            pass
                    
                    # Небольшая пауза между сообщениями
                    await asyncio.sleep(0.5)
                
        except Exception as e:
            logger.error(f"Ошибка отправки изображений: {e}")
            await self._send_fallback_card_description(message, spread_cards, spread_type, bot)

    async def _send_fallback_card_description(self, message, spread_cards, spread_type, bot):
        """Отправка текстового описания карт при ошибке изображений"""
        if spread_type == "one_card":
            fallback_text = "🎴 <b>Карта дня:</b>\n"
            for card in spread_cards:
                position = card.get('position', 'upright')
                fallback_text += f"\n🃏 <b>{card['name']}</b> ({'🔼 Прямое' if position == 'upright' else '🔽 Перевернутое'})"
        else:  # three_card
            positions = ["Прошлое", "Настоящее", "Будущее"]
            fallback_text = "🎴 <b>Расклад из 3 карт:</b>\n"
            for i, card in enumerate(spread_cards):
                position = card.get('position', 'upright')
                pos_name = positions[i] if i < len(positions) else f"Карта {i+1}"
                fallback_text += f"\n🃏 <b>{pos_name}: {card['name']}</b> ({'🔼 Прямое' if position == 'upright' else '🔽 Перевернутое'})"
        
        await bot.send_message(
            chat_id=message.chat_id,
            text=fallback_text,
            parse_mode='HTML'
        )

    def format_cards_message(self, cards, spread_type, category):
        """Форматирование сообщение с картами"""
        # Преобразуем внутренний тип в пользовательский для отображения
        spread_type_mapping = {
            'one_card': '1 карта',
            'three_card': '3 карты'
        }
        user_spread_type = spread_type_mapping.get(spread_type, spread_type)
        
        if spread_type == "one_card":
            # ИСПРАВЛЕНИЕ: Убираем префикс "Прошлое:" для карты дня
            text = f"🔮 <b>Расклад одной карты</b>\n"
            text += f"📋 Категория: {category}\n\n"
            text += f"<b>Выпавшая карта:</b> {cards[0]['name']}\n"
            if cards[0].get('is_reversed', False):
                text += "🔄 <i>Перевернутая позиция</i>\n"
        else:  # three_card
            text = f"🔮 <b>Расклад трёх карт</b>\n"
            text += f"📋 Категория: {category}\n\n"
            text += "<b>Выпавшие карты:</b>\n"
            positions = ['Прошлое', 'Настоящее', 'Будущее']
            for i, card in enumerate(cards):
                text += f"• <b>{positions[i]}:</b> {card['name']}"
                if card.get('is_reversed', False):
                    text += " 🔄"
                text += "\n"
        
        return text

    def format_interpretation_message(self, interpretation):
        """Форматирование сообщения с интерпретацией"""
        if interpretation:
            # 🆕 ЭКРАНИРОВАНИЕ HTML ДЛЯ БЕЗОПАСНОЙ ОТПРАВКИ
            safe_interpretation = html.escape(interpretation)
            text = "💫 <b>Интерпретация:</b>\n\n"
            text += f"<pre>{safe_interpretation}</pre>\n\n"
            text += "✨ <i>Интерпретация создана с помощью AI</i>"
        else:
            text = "❌ <b>Не удалось сгенерировать интерпретацию</b>\n\n"
            text += "Попробуйте сделать расклад еще раз"
        
        return text

    async def generate_spread(self, user_id, username, spread_type, category):
        """
        Генерация обычного расклада с сохранением в БД
        Сохраняет обратную совместимость с существующей системой
        """
        try:
            logger.info(f"Generating spread: user_id={user_id}, username={username}, type={spread_type}, category={category}")
            
            # Используем tarot_engine.generate_spread с правильными внутренними типами
            spread_cards_data, spread_text = self.tarot_engine.generate_spread(spread_type, category)
            
            # Логируем выпавшие карты и проверяем пути изображений
            card_names = [card['name'] for card in spread_cards_data]
            logger.debug(f"Cards drawn for user {user_id}: {card_names}")
            
            # Проверяем пути изображений для каждой карты
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            for card in spread_cards_data:
                image_path = os.path.join(project_root, card['image_url'])
                if os.path.exists(image_path):
                    logger.debug(f"✅ Изображение найдено: {card['name']} -> {image_path}")
                else:
                    logger.warning(f"❌ Изображение не найдено: {card['name']} -> {image_path}")
            
            # Детальное логирование данных карт перед сохранением
            logger.debug(f"📦 Данные карт для сохранения в БД:")
            for i, card in enumerate(spread_cards_data):
                logger.debug(f"  🎴 Карта {i}: {card.get('name', 'No name')}, "
                           f"position: {card.get('position', 'unknown')}, "
                           f"is_reversed: {card.get('is_reversed', 'unknown')}")
            
            # ДИАГНОСТИКА КАТЕГОРИИ ПЕРЕД СОХРАНЕНИЕМ
            logger.debug(f"📋 Категория перед сохранением: '{category}'")

            # ✅ ПРАВИЛЬНОЕ СОХРАНЕНИЕ В БАЗУ ДАННЫХ
            spread_id = self.user_db.add_spread_to_history(
                user_id=user_id,
                username=username,
                spread_type=spread_type,
                category=category,
                cards=spread_cards_data,
                interpretation=None
            )
            
            logger.info(f"💾 Расклад {spread_id} сохранен с {len(spread_cards_data)} картами")
            
            return spread_cards_data, spread_id
            
        except Exception as e:
            logger.error(f"Error in generate_spread for user {user_id}: {e}")
            raise

# ==================== ГЛОБАЛЬНЫЕ ФУНКЦИИ ДЛЯ ОБРАТНОЙ СОВМЕСТИМОСТИ ====================

_active_card_service = None

def set_global_card_service(card_service: CardService):
    """Устанавливает глобальный экземпляр CardService для обратной совместимости"""
    global _active_card_service
    _active_card_service = card_service
    logger.info("✅ Глобальный CardService установлен")

def get_global_card_service():
    """Получение глобального экземпляра CardService"""
    return _active_card_service

async def start_interactive_spread(user_id: int, spread_type: str, category: str, 
                                 chat_id: int = None, context=None, bot=None) -> str:
    """Глобальная функция для обратной совместимости"""
    if _active_card_service:
        return await _active_card_service.start_interactive_spread(
            user_id, spread_type, category, chat_id, context, bot
        )
    raise RuntimeError("CardService не инициализирован. Вызовите set_global_card_service() first.")

async def process_card_selection(session_id: str, position: int, selected_number: int,
                               user_id: int = None, chat_id: int = None, 
                               context: Any = None, bot: Any = None) -> Dict[str, Any]:
    """Глобальная функция для обратной совместимости"""
    if _active_card_service:
        return await _active_card_service.process_card_selection(
            session_id, position, selected_number, user_id, chat_id, context, bot
        )
    return {
        'success': False,
        'status': 'error',
        'message': 'CardService не инициализирован. Вызовите set_global_card_service() first.',
        'completed': False,
        'session': None
    }

async def send_card_selection_interface(update, context, session_id: str, position: int = 1):
    """Глобальная функция для обратной совместимости"""
    if _active_card_service:
        return await _active_card_service.send_card_selection_interface(update, context, session_id, position)
    
    # Fallback: если глобальный сервис не установлен, попробуем отправить сообщение об ошибке
    if hasattr(update, "callback_query") and update.callback_query:
        await update.callback_query.edit_message_text("Ошибка: сервис карт не инициализирован")
    else:
        chat_id = update.effective_chat.id if update and getattr(update, "effective_chat", None) else None
        if chat_id and context and hasattr(context, 'bot'):
            await context.bot.send_message(chat_id=chat_id, text="Ошибка: сервис карт не инициализирован")

async def complete_interactive_spread(session_id: str, bot=None, chat_id: int = None, context=None) -> Dict[str, Any]:
    """Глобальная функция для обратной совместимости"""
    if _active_card_service:
        return await _active_card_service.complete_interactive_spread(session_id, bot, chat_id, context)
    return {
        'status': 'error',
        'message': 'CardService не инициализирован. Вызовите set_global_card_service() first.'
    }