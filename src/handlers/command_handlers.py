# src/handlers/command_handlers.py
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from .. import keyboards
from ..services.profile_service import ProfileService
from ..services.history_service import HistoryService

logger = logging.getLogger(__name__)

class CommandHandlers:
    def __init__(self, bot_instance, application):
        self.bot = bot_instance
        self.application = application

    def setup_handlers(self):
        """Регистрация обработчиков команд в приложении"""
        from telegram.ext import CommandHandler
        
        self.application.add_handler(CommandHandler("start", self.handle_start))
        self.application.add_handler(CommandHandler("help", self.handle_help))
        self.application.add_handler(CommandHandler("history", self.handle_history))
        self.application.add_handler(CommandHandler("profile", self.handle_profile))
        self.application.add_handler(CommandHandler("details", self.handle_details))
        
        logger.info("✅ Command handlers registered successfully")

    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        user = update.effective_user
        user_id = user.id
        
        logger.info(f"🚀 User {user_id} started the bot")
        
        try:
            # Регистрируем/обновляем пользователя в БД
            self.bot.user_db.add_user({
                'user_id': user_id,
                'username': user.username,
                'first_name': user.first_name,
                'last_name': user.last_name
            })
            
            # ✅ ПРОВЕРКА: Используем прямой вызов show_main_menu
            # Если метод существует в bot - используем его
            if hasattr(self.bot, 'show_main_menu') and callable(self.bot.show_main_menu):
                await self.bot.show_main_menu(update, context)
            else:
                # ✅ РЕЗЕРВНЫЙ ВАРИАНТ: Отправляем меню напрямую
                await self._send_main_menu_directly(update, context)
            
        except Exception as e:
            logger.error(f"❌ Error in handle_start for user {user_id}: {str(e)}")
            await self._safe_send_message(
                update, context, 
                "❌ Произошла ошибка при запуске бота. Пожалуйста, попробуйте еще раз.",
                keyboards.get_back_to_menu_keyboard()
            )

    async def _send_main_menu_directly(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Резервный метод для отправки главного меню напрямую"""
        menu_text = (
            "🔮 <b>Добро пожаловать в бота Таро!</b>\n\n"
            "Я помогу вам получить предсказание на интересующие вопросы.\n"
            "Выберите тип расклада:"
        )
        
        await self._safe_send_message(
            update, context,
            menu_text,
            keyboards.get_main_menu_keyboard(),
            parse_mode='HTML'
        )

    async def handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help"""
        logger.info(f"ℹ️ User {update.effective_user.id} requested help via command")
        
        help_text = """
🔮 <b>Помощь по использованию бота Таро</b>

<b>Основные функции:</b>
• <b>🎴 Карта дня</b> - быстрый расклад на текущую ситуацию
• <b>🔮 3 карты</b> - расклад "Прошлое-Настоящее-Будущее"  
• <b>📖 История раскладов</b> - ваши предыдущие расклады
• <b>👤 Профиль</b> - настройки профиля для персонализации
• <b>ℹ️ Помощь</b> - эта справка

<b>Категории вопросов:</b>
• 💖 <b>Любовь</b> - отношения, чувства, семья
• 💼 <b>Карьера</b> - работа, бизнес, профессиональный рост
• 💰 <b>Финансы</b> - деньги, инвестиции, материальные вопросы
• 👥 <b>Отношения</b> - общение, дружба, социальные связи
• 🔮 <b>Личностный рост</b> - развитие, обучение, самопознание
• ❓ <b>Общий вопрос</b> - без специфической тематики
• 💬 <b>Свой вопрос</b> - задайте любой вопрос для расклада

<b>Доступные команды:</b>
/start - главное меню
/profile - управление профиля
/history - история раскладов
/help - справка  
/details номер - детали расклада (например: /details 1)
"""
        
        reply_markup = keyboards.get_back_to_menu_keyboard()
        
        try:
            await self._safe_send_message(
                update, context,
                help_text,
                reply_markup,
                parse_mode='HTML'
            )
        except Exception as e:
            logger.error(f"💥 Error showing help: {str(e)}")
            fallback_help = help_text.replace('<b>', '').replace('</b>', '')
            await self._safe_send_message(
                update, context,
                fallback_help,
                reply_markup
            )

    async def handle_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /history - показывает краткий список с кнопками"""
        user_id = update.effective_user.id
        logger.info(f"📖 Пользователь {user_id} запросил историю")

        try:
            message = update.message
            if update.callback_query and update.callback_query.message:
                message = update.callback_query.message
            
            if not message:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="❌ Не удалось обработать запрос. Попробуйте еще раз.",
                    reply_markup=keyboards.get_main_menu_keyboard()
                )
                return

            result = self.bot.history_service.get_user_history_formatted(user_id=user_id, page=1)
            
            if result and len(result) == 4:
                history_text, keyboard, current_page, total_pages = result
                
                logger.info(f"📄 Отображение истории: страница {current_page}/{total_pages}")
                
                await self._safe_reply_to_message(
                    message,
                    history_text,
                    reply_markup=keyboard,
                    parse_mode='HTML'
                )
            else:
                logger.info("📭 История пуста")
                await self._safe_reply_to_message(
                    message,
                    "📭 Ваша история раскладов пуста.\n\nСделайте первый расклад через главное меню!",
                    keyboards.get_main_menu_keyboard()
                )

        except Exception as e:
            logger.error(f"❌ Ошибка загрузки истории: {e}")
            await self._safe_send_message(
                update, context,
                "❌ Произошла ошибка при загрузке истории. Попробуйте позже.",
                keyboards.get_main_menu_keyboard()
            )

    async def handle_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /profile"""
        user_id = update.effective_user.id
        logger.info(f"👤 User {user_id} requested profile via command")
        
        try:
            profile = self.bot.profile_service.get_user_profile_data(user_id)
            profile_text = self.bot.profile_service.format_profile_text(profile)

            help_text = (
                "\n\n📝 <b>Как редактировать:</b>\n"
                "• Нажмите <b>«📅 Дата рождения»</b> и введите дату в формате <b>ДД.ММ.ГГГГ</b>\n"
                "• Нажмите <b>«⚧ Пол»</b> для выбора пола\n"
                "• Нажмите <b>«🗑️ Очистить профиль»</b> чтобы удалить данные\n"
                "• Пример даты: <code>15.05.1990</code>"
            )

            full_text = profile_text + help_text

            await self._safe_edit_or_send_message(
                update, context,
                full_text,
                keyboards.get_profile_keyboard(),
                parse_mode='HTML'
            )

        except Exception as e:
            logger.error(f"❌ Ошибка показа профиля для пользователя {user_id}: {e}")
            error_message = "❌ Произошла ошибка при загрузке профиля. Попробуйте позже."

            await self._safe_edit_or_send_message(
                update, context,
                error_message,
                keyboards.get_back_to_menu_inline_keyboard()
            )

    async def handle_details(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /details"""
        user_id = update.effective_user.id
        args = context.args
        
        if not args or not args[0].isdigit():
            await self._safe_send_message(
                update, context,
                "❌ Пожалуйста, укажите номер расклада. Например: /details 1",
                keyboards.get_back_to_menu_keyboard()
            )
            return
        
        spread_number = int(args[0])
        logger.info(f"📖 User {user_id} requested details for spread {spread_number} via command")
        
        try:
            spread_info = self.bot.history_service.find_spread_by_number(user_id, spread_number)
            
            if not spread_info:
                await self._safe_send_message(
                    update, context,
                    f"❌ Расклад с номером {spread_number} не найден.",
                    keyboards.get_back_to_menu_keyboard()
                )
                return
            
            spread_data = spread_info['spread_data']
            spread_id = spread_info['spread_id']
            
            questions = self.bot.user_db.get_spread_questions(spread_id)
            details_text = self.bot.history_service.format_spread_details(spread_data, spread_number)
            
            if questions:
                details_text += f"<b>💭 Вопросы по раскладу ({len(questions)}):</b>\n\n"
                
                for i, qa in enumerate(questions, 1):
                    question_preview = qa['question']
                    if len(question_preview) > 100:
                        question_preview = question_preview[:100] + "..."
                    
                    answer_preview = qa['answer']
                    if len(answer_preview) > 150:
                        answer_preview = answer_preview[:150] + "..."
                    
                    details_text += (
                        f"<b>{i}. Вопрос:</b>\n{question_preview}\n"
                        f"<b>Ответ:</b>\n{answer_preview}\n"
                        f"────────────────────\n\n"
                    )
            else:
                details_text += "<b>💭 Вопросы по раскладу:</b> пока нет заданных вопросов\n\n"
            
            details_text += "💡 <i>Чтобы задать новый вопрос по этому раскладу, используйте кнопку ниже</i>"
            
            await self._safe_send_message(
                update, context,
                details_text,
                keyboards.get_spread_details_keyboard(spread_id, len(questions) > 0),
                parse_mode='HTML'
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка показа деталей расклада {spread_number} для пользователя {user_id}: {e}")
            await self._safe_send_message(
                update, context,
                "❌ Произошла ошибка при загрузке деталей расклада.",
                keyboards.get_back_to_menu_keyboard()
            )

    async def _safe_send_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE, 
                               text: str, reply_markup=None, parse_mode=None):
        """Безопасная отправка сообщения с учетом разных типов update"""
        try:
            if update.callback_query:
                await update.callback_query.message.reply_text(
                    text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
            else:
                await update.message.reply_text(
                    text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
        except Exception as e:
            logger.error(f"❌ Ошибка отправки сообщения: {str(e)}")
            await context.bot.send_message(
                chat_id=update.effective_user.id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )

    async def _safe_reply_to_message(self, message, text: str, reply_markup=None, parse_mode=None):
        """Безопасный ответ на сообщение"""
        try:
            await message.reply_text(
                text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        except Exception as e:
            logger.error(f"❌ Ошибка ответа на сообщение: {str(e)}")

    async def _safe_edit_or_send_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE,
                                       text: str, reply_markup=None, parse_mode=None):
        """Безопасное редактирование или отправка сообщения"""
        try:
            if update.callback_query:
                await update.callback_query.edit_message_text(
                    text,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup
                )
            else:
                await update.message.reply_text(
                    text,
                    parse_mode=parse_mode,
                    reply_markup=reply_markup
                )
        except Exception as e:
            logger.error(f"❌ Ошибка редактирования/отправки сообщения: {str(e)}")
            await context.bot.send_message(
                chat_id=update.effective_user.id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )