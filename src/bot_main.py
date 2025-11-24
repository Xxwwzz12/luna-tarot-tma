# src/bot_main.py
import os
import logging
import time
from logging import FileHandler, StreamHandler, Formatter
import inspect
from typing import Any, Dict
from collections import deque
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
from telegram.ext import Defaults
from telegram.constants import ParseMode

# Импорты из наших модулей
from . import config
from . import tarot_engine  
from . import user_database
from . import ai_interpreter
from . import keyboards

# Импорты сервисов
from .services.card_service import CardService
from .services.ai_service import AIService
from .services.profile_service import ProfileService
from .services.history_service import HistoryService

# Импорты обработчиков
from .handlers.command_handlers import CommandHandlers
from .handlers.callback_handlers import CallbackHandlers
from .handlers.message_handlers import MessageHandlers
from .handlers.error_handlers import ErrorHandlers

# ✅ ЦЕНТРАЛИЗОВАННАЯ КОНФИГУРАЦИЯ ЛОГИРОВАНИЯ
class DedupFilter(logging.Filter):
    """Отключает одинаковые сообщения, пришедшие чаще одного раза в WINDOW sec."""
    def __init__(self, window=2.0, max_cache=200):
        super().__init__()
        self.window = window
        self.cache = deque(maxlen=max_cache)  # (msg, ts)

    def filter(self, record):
        now = time.time()
        msg = record.getMessage()
        # Удаляем устаревшие
        while self.cache and now - self.cache[0][1] > self.window:
            self.cache.popleft()
        # Если такое сообщение уже есть в окне — подавляем
        for m, ts in self.cache:
            if m == msg:
                return False
        self.cache.append((msg, now))
        return True

def configure_logging():
    """Централизованная настройка логирования для всего приложения"""
    level_name = os.getenv("TAROT_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    
    root = logging.getLogger()
    # Очистка handler'ов чтобы исключить дублирование
    for h in root.handlers[:]:
        root.removeHandler(h)
    
    # ✅ НАСТРОЙКА HANDLER'ОВ
    file_handler = FileHandler('tarot_bot.log', mode='a', encoding='utf-8')
    console_handler = StreamHandler()
    
    # ✅ ФОРМАТТЕР
    formatter = Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # ✅ ДОБАВЛЕНИЕ HANDLER'ОВ
    root.addHandler(file_handler)
    root.addHandler(console_handler)
    root.setLevel(level)
    
    # ✅ ФИЛЬТР ДУБЛИКАТОВ НА УРОВНЕ ROOT
    root.addFilter(DedupFilter(window=2.0))
    
    # ✅ НАСТРОЙКА MODULE-LOGGER'ОВ (propagate=False чтобы избежать дублирования)
    module_loggers = [
        "src.ai_interpreter", 
        "src.services.ai_service", 
        "src.services.card_service", 
        "src.handlers",
        "src.bot_main",
        "src.tarot_engine",
        "src.user_database",
        "src.keyboards"
    ]
    
    for name in module_loggers:
        logger = logging.getLogger(name)
        logger.propagate = False
        logger.setLevel(level)
        # Добавляем handlers только если их нет
        if not logger.handlers:
            logger.addHandler(file_handler)
            logger.addHandler(console_handler)
    
    logging.info(f"✅ Logging configured with level: {level_name}")

# ✅ БЕЗОПАСНАЯ ФАБРИКА ДЛЯ СОЗДАНИЯ ОБРАБОТЧИКОВ
def _instantiate_handler_safe(handler_cls: type, deps: Dict[str, Any], logger) -> Any:
    """
    Безопасно инстанцирует handler_cls, фильтруя deps по сигнатуре конструктора.
    Возвращает экземпляр или None при фатальной ошибке.
    """
    try:
        sig = inspect.signature(handler_cls.__init__)
        params = sig.parameters

        # Если __init__ принимает **kwargs — можно передавать всё
        accepts_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())

        if accepts_kwargs:
            filtered = deps.copy()
        else:
            # Оставляем только имена аргументов, которые присутствуют в сигнатуре (кроме self)
            allowed = [name for name, p in params.items() if name != 'self' and p.kind in (
                inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)]
            filtered = {k: v for k, v in deps.items() if k in allowed}

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"DIAG: Instantiating {handler_cls.__name__} with params: {list(filtered.keys())}")

        # Попытка создать экземпляр с отфильтрованными kwargs
        try:
            return handler_cls(**filtered)
        except TypeError as te:
            logger.warning(f"DIAG: {handler_cls.__name__} init with kwargs failed: {te}. Trying fallback attempts.")

            # fallback: если application в deps — пробуем только application
            if 'application' in deps:
                try:
                    return handler_cls(deps['application'])
                except Exception:
                    pass

            # fallback: без аргументов
            try:
                return handler_cls()
            except Exception as e:
                logger.error(f"ERROR: Failed to instantiate {handler_cls.__name__} with fallbacks: {e}")
                return None

    except Exception as e:
        logger.error(f"ERROR: Unexpected error while instantiating {handler_cls}: {e}")
        return None

