# src/handlers/error_handlers.py
import logging
import traceback
from telegram import Update
from telegram.ext import ContextTypes
from .. import keyboards

logger = logging.getLogger(__name__)

class ErrorHandlers:
    def __init__(self, bot_instance, application):
        self.bot = bot_instance
        self.application = application  # ✅ Добавлен параметр application

    def setup_handlers(self):
        """Регистрация обработчика ошибок в приложении"""
        # Регистрация глобального обработчика ошибок
        self.application.add_error_handler(self.error_handler)
        
        logger.info("✅ Error handlers registered successfully")

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """УЛУЧШЕННЫЙ обработчик ошибок с диагностикой HTML"""
        logger.error(f"💥 Exception while handling an update: {context.error}")
        
        # Логируем полный traceback для диагностики
        logger.error(f"📋 Full traceback: {traceback.format_exc()}")
        
        # Детальная диагностика для HTML ошибок
        if "Can't parse entities" in str(context.error):
            logger.error("🔄 HTML parsing error detected - likely malformed HTML tags")
            
            # Пытаемся получить текст сообщения который вызвал ошибку
            if update and update.effective_message:
                logger.error(f"📝 Problematic message text: {update.effective_message.text}")
        
        # Диагностика для других типов ошибок
        elif "ConnectionError" in str(context.error) or "Timeout" in str(context.error):
            logger.error("🌐 Network connection error detected")
        
        elif "Forbidden" in str(context.error):
            logger.error("🚫 Bot was blocked by the user")
        
        # Отправляем пользователю сообщение об ошибке
        if update and update.effective_chat:
            try:
                # Отправляем без HTML чтобы избежать повторной ошибки
                error_message = (
                    "❌ Произошла непредвиденная ошибка.\n\n"
                    "Возможные причины:\n"
                    "• Проблемы с интернет-соединением\n" 
                    "• Временная недоступность сервиса\n"
                    "• Ошибка форматирования сообщения\n\n"
                    "Попробуйте выполнить действие еще раз или используйте /start для перезапуска бота."
                )
                
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=error_message,
                    reply_markup=keyboards.get_back_to_menu_keyboard()
                )
                
            except Exception as e:
                logger.error(f"💥 Failed to send error message: {e}")

    async def handle_critical_errors(self, update: Update, context: ContextTypes.DEFAULT_TYPE, error_type: str = "general"):
        """Обработка критических ошибок с классификацией"""
        
        error_messages = {
            "network": (
                "🌐 <b>Проблемы с соединением</b>\n\n"
                "Не удается подключиться к сервису. Пожалуйста:\n"
                "• Проверьте интернет-соединение\n"
                "• Попробуйте позже\n"
                "• Используйте /start для перезапуска"
            ),
            "ai_service": (
                "🤖 <b>AI-сервис временно недоступен</b>\n\n"
                "Используется базовая интерпретация. Вы можете:\n"
                "• Попробовать позже\n"
                "• Использовать расклад без AI-интерпретации\n"
                "• Проверить /help для дополнительной информации"
            ),
            "database": (
                "💾 <b>Ошибка доступа к данным</b>\n\n"
                "Не удается сохранить или загрузить данные. Пожалуйста:\n"
                "• Попробуйте позже\n"
                "• Используйте /start для перезапуска\n"
                "• Если проблема повторяется, сообщите разработчику"
            ),
            "general": (
                "❌ <b>Произошла ошибка</b>\n\n"
                "Пожалуйста, попробуйте еще раз или используйте /start для перезапуска бота."
            )
        }
        
        message = error_messages.get(error_type, error_messages["general"])
        
        try:
            if update and update.effective_chat:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=message,
                    parse_mode='HTML',
                    reply_markup=keyboards.get_back_to_menu_keyboard()
                )
        except Exception as e:
            logger.error(f"💥 Failed to send critical error message: {e}")

    async def handle_user_blocked_error(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка ситуации когда пользователь заблокировал бота"""
        logger.warning(f"🚫 Bot was blocked by user {update.effective_user.id if update else 'unknown'}")
        
        # Здесь можно добавить логику очистки данных пользователя
        # или отправки уведомления администратору

    async def handle_message_too_long_error(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка ошибки слишком длинного сообщения"""
        logger.warning(f"📏 Message too long for user {update.effective_user.id}")
        
        try:
            if update and update.effective_chat:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=(
                        "📏 <b>Сообщение слишком длинное</b>\n\n"
                        "Пожалуйста, сократите текст или разбейте его на несколько сообщений.\n"
                        "Максимальная длина сообщения в Telegram: 4096 символов."
                    ),
                    parse_mode='HTML',
                    reply_markup=keyboards.get_back_to_menu_keyboard()
                )
        except Exception as e:
            logger.error(f"💥 Failed to send message too long error: {e}")

    async def handle_retry_after_error(self, update: Update, context: ContextTypes.DEFAULT_TYPE, retry_after: int):
        """Обработка ошибки ограничения частоты запросов"""
        logger.warning(f"⏰ Rate limit exceeded, retry after {retry_after} seconds")
        
        try:
            if update and update.effective_chat:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=(
                        "⏰ <b>Слишком много запросов</b>\n\n"
                        f"Пожалуйста, подождите {retry_after} секунд перед следующим запросом.\n"
                        "Это ограничение Telegram для защиты от спама."
                    ),
                    parse_mode='HTML',
                    reply_markup=keyboards.get_back_to_menu_keyboard()
                )
        except Exception as e:
            logger.error(f"💥 Failed to send rate limit error: {e}")