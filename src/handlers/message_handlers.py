# src/handlers/message_handlers.py
import logging
import re
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes, MessageHandler, filters
from .. import keyboards

logger = logging.getLogger(__name__)

class MessageHandlers:
    def __init__(self, bot_instance, application, card_service):
        """
        Исправленный конструктор с инъекцией зависимостей
        
        Args:
            bot_instance: Экземпляр основного бота
            application: Экземпляр Application из python-telegram-bot
            card_service: Сервис для работы с картами и раскладами
        """
        self.bot = bot_instance
        self.application = application
        self.card_service = card_service

    async def handle_text_messages(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Унифицированная обработка текстовых сообщений с гарантированными inline-клавиатурами"""
        
        user_id = update.effective_user.id
        text = update.message.text.strip()
        
        logger.debug(f"Text message from user {user_id}")
        
        if not self.card_service:
            logger.error("card_service unavailable")
            await self._safe_reply_with_menu(update, "❌ Сервис временно недоступен.")
            return
        
        # Проверяем ожидание пользовательского вопроса
        awaiting = context.user_data.get('awaiting_custom_question_for')
        if awaiting:
            await self.handle_custom_question(update, context)
            return
        
        # Обратная совместимость
        if context.user_data.get('waiting_for_custom_question'):
            await self.handle_custom_question(update, context)
            return
            
        # Вопросы по существующим раскладам
        elif 'current_spread_id' in context.user_data:
            await self.handle_spread_question(update, context)
            return
        
        # Редактирование даты рождения
        elif context.user_data.get('editing_profile') and context.user_data.get('editing_field') == 'birth_date':
            await self.handle_birth_date_input(update, context)
            return
        
        # Автоопределение даты рождения
        elif re.match(r'\d{2}\.\d{2}\.\d{4}', text):
            await self.handle_birth_date_input(update, context)
            return
        
        # Обработка команд главного меню
        elif text == "🎴 Карта дня":
            logger.info(f"User {user_id} selected single spread")
            context.user_data['selected_spread_type'] = 'single'
            await self._send_categories_menu(update, "single")
            
        elif text == "🔮 3 карты":
            logger.info(f"User {user_id} selected three-card spread")
            context.user_data['selected_spread_type'] = 'three'
            await self._send_categories_menu(update, "three")
            
        elif text == "📖 История раскладов":
            logger.info(f"User {user_id} requested history")
            await self.bot.command_handlers.handle_history(update, context)
            
        elif text == "👤 Профиль":
            logger.info(f"User {user_id} requested profile")
            await self.bot.command_handlers.handle_profile(update, context)
            
        elif text == "ℹ️ Помощь":
            logger.info(f"User {user_id} requested help")
            await self.bot.command_handlers.handle_help(update, context)
            
        elif text == "🏠 Главное меню":
            logger.info(f"User {user_id} requested main menu")
            await self._safe_reply_with_menu(update, "🏠 <b>Главное меню</b>")
            
        else:
            logger.debug(f"Unknown text from user {user_id}")
            await self._safe_reply_with_menu(
                update, 
                "Неизвестная команда. Используйте кнопки меню или команды."
            )

    async def _safe_reply_with_menu(self, update: Update, text: str, parse_mode: str = 'HTML'):
        """Безопасная отправка сообщения с главным меню"""
        try:
            menu_keyboard = keyboards.get_main_menu_keyboard()
            # Гарантируем, что это InlineKeyboardMarkup
            if not isinstance(menu_keyboard, InlineKeyboardMarkup):
                logger.warning("get_main_menu_keyboard() returned non-inline keyboard, creating inline")
                menu_keyboard = InlineKeyboardMarkup([])
                
            await update.message.reply_text(
                text,
                parse_mode=parse_mode,
                reply_markup=menu_keyboard
            )
        except Exception as e:
            logger.error(f"Error sending menu message: {e}")
            # Fallback: отправка без клавиатуры
            await update.message.reply_text(text, parse_mode=parse_mode)

    async def _send_categories_menu(self, update: Update, spread_type: str):
        """Отправка меню категорий с гарантированной inline-клавиатурой"""
        spread_text = "1 карту" if spread_type == "single" else "3 карты"
        
        try:
            categories_keyboard = keyboards.get_categories_keyboard()
            # Гарантируем, что это InlineKeyboardMarkup
            if not isinstance(categories_keyboard, InlineKeyboardMarkup):
                logger.warning("get_categories_keyboard() returned non-inline keyboard, creating inline")
                categories_keyboard = InlineKeyboardMarkup([])
                
            await update.message.reply_text(
                f"🔮 <b>Выберите категорию для расклада на {spread_text}:</b>",
                parse_mode='HTML',
                reply_markup=categories_keyboard
            )
        except Exception as e:
            logger.error(f"Error sending categories menu: {e}")
            await self._safe_reply_with_menu(
                update,
                "❌ Ошибка при загрузке категорий. Попробуйте позже."
            )

    async def handle_custom_question(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик пользовательских вопросов с гарантированными клавиатурами"""
        user_id = update.effective_user.id
        user_question = update.message.text.strip()

        card_srv = getattr(self, 'card_service', None)
        if not card_srv:
            logger.error("card_service unavailable")
            await self._safe_reply_with_menu(
                update,
                "❌ Внутренняя ошибка: сервис карт недоступен."
            )
            return

        # Краткий summary методов
        expected_methods = [
            'start_interactive_spread',
            'send_card_selection_interface', 
            'generate_spread',
            'complete_interactive_spread',
            'generate_basic_interpretation'
        ]
        
        available_count = sum(1 for m in expected_methods if getattr(card_srv, m, None) is not None)
        logger.info(f"CardService methods available: {available_count}/{len(expected_methods)}")

        # Получаем методы с проверкой
        available_methods = {
            'start_interactive_spread': getattr(card_srv, 'start_interactive_spread', None),
            'send_card_selection_interface': getattr(card_srv, 'send_card_selection_interface', None),
            'generate_spread': getattr(card_srv, 'generate_spread', None),
            'complete_interactive_spread': getattr(card_srv, 'complete_interactive_spread', None),
            'generate_basic_interpretation': getattr(card_srv, 'generate_basic_interpretation', None)
        }

        awaiting = context.user_data.pop('awaiting_custom_question_for', None)
        # Обратная совместимость
        if not awaiting and context.user_data.get('waiting_for_custom_question'):
            spread_type = context.user_data.get('selected_spread_type', 'single')
            return_action = 'start_interactive' if spread_type == 'three' else 'generate_spread'
            awaiting = {
                'spread_type': spread_type,
                'return_action': return_action
            }
            context.user_data.pop('waiting_for_custom_question', None)

        if not awaiting:
            await self._safe_reply_with_menu(update, "❌ Нечего обрабатывать.")
            return

        # Валидация вопроса
        if len(user_question) < 5:
            context.user_data['awaiting_custom_question_for'] = awaiting
            await self._safe_reply_with_menu(
                update,
                "❌ Вопрос слишком короткий. Пожалуйста, сформулируйте более развернутый вопрос."
            )
            return

        if len(user_question) > 500:
            context.user_data['awaiting_custom_question_for'] = awaiting
            await self._safe_reply_with_menu(
                update,
                "❌ Вопрос слишком длинный. Сформулируйте короче (до 500 символов)."
            )
            return

        spread_type = awaiting.get('spread_type', 'single')
        action = awaiting.get('return_action', 'generate_spread')

        logger.info(f"Custom question from {user_id}, spread: {spread_type}, action: {action}")

        try:
            if action == 'ask_on_spread':
                await self._handle_ask_on_spread(update, context, user_id, awaiting, user_question)
                return

            elif action == 'start_interactive':
                await self._handle_three_card_spread(
                    update, context, user_id, spread_type, user_question, available_methods
                )
                return

            else:
                await self._handle_single_card_spread(
                    update, context, user_id, spread_type, user_question, available_methods
                )
                return

        except Exception as e:
            logger.exception(f"Error processing custom question: {e}")
            await self._safe_reply_with_menu(
                update,
                "❌ Произошла ошибка при создании расклада. Попробуйте позже."
            )

    async def _handle_ask_on_spread(self, update, context, user_id, awaiting, user_question):
        """Обработка вопроса по существующему раскладу"""
        spread_id = awaiting.get('spread_id')
        if not spread_id:
            await self._safe_reply_with_menu(
                update,
                "❌ Нечего обрабатывать (нет id расклада)."
            )
            return

        try:
            question_id = self.bot.user_db.add_question_to_spread(
                spread_id=spread_id, 
                question_text=user_question, 
                answer=None
            )
            
            if not question_id:
                raise Exception("DB save failed")
            
            logger.debug(f"Question saved for spread {spread_id}")
            
            await self._safe_reply_with_menu(
                update,
                "✅ Вопрос сохранён. Я пришлю ответ, когда он будет готов."
            )
            
            user_data = self.bot.user_db.get_user_data(user_id)
            user_age = user_data.get('age') if user_data else None
            user_gender = user_data.get('gender') if user_data else None
            user_name = user_data.get('name', 'друг')
            
            # Фоновая задача
            asyncio.create_task(
                self._generate_and_save_answer(
                    user_id=user_id,
                    spread_id=spread_id,
                    question_id=question_id,
                    question_text=user_question,
                    user_age=user_age,
                    user_gender=user_gender,
                    user_name=user_name,
                    chat_id=update.effective_chat.id,
                    context=context
                )
            )
            
        except Exception as e:
            logger.error(f"Error saving question for spread_id={spread_id}: {e}")
            await self._safe_reply_with_menu(
                update,
                "❌ Не удалось сохранить вопрос. Попробуйте позже."
            )

    async def _handle_three_card_spread(self, update, context, user_id, spread_type, user_question, methods):
        """Обработка three-card расклада"""
        start_spread = methods['start_interactive_spread']
        send_iface = methods['send_card_selection_interface']
        complete_spread = methods['complete_interactive_spread']
        
        # Уровень 1: Полный интерактивный процесс
        if start_spread and send_iface:
            try:
                session_id = await start_spread(
                    user_id=user_id,
                    spread_type=spread_type,
                    category=user_question,
                    chat_id=update.effective_chat.id,
                    context=context,
                    bot=context.bot
                )
                
                if session_id:
                    context.user_data['current_session_id'] = session_id
                    await send_iface(update, context, session_id, position=1)
                    return
            except Exception as e:
                logger.error(f"Error in interactive three-card spread: {e}")

        # Уровень 2: Прямое завершение
        if start_spread and complete_spread:
            try:
                session_id = await start_spread(
                    user_id=user_id,
                    spread_type=spread_type,
                    category=user_question,
                    chat_id=update.effective_chat.id,
                    context=context,
                    bot=context.bot
                )
                if session_id:
                    await complete_spread(session_id, bot=context.bot, chat_id=update.effective_chat.id, context=context)
                    return
            except Exception as e:
                logger.error(f"Error completing three-card spread: {e}")

        # Уровень 3: Fallback
        await self._fallback_generate_spread(update, context, user_id, spread_type, user_question, methods)

    async def _handle_single_card_spread(self, update, context, user_id, spread_type, user_question, methods):
        """Обработка single-card расклада"""
        generate_spread = methods['generate_spread']
        
        # Уровень 1: Прямая генерация
        if generate_spread:
            try:
                await generate_spread(
                    user_id=user_id,
                    spread_type=spread_type,
                    category=user_question,
                    chat_id=update.effective_chat.id,
                    context=context,
                    bot=context.bot
                )
                return
            except Exception as e:
                logger.error(f"Error in generate_spread: {e}")

        # Уровень 2: Интерактивный процесс
        start_spread = methods['start_interactive_spread']
        complete_spread = methods['complete_interactive_spread']
        
        if start_spread and complete_spread:
            try:
                session_id = await start_spread(
                    user_id=user_id,
                    spread_type=spread_type,
                    category=user_question,
                    chat_id=update.effective_chat.id,
                    context=context,
                    bot=context.bot
                )
                
                if session_id:
                    context.user_data['current_session_id'] = session_id
                    await complete_spread(session_id, bot=context.bot, chat_id=update.effective_chat.id, context=context)
                    return
            except Exception as e:
                logger.error(f"Error in interactive single-card spread: {e}")

        # Уровень 3: Fallback
        await self._fallback_generate_spread(update, context, user_id, spread_type, user_question, methods)

    async def _fallback_generate_spread(self, update, context, user_id, spread_type, user_question, methods):
        """Универсальный fallback"""
        generate_basic = methods['generate_basic_interpretation']
        generate_spread = methods['generate_spread']
        
        if generate_basic:
            try:
                await generate_basic(
                    user_id=user_id,
                    spread_type=spread_type,
                    category=user_question,
                    chat_id=update.effective_chat.id,
                    context=context
                )
                return
            except Exception as e:
                logger.error(f"Error in generate_basic_interpretation: {e}")

        if generate_spread:
            try:
                await generate_spread(
                    user_id=user_id,
                    spread_type=spread_type,
                    category=user_question,
                    chat_id=update.effective_chat.id,
                    context=context,
                    bot=context.bot
                )
                return
            except Exception as e:
                logger.error(f"Error in generate_spread fallback: {e}")

        # Последний вариант
        logger.error("All spread generation methods unavailable")
        await self._safe_reply_with_menu(
            update,
            "❌ Внутренняя ошибка: невозможно создать расклад сейчас. Попробуйте позже."
        )

    async def _generate_and_save_answer(self, user_id, spread_id, question_id, question_text, 
                                       user_age, user_gender, user_name, chat_id, context):
        """Фоновая задача для генерации ответа"""
        try:
            logger.debug(f"Background answer generation for question {question_id}")
            
            if not hasattr(self.bot, 'ai_service') or not self.bot.ai_service:
                logger.error("AI service unavailable for background task")
                self.bot.user_db.update_question_answer(
                    question_id, 
                    "❌ Сервис генерации ответов временно недоступен."
                )
                return
            
            answer = await self.bot.ai_service.generate_question_answer(
                user_id=user_id,
                spread_id=spread_id,
                question=question_text,
                user_age=user_age,
                user_gender=user_gender,
                user_name=user_name
            )
            
            if answer:
                success = self.bot.user_db.update_question_answer(question_id, answer)
                
                if success:
                    logger.info(f"Answer generated and saved for question {question_id}")
                    
                    try:
                        # Используем безопасную отправку с меню
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=f"💭 <b>Ответ на ваш вопрос по раскладу:</b>\n\n{answer}",
                            parse_mode='HTML',
                            reply_markup=keyboards.get_main_menu_keyboard()
                        )
                    except Exception as send_error:
                        logger.error(f"Failed to send answer message: {send_error}")
                else:
                    logger.error(f"Failed to save answer for question {question_id}")
            else:
                logger.warning(f"AI failed to generate answer for question {question_id}")
                self.bot.user_db.update_question_answer(
                    question_id, 
                    "❌ Не удалось сгенерировать ответ. Пожалуйста, попробуйте позже."
                )
                
        except Exception as e:
            logger.error(f"Error in background answer generation: {e}")

    async def handle_spread_question(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик вопросов по раскладам"""
        user_id = update.effective_user.id
        question_text = update.message.text
        
        if not context.user_data.get('current_spread_id'):
            await self._safe_reply_with_menu(update, "🏠 <b>Главное меню</b>")
            return
        
        spread_id = context.user_data.get('current_spread_id')
        user_age = context.user_data.get('user_age')
        user_gender = context.user_data.get('user_gender')
        user_name = context.user_data.get('user_name', 'друг')
        
        # Сбрасываем состояние
        context.user_data.pop('current_spread_id', None)
        context.user_data.pop('user_age', None)
        context.user_data.pop('user_gender', None)
        context.user_data.pop('user_name', None)
        
        logger.debug(f"User {user_id} asked question about spread {spread_id}")
        
        # Валидация
        if len(question_text) < 5:
            await self._safe_reply_with_menu(
                update,
                "❌ Вопрос слишком короткий. Пожалуйста, сформулируйте более развернутый вопрос."
            )
            return
        
        if len(question_text) > 500:
            await self._safe_reply_with_menu(
                update,
                "❌ Вопрос слишком длинный. Пожалуйста, сформулируйте вопрос короче."
            )
            return
        
        try:
            processing_msg = await update.message.reply_text(
                "🔄 Обрабатываю ваш вопрос...",
                reply_markup=keyboards.get_main_menu_keyboard()
            )
            
            # Проверяем существование расклада
            history = self.bot.user_db.get_user_history(user_id, limit=100)
            spread_data = next((spread for spread in history if spread.get('id') == spread_id), None)
            
            if not spread_data:
                await processing_msg.delete()
                await self._safe_reply_with_menu(update, "❌ Расклад не найден.")
                return
            
            # Сохраняем вопрос
            question_id = self.bot.user_db.add_question_to_spread(spread_id, question_text, None)
            
            if not question_id:
                await processing_msg.delete()
                await self._safe_reply_with_menu(
                    update,
                    "❌ Произошла ошибка при сохранении вопроса."
                )
                return
            
            logger.debug(f"Question saved with ID: {question_id}")
            
            # Фоновая задача
            asyncio.create_task(
                self._generate_and_save_answer(
                    user_id=user_id,
                    spread_id=spread_id,
                    question_id=question_id,
                    question_text=question_text,
                    user_age=user_age,
                    user_gender=user_gender,
                    user_name=user_name,
                    chat_id=update.effective_chat.id,
                    context=context
                )
            )
            
            await processing_msg.delete()
            await self._safe_reply_with_menu(
                update,
                "✅ Вопрос сохранён. Я пришлю ответ, когда он будет готов."
            )
                    
        except Exception as e:
            logger.error(f"Error processing spread question: {e}")
            await self._safe_reply_with_menu(
                update,
                "❌ Произошла ошибка при обработке вопроса."
            )

    async def handle_birth_date_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик ввода даты рождения"""
        user_id = update.effective_user.id
        text = update.message.text.strip()
        
        logger.debug(f"User {user_id} entered birth date: {text}")
        
        # Проверка формата
        if not re.match(r'^\d{2}\.\d{2}\.\d{4}$', text):
            await self._send_validation_error(update.message, 'format', '15.05.1990')
            return
        
        # Проверка валидности
        try:
            birth_date = datetime.strptime(text, '%d.%m.%Y')
            today = datetime.now()
            
            if birth_date > today:
                await self._send_validation_error(update.message, 'future')
                return
                
            age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
            if age > 150:
                await self._send_validation_error(update.message, 'age')
                return
                
        except ValueError:
            await self._send_validation_error(update.message, 'invalid')
            return
        
        # Сохранение
        success = self.bot.profile_service.update_user_profile(
            user_id=user_id,
            birth_date=text
        )
        
        if success:
            try:
                day = birth_date.day
                month = birth_date.month
                zodiac = self.bot.profile_service._calculate_zodiac_sign(day, month)
            except Exception as e:
                logger.debug(f"Error calculating zodiac: {e}")
                zodiac = None
            
            response_text = f"✅ <b>Дата рождения сохранена!</b>\n\n📅 {text}"
            if age:
                response_text += f"\n🎂 Возраст: {age} лет"
            if zodiac:
                response_text += f"\n♈️ Знак зодиака: {zodiac}"
                
            response_text += "\n\n💡 Теперь ваши интерпретации будут более точными!"
            
            await self._safe_reply_with_menu(update, response_text)
        else:
            await self._safe_reply_with_menu(
                update,
                "❌ Произошла ошибка при сохранении. Попробуйте позже."
            )
        
        # Сброс состояния
        if 'editing_profile' in context.user_data:
            del context.user_data['editing_profile']
            del context.user_data['editing_field']

    async def _send_validation_error(self, message, error_type, example="15.05.1990"):
        """Отправка сообщения об ошибке валидации"""
        error_messages = {
            'format': f"❌ <b>Неверный формат даты</b>\n\nПожалуйста, используйте формат: <b>ДД.ММ.ГГГГ</b>\nНапример: <code>{example}</code>",
            'future': "❌ <b>Дата рождения не может быть в будущем</b>\n\nПожалуйста, введите корректную дату:",
            'age': "❌ <b>Пожалуйста, проверьте дату рождения</b>\n\nВозраст не должен превышать 150 лет.",
            'invalid': "❌ <b>Неверная дата</b>\n\nПожалуйста, введите существующую дату в формате <b>ДД.ММ.ГГГГ</b>"
        }
        
        await message.reply_text(
            error_messages.get(error_type, "❌ Произошла ошибка валидации."),
            parse_mode='HTML',
            reply_markup=keyboards.get_cancel_edit_keyboard()
        )

    def setup_handlers(self):
        """Регистрация обработчиков сообщений"""
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_messages)
        )
        logger.info("Message handlers registered successfully")