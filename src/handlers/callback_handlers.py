# src/handlers/callback_handlers.py
import logging
import asyncio
import re
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import BadRequest, TelegramError
from telegram.ext import ContextTypes, CallbackQueryHandler
from .. import keyboards

logger = logging.getLogger(__name__)

class CallbackHandlers:
    def __init__(self, bot_instance, application):
        """🔄 Конструктор с параметром application"""
        self.bot = bot_instance
        self.application = application
        self.card_service = getattr(bot_instance, 'card_service', None)
        if not self.card_service:
            logger.warning("⚠️ CardService не доступен в боте")

    async def _get_session_safe(self, session_id):
        """🛡️ Безопасное получение сессии (поддержка async/sync)"""
        get_sess = getattr(self.card_service, 'get_session', None)
        if get_sess is None:
            return None
        if asyncio.iscoroutinefunction(get_sess):
            return await get_sess(session_id)
        return get_sess(session_id)

    async def log_all_callbacks(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """📱 Глобальное логирование ВСЕХ callback'ов для диагностики (DEBUG уровень)"""
        query = update.callback_query
        if query:
            msg_id = query.message.message_id if query.message else 'N/A'
            logger.debug(f"📱 CALLBACK RECEIVED: user={query.from_user.id}, data='{query.data}', msg_id={msg_id}")

    async def safe_edit_or_send_message(self, bot, chat_id, message_id, text, reply_markup=None, parse_mode='HTML'):
        """🛡️ УНИВЕРСАЛЬНЫЙ метод: пытается редактировать, при ошибке отправляет новое сообщение"""
        try:
            # 🔧 Попытка редактирования существующего сообщения
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup
            )
            logger.debug(f"✅ Сообщение успешно отредактировано: msg_id={message_id}")
            return 'edited'
        except BadRequest as e:
            # 🔧 Сообщение нельзя редактировать (старое/удалено) -> fallback на send_message
            logger.warning(f"⚠️ Edit failed ({e}), sending new message instead")
            sent = await bot.send_message(
                chat_id=chat_id, 
                text=text, 
                parse_mode=parse_mode,
                reply_markup=reply_markup
            )
            logger.info(f"📤 Fallback сообщение отправлено: msg_id={sent.message_id}")
            return ('sent', sent.message_id)
        except TelegramError as e:
            logger.exception(f"💥 Unexpected Telegram error while editing/sending message: {e}")
            # 🔧 Аварийный fallback
            sent = await bot.send_message(
                chat_id=chat_id, 
                text=text, 
                parse_mode=parse_mode,
                reply_markup=reply_markup
            )
            logger.info(f"📤 Аварийное fallback сообщение отправлено: msg_id={sent.message_id}")
            return ('sent', sent.message_id)

    async def handle_history_pagination_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        📄 Обработчик клика по пагинации истории: callback_data = "history_page_{n}"
        """
        query = update.callback_query
        # ✅ РАННИЙ ОТВЕТ ДЛЯ ПРЕДОТВРАЩЕНИЯ ПОВТОРНЫХ CALLBACK
        await query.answer(cache_time=1)
        
        user_id = None
        chat_id = None
        message_id = None

        try:
            user_id = query.from_user.id if query.from_user else None
            chat_id = query.message.chat.id if query.message and getattr(query.message, "chat", None) else None
            message_id = query.message.message_id if query.message else None

            data = query.data or ""
            m = re.match(r"^history_page_(\d+)$", data)
            if not m:
                logger.error(f"❌ Invalid history_page callback_data: {data}")
                await self.safe_edit_or_send_message(
                    context.bot,
                    chat_id,
                    message_id,
                    "❌ Неверный формат запроса (pagination).",
                    reply_markup=keyboards.get_back_to_menu_keyboard()
                )
                return

            page = int(m.group(1))
            logger.info(f"🔙 HISTORY_PAGE requested by user={user_id}, page={page}")

            # Получаем данные через history_service
            # history_service.get_user_spreads -> (spreads, current_page, total_pages)
            spreads, current_page, total_pages = self.bot.history_service.get_user_spreads(user_id, page)

            # build keyboard, передаём spreads явно для корректного формирования details / spread_{id}
            keyboard = self.bot.history_service.build_history_keyboard(page=current_page, total_pages=total_pages, spreads=spreads)

            # Текст страницы истории
            text = f"📜 <b>История раскладов</b>\nСтраница {current_page}/{total_pages}"

            # Safe edit или send
            status = await self.safe_edit_or_send_message(
                context.bot,
                chat_id,
                message_id,
                text,
                reply_markup=keyboard
            )
            logger.debug(f"🔁 HISTORY_PAGE handled: {status}")

        except Exception as e:
            logger.exception(f"❌ Ошибка в handle_history_pagination_callback: {e}")
            # Fallback: показать главное меню
            try:
                await self.safe_edit_or_send_message(
                    context.bot,
                    chat_id or (update.effective_chat.id if getattr(update, "effective_chat", None) else None),
                    message_id or (query.message.message_id if query and query.message else None),
                    "❌ Произошла ошибка при открытии истории. Возвращаю в главное меню.",
                    reply_markup=keyboards.get_main_menu_keyboard()
                )
            except Exception:
                logger.exception("❌ Не удалось отправить fallback-меню после ошибки пагинации истории.")

    async def handle_profile_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """👤 Обработчик callback для кнопки профиля"""
        query = update.callback_query
        # ✅ РАННИЙ ОТВЕТ ДЛЯ ПРЕДОТВРАЩЕНИЯ ПОВТОРНЫХ CALLBACK
        await query.answer(cache_time=1)
        
        user_id = query.from_user.id
        chat_id = query.message.chat_id
        message_id = query.message.message_id
        
        logger.info(f"👤 Пользователь {user_id} запросил профиль")
        
        try:
            # 🔧 Показываем профиль пользователя
            await self.bot.show_profile(update, context)
        except Exception as e:
            logger.exception(f"❌ Ошибка показа профиля: {e}")
            await self.safe_edit_or_send_message(
                context.bot, 
                chat_id, 
                message_id,
                "❌ Произошла ошибка при загрузке профиля.",
                reply_markup=keyboards.get_main_menu_keyboard()
            )

    async def show_spread_result(self, update: Update, context: ContextTypes.DEFAULT_TYPE, session_id: str):
        """📊 УЛУЧШЕННЫЙ метод завершения расклада с ИДЕМПОТЕНТНОСТЬЮ через CardService API"""
        query = update.callback_query
        # ✅ РАННИЙ ОТВЕТ ДЛЯ ПРЕДОТВРАЩЕНИЯ ПОВТОРНЫХ CALLBACK
        await query.answer(cache_time=1)
        
        try:
            user_id = query.from_user.id
            chat_id = query.message.chat_id
            message_id = query.message.message_id
            
            # ✅ ИСПРАВЛЕНИЕ: Используем CardService API для проверки состояния сессии
            if self.card_service and hasattr(self.card_service, 'is_session_completed'):
                if await self.card_service.is_session_completed(session_id):
                    logger.warning(f"⚠️ Сессия {session_id} уже завершена, возвращаем результат")
                    await self.send_completed_spread_result(update, context, session_id)
                    return
            else:
                # 🔧 Fallback: проверка через локальное хранилище
                completed_sessions = context.user_data.setdefault('completed_sessions', set())
                if session_id in completed_sessions:
                    logger.warning(f"⚠️ Сессия {session_id} уже завершена (local), возвращаем результат")
                    await self.send_completed_spread_result(update, context, session_id)
                    return
            
            # 🔧 ЛОГИРОВАНИЕ ТИПА СЕССИИ ПЕРЕД ЗАВЕРШЕНИЕМ
            spread_type = context.user_data.get('selected_spread_type', 'single')
            logger.info(f"🎴 Запуск завершения расклада: session={session_id}, user={user_id}, type={spread_type}")
            
            # 🔧 ВАЖНО: используем context.bot и правильный chat_id
            result = await self.card_service.complete_interactive_spread(
                session_id=session_id,
                bot=context.bot,
                chat_id=chat_id,
                context=context
            )
            
            if result and result.get('status') == 'success':
                logger.info(f"✅ Расклад успешно завершен: session={session_id}, type={spread_type}")
                
                # ✅ ИСПРАВЛЕНИЕ: Используем CardService API для отметки завершения
                if self.card_service and hasattr(self.card_service, 'mark_session_completed'):
                    await self.card_service.mark_session_completed(session_id)
                else:
                    # 🔧 Fallback: локальное хранилище
                    completed_sessions = context.user_data.setdefault('completed_sessions', set())
                    completed_sessions.add(session_id)
                    logger.debug(f"✅ Сессия {session_id} добавлена в completed_sessions")
                    
            else:
                error_msg = result.get('message', 'Неизвестная ошибка') if result else 'Результат не получен'
                logger.error(f"❌ Ошибка завершения расклада: {error_msg}, session={session_id}, type={spread_type}")
                await self.safe_edit_or_send_message(
                    context.bot, chat_id, message_id,
                    "❌ Произошла ошибка при завершении расклада. Попробуйте снова.",
                    reply_markup=keyboards.get_back_to_menu_keyboard()
                )
                
        except Exception as e:
            logger.exception(f"💥 Критическая ошибка в show_spread_result: {e}, session={session_id}")
            await self.safe_edit_or_send_message(
                context.bot, query.message.chat_id, query.message.message_id,
                "❌ Произошла критическая ошибка при завершении расклада.",
                reply_markup=keyboards.get_back_to_menu_keyboard()
            )

    async def handle_category_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """🎯 УЛУЧШЕННЫЙ обработчик выбора категории с надежной обработкой ошибок"""
        query = update.callback_query
        # ✅ РАННИЙ ОТВЕТ ДЛЯ ПРЕДОТВРАЩЕНИЯ ПОВТОРНЫХ CALLBACK
        await query.answer(cache_time=1)
        
        user_id = query.from_user.id
        chat_id = query.message.chat_id
        message_id = query.message.message_id
        callback_data = query.data
        
        try:
            logger.info(f"🎯 CATEGORY SELECTION: User {user_id}, callback: {callback_data}")
            
            # ИЗВЛЕКАЕМ ТИП РАСКЛАДА ИЗ КОНТЕКСТА
            spread_type = context.user_data.get('selected_spread_type', 'single')
            
            logger.debug(f"🎯 CATEGORY SELECTION: User {user_id}, callback: {callback_data}, spread_type: {spread_type}")
            
            if callback_data in ['spread_single', 'spread_three']:
                spread_type = 'single' if callback_data == 'spread_single' else 'three'
                context.user_data['selected_spread_type'] = spread_type
                
                spread_text = '1 карты' if spread_type == 'single' else '3 карт'
                
                status = await self.safe_edit_or_send_message(
                    context.bot, chat_id, message_id,
                    f"🔮 <b>Выберите категорию для {spread_text}:</b>\n\n"
                    f"💫 Категория помогает AI точнее интерпретировать карты в контексте вашего вопроса.",
                    reply_markup=keyboards.get_categories_keyboard()
                )
                logger.debug(f"🎯 SPREAD_TYPE_{spread_type} handled: {status}")
                return
            
            category_map = {
                'category_love': 'Любовь и отношения',
                'category_career': 'Карьера и работа', 
                'category_finance': 'Финансы и богатство',
                'category_relationships': 'Отношения',
                'category_growth': 'Личностный рост',
                'category_general': 'Общий вопрос'
            }
            
            # 🔧 ПАТЧ 2.1: КОРРЕКТНАЯ УСТАНОВКА return_action ДЛЯ category_custom
            if callback_data == "category_custom":
                # Для трехкарточного расклада — хотим интерактивный выбор после ввода вопроса
                if spread_type == 'three':
                    context.user_data['awaiting_custom_question_for'] = {
                        'spread_type': spread_type,
                        'return_action': 'start_interactive'
                    }
                else:
                    # Для single — чаще ожидаем генерацию без интерактивного выбора
                    context.user_data['awaiting_custom_question_for'] = {
                        'spread_type': spread_type,
                        'return_action': 'generate_spread'
                    }

                status = await self.safe_edit_or_send_message(
                    context.bot, chat_id, message_id,
                    "💭 <b>Пользовательский вопрос</b>\n\nЗадайте свой вопрос для расклада (или нажмите ❌ Отмена):",
                    reply_markup=keyboards.get_cancel_question_keyboard()
                )
                logger.debug(f"🎯 CUSTOM_QUESTION handled: {status}")
                return
            
            category = category_map.get(callback_data, 'Общий вопрос')
            spread_type = context.user_data.get('selected_spread_type', 'single')
            
            logger.info(f"🎴 Запуск интерактивного расклада: user={user_id}, type={spread_type}, category={category}")
            
            # ✅ ИСПРАВЛЕНО: Проверка доступности card_service
            if not self.card_service:
                logger.error("❌ CardService недоступен")
                await self.safe_edit_or_send_message(
                    context.bot, chat_id, message_id,
                    "❌ Сервис раскладов временно недоступен. Попробуйте позже.",
                    reply_markup=keyboards.get_back_to_menu_keyboard()
                )
                return
            
            # ✅ ИСПРАВЛЕНИЕ: Гарантируем корректную инициализацию completed_sessions
            if 'completed_sessions' not in context.user_data:
                context.user_data['completed_sessions'] = set()
            elif not isinstance(context.user_data['completed_sessions'], set):
                logger.warning(f"⚠️ completed_sessions имеет неправильный тип: {type(context.user_data['completed_sessions'])}. Исправляем на set.")
                context.user_data['completed_sessions'] = set()
            
            # ✅ ИСПРАВЛЕНО: Вызов через card_service с context.bot
            session_id = await self.card_service.start_interactive_spread(
                user_id=user_id,
                spread_type=spread_type,
                category=category,
                chat_id=chat_id,
                context=context,
                bot=context.bot
            )
            
            if not session_id:
                logger.error(f"❌ Не удалось создать сессию выбора карт для пользователя {user_id}")
                await self.safe_edit_or_send_message(
                    context.bot, chat_id, message_id,
                    "❌ Произошла ошибка при создании сессии расклада. Попробуйте позже.",
                    reply_markup=keyboards.get_back_to_menu_keyboard()
                )
                return
            
            # ✅ ИСПРАВЛЕНИЕ: Убеждаемся, что completed_sessions не содержит session_id при старте
            completed_sessions = context.user_data['completed_sessions']
            if session_id in completed_sessions:
                logger.warning(f"⚠️ Удаляем session_id {session_id} из completed_sessions при старте нового расклада")
                completed_sessions.discard(session_id)
            
            context.user_data['current_session_id'] = session_id
            await self.send_card_selection_interface(update, context, session_id, position=1)
            
        except Exception as e:
            logger.exception(f"❌ Критическая ошибка в handle_category_selection: {e}")
            await self.safe_edit_or_send_message(
                context.bot, chat_id, message_id,
                "❌ Произошла ошибка при выборе категории. Пожалуйста, попробуйте снова.",
                reply_markup=keyboards.get_back_to_menu_keyboard()
            )

    async def handle_spread_details_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """📋 УЛУЧШЕННЫЙ обработчик деталей расклада с безопасным редактированием"""
        query = update.callback_query
        # ✅ РАННИЙ ОТВЕТ ДЛЯ ПРЕДОТВРАЩЕНИЯ ПОВТОРНЫХ CALLBACK
        await query.answer(cache_time=1)
        
        user_id = query.from_user.id
        chat_id = query.message.chat_id
        message_id = query.message.message_id
        callback_data = query.data
        
        try:
            # 🔧 ВАЛИДАЦИАЯ: проверяем формат details_{spread_id}
            if not callback_data.startswith('details_'):
                logger.error(f"❌ Неверный формат callback_data: {callback_data}")
                await self.safe_edit_or_send_message(
                    context.bot, chat_id, message_id,
                    "❌ Неверный формат запроса.",
                    reply_markup=keyboards.get_back_to_menu_keyboard()
                )
                return
            
            # 🔧 ИЗВЛЕКАЕМ SPREAD_ID
            spread_id_str = callback_data.split('_', 1)[1]
            if not spread_id_str.isdigit():
                logger.error(f"❌ Нечисловой spread_id: {spread_id_str}")
                await self.safe_edit_or_send_message(
                    context.bot, chat_id, message_id,
                    "❌ Неверный идентификатор расклада.",
                    reply_markup=keyboards.get_back_to_menu_keyboard()
                )
                return
            
            spread_id = int(spread_id_str)
            logger.info(f"📋 Пользователь {user_id} запросил детали расклада {spread_id}")
            
            # 🔧 ДИАГНОСТИКА: получаем расклад через history_service
            spread = self.bot.history_service.get_spread_by_id(spread_id)
            if not spread:
                logger.warning(f"⚠️ Расклад {spread_id} не найден для пользователя {user_id}")
                await self.safe_edit_or_send_message(
                    context.bot, chat_id, message_id,
                    "❌ Расклад не найден.",
                    reply_markup=keyboards.get_back_to_history_keyboard()
                )
                return
            
            # 🔧 ДИАГНОСТИКА: получаем вопросы
            questions = self.bot.user_db.get_spread_questions(spread_id)
            logger.debug(f"📋 Для расклада {spread_id} найдено {len(questions)} вопросов")
            
            # 🔧 ФОРМАТИРОВАНИЕ ТЕКСТА ДЕТАЛЕЙ
            details_text = self.format_spread_full_text(spread)
            
            # 🔧 ФОРМИРОВАНИЕ КЛАВИАТУРЫ: используем history_service для получения клавиатуры
            has_questions = len(questions) > 0
            kb = self.bot.history_service.get_spread_details_keyboard(spread_id, has_questions)
            
            # 🔧 УНИВЕРСАЛЬНАЯ ОТПРАВКА С FALLBACK
            status = await self.safe_edit_or_send_message(
                context.bot, chat_id, message_id, details_text, kb
            )
            logger.debug(f"📋 SPREAD_DETAILS_{spread_id} handled: {status}")
            
        except Exception as e:
            logger.exception(f"❌ Критическая ошибка показа деталей расклада: {e}")
            await self.safe_edit_or_send_message(
                context.bot, chat_id, message_id,
                "❌ Произошла ошибка при загрузке деталей расклада.",
                reply_markup=keyboards.get_back_to_history_keyboard()
            )

    async def handle_back_to_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """🔙 Обработчик возврата к истории раскладов"""
        query = update.callback_query
        # ✅ РАННИЙ ОТВЕТ ДЛЯ ПРЕДОТВРАЩЕНИЯ ПОВТОРНЫХ CALLBACK
        await query.answer(cache_time=1)
        
        user_id = query.from_user.id
        chat_id = query.message.chat_id
        msg_id = query.message.message_id

        logger.info(f"🔙 BACK_TO_HISTORY: user={user_id}")

        try:
            # 🔧 Получаем историю раскладов пользователя
            spreads, total_pages = self.bot.history_service.get_user_spreads(user_id, page=1)
            kb = self.bot.history_service.build_history_keyboard(spreads=spreads, page=1, total_pages=total_pages)

            status = await self.safe_edit_or_send_message(
                context.bot,
                chat_id,
                msg_id,
                "📜 История раскладов:",
                reply_markup=kb
            )
            logger.debug(f"🔙 BACK_TO_HISTORY handled: {status}")

        except Exception as e:
            logger.exception(f"❌ Ошибка в handle_back_to_history: {e}")
            # 🔧 Fallback при ошибке
            await self.safe_edit_or_send_message(
                context.bot,
                chat_id,
                msg_id,
                "❌ Произошла ошибка при загрузке истории.",
                reply_markup=keyboards.get_back_to_menu_keyboard()
            )

    def format_spread_full_text(self, spread):
        """📝 Форматирует полный текст расклада для показа в деталях"""
        try:
            spread_type = spread.get('spread_type', 'single')
            cards = spread.get('cards', [])
            interpretation = spread.get('interpretation', '')
            category = spread.get('category', 'Общий вопрос')
            created_at = spread.get('created_at', '')
            
            if spread_type == 'single':
                card = cards[0] if cards else {}
                result_text = (
                    f"🎴 <b>Детали расклада</b>\n\n"
                    f"📊 <b>Тип:</b> Расклад на 1 карту\n"
                    f"🎯 <b>Категория:</b> {category}\n"
                    f"📅 <b>Дата:</b> {created_at}\n\n"
                    f"🃏 <b>Выпавшая карта:</b> {card.get('name', 'Неизвестно')}\n"
                    f"📖 <b>Значение:</b> {card.get('meaning', '')}\n\n"
                    f"💫 <b>Интерпретация:</b>\n{interpretation}"
                )
            else:
                position_names = ["🕰️ <b>Прошлое</b>", "🌅 <b>Настоящее</b>", "🔮 <b>Будущее</b>"]
                cards_text = ""
                
                for i, card in enumerate(cards):
                    if i < len(position_names):
                        cards_text += (
                            f"{position_names[i]}:\n"
                            f"   🃏 <b>{card.get('name', 'Неизвестно')}</b>\n"
                            f"   📖 {card.get('meaning', '')}\n\n"
                        )
                
                result_text = (
                    f"🎴 <b>Детали расклада</b>\n\n"
                    f"📊 <b>Тип:</b> Расклад на 3 карты\n"
                    f"🎯 <b>Категория:</b> {category}\n"
                    f"📅 <b>Дата:</b> {created_at}\n\n"
                    f"{cards_text}"
                    f"💫 <b>Общая интерпретация:</b>\n{interpretation}"
                )
            
            return result_text
            
        except Exception as e:
            logger.exception(f"❌ Ошибка форматирования деталей расклада: {e}")
            return "❌ Произошла ошибка при форматировании деталей расклада."

    async def handle_main_menu_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """🏠 Обработчик возврата в главное меню с УНИВЕРСАЛЬНОЙ отправкой"""
        query = update.callback_query
        # ✅ РАННИЙ ОТВЕТ ДЛЯ ПРЕДОТВРАЩЕНИЯ ПОВТОРНЫХ CALLBACK
        await query.answer(cache_time=1)
        
        user_id = query.from_user.id
        chat_id = query.message.chat_id
        message_id = query.message.message_id
        
        logger.info(f"🏠 Пользователь {user_id} возвращается в главное меню")
        
        menu_text = (
            "🔮 <b>Добро пожаловать в AI-Таролога 'Луна'!</b>\n\n"
            "Я помогу вам получить инсайты и ответы на ваши вопросы "
            "с помощью мудрости карт Таро и искусственного интеллекта.\n\n"
            "Выберите действие:"
        )
        
        # 🔧 УНИФИЦИРОВАННАЯ КЛАВИАТУРА ГЛАВНОГО МЕНЮ
        keyboard = keyboards.get_main_menu_keyboard()
        
        # 🔧 УНИВЕРСАЛЬНАЯ ОТПРАВКА
        status = await self.safe_edit_or_send_message(
            context.bot, chat_id, message_id, menu_text, keyboard
        )
        logger.debug(f"🏠 MAIN_MENU handled: {status}")

    async def handle_back_to_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """🔙 Обработчик возврата в главное меню (унифицированный)"""
        query = update.callback_query
        # ✅ РАННИЙ ОТВЕТ ДЛЯ ПРЕДОТВРАЩЕНИЯ ПОВТОРНЫХ CALLBACK
        await query.answer(cache_time=1)
        
        user_id = query.from_user.id
        chat_id = query.message.chat_id
        message_id = query.message.message_id
        
        logger.info(f"🔙 Пользователь {user_id} вернулся в главное меню через back_to_menu")
        
        menu_text = (
            "🔮 <b>Добро пожаловать в AI-Таролога 'Луна'!</b>\n\n"
            "Я помогу вам получить инсайты и ответы на ваши вопросы "
            "с помощью мудрости карт Таро и искусственного интеллекта.\n\n"
            "Выберите действие:"
        )
        
        # 🔧 УНИФИЦИРОВАННАЯ КЛАВИАТУРА ГЛАВНОГО МЕНЮ
        keyboard = keyboards.get_main_menu_keyboard()
        
        # 🔧 УНИВЕРСАЛЬНААЯ ОТПРАВКА
        status = await self.safe_edit_or_send_message(
            context.bot, chat_id, message_id, menu_text, keyboard
        )
        logger.debug(f"🔙 BACK_TO_MENU handled: {status}")

    async def send_completed_spread_result(self, update: Update, context: ContextTypes.DEFAULT_TYPE, session_id: str):
        """✅ УЛУЧШЕННАЯ отправка результата завершенного расклада (для идемпотентности)"""
        try:
            query = update.callback_query
            chat_id = query.message.chat_id
            message_id = query.message.message_id
            
            # 🔧 Получаем результат завершенного расклада
            if self.card_service:
                session = await self._get_session_safe(session_id)
                if session and hasattr(session, 'result_data'):
                    result_data = session.result_data
                    spread_type = getattr(session, 'spread_type', 'single')
                    
                    result_text = await self.format_spread_result_with_ai(result_data, spread_type)
                    keyboard = keyboards.get_spread_result_keyboard(session_id)
                    
                    status = await self.safe_edit_or_send_message(
                        context.bot, chat_id, message_id, result_text, keyboard
                    )
                    logger.debug(f"✅ COMPLETED_SPREAD_RESULT handled: {status}")
                    return
            
            # 🔧 Fallback: стандартное сообщение
            fallback_text = (
                "🎴 <b>Этот расклад уже был завершен ранее.</b>\n\n"
                "💫 Вы можете просмотреть результат в истории раскладов или задать новый вопрос."
            )
            
            status = await self.safe_edit_or_send_message(
                context.bot, chat_id, message_id,
                fallback_text,
                reply_markup=keyboards.get_back_to_menu_keyboard()
            )
            logger.debug(f"✅ COMPLETED_SPREAD_FALLBACK handled: {status}")
            
        except Exception as e:
            logger.exception(f"❌ Ошибка отправки завершенного расклада: {e}")
            await self.safe_edit_or_send_message(
                context.bot, query.message.chat_id, query.message.message_id,
                "❌ Произошла ошибка при загрузке результата расклада.",
                reply_markup=keyboards.get_back_to_menu_keyboard()
            )

    async def handle_card_choice_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """🎴 ИСПРАВЛЕННЫЙ обработчик выбора карты с ИДЕМПОТЕНТНОСТЬЮ"""
        query = update.callback_query
        # ✅ РАННИЙ ОТВЕТ ДЛЯ ПРЕДОТВРАЩЕНИЯ ПОВТОРНЫХ CALLBACK
        await query.answer(cache_time=1)
        
        try:
            user_id = query.from_user.id
            chat_id = query.message.chat_id
            message_id = query.message.message_id
            data = query.data.split(':')
            
            if len(data) != 4 or data[0] != 'card_choice':
                logger.error(f"❌ Неверный формат callback_data для выбора карты: {query.data}")
                await self.safe_edit_or_send_message(
                    context.bot, chat_id, message_id,
                    "❌ Неверный формат запроса.",
                    reply_markup=keyboards.get_back_to_menu_keyboard()
                )
                return
            
            session_id = data[1]
            position = int(data[2])
            selected_number = int(data[3])
            
            logger.info(f"🎴 Пользователь {user_id} выбрал карту: session={session_id}, position={position}, number={selected_number}")
            
            # ✅ ИДЕМПОТЕНТНОСТЬ: Проверка состояния сессии
            if self.card_service:
                session = await self._get_session_safe(session_id)
                if session and getattr(session, 'ai_executed', False):
                    logger.warning(f"⚠️ Сессия {session_id} уже завершена (ai_executed=True), возвращаем результат")
                    await self.send_completed_spread_result(update, context, session_id)
                    return
            
            # ✅ Проверка доступности card_service
            if not self.card_service:
                logger.error("❌ CardService недоступен")
                await self.safe_edit_or_send_message(
                    context.bot, chat_id, message_id,
                    "❌ Сервис выбора карт временно недоступен. Попробуйте позже.",
                    reply_markup=keyboards.get_back_to_menu_keyboard()
                )
                return
            
            # 🔧 ЛОГИРОВАНИЕ СОСТОЯНИЯ СЕССИИ
            session_state = "unknown"
            if self.card_service:
                session = await self._get_session_safe(session_id)
                session_state = f"ai_executed={getattr(session, 'ai_executed', 'N/A')}, status={getattr(session, 'status', 'N/A')}"
            
            logger.debug(f"🔍 CALLBACK SESSION STATE: session={session_id}, {session_state}")
            
            # 🔧 ПЕРЕДАЧА ПАРАМЕТРОВ
            result = await self.card_service.process_card_selection(
                session_id=session_id,
                position=position, 
                selected_number=selected_number,
                user_id=user_id,
                chat_id=chat_id,
                context=context,
                bot=context.bot
            )
            
            # 🔧 ДИАГНОСТИКА РЕЗУЛЬТАТА
            logger.debug(f"🔄 Результат process_card_selection: статус={result.get('status')}")
            
            # ✅ ОБРАБОТКА ОШИБОК
            if result.get('status') == 'error':
                error_message = result.get('message', 'Неизвестная ошибка')
                logger.error(f"❌ Ошибка обработки выбора карты: {error_message}")
                await self.safe_edit_or_send_message(
                    context.bot, chat_id, message_id,
                    f"❌ Произошла ошибка при обработке выбора карты: {error_message}",
                    reply_markup=keyboards.get_back_to_menu_keyboard()
                )
                return
            
            # ✅ ПОЛУЧЕНИЕ ТИПА РАСКЛАДА
            spread_type = context.user_data.get('selected_spread_type', 'single')
            logger.debug(f"🔄 Обработка результата: status={result.get('status')}, spread_type={spread_type}")
            
            # ✅ ОСНОВНАЯ ЛОГИКА ПЕРЕХОДА МЕЖДУ ШАГАМИ
            if result.get('status') == 'completed':
                logger.info("🎴 Расклад завершен, показываем результат")
                await self.show_spread_result(update, context, session_id)
                
            elif result.get('status') == 'in_progress':
                next_position = position + 1
                logger.debug(f"➡️ Продолжаем выбор карты, следующая позиция: {next_position}")
                await self.send_card_selection_interface(update, context, session_id, next_position)
                
            elif result.get('status') == 'continue':
                logger.debug("⏭️ Показываем интерфейс продолжения для three расклада")
                await self.show_continue_selection(update, context, session_id, position)
                
            else:
                logger.error(f"❌ Неизвестный статус в результате: {result.get('status')}")
                await self.safe_edit_or_send_message(
                    context.bot, chat_id, message_id,
                    "❌ Произошла неизвестная ошибка при обработке выбора карты.",
                    reply_markup=keyboards.get_back_to_menu_keyboard()
                )
                
        except Exception as e:
            logger.exception(f"❌ Критическая ошибка в handle_card_choice_callback: {e}")
            await self.safe_edit_or_send_message(
                context.bot, query.message.chat_id, query.message.message_id,
                "❌ Произошла ошибка при выборе карты.",
                reply_markup=keyboards.get_back_to_menu_keyboard()
            )

    async def handle_ask_question_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """🛡️ ИСПРАВЛЕННЫЙ обработчик кнопки 'Задать вопрос по раскладу' - правильная установка флага"""
        query = update.callback_query
        # ✅ РАННИЙ ОТВЕТ ДЛЯ ПРЕДОТВРАЩЕНИЯ ПОВТОРНЫХ CALLBACK
        await query.answer(cache_time=1)
        
        user_id = query.from_user.id
        chat_id = query.message.chat_id
        message_id = query.message.message_id
        callback_data = query.data
        
        try:
            # 🛡️ ВАЛИДАЦИЯ: извлекаем spread_id из callback_data
            if not callback_data.startswith('ask_question_'):
                logger.error(f"❌ [ASK_QUESTION] Неверный префикс callback_data: {callback_data}")
                status = await self.safe_edit_or_send_message(
                    context.bot, chat_id, message_id,
                    "❌ <b>Неверный формат запроса</b>",
                    reply_markup=keyboards.get_back_to_menu_keyboard()
                )
                return
            
            spread_id_str = callback_data.replace('ask_question_', '')
            if not spread_id_str.isdigit():
                logger.error(f"❌ [ASK_QUESTION] ID расклада не является числом: {spread_id_str}")
                status = await self.safe_edit_or_send_message(
                    context.bot, chat_id, message_id,
                    "❌ <b>Неверный идентификатор расклада</b>",
                    reply_markup=keyboards.get_back_to_menu_keyboard()
                )
                return
            
            spread_id = int(spread_id_str)
            logger.info(f"💭 Пользователь {user_id} задает вопрос по раскладу {spread_id}")
            
            # 🛡️ ПРОВЕРКА СУЩЕСТВОВАНИЯ РАСКЛАДА
            spread = self.bot.user_db.get_user_history_by_spread_id(user_id, spread_id)
            if not spread:
                logger.error(f"❌ [ASK_QUESTION] Расклад {spread_id} не найден для пользователя {user_id}")
                status = await self.safe_edit_or_send_message(
                    context.bot, chat_id, message_id,
                    "❌ <b>Расклад не найден</b>\n\nВозможно, он был удален или у вас нет к нему доступа.",
                    reply_markup=keyboards.get_back_to_history_keyboard()
                )
                return
            
            # ✅ ИСПРАВЛЕНИЕ: ПРАВИЛЬНАЯ УСТАНОВКА ФЛАГА
            context.user_data['awaiting_custom_question_for'] = {
                'spread_type': spread.get('spread_type', 'single'),
                'return_action': 'ask_on_spread',
                'spread_id': spread_id
            }
            
            # 🔧 ОЧИСТКА СТАРЫХ ФЛАГОВ (на всякий случай)
            context.user_data.pop('waiting_for_spread_question', None)
            context.user_data.pop('current_spread_id', None)
            
            logger.debug(f"✅ [ASK_QUESTION] Флаг установлен: spread_id={spread_id}, return_action=ask_on_spread")
            
            # 📝 ОТПРАВКА СООБЩЕНИЯ С ЗАПРОСОМ ВОПРОСА
            question_text = (
                "💭 <b>Задайте вопрос по раскладу</b>\n\n"
                "📝 <b>Введите ваш вопрос в чат...</b>\n\n"
                "💡 <i>Вопрос должен быть связан с этим раскладом и его интерпретацией.</i>\n"
                "✨ <i>Я сохраню вопрос и пришлю ответ.</i>"
            )
            
            status = await self.safe_edit_or_send_message(
                context.bot, chat_id, message_id,
                question_text,
                reply_markup=keyboards.get_cancel_spread_question_keyboard()
            )
            logger.debug(f"💭 ASK_QUESTION_{spread_id} handled: {status}")
            
        except Exception as e:
            logger.exception(f"❌ [ASK_QUESTION] Критическая ошибка в handle_ask_question_callback: {e}")
            
            # 🆘 АВАРИЙНЫЙ FALLBACK
            status = await self.safe_edit_or_send_message(
                context.bot, chat_id, message_id,
                "❌ <b>Произошла непредвиденная ошибка</b>\n\nПожалуйста, вернитесь в главное меню и попробуйте снова.",
                reply_markup=keyboards.get_back_to_menu_keyboard()
            )

    async def handle_view_question_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """❓ Показывает вопрос и ответ"""
        query = update.callback_query
        # ✅ РАННИЙ ОТВЕТ ДЛЯ ПРЕДОТВРАЩЕНИЯ ПОВТОРНЫХ CALLBACK
        await query.answer(cache_time=1)
        
        user_id = query.from_user.id
        chat_id = query.message.chat_id
        message_id = query.message.message_id
        callback_data = query.data
        
        try:
            question_id = int(callback_data.split('_')[-1])
            logger.info(f"❓ Пользователь {user_id} запросил вопрос {question_id}")
            
            question = self.bot.user_db.get_question_by_id(question_id)
            if not question:
                status = await self.safe_edit_or_send_message(
                    context.bot, chat_id, message_id,
                    "❌ Вопрос не найден.",
                    reply_markup=keyboards.get_back_to_history_keyboard()
                )
                return
            
            # ✅ ИСПРАВЛЕНИЕ: Используем правильное поле для текста вопроса с резервным вариантом
            question_text = question.get('question_text', '') or question.get('question', '')
            
            response_text = f"<b>❓ Ваш вопрос:</b>\n{question_text}\n\n"
            
            if question.get('answer_text'):
                response_text += f"💫 <b>Ответ:</b>\n{question['answer_text']}"
            else:
                response_text += "<i>⏳ Ответ еще генерируется...</i>"
            
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("📖 Назад к раскладу", callback_data=f"details_{question['spread_id']}"),
                InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")
            ]])
            
            status = await self.safe_edit_or_send_message(
                context.bot, chat_id, message_id, response_text, keyboard
            )
            logger.debug(f"❓ VIEW_QUESTION_{question_id} handled: {status}")
            
        except Exception as e:
            logger.exception(f"❌ Ошибка показа вопроса: {e}")
            status = await self.safe_edit_or_send_message(
                context.bot, chat_id, message_id,
                "❌ Произошла ошибка при загрузке вопроса.",
                reply_markup=keyboards.get_back_to_history_keyboard()
            )

    async def handle_view_questions_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """📋 Обработчик для просмотра списка вопросов по раскладу"""
        query = update.callback_query
        # ✅ РАННИЙ ОТВЕТ ДЛЯ ПРЕДОТВРАЩЕНИЯ ПОВТОРНЫХ CALLBACK
        await query.answer(cache_time=1)
        
        user_id = query.from_user.id
        chat_id = query.message.chat_id
        message_id = query.message.message_id
        callback_data = query.data
        
        try:
            # Извлекаем spread_id из callback_data
            if not callback_data.startswith('view_questions_'):
                logger.error(f"❌ Неверный формат callback_data для списка вопросов: {callback_data}")
                status = await self.safe_edit_or_send_message(
                    context.bot, chat_id, message_id,
                    "❌ Неверный формат запроса.",
                    reply_markup=keyboards.get_back_to_menu_keyboard()
                )
                return
            
            spread_id_str = callback_data.replace('view_questions_', '')
            if not spread_id_str.isdigit():
                logger.error(f"❌ Нечисловой spread_id: {spread_id_str}")
                status = await self.safe_edit_or_send_message(
                    context.bot, chat_id, message_id,
                    "❌ Неверный идентификатор расклада.",
                    reply_markup=keyboards.get_back_to_menu_keyboard()
                )
                return
            
            spread_id = int(spread_id_str)
            logger.info(f"📋 Пользователь {user_id} запросил список вопросов для расклада {spread_id}")
            
            # Получаем вопросы по раскладу
            questions = self.bot.user_db.get_spread_questions(spread_id)
            
            if not questions:
                # Если вопросов нет, показываем сообщение и кнопку для создания вопроса
                text = (
                    "📭 <b>По этому раскладу пока нет вопросов</b>\n\n"
                    "Вы можете задать первый вопрос, чтобы получить дополнительную интерпретацию."
                )
                
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("💭 Задать вопрос", callback_data=f"ask_question_{spread_id}")],
                    [InlineKeyboardButton("📖 Назад к раскладу", callback_data=f"details_{spread_id}")],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
                ])
            else:
                # Форматируем список вопросов
                text = f"📋 <b>Вопросы по раскладу:</b>\n\n"
                
                for i, question in enumerate(questions, 1):
                    question_text = question.get('question_text', '') or question.get('question', '')
                    # Обрезаем длинный текст вопроса для лучшего отображения
                    if len(question_text) > 50:
                        question_text = question_text[:50] + "..."
                    
                    status_icon = "✅" if question.get('answer_text') else "⏳"
                    text += f"{i}. {status_icon} {question_text}\n"
                
                text += f"\n📊 Всего вопросов: {len(questions)}"
                
                # Создаем клавиатуру с вопросами
                keyboard_buttons = []
                
                # Кнопки для каждого вопроса
                for i, question in enumerate(questions, 1):
                    status_text = " (отвечено)" if question.get('answer_text') else " (ожидает)"
                    keyboard_buttons.append([
                        InlineKeyboardButton(
                            f"❓ Вопрос {i}{status_text}",
                            callback_data=f"view_question_{question['id']}"
                        )
                    ])
                
                # Дополнительные кнопки
                keyboard_buttons.append([
                    InlineKeyboardButton("💭 Задать новый вопрос", callback_data=f"ask_question_{spread_id}")
                ])
                keyboard_buttons.append([
                    InlineKeyboardButton("📖 Назад к раскладу", callback_data=f"details_{spread_id}"),
                    InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")
                ])
                
                keyboard = InlineKeyboardMarkup(keyboard_buttons)
            
            status = await self.safe_edit_or_send_message(
                context.bot, chat_id, message_id, text, keyboard
            )
            logger.debug(f"📋 VIEW_QUESTIONS_{spread_id} handled: {status}")
            
        except Exception as e:
            logger.exception(f"❌ Ошибка показа списка вопросов: {e}")
            status = await self.safe_edit_or_send_message(
                context.bot, chat_id, message_id,
                "❌ Произошла ошибка при загрузке списка вопросов.",
                reply_markup=keyboards.get_back_to_menu_keyboard()
            )

    async def handle_spread_type_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """🔮 ИСПРАВЛЕННЫЙ обработчик выбора типа расклада - использует только selected_spread_type"""
        query = update.callback_query
        # ✅ РАННИЙ ОТВЕТ ДЛЯ ПРЕДОТВРАЩЕНИЯ ПОВТОРНЫХ CALLBACK
        await query.answer(cache_time=1)
        
        user_id = query.from_user.id
        chat_id = query.message.chat_id
        message_id = query.message.message_id
        callback_data = query.data
        
        try:
            logger.debug(f"🎯 SPREAD TYPE SELECTION: User {user_id}, callback: {callback_data}")
            
            if callback_data == 'spread_single':
                # ✅ ИСПРАВЛЕНО: Сохраняем только selected_spread_type
                context.user_data['selected_spread_type'] = 'single'
                spread_text = '1 карты'
            else:
                # ✅ ИСПРАВЛЕНО: Сохраняем только selected_spread_type  
                context.user_data['selected_spread_type'] = 'three'
                spread_text = '3 карт'
            
            status = await self.safe_edit_or_send_message(
                context.bot, chat_id, message_id,
                f"🔮 <b>Выберите категорию для {spread_text}:</b>\n\n"
                f"💫 Категория помогает AI точнее интерпретировать карты в контексте вашего вопроса.",
                reply_markup=keyboards.get_categories_keyboard()
            )
            logger.debug(f"🔮 SPREAD_TYPE_{callback_data} handled: {status}")
            
        except Exception as e:
            logger.exception(f"❌ Ошибка в handle_spread_type_selection: {e}")
            status = await self.safe_edit_or_send_message(
                context.bot, chat_id, message_id,
                "❌ Произошла ошибка при выборе типа расклада.",
                reply_markup=keyboards.get_back_to_menu_keyboard()
            )

    async def handle_continue_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """➡️ Обработчик продолжения выбора для three раскладов"""
        query = update.callback_query
        # ✅ РАННИЙ ОТВЕТ ДЛЯ ПРЕДОТВРАЩЕНИЯ ПОВТОРНЫХ CALLBACK
        await query.answer(cache_time=1)
        
        try:
            data = query.data.split(':')
            chat_id = query.message.chat_id
            message_id = query.message.message_id
            
            if len(data) != 3 or data[0] != 'continue_select':
                logger.error(f"❌ Неверный формат callback_data для продолжения: {query.data}")
                status = await self.safe_edit_or_send_message(
                    context.bot, chat_id, message_id,
                    "❌ Неверный формат запроса.",
                    reply_markup=keyboards.get_back_to_menu_keyboard()
                )
                return
            
            session_id = data[1]
            next_position = int(data[2])
            
            await self.send_card_selection_interface(update, context, session_id, next_position)
            
        except Exception as e:
            logger.exception(f"❌ Ошибка в handle_continue_selection: {e}")
            status = await self.safe_edit_or_send_message(
                context.bot, query.message.chat_id, query.message.message_id,
                "❌ Произошла ошибка при продолжении выбора.",
                reply_markup=keyboards.get_back_to_menu_keyboard()
            )

    async def handle_back_to_selection_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """🔙 Обработчик возврата к выбору карт"""
        query = update.callback_query
        # ✅ РАННИЙ ОТВЕТ ДЛЯ ПРЕДОТВРАЩЕНИЯ ПОВТОРНЫХ CALLBACK
        await query.answer(cache_time=1)
        
        try:
            data = query.data.split(':')
            chat_id = query.message.chat_id
            message_id = query.message.message_id
            
            if len(data) != 3 or data[0] != 'back_to_select':
                logger.error(f"❌ Неверный формат callback_data для возврата к выбору: {query.data}")
                status = await self.safe_edit_or_send_message(
                    context.bot, chat_id, message_id,
                    "❌ Неверный формат запроса.",
                    reply_markup=keyboards.get_back_to_menu_keyboard()
                )
                return
            
            session_id = data[1]
            position = int(data[2])
            
            logger.debug(f"🔙 Возврат к выбору карты: session={session_id}, position={position}")
            
            # Возвращаемся к интерфейсу выбора карты
            await self.send_card_selection_interface(update, context, session_id, position)
            
        except Exception as e:
            logger.exception(f"❌ Ошибка возврата к выбору карт: {e}")
            status = await self.safe_edit_or_send_message(
                context.bot, query.message.chat_id, query.message.message_id,
                "❌ Произошла ошибка при возврате к выбору карт.",
                reply_markup=keyboards.get_back_to_menu_keyboard()
            )

    async def handle_profile_edit_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """👤 Обработчик callback от кнопок редактирования профиля"""
        query = update.callback_query
        # ✅ РАННИЙ ОТВЕТ ДЛЯ ПРЕДОТВРАЩЕНИЯ ПОВТОРНЫХ CALLBACK
        await query.answer(cache_time=1)
        
        user_id = query.from_user.id
        chat_id = query.message.chat_id
        message_id = query.message.message_id
        callback_data = query.data
        
        try:
            if callback_data == "edit_birth_date":
                context.user_data['editing_profile'] = True
                context.user_data['editing_field'] = 'birth_date'
                context.user_data['awaiting_birth_date'] = True
                
                status = await self.safe_edit_or_send_message(
                    context.bot, chat_id, message_id,
                    "📅 <b>Введите вашу дату рождения</b>\n\n"
                    "Формат: <b>ДД.ММ.ГГГГ</b>\n"
                    "Например: <code>15.05.1990</code>\n\n"
                    "💡 <i>Эта информация поможет делать интерпретации более точными</i>",
                    reply_markup=keyboards.get_cancel_edit_inline_keyboard()
                )
                logger.debug(f"👤 EDIT_BIRTH_DATE handled: {status}")
                
            elif callback_data == "edit_gender":
                status = await self.safe_edit_or_send_message(
                    context.bot, chat_id, message_id,
                    "⚧ <b>Выберите ваш пол</b>\n\n"
                    "💡 <i>Эта информация поможет адаптировать интерпретации specifically для вас</i>",
                    reply_markup=keyboards.get_gender_selection_keyboard()
                )
                logger.debug(f"👤 EDIT_GENDER handled: {status}")
                
            elif callback_data.startswith("gender_"):
                gender = callback_data.replace("gender_", "")
                gender_display = self.bot.profile_service._format_gender(gender)
                
                logger.info(f"⚧ Пользователь {user_id} выбрал пол: {gender_display}")
                
                try:
                    success = self.bot.profile_service.update_user_profile(user_id=user_id, gender=gender)
                    
                    if success:
                        await self.bot.show_profile(update, context)
                    else:
                        status = await self.safe_edit_or_send_message(
                            context.bot, chat_id, message_id,
                            "❌ Произошла ошибка при сохранении. Попробуйте позже.",
                            reply_markup=keyboards.get_back_to_menu_inline_keyboard()
                        )
                except Exception as e:
                    logger.exception(f"❌ Ошибка БД при обновлении пола пользователя {user_id}: {e}")
                    status = await self.safe_edit_or_send_message(
                        context.bot, chat_id, message_id,
                        "❌ Ошибка доступа к базе данных.",
                        reply_markup=keyboards.get_back_to_menu_inline_keyboard()
                    )
                        
            elif callback_data == "clear_profile":
                await self.handle_clear_profile_callback(update, context)
                        
            elif callback_data == "cancel_edit":
                await self.handle_cancel_edit_callback(update, context)
                    
        except Exception as e:
            logger.exception(f"❌ Критическая ошибка обработки callback профиля: {e}")
            status = await self.safe_edit_or_send_message(
                context.bot, chat_id, message_id,
                "❌ Произошла критическая ошибка. Попробуйте позже.",
                reply_markup=keyboards.get_back_to_menu_inline_keyboard()
            )

    async def handle_gender_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """⚧ ИСПРАВЛЕННЫЙ обработчик выбора пола - не очищает дату рождения"""
        query = update.callback_query
        # ✅ РАННИЙ ОТВЕТ ДЛЯ ПРЕДОТВРАЩЕНИЯ ПОВТОРНЫХ CALLBACK
        await query.answer(cache_time=1)
        
        user_id = query.from_user.id
        chat_id = query.message.chat_id
        message_id = query.message.message_id
        callback_data = query.data
        
        try:
            gender_map = {
                'gender_male': 'male',
                'gender_female': 'female', 
                'gender_other': 'other'
            }
            
            selected_gender = gender_map.get(callback_data)
            if selected_gender:
                gender_display = self.bot.profile_service._format_gender(selected_gender)
                logger.info(f"⚧ Пользователь {user_id} выбрал пол: {gender_display}")
                
                success = self.bot.user_db.update_user_profile(user_id=user_id, gender=selected_gender)
                
                if success:
                    await self.bot.show_profile(update, context)
                else:
                    status = await self.safe_edit_or_send_message(
                        context.bot, chat_id, message_id,
                        "❌ Произошла ошибка при сохранении. Попробуйте позже.",
                        reply_markup=keyboards.get_back_to_menu_inline_keyboard()
                    )
            else:
                logger.error(f"❌ Неизвестный выбор пола: {callback_data}")
                status = await self.safe_edit_or_send_message(
                    context.bot, chat_id, message_id,
                    "❌ Произошла ошибка при выборе пола.",
                    reply_markup=keyboards.get_back_to_menu_inline_keyboard()
                )
                    
        except Exception as e:
            logger.exception(f"❌ Критическая ошибка обработки выбора пола: {e}")
            status = await self.safe_edit_or_send_message(
                context.bot, chat_id, message_id,
                "❌ Произошла критическая ошибка. Попробуйте позже.",
                reply_markup=keyboards.get_back_to_menu_inline_keyboard()
            )

    async def handle_clear_profile_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """🗑️ Обработчик кнопки очистки профиля"""
        query = update.callback_query
        # ✅ РАННИЙ ОТВЕТ ДЛЯ ПРЕДОТВРАЩЕНИЯ ПОВТОРНЫХ CALLBACK
        await query.answer(cache_time=1)
        
        chat_id = query.message.chat_id
        message_id = query.message.message_id
        
        try:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Да, очистить", callback_data="confirm_clear_profile")],
                [InlineKeyboardButton("❌ Нет, отмена", callback_data="back_to_profile")]
            ])
            
            status = await self.safe_edit_or_send_message(
                context.bot, chat_id, message_id,
                "🗑️ <b>Очистка профиля</b>\n\n"
                "Вы уверены, что хотите очистить все данные профиля?\n\n"
                "❌ Дата рождения\n"
                "❌ Пол\n" 
                "❌ Возраст и знак зодиака\n\n"
                "Это действие нельзя отменить.",
                reply_markup=keyboard
            )
            logger.debug(f"🗑️ CLEAR_PROFILE handled: {status}")
            
        except Exception as e:
            logger.exception(f"❌ Ошибка показа подтверждения очистки профиля: {e}")
            status = await self.safe_edit_or_send_message(
                context.bot, chat_id, message_id,
                "❌ Произошла ошибка при запросе очистки профиля.",
                reply_markup=keyboards.get_back_to_profile_keyboard()
            )

    async def handle_confirm_clear_profile_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """🗑️ УЛУЧШЕННЫЙ обработчик подтверждения очистки профиля"""
        query = update.callback_query
        # ✅ РАННИЙ ОТВЕТ ДЛЯ ПРЕДОТВРАЩЕНИЯ ПОВТОРНЫХ CALLBACK
        await query.answer(cache_time=1)
        
        user_id = query.from_user.id
        chat_id = query.message.chat_id
        message_id = query.message.message_id
        
        try:
            success = self.bot.profile_service.clear_user_profile(user_id)
            
            if success:
                logger.info(f"✅ Пользователь {user_id} очистил профиль")
                
                profile_fields = [
                    'user_age', 'user_gender', 'user_name', 'editing_profile', 
                    'editing_field', 'awaiting_birth_date', 'user_profile_data',
                    'birth_date', 'gender', 'zodiac_sign', 'profile_complete',
                    'current_spread_id', 'waiting_for_custom_question', 'waiting_for_spread_question'
                ]
                for field in profile_fields:
                    context.user_data.pop(field, None)
                
                logger.debug(f"🧹 Контекст пользователя {user_id} очищен от данных профиля")
                await self.bot.show_profile(update, context)
                
            else:
                logger.error(f"❌ Не удалось очистить профиль пользователя {user_id}")
                status = await self.safe_edit_or_send_message(
                    context.bot, chat_id, message_id,
                    "❌ <b>Ошибка очистки</b>\n\nНе удалось очистить профиль. Попробуйте позже.",
                    reply_markup=keyboards.get_back_to_profile_keyboard()
                )
                
        except Exception as e:
            logger.exception(f"❌ Ошибка очистки профиля пользователя {user_id}: {e}")
            status = await self.safe_edit_or_send_message(
                context.bot, chat_id, message_id,
                "❌ <b>Системная ошибка</b>\n\nПроизошла ошибка при очистке профиля.",
                reply_markup=keyboards.get_back_to_menu_keyboard()
            )

    async def handle_cancel_edit_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """🛡️ Обработчик отмены редактирования профиля"""
        query = update.callback_query
        # ✅ РАННИЙ ОТВЕТ ДЛЯ ПРЕДОТВРАЩЕНИЯ ПОВТОРНЫХ CALLBACK
        await query.answer(cache_time=1)
        
        chat_id = query.message.chat_id
        message_id = query.message.message_id
        
        try:
            context.user_data.pop('editing_profile', None)
            context.user_data.pop('editing_field', None)
            context.user_data.pop('awaiting_birth_date', None)
            context.user_data.pop('waiting_for_custom_question', None)
            
            logger.debug(f"📝 Пользователь {query.from_user.id} отменил редактирование профиля")
            
            status = await self.safe_edit_or_send_message(
                context.bot, chat_id, message_id,
                "👤 <b>Редактирование отменено</b>\n\nВозврат к профилю...",
                reply_markup=keyboards.get_back_to_menu_inline_keyboard()
            )
            
            await self.bot.show_profile(update, context)
            
        except Exception as e:
            logger.exception(f"❌ Ошибка при отмене редактирования: {e}")
            status = await self.safe_edit_or_send_message(
                context.bot, chat_id, message_id,
                "❌ Произошла ошибка при отмене редактирования.",
                reply_markup=keyboards.get_back_to_menu_inline_keyboard()
            )

    async def handle_clear_history_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """🗑️ Обработчик кнопки очистки истории"""
        query = update.callback_query
        # ✅ РАННИЙ ОТВЕТ ДЛЯ ПРЕДОТВРАЩЕНИЯ ПОВТОРНЫХ CALLBACK
        await query.answer(cache_time=1)
        
        chat_id = query.message.chat_id
        message_id = query.message.message_id
        
        try:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Да, очистить всю историю", callback_data="confirm_clear_history")],
                [InlineKeyboardButton("❌ Нет, отмена", callback_data="back_to_history")]
            ])
            
            status = await self.safe_edit_or_send_message(
                context.bot, chat_id, message_id,
                "🗑️ <b>Очистка истории раскладов</b>\n\n"
                "⚠️ <b>Вы уверены, что хотите очистить всю историю?</b>\n\n"
                "• Все ваши расклады будут удалены\n"
                "• Все вопросы и ответы по раскладам будут удалены\n"
                "• Это действие нельзя отменить\n\n"
                "<i>После очистки история будет пуста</i>",
                reply_markup=keyboard
            )
            logger.debug(f"🗑️ CLEAR_HISTORY handled: {status}")
            
        except Exception as e:
            logger.exception(f"❌ Ошибка показа подтверждения очистки истории: {e}")
            status = await self.safe_edit_or_send_message(
                context.bot, chat_id, message_id,
                "❌ Произошла ошибка при запросе очистки истории.",
                reply_markup=keyboards.get_back_to_history_keyboard()
            )

    async def handle_confirm_clear_history_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """🗑️ Обработчик подтверждения очистки истории"""
        query = update.callback_query
        # ✅ РАННИЙ ОТВЕТ ДЛЯ ПРЕДОТВРАЩЕНИЯ ПОВТОРНЫХ CALLBACK
        await query.answer(cache_time=1)
        
        user_id = query.from_user.id
        chat_id = query.message.chat_id
        message_id = query.message.message_id
        
        try:
            success = self.bot.user_db.clear_user_history(user_id)
            
            if success:
                logger.info(f"✅ Пользователь {user_id} очистил историю раскладов")
                status = await self.safe_edit_or_send_message(
                    context.bot, chat_id, message_id,
                    "✅ <b>История раскладов очищена</b>\n\n"
                    "Все ваши расклады и вопросы были успешно удалены.\n\n"
                    "✨ Вы можете начать новую историю с чистого листа!",
                    reply_markup=keyboards.get_back_to_menu_keyboard()
                )
            else:
                logger.error(f"❌ Не удалось очистить историю пользователя {user_id}")
                status = await self.safe_edit_or_send_message(
                    context.bot, chat_id, message_id,
                    "❌ <b>Ошибка очистки истории</b>\n\n"
                    "Не удалось очистить историю. Попробуйте позже.",
                    reply_markup=keyboards.get_back_to_history_keyboard()
                )
                
        except Exception as e:
            logger.exception(f"❌ Ошибка очистки истории пользователя {user_id}: {e}")
            status = await self.safe_edit_or_send_message(
                context.bot, chat_id, message_id,
                "❌ <b>Системная ошибка</b>\n\n"
                "Произошла ошибка при очистке истории. Попробуйте позже.",
                reply_markup=keyboards.get_back_to_menu_keyboard()
            )

    async def handle_cancel_custom_question(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """❌ Обработчик отмены пользовательского вопроса"""
        query = update.callback_query
        # ✅ РАННИЙ ОТВЕТ ДЛЯ ПРЕДОТВРАЩЕНИЯ ПОВТОРНЫХ CALLBACK
        await query.answer(cache_time=1)
        
        chat_id = query.message.chat_id
        message_id = query.message.message_id
        
        # 🔧 ИСПРАВЛЕНИЕ: Очищаем новый флаг
        context.user_data.pop('awaiting_custom_question_for', None)
        context.user_data.pop('waiting_for_custom_question', None)
        context.user_data.pop('selected_category', None)
        
        # ВОЗВРАЩАЕМСЯ К ВЫБОРУ КАТЕГОРИИ
        status = await self.safe_edit_or_send_message(
            context.bot, chat_id, message_id,
            "❌ <b>Ввод вопроса отменен</b>\n\nВыберите категорию вопроса:",
            reply_markup=keyboards.get_categories_keyboard()
        )
        logger.debug(f"❌ CANCEL_CUSTOM_QUESTION handled: {status}")

    async def handle_cancel_spread_question(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """🛡️ Безопасный обработчик отмены вопроса по раскладу"""
        query = update.callback_query
        # ✅ РАННИЙ ОТВЕТ ДЛЯ ПРЕДОТВРАЩЕНИЯ ПОВТОРНЫХ CALLBACK
        await query.answer(cache_time=1)
        
        chat_id = query.message.chat_id
        message_id = query.message.message_id
        
        try:
            # 🔧 ИСПРАВЛЕНИЕ: Очищаем оба флага на всякий случай
            context.user_data.pop('waiting_for_spread_question', None)
            context.user_data.pop('awaiting_custom_question_for', None)
            await self.bot.show_main_menu(update, context)
        except Exception as e:
            logger.exception(f"❌ Ошибка в handle_cancel_spread_question: {e}")
            status = await self.safe_edit_or_send_message(
                context.bot, chat_id, message_id,
                "❌ Произошла ошибка при отмене.",
                reply_markup=keyboards.get_back_to_menu_keyboard()
            )

    async def handle_unknown_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """🔄 Обработчик для неизвестных callback'ов с улучшенной диагностикой"""
        query = update.callback_query
        # ✅ РАННИЙ ОТВЕТ ДЛЯ ПРЕДОТВРАЩЕНИЯ ПОВТОРНЫХ CALLBACK
        await query.answer(cache_time=1)
        
        chat_id = query.message.chat_id
        message_id = query.message.message_id
        
        # 🔧 ДОБАВЛЕНО: Детальное логирование неизвестных callback'ов
        logger.warning(f"❓ НЕОБРАБОТАННЫЙ CALLBACK: user={query.from_user.id}, data='{query.data}', message_id={message_id}")
        
        status = await self.safe_edit_or_send_message(
            context.bot, chat_id, message_id,
            "❌ <b>Неизвестная команда</b>\n\nЭта кнопка временно не работает. Пожалуйста, используйте кнопки меню.",
            reply_markup=keyboards.get_back_to_menu_keyboard()
        )
        logger.warning(f"❓ UNKNOWN_CALLBACK handled: {status}")

    async def handle_back_to_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """👤 Обработчик возврата к профилю"""
        query = update.callback_query
        # ✅ РАННИЙ ОТВЕТ ДЛЯ ПРЕДОТВРАЩЕНИЯ ПОВТОРНЫХ CALLBACK
        await query.answer(cache_time=1)
        
        try:
            await self.bot.show_profile(update, context)
        except Exception as e:
            logger.exception(f"❌ Ошибка возврата к профилю: {e}")
            status = await self.safe_edit_or_send_message(
                context.bot, query.message.chat_id, query.message.message_id,
                "❌ Произошла ошибка при загрузке профиля.",
                reply_markup=keyboards.get_back_to_menu_keyboard()
            )

    async def send_card_selection_interface(self, update: Update, context: ContextTypes.DEFAULT_TYPE, session_id: str, position: int):
        """🃏 ИСПРАВЛЕННЫЙ метод отправки интерфейса выбора карты для указанной позиции"""
        try:
            query = update.callback_query
            chat_id = query.message.chat_id
            message_id = query.message.message_id
            
            spread_type = context.user_data.get('selected_spread_type', 'single')
            
            if spread_type == 'single':
                selection_text = (
                    "🃏 <b>Выбор карты для расклада</b>\n\n"
                    "✨ <i>Выберите одну из пяти карт ниже. Каждая карта будет случайным образом определена системой.</i>\n\n"
                    "💫 <b>Просто доверьтесь интуиции и выберите номер карты!</b>"
                )
            else:
                position_names = {
                    1: "🕰️ <b>Прошлое</b> - ситуация, которая привела к настоящему",
                    2: "🌅 <b>Настоящее</b> - текущее положение дел", 
                    3: "🔮 <b>Будущее</b> - возможное развитие событий"
                }
                
                selection_text = (
                    f"{position_names.get(position, f'Позиция {position}')}\n\n"
                    "✨ <i>Выберите одну из пяти карт. Каждая карта будет случайным образом определена системой.</i>\n\n"
                    f"📋 <b>Позиция {position}/3</b>"
                )
            
            # ✅ ИСПРАВЛЕНО: Используем клавиатуры из card_service или fallback
            if self.card_service and hasattr(self.card_service, 'get_card_selection_keyboard'):
                keyboard = self.card_service.get_card_selection_keyboard(session_id, position)
            else:
                # Fallback клавиатура
                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton("1️⃣", callback_data=f"card_choice:{session_id}:{position}:1"),
                    InlineKeyboardButton("2️⃣", callback_data=f"card_choice:{session_id}:{position}:2"),
                    InlineKeyboardButton("3️⃣", callback_data=f"card_choice:{session_id}:{position}:3"),
                    InlineKeyboardButton("4️⃣", callback_data=f"card_choice:{session_id}:{position}:4"),
                    InlineKeyboardButton("5️⃣", callback_data=f"card_choice:{session_id}:{position}:5")
                ]])
            
            status = await self.safe_edit_or_send_message(
                context.bot, chat_id, message_id, selection_text, keyboard
            )
            logger.debug(f"🎴 CARD_SELECTION_{position} handled: {status}")
            
        except Exception as e:
            logger.exception(f"❌ Ошибка отправки интерфейса выбора карты: {e}")
            status = await self.safe_edit_or_send_message(
                context.bot, query.message.chat_id, query.message.message_id,
                "❌ Ошибка при загрузке интерфейса выбора карт",
                reply_markup=keyboards.get_back_to_menu_keyboard()
            )

    async def show_continue_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE, session_id: str, current_position: int):
        """➡️ УЛУЧШЕННЫЙ интерфейс продолжения выбора для three раскладов с прогрессом"""
        try:
            query = update.callback_query
            chat_id = query.message.chat_id
            message_id = query.message.message_id
            
            position_names = {
                1: "🕰️ <b>Прошлое</b>",
                2: "🌅 <b>Настоящее</b>", 
                3: "🔮 <b>Будущее</b>"
            }
            
            progress = f"📊 Прогресс: {current_position}/3"
            progress_bar = "🟢" * current_position + "⚪" * (3 - current_position)
            
            continue_text = (
                f"✅ <b>Карта {position_names.get(current_position)} выбрана!</b>\n\n"
                f"{progress}\n{progress_bar}\n\n"
                f"➡️ <b>Готовы выбрать следующую карту?</b>"
            )
            
            # ✅ ИСПРАВЛЕНО: Используем клавиатуры из card_service или fallback
            if self.card_service and hasattr(self.card_service, 'get_continue_selection_keyboard'):
                keyboard = self.card_service.get_continue_selection_keyboard(session_id, current_position + 1)
            else:
                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton("➡️ Продолжить", callback_data=f"continue_select:{session_id}:{current_position + 1}")
                ]])
            
            status = await self.safe_edit_or_send_message(
                context.bot, chat_id, message_id, continue_text, keyboard
            )
            logger.debug(f"➡️ CONTINUE_SELECTION_{current_position} handled: {status}")
            
        except Exception as e:
            logger.exception(f"❌ Ошибка показа интерфейса продолжения: {e}")
            status = await self.safe_edit_or_send_message(
                context.bot, query.message.chat_id, query.message.message_id,
                "❌ Ошибка при продолжении выбора",
                reply_markup=keyboards.get_back_to_menu_keyboard()
            )

    async def format_spread_result_with_ai(self, result_data: dict, spread_type: str) -> str:
        """📝 УЛУЧШЕННОЕ форматирование результата расклада с AI-интерпретацией и правильным типом"""
        try:
            cards = result_data.get('cards', [])
            interpretation = result_data.get('interpretation', '')
            category = result_data.get('category', 'Общий вопрос')
            
            # ✅ ИСПРАВЛЕНИЕ: Используем переданный spread_type вместо получения из result_data
            if spread_type == 'single':
                card = cards[0] if cards else {}
                result_text = (
                    f"🎴 <b>Твой расклад завершен!</b>\n\n"
                    f"📊 <b>Тип:</b> Расклад на 1 карту\n"
                    f"🎯 <b>Категория:</b> {category}\n\n"
                    f"🃏 <b>Выпавшая карта:</b> {card.get('name', 'Неизвестно')}\n"
                    f"📖 <b>Значение:</b> {card.get('meaning', '')}\n\n"
                    f"💫 <b>AI-интерпретация:</b>\n{interpretation}\n\n"
                    f"✨ <i>Используйте кнопку ниже, чтобы задать дополнительные вопросы</i>"
                )
            else:
                position_names = ["🕰️ <b>Прошлое</b> - ситуация, которая привела к настоящему", 
                                "🌅 <b>Настоящее</b> - текущее положение дел", 
                                "🔮 <b>Будущее</b> - возможное развитие событий"]
                
                cards_text = ""
                
                for i, card in enumerate(cards):
                    if i < len(position_names):
                        cards_text += (
                            f"{position_names[i]}:\n"
                            f"   🃏 <b>{card.get('name', 'Неизвестно')}</b>\n"
                            f"   📖 {card.get('meaning', '')}\n\n"
                        )
                
                result_text = (
                    f"🎴 <b>Твой расклад завершен!</b>\n\n"
                    f"📊 <b>Тип:</b> Расклад на 3 карты\n"
                    f"🎯 <b>Категория:</b> {category}\n\n"
                    f"{cards_text}"
                    f"💫 <b>AI-интерпретация:</b>\n{interpretation}\n\n"
                    f"✨ <i>Используйте кнопку ниже, чтобы задать дополнительные вопросы</i>"
                )
            
            return result_text
            
        except Exception as e:
            logger.exception(f"❌ Ошибка форматирования результата расклада с AI: {e}")
            return (
                "🎴 <b>Твой расклад завершен!</b>\n\n"
                "💫 <b>AI-интерпретация генерируется...</b>\n\n"
                "✨ <i>Используйте кнопку ниже, чтобы задать дополнительные вопросы</i>"
            )

    async def format_spread_result(self, result_data: dict) -> str:
        """📝 Форматирует результат расклада для показа пользователю"""
        try:
            spread_type = result_data.get('spread_type', 'single')
            cards = result_data.get('cards', [])
            interpretation = result_data.get('interpretation', '')
            category = result_data.get('category', 'Общий вопрос')
            
            if spread_type == 'single':
                card = cards[0] if cards else {}
                result_text = (
                    f"🎴 <b>Твой расклад завершен!</b>\n\n"
                    f"📊 <b>Тип:</b> Расклад на 1 карту\n"
                    f"🎯 <b>Категория:</b> {category}\n\n"
                    f"🃏 <b>Выпавшая карта:</b> {card.get('name', 'Неизвестно')}\n"
                    f"📖 <b>Значение:</b> {card.get('meaning', '')}\n\n"
                    f"💫 <b>Интерпретация:</b>\n{interpretation}\n\n"
                    f"<i>Используй /history чтобы посмотреть историю раскладов</i>"
                )
            else:
                position_names = ["🕰️ Прошлое", "🌅 Настоящее", "🔮 Будущее"]
                cards_text = ""
                
                for i, card in enumerate(cards):
                    if i < len(position_names):
                        cards_text += (
                            f"{position_names[i]}:\n"
                            f"   🃏 <b>{card.get('name', 'Неизвестно')}</b>\n"
                            f"   📖 {card.get('meaning', '')}\n\n"
                        )
                
                result_text = (
                    f"🎴 <b>Твой расклад завершен!</b>\n\n"
                    f"📊 <b>Тип:</b> Расклад на 3 карты\n"
                    f"🎯 <b>Категория:</b> {category}\n\n"
                    f"{cards_text}"
                    f"💫 <b>Общая интерпретация:</b>\n{interpretation}\n\n"
                    f"<i>Используй /history чтобы посмотреть историю раскладов</i>"
                )
            
            return result_text
            
        except Exception as e:
            logger.exception(f"❌ Ошибка форматирования результата расклада: {e}")
            return "❌ Произошла ошибка при форматировании результата расклада."

    def setup_handlers(self):
        """🔧 Регистрация всех callback обработчиков с ПРАВИЛЬНЫМИ PATTERN'ами"""
        logger.info("🔧 Начинаем регистрацию callback обработчиков...")
        
        # ✅ ОСНОВНЫЕ ОБРАБОТЧИКИ СТРАНИЦ (точное совпадение с pattern'ами)
        self.application.add_handler(CallbackQueryHandler(self.handle_main_menu_callback, pattern="^main_menu$"))
        logger.debug("✅ Обработчик main_menu зарегистрирован")
        
        self.application.add_handler(CallbackQueryHandler(self.handle_back_to_history, pattern="^back_to_history$"))
        logger.debug("✅ Обработчик back_to_history зарегистрирован")
        
        self.application.add_handler(CallbackQueryHandler(self.handle_back_to_menu, pattern="^back_to_menu$"))
        logger.debug("✅ Обработчик back_to_menu зарегистрирован")
        
        self.application.add_handler(CallbackQueryHandler(self.handle_back_to_profile, pattern="^back_to_profile$"))
        logger.debug("✅ Обработчик back_to_profile зарегистрирован")
        
        # ✅ НОВЫЙ ОБРАБОТЧИК ПРОФИЛЯ
        self.application.add_handler(CallbackQueryHandler(self.handle_profile_callback, pattern="^profile$"))
        logger.debug("✅ Обработчик profile зарегистрирован")
        
        # ✅ ОБРАБОТЧИКИ РАСКЛАДОВ И ВОПРОСОВ
        self.application.add_handler(CallbackQueryHandler(self.handle_spread_details_callback, pattern="^details_"))
        logger.debug("✅ Обработчик details_ зарегистрирован")
        
        self.application.add_handler(CallbackQueryHandler(self.handle_ask_question_callback, pattern="^ask_question_"))
        logger.debug("✅ Обработчик ask_question_ зарегистрирован")
        
        self.application.add_handler(CallbackQueryHandler(self.handle_view_question_callback, pattern="^view_question_"))
        logger.debug("✅ Обработчик view_question_ зарегистрирован")
        
        self.application.add_handler(CallbackQueryHandler(self.handle_view_questions_callback, pattern="^view_questions_"))
        logger.debug("✅ Обработчик view_questions_ зарегистрирован")
        
        self.application.add_handler(CallbackQueryHandler(self.handle_history_pagination_callback, pattern="^history_page_"))
        logger.debug("✅ Обработчик history_page_ зарегистрирован")
        
        # ✅ ОБРАБОТЧИКИ ВЫБОРА ТИПА И КАТЕГОРИИ
        self.application.add_handler(CallbackQueryHandler(self.handle_spread_type_selection, pattern="^(spread_single|spread_three)$"))
        logger.debug("✅ Обработчик spread_type зарегистрирован")
        
        self.application.add_handler(CallbackQueryHandler(self.handle_category_selection, pattern="^category_"))
        logger.debug("✅ Обработчик category_ зарегистрирован")
        
        # ✅ ОБРАБОТЧИКИ ИНТЕРАКТИВНОГО ВЫБОРА КАРТ (точное совпадение)
        self.application.add_handler(CallbackQueryHandler(self.handle_card_choice_callback, pattern="^card_choice:"))
        logger.debug("✅ Обработчик card_choice зарегистрирован")
        
        self.application.add_handler(CallbackQueryHandler(self.handle_continue_selection, pattern="^continue_select:"))
        logger.debug("✅ Обработчик continue_select зарегистрирован")
        
        self.application.add_handler(CallbackQueryHandler(self.handle_back_to_selection_callback, pattern="^back_to_select:"))
        logger.debug("✅ Обработчик back_to_select зарегистрирован")
        
        # ✅ ОБРАБОТЧИКИ ПРОФИЛЯ (редактирование)
        self.application.add_handler(CallbackQueryHandler(self.handle_profile_edit_callback, pattern="^(edit_|clear_profile$|cancel_edit$)"))
        logger.debug("✅ Обработчик профиля зарегистрирован")
        
        self.application.add_handler(CallbackQueryHandler(self.handle_gender_selection, pattern="^gender_"))
        logger.debug("✅ Обработчик gender_ зарегистрирован")
        
        # ✅ ОБРАБОТЧИКИ ПОДТВЕРЖДЕНИЙ И ОТМЕН
        self.application.add_handler(CallbackQueryHandler(self.handle_clear_profile_callback, pattern="^clear_profile$"))
        logger.debug("✅ Обработчик clear_profile зарегистрирован")
        
        self.application.add_handler(CallbackQueryHandler(self.handle_confirm_clear_profile_callback, pattern="^confirm_clear_profile$"))
        logger.debug("✅ Обработчик confirm_clear_profile зарегистрирован")
        
        self.application.add_handler(CallbackQueryHandler(self.handle_clear_history_callback, pattern="^clear_history$"))
        logger.debug("✅ Обработчик clear_history зарегистрирован")
        
        self.application.add_handler(CallbackQueryHandler(self.handle_confirm_clear_history_callback, pattern="^confirm_clear_history$"))
        logger.debug("✅ Обработчик confirm_clear_history зарегистрирован")
        
        self.application.add_handler(CallbackQueryHandler(self.handle_cancel_custom_question, pattern="^cancel_custom_question$"))
        logger.debug("✅ Обработчик cancel_custom_question зарегистрирован")
        
        self.application.add_handler(CallbackQueryHandler(self.handle_cancel_spread_question, pattern="^cancel_spread_question$"))
        logger.debug("✅ Обработчик cancel_spread_question зарегистрирован")
        
        # 🔧 ОБРАБОТЧИК НЕИЗВЕСТНЫХ CALLBACK'ОВ (должен быть ПОСЛЕДНИМ)
        self.application.add_handler(CallbackQueryHandler(self.handle_unknown_callback, pattern=".*"))
        logger.debug("✅ Обработчик unknown_callback зарегистрирован")
        
        handler_count = len(self.application.handlers[0]) if self.application.handlers else 0
        logger.info(f"🔧 Всего зарегистрировано обработчиков: {handler_count}")
        logger.info("✅ Все callback обработчики успешно зарегистрированы с правильными pattern'ами")