class TarotBot:
    # ✅ IDEMPOTENT SINGLETON PATTERN - КЛАССОВЫЕ АТРИБУТЫ ДЛЯ КЭШИРОВАНИЯ
    _already_initialized = False
    _services_cache = {}
    _handlers_cache = {}
    _application_cache = None
    _ai_interpreter_cache = None

    def __init__(self):
        logger = logging.getLogger(__name__)
        
        # ✅ ПРОВЕРКА ДВОЙНОЙ ИНИЦИАЛИЗАЦИИ С БЕЗОПАСНЫМ ВОССТАНОВЛЕНИЕМ
        if TarotBot._already_initialized:
            logger.info("ℹ️ TarotBot already initialized — restoring instance attributes from cache")
            
            # Восстанавливаем ссылки на общие объекты из кэша
            self.ai_interpreter = TarotBot._ai_interpreter_cache
            self.card_service = TarotBot._services_cache.get('card_service')
            self.ai_service = TarotBot._services_cache.get('ai_service')
            self.profile_service = TarotBot._services_cache.get('profile_service')
            self.history_service = TarotBot._services_cache.get('history_service')
            self.application = TarotBot._application_cache
            
            # Восстанавливаем обработчики из кэша
            self.command_handlers = TarotBot._handlers_cache.get('command_handlers')
            self.callback_handlers = TarotBot._handlers_cache.get('callback_handlers')
            self.message_handlers = TarotBot._handlers_cache.get('message_handlers')
            self.error_handlers = TarotBot._handlers_cache.get('error_handlers')
            
            # ✅ ПРОВЕРКА НАЛИЧИЯ ВСЕХ КРИТИЧЕСКИХ СЕРВИСОВ
            required_services = ['card_service', 'ai_service', 'profile_service', 'history_service']
            missing_services = [svc for svc in required_services if not getattr(self, svc, None)]
            
            if missing_services:
                error_msg = f"TarotBot re-init failed: missing services in cache: {missing_services}"
                logger.error(error_msg)
                raise RuntimeError(error_msg)
            
            logger.info("✅ TarotBot instance restored from cache successfully")
            return
        
        # ✅ ПЕРВИЧНАЯ ИНИЦИАЛИЗАЦИЯ
        logger.info("🔄 TarotBot first initialization started")
        
        self.application = None
        self.user_db = user_database.user_db
        self.tarot_engine = tarot_engine
        self.ai_interpreter = None
        
        # ✅ ЕДИНСТВЕННАЯ ИНИЦИАЛИЗАЦИЯ AI-ИНТЕРПРЕТАТОРА
        try:
            logger.info("🔄 Initializing AI Interpreter...")
            self.ai_interpreter = ai_interpreter.AIInterpreter()
            logger.info("✅ AI Interpreter initialized successfully")
            if logger.isEnabledFor(logging.DEBUG) and hasattr(self.ai_interpreter, 'models') and self.ai_interpreter.models:
                logger.debug(f"AI Interpreter loaded with {len(self.ai_interpreter.models)} models")
        except Exception as e:
            logger.exception(f"❌ Failed to initialize AI Interpreter: {e}")
            self.ai_interpreter = None

        # ✅ ИНИЦИАЛИЗАЦИЯ СЕРВИСОВ
        self._setup_services()

        # Обработчики будут инициализированы после создания application
        self.command_handlers = None
        self.callback_handlers = None
        self.message_handlers = None
        self.error_handlers = None

        # ✅ СОХРАНЕНИЕ В КЭШ ПОСЛЕ УСПЕШНОЙ ИНИЦИАЛИЗАЦИИ
        TarotBot._ai_interpreter_cache = self.ai_interpreter
        TarotBot._services_cache = {
            'card_service': self.card_service,
            'ai_service': self.ai_service,
            'profile_service': self.profile_service,
            'history_service': self.history_service,
        }
        TarotBot._application_cache = self.application
        TarotBot._already_initialized = True
        
        # ✅ АГРЕГИРОВАННОЕ ЛОГИРОВАНИЕ СЕРВИСОВ
        services = ["ai_service", "card_service", "profile_service", "history_service"]
        available = sum(1 for s in services if hasattr(self, s) and getattr(self, s) is not None)
        logger.info(f"✅ Services initialized: {available}/{len(services)}")
        
        if logger.isEnabledFor(logging.DEBUG):
            service_details = []
            for s in services:
                if hasattr(self, s) and getattr(self, s) is not None:
                    service_details.append(f"{s}:{type(getattr(self, s)).__name__}")
            logger.debug(f"Service details: {', '.join(service_details)}")
        
        logger.info("✅ TarotBot first initialization completed and cached")

    def _setup_services(self):
        """Инициализация всех сервисов бота - ВНУТРЕННИЙ МЕТОД"""
        logger = logging.getLogger(__name__)
        logger.info("🔄 Setting up services...")
        
        # Создаем сервисы
        self.ai_service = AIService(self.user_db, self.ai_interpreter)
        self.card_service = CardService(
            user_db=self.user_db,
            tarot_engine=self.tarot_engine,
            ai_service=self.ai_service
        )
        self.profile_service = ProfileService(self.user_db)
        self.history_service = HistoryService(self.user_db)
        
        # ✅ Установка глобального экземпляра CardService
        from .services.card_service import set_global_card_service
        set_global_card_service(self.card_service)

    async def initialize_ai_interpreter(self):
        """Инициализация AI-интерпретатора с обработкой ошибок - ЛЕНИВАЯ ИНИЦИАЛИЗАЦИЯ"""
        logger = logging.getLogger(__name__)
        if self.ai_interpreter is not None:
            logger.info("ℹ️ AI Interpreter already initialized, skipping lazy init")
            return True
            
        try:
            logger.info("🔄 Lazy initializing AI Interpreter...")
            self.ai_interpreter = ai_interpreter.AIInterpreter()
            logger.info("✅ AI Interpreter initialized successfully (lazy init)")
            self.ai_service.update_ai_interpreter(self.ai_interpreter)
            return True
        except Exception as e:
            logger.error(f"❌ Failed to initialize AI Interpreter in lazy init: {str(e)}")
            self.ai_interpreter = None
            return False

    def initialize_handlers(self):
        """Инициализация обработчиков после создания application"""
        logger = logging.getLogger(__name__)
        if self.application is None:
            raise ValueError("Application must be created before initializing handlers")
        
        # ✅ ПРОВЕРКА НАЛИЧИЯ ВСЕХ СЕРВИСОВ
        required_services = {
            'card_service': self.card_service,
            'ai_service': self.ai_service,
            'profile_service': self.profile_service,
            'history_service': self.history_service
        }
        
        for service_name, service_instance in required_services.items():
            if service_instance is None:
                logger.error(f"❌ Required service {service_name} is None")
                raise ValueError(f"Required service {service_name} is not initialized")
        
        logger.info("✅ All required services are available for handlers")
        
        # ✅ СЛОВАРЬ ЗАВИСИМОСТЕЙ
        deps = {
            'application': self.application,
            'bot_instance': self,
            'card_service': self.card_service,
            'ai_service': self.ai_service,
            'profile_service': self.profile_service,
            'history_service': self.history_service,
        }
        
        # ✅ БЕЗОПАСНОЕ СОЗДАНИЕ ОБРАБОТЧИКОВ С ОБРАБОТКОЙ ОШИБОК
        try:
            self.command_handlers = _instantiate_handler_safe(CommandHandlers, deps, logger)
            if self.command_handlers is None:
                raise RuntimeError("Не удалось создать CommandHandlers")
            
            self.callback_handlers = _instantiate_handler_safe(CallbackHandlers, deps, logger)
            if self.callback_handlers is None:
                raise RuntimeError("Не удалось создать CallbackHandlers")
            
            self.message_handlers = _instantiate_handler_safe(MessageHandlers, deps, logger)
            if self.message_handlers is None:
                raise RuntimeError("Не удалось создать MessageHandlers")
            
            self.error_handlers = _instantiate_handler_safe(ErrorHandlers, deps, logger)
            if self.error_handlers is None:
                raise RuntimeError("Не удалось создать ErrorHandlers")
            
        except Exception as e:
            logger.exception(f"❌ Failed to initialize handlers: {e}")
            raise RuntimeError(f"Handler initialization failed: {e}")
        
        # ✅ СОХРАНЕНИЕ ОБРАБОТЧИКОВ В КЭШ
        TarotBot._handlers_cache.update({
            'command_handlers': self.command_handlers,
            'callback_handlers': self.callback_handlers,
            'message_handlers': self.message_handlers,
            'error_handlers': self.error_handlers,
        })
        
        logger.info("✅ All handlers created and cached successfully")

    def _initialize_handlers_and_start(self):
        """Безопасная инициализация обработчиков и запуск бота"""
        logger = logging.getLogger(__name__)
        try:
            logger.info("🔄 Initializing handlers and starting bot...")
            
            # 1. Инициализируем обработчики
            self.initialize_handlers()
            
            # 2. Настраиваем обработчики
            self.setup_handlers()
            
            logger.info("✅ Handlers initialized and bot ready for polling")
            
        except AttributeError as e:
            logger.exception(f"❌ AttributeError in handler initialization: {e}")
            raise RuntimeError(f"Handler method missing: {e}")
        except Exception as e:
            logger.exception(f"❌ Failed to initialize handlers and start bot: {e}")
            raise RuntimeError(f"Bot startup failed: {e}")

    async def show_main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показ главного меню"""
        logger = logging.getLogger(__name__)
        menu_text = """
🔮 <b>Добро пожаловать в AI-Таролог "Луна"!</b>

Я помогу вам получить инсайты с помощью карт Таро и искусственного интеллекта.

<b>Выберите действие:</b>
• 🎴 <b>Карта дня</b> - быстрый ответ на вопрос
• 🔮 <b>3 карты</b> - прошлое, настоящее, будущее  
• 📖 <b>История раскладов</b> - ваши предыдущие расклады
• 👤 <b>Профиль</b> - настройки профиля
• ℹ️ <b>Помощь</b> - инструкция по использованию

<b>Доступные команды:</b>
/start - главное меню
/profile - управление профилем
/history - история раскладов
/help - справка
/details номер - детали расклада (например: /details 1)
"""
        
        reply_markup = keyboards.get_main_menu_keyboard()
        
        try:
            if update.callback_query:
                await update.callback_query.message.reply_text(
                    menu_text,
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
            else:
                await update.message.reply_text(
                    menu_text,
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
        except Exception as e:
            logger.error(f"Error showing main menu: {str(e)}")
            # Fallback без HTML
            fallback_text = menu_text.replace('<b>', '').replace('</b>', '')
            if update.callback_query:
                await update.callback_query.message.reply_text(fallback_text, reply_markup=reply_markup)
            else:
                await update.message.reply_text(fallback_text, reply_markup=reply_markup)

    async def show_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показ справки - ИСПРАВЛЕННАЯ ВЕРСИЯ БЕЗ РЕКУРСИИ"""
        await self.command_handlers.handle_help(update, context)

    async def show_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показ профиля - ИСПРАВЛЕННАЯ ВЕРСИЯ БЕЗ РЕКУРСИИ"""
        await self.command_handlers.handle_profile(update, context)

    async def show_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показ истории - ИСПРАВЛЕННАЯ ВЕРСИЯ БЕЗ РЕКУРСИИ"""
        await self.command_handlers.handle_history(update, context)

    async def show_spread_details(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показ деталей расклада - ИСПРАВЛЕННАЯ ВЕРСИЯ БЕЗ РЕКУРСИИ"""
        await self.command_handlers.handle_details(update, context)

    async def generate_spread(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Генерация расклада"""
        logger = logging.getLogger(__name__)
        user_id = update.effective_user.id
        username = update.effective_user.username or f"user_{user_id}"
        
        user_spread_type = context.user_data.get('spread_type', '1 карта')
        category = context.user_data.get('category', 'Общий вопрос')
        
        # Преобразуем пользовательские типы в внутренние типы
        spread_type_mapping = {
            '1 карта': 'one_card',
            '3 карты': 'three_card'
        }
        
        internal_spread_type = spread_type_mapping.get(user_spread_type, 'one_card')
        
        try:
            # ✅ ИСПРАВЛЕНО: добавлен await перед вызовом асинхронного метода
            spread_cards_data, spread_id = await self.card_service.generate_spread(
                user_id, username, internal_spread_type, category
            )
            
            context.user_data['spread_cards'] = spread_cards_data
            context.user_data['internal_spread_type'] = internal_spread_type
            context.user_data['last_spread_id'] = spread_id

            await self.show_spread_result(update, context)
            
        except Exception as e:
            logger.error(f"Error in generate_spread for user {user_id}: {e}")
            error_text = "❌ Произошла ошибка при генерации расклада. Попробуйте еще раз."
            reply_markup = keyboards.get_back_to_menu_keyboard()
            
            if update.callback_query:
                await update.callback_query.message.reply_text(error_text, reply_markup=reply_markup)
            else:
                await update.message.reply_text(error_text, reply_markup=reply_markup)

    async def show_spread_result(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показ результатов расклада"""
        logger = logging.getLogger(__name__)
        user_id = update.effective_user.id
        internal_spread_type = context.user_data.get('internal_spread_type', 'one_card')
        category = context.user_data.get('category', 'Общий вопрос')
        spread_cards = context.user_data.get('spread_cards', [])
        spread_id = context.user_data.get('last_spread_id')
        
        user_name = update.effective_user.first_name
        if not user_name:
            user_profile = self.user_db.get_user_profile(user_id)
            user_name = user_profile.get('first_name', 'друг') if user_profile else 'друг'
        
        if not spread_cards:
            error_text = "❌ Ошибка: данные расклада не найдены. Пожалуйста, начните заново с /start"
            if update.callback_query:
                await update.callback_query.message.reply_text(error_text)
            else:
                await update.message.reply_text(error_text)
            return
        
        try:
            if update.callback_query:
                message = update.callback_query.message
                chat_id = message.chat_id
            else:
                message = update.message
                chat_id = update.effective_chat.id

            # 1. Выводим карты текстом
            cards_text = self.card_service.format_cards_message(spread_cards, internal_spread_type, category)
            
            if update.callback_query:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message.message_id,
                    text=cards_text,
                    parse_mode='HTML'
                )
            else:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=cards_text,
                    parse_mode='HTML'
                )

            # 2. Отправляем изображения карт
            await self.card_service._send_card_images(message, spread_cards, internal_spread_type, context.bot)

            # 3. Генерируем интерпретацию
            interpretation = await self.ai_service.generate_ai_interpretation(
                spread_cards, internal_spread_type, category, user_id, chat_id, context.bot, spread_id, user_name
            )
            
            # 4. Если AI не сработал, используем базовую интерпретацию
            if not interpretation:
                interpretation = self.card_service.generate_basic_interpretation(spread_cards, internal_spread_type)
            
            # 5. Показываем финальную интерпретацию
            interpretation_text = self.card_service.format_interpretation_message(interpretation)
            await context.bot.send_message(
                chat_id=chat_id,
                text=interpretation_text,
                parse_mode='HTML'
            )
            
            # 6. Финальное сообщение
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"✅ <b>Интерпретация завершена!</b>\n\n"
                    f"🔮 Расклад сохранен в вашей истории.\n"
                    f"💭 Вы можете задать дополнительные вопросы по этому раскладу."
                ),
                parse_mode='HTML',
                reply_markup=keyboards.get_interpretation_keyboard(spread_id)
            )
            
        except Exception as e:
            logger.warning(f"Using fallback interpretation for user {user_id}: {str(e)}")
            
            basic_interpretation = self.card_service.generate_basic_interpretation(spread_cards, internal_spread_type)
            interpretation_text = self.card_service.format_interpretation_message(basic_interpretation)
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=interpretation_text,
                parse_mode='HTML'
            )

    def setup_handlers(self):
        """Настройка обработчиков сообщений и callback-ов"""
        logger = logging.getLogger(__name__)
        
        # Очистка существующих обработчиков
        if hasattr(self.application, 'handlers'):
            for handler_group in self.application.handlers.values():
                handler_group.clear()
        
        # ✅ РЕГИСТРАЦИЯ ОБРАБОТЧИКОВ С ОПТИМИЗИРОВАННЫМ ЛОГИРОВАНИЕМ
        handler_counts = {
            'command_handlers': 0,
            'callback_handlers': 0,
            'message_handlers': 0,
            'error_handlers': 0
        }
        
        # 1. Обработчики команд
        command_handlers = [
            ("start", self.command_handlers.handle_start),
            ("history", self.command_handlers.handle_history),
            ("help", self.command_handlers.handle_help),
            ("details", self.command_handlers.handle_details),
            ("profile", self.command_handlers.handle_profile)
        ]
        
        for command, handler in command_handlers:
            self.application.add_handler(CommandHandler(command, handler))
            handler_counts['command_handlers'] += 1
        
        # 2. Обработчики callback-запросов - СИНХРОНИЗАЦИЯ С KEYBOARDS.PY
        callback_handlers = [
            # ✅ ДОБАВЛЕНО: обработчик для кнопки профиля
            ("^profile$", self.callback_handlers.handle_profile_callback),
            
            # Выбор типа расклада (соответствует keyboards.py)
            ("^(spread_single|spread_three)$", self.callback_handlers.handle_category_selection),
            
            # Выбор категории (соответствует keyboards.py) 
            ("^(category_love|category_career|category_finance|category_relationships|category_growth|category_general|category_custom)$", self.callback_handlers.handle_category_selection),
            
            # ✅ СИНХРОНИЗИРОВАНО: детали расклада - используем spread_ согласно keyboards.py
            ("^spread_", self.callback_handlers.handle_spread_details_callback),
            
            # Вопросы по раскладам
            ("^ask_question_", self.callback_handlers.handle_ask_question_callback),
            ("^view_questions_", self.callback_handlers.handle_view_questions_callback),
            
            # Профиль пользователя (редактирование и настройки)
            ("^edit_|^gender_|^clear_profile|^cancel_edit", self.callback_handlers.handle_profile_callback),
            
            # Навигация (соответствует keyboards.py)
            ("^back_to_menu$", self.callback_handlers.handle_back_to_menu),
            ("^back_to_history$", self.callback_handlers.handle_back_to_history),
            ("^main_menu$", self.callback_handlers.handle_main_menu_callback),
            ("^cancel_custom_question$", self.callback_handlers.handle_cancel_custom_question),
            
            # Выбор карт (соответствует keyboards.py)
            ("^card_choice:", self.callback_handlers.handle_card_choice_callback),
            ("^continue_select:", self.callback_handlers.handle_continue_selection),
            ("^back_to_select:", self.callback_handlers.handle_back_to_selection_callback),
            
            # Пагинация истории (соответствует keyboards.py)
            ("^history_page_", self.callback_handlers.handle_history_pagination_callback)
        ]
        
        for pattern, handler in callback_handlers:
            self.application.add_handler(CallbackQueryHandler(handler, pattern=pattern))
            handler_counts['callback_handlers'] += 1

        # 3. Обработчик текстовых сообщений
        self.application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            self.message_handlers.handle_text_messages
        ))
        handler_counts['message_handlers'] += 1
        
        # 4. Обработчик ошибок
        self.application.add_error_handler(self.error_handlers.error_handler)
        handler_counts['error_handlers'] += 1
        
        # ✅ ОПТИМИЗИРОВАННОЕ ЛОГИРОВАНИЕ РЕГИСТРАЦИИ
        total_handlers = sum(handler_counts.values())
        logger.info(f"✅ Handlers registered: {total_handlers} total")
        logger.info(f"   - Commands: {handler_counts['command_handlers']}")
        logger.info(f"   - Callbacks: {handler_counts['callback_handlers']}") 
        logger.info(f"   - Messages: {handler_counts['message_handlers']}")
        logger.info(f"   - Errors: {handler_counts['error_handlers']}")
        
        # ✅ ЛОГИРОВАНИЕ СИНХРОНИЗАЦИИ С KEYBOARDS
        logger.info("🔄 Callback patterns synchronized with keyboards.py:")
        logger.info("   - ✅ 'profile$' - профиль пользователя")
        logger.info("   - ✅ 'spread_' - детали расклада")
        logger.info("   - ✅ Все паттерны соответствуют keyboard callback_data")
        
        # Детальное логирование только в DEBUG режиме
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("📋 Detailed handler registration:")
            for command, _ in command_handlers:
                logger.debug(f"   - Command: /{command}")
            for pattern, _ in callback_handlers:
                logger.debug(f"   - Callback: {pattern}")
            logger.debug("   - Message: TEXT & ~COMMAND")
            logger.debug("   - Error: global error handler")

    def main(self):
        """Основная функции запуска бота"""
        logger = logging.getLogger(__name__)
        logger.info("Starting Tarot Bot initialization...")
        
        bot_token = config.TELEGRAM_BOT_TOKEN
        if not bot_token:
            logger.error("TELEGRAM_BOT_TOKEN not found in configuration")
            raise ValueError("TELEGRAM_BOT_TOKEN not found in configuration")
        
        # 1. Создаем application с КОРРЕКТНЫМИ DEFAULTS И FALLBACK
        if self.application is None:
            try:
                # ✅ ИСПРАВЛЕНО: используем только поддерживаемые параметры
                defaults = Defaults(
                    parse_mode=ParseMode.HTML,  # ✅ HTML ПО УМОЛЧАНИЮ
                    timeout=120  # ✅ Только поддерживаемые параметры
                )
                self.application = (
                    ApplicationBuilder()
                    .token(bot_token)
                    .concurrent_updates(True)
                    .defaults(defaults)
                    .build()
                )
                logger.info("✅ Application created with HTML defaults")
            except TypeError as e:
                # ✅ РЕЗЕРВНЫЙ ВАРИАНТ: если Defaults не поддерживается
                logger.warning(f"Defaults not supported: {e}. Creating application without defaults.")
                self.application = (
                    ApplicationBuilder()
                    .token(bot_token)
                    .concurrent_updates(True)
                    .build()
                )
                logger.info("✅ Application created without defaults (fallback)")
            
            # ✅ ОБНОВЛЯЕМ КЭШ С НОВЫМ APPLICATION
            TarotBot._application_cache = self.application
        
        # 2. Безопасная инициализация обработчиков и запуск
        self._initialize_handlers_and_start()
        
        logger.info("Bot started polling...")
        self.application.run_polling()


# Глобальный экземпляр бота
tarot_bot = TarotBot()

def main():
    """Точка входа для запуска бота"""
    # ✅ ЦЕНТРАЛИЗОВАННАЯ КОНФИГУРАЦИЯ ЛОГОВ ПРИ ЗАПУСКЕ
    configure_logging()
    tarot_bot.main()

if __name__ == "__main__":
    main()