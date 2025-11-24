# src/bot_main.py
import logging
import asyncio
import os
import aiohttp
import tempfile
import re
from datetime import datetime
from PIL import Image, ImageOps
from telegram import Update, InputMediaPhoto, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
# Относительные импорты внутри пакета src
from . import config
from . import tarot_engine  
from . import user_database
from . import ai_interpreter
from . import keyboards

# Состояния для ConversationHandler
CHOOSING_SPREAD, CHOOSING_CATEGORY, WAITING_FOR_QUESTION = range(3)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename='tarot_bot.log',
    filemode='a'
)
logger = logging.getLogger(__name__)

class TarotBot:
    def __init__(self):
        self.application = None
        self.user_db = user_database.user_db  # Добавляем ссылку на базу данных

        # Инициализация AI-интерпретатора (OpenRouter)
        try:
            self.ai_interpreter = ai_interpreter.AIInterpreter()
            logger.info("✅ OpenRouter Interpreter initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to initialize OpenRouter Interpreter: {e}")
            self.ai_interpreter = None
    
    async def initialize_ai_interpreter(self):
        """Инициализация AI-интерпретатора с обработкой ошибок"""
        try:
            # Попытка лениной инициализации только если ещё нет интерпретатора
            if self.ai_interpreter is None:
                self.ai_interpreter = ai_interpreter.AIInterpreter()
                logger.info("OpenRouter Interpreter initialized successfully (lazy init)")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize OpenRouter Interpreter: {str(e)}")
            self.ai_interpreter = None
            return False

    def _calculate_zodiac_sign(self, day: int, month: int) -> str:
        """Вычисление знака зодиака по дате рождения"""
        if (month == 1 and day >= 20) or (month == 12 and day <= 19):
            return "♑️ Козерог"
        elif (month == 1 and day >= 20) or (month == 2 and day <= 18):
            return "♒️ Водолей"
        elif (month == 2 and day >= 19) or (month == 3 and day <= 20):
            return "♓️ Рыбы"
        elif (month == 3 and day >= 21) or (month == 4 and day <= 19):
            return "♈️ Овен"
        elif (month == 4 and day >= 20) or (month == 5 and day <= 20):
            return "♉️ Телец"
        elif (month == 5 and day >= 21) or (month == 6 and day <= 20):
            return "♊️ Близнецы"
        elif (month == 6 and day >= 21) or (month == 7 and day <= 22):
            return "♋️ Рак"
        elif (month == 7 and day >= 23) or (month == 8 and day <= 22):
            return "♌️ Лев"
        elif (month == 8 and day >= 23) or (month == 9 and day <= 22):
            return "♍️ Дева"
        elif (month == 9 and day >= 23) or (month == 10 and day <= 22):
            return "♎️ Весы"
        elif (month == 10 and day >= 23) or (month == 11 and day <= 21):
            return "♏️ Скорпион"
        elif (month == 11 and day >= 22) or (month == 12 and day <= 21):
            return "♐️ Стрелец"
        else:
            return "❓ Не определен"

    def _format_gender(self, gender: str) -> str:
        """Форматирование пола для отображения"""
        gender_map = {
            'male': 'Мужской ♂️',
            'female': 'Женский ♀️',
            'other': 'Другой'
        }
        return gender_map.get(gender, 'не указан')

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
                
                logger.info(f"🔄 Изображение перевернуто: {card['name']}")
                return temp_file.name
                
        except Exception as e:
            logger.error(f"❌ Ошибка переворота изображения {card['name']}: {e}")
            return original_path

    def _generate_card_caption(self, card, spread_type, index=0, positions=None):
        """Генерация подписи для карты"""
        position = card.get('position', 'upright')
        
        if spread_type == "one_card":
            caption = f"🎴 <b>Карта дня: {card['name']}</b>\n"
            caption += f"📏 Положение: {'🔼 Прямое' if position == 'upright' else '🔽 Перевернутое'}\n"
        else:
            pos_name = positions[index] if positions and index < len(positions) else f"Карта {index+1}"
            caption = f"🎴 <b>{pos_name}: {card['name']}</b>\n"
            caption += f"📏 Положение: {'🔼 Прямое' if position == 'upright' else '🔽 Перевернутоe'}\n"
        
        # Добавляем ключевые слова если они есть
        keywords = card.get('keywords', {}).get(position, [])
        if keywords:
            caption += f"🔑 Ключевые слова: {', '.join(keywords[:5])}"  # Ограничиваем до 5 ключевых слов
        
        return caption

    async def _send_card_images(self, message, spread_cards, spread_type):
        """Улучшенная отправка изображений карт с переворачиванием и отдельными подписями"""
        
        try:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            
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
                            await message.reply_photo(
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
            await self._send_fallback_card_description(message, spread_cards, spread_type)

    async def _send_fallback_card_description(self, message, spread_cards, spread_type):
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
        
        await message.reply_text(
            fallback_text,
            parse_mode='HTML'
        )

    async def generate_ai_interpretation(self, spread_cards, spread_type, category, user_id, chat_id, original_message_id, spread_id=None, user_name=None):
        """Исправленная генерация AI-интерпретации с обработкой ошибок"""
        if not self.ai_interpreter:
            logger.warning("OpenRouter interpreter not available")
            return None
        
        try:
            # Начальное сообщение
            process_message = await self.application.bot.send_message(
                chat_id=chat_id,
                text="🔮 <b>Запускаю AI-интерпретацию...</b>\n"
                     "Использую 5 моделей через OpenRouter\n"
                     "⏳ Подбираю оптимальную модель...",
                parse_mode='HTML'
            )
            
            # Получаем список моделей (если доступно)
            models = getattr(self.ai_interpreter, 'model_list', ['openai/gpt-3.5-turbo', 'anthropic/claude-3-haiku', 'meta-llama/llama-3-70b-instruct', 'google/gemini-pro', 'microsoft/wizardlm-2'])
            
            # ✅ ПОЛУЧАЕМ ДАННЫЕ ПРОФИЛЯ ДЛЯ AI
            user_profile = self.user_db.get_user_profile(user_id)
            user_age = None
            user_gender = None
            
            if user_profile and user_profile.get('birth_date'):
                try:
                    # Парсим дату из нового формата ДД.ММ.ГГГГ
                    birth_date_str = user_profile.get('birth_date')
                    if '.' in birth_date_str:
                        birth_date = datetime.strptime(birth_date_str, '%d.%m.%Y')
                    else:
                        # Если дата в старом формате, используем его
                        birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d')
                    
                    # Вычисляем возраст
                    today = datetime.now()
                    user_age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
                    
                    logger.info(f"🎯 Расчет возраста: {birth_date_str} -> {user_age} лет")
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка расчета возраста из {user_profile.get('birth_date')}: {e}")

            if user_profile and user_profile.get('gender'):
                user_gender = user_profile.get('gender')
                logger.info(f"🎯 Передаем пол в AI: {user_gender}")

            # Если имя не передано, получаем из профиля
            if not user_name and user_profile:
                user_name = user_profile.get('first_name', 'друг')

            # Логируем что передаем в AI
            logger.info(f"👤 Данные профиля для AI: gender={user_gender}, age={user_age}, name={user_name}")
            
            for model_index, model in enumerate(models, 1):
                model_name = model.split('/')[-1]
                
                # Обновляем статус для каждой модели
                await self.application.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=process_message.message_id,
                    text=f"🔄 <b>Модель {model_index}/{len(models)}</b>\n"
                         f"Пробую: <code>{model_name}</code>\n"
                         f"⏳ Ожидаю ответа...",
                    parse_mode='HTML'
                )
                
                try:
                    logger.info(f"Trying model {model} for user {user_id}")
                    
                    # ✅ ИСПРАВЛЕННЫЙ ВЫЗОВ AI-ИНТЕРПРЕТАТОРА
                    interpretation = await self.ai_interpreter.generate_interpretation(
                        spread_type=spread_type,
                        cards=spread_cards,
                        category=category,
                        user_age=user_age,
                        user_gender=user_gender,
                        user_name=user_name
                    )
                    
                    # Логируем что именно передаем
                    logger.info(f"🔧 Передаем в AI: age={user_age}, gender={user_gender}, name={user_name}")
                    
                    # ✅ ДОБАВЛЕНА ПРОВЕРКА РЕЗУЛЬТАТА
                    if interpretation and len(interpretation) > 50:
                        # ДИАГНОСТИКА: логируем сгенерированную интерпретацию
                        logger.info(f"🤖 AI-интерпретация сгенерирована, длина: {len(interpretation)}")
                        logger.info(f"📝 Первые 100 символов: {interpretation[:100]}...")
                        
                        # ✅ ИСПРАВЛЕНИЕ: ОБНОВЛЯЕМ ИНТЕРПРЕТАЦИЮ В БАЗЕ ДАННЫХ
                        if spread_id:
                            logger.info(f"💾 Обновление интерпретации для расклада {spread_id}")
                            success = self.user_db.update_interpretation(spread_id, interpretation)
                            
                            if success:
                                logger.info(f"✅ Интерпретация успешно обновлена для расклада {spread_id}")
                            else:
                                logger.error(f"❌ Ошибка обновления интерпретации для расклада {spread_id}")
                        
                        # УСПЕХ
                        await self.application.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=process_message.message_id,
                            text=f"✅ <b>Успешно!</b>\n"
                                 f"Модель: <code>{model_name}</code>\n"
                                 f"📝 Сгенерирована интерпретация",
                            parse_mode='HTML'
                        )
                        return interpretation
                    else:
                        logger.warning(f"Model {model} returned invalid interpretation")
                        continue
                        
                except Exception as e:
                    logger.warning(f"Model {model} failed: {str(e)}")
                    continue
            
            # Все модели не сработали
            await self.application.bot.edit_message_text(
                chat_id=chat_id,
                message_id=process_message.message_id,
                text="❌ <b>Все AI-модели недоступны</b>\n"
                     "Использую базовую интерпретацию",
                parse_mode='HTML'
            )
            
            # Fallback-интерпретация
            interpretation = self._generate_fallback_interpretation(spread_type, spread_cards, category, user_name)
            
            await self.application.bot.send_message(
                chat_id=chat_id,
                text="⚠️ AI-сервисы временно недоступны. Используется базовая интерпретация.",
                reply_markup=keyboards.get_back_to_menu_keyboard()
            )
            
            return interpretation
            
        except Exception as e:
            logger.error(f"AI interpretation process failed: {e}")
            
            # Fallback на случай критической ошибки
            interpretation = self._generate_fallback_interpretation(spread_type, spread_cards, category, user_name or "друг")
            
            await self.application.bot.send_message(
                chat_id=chat_id,
                text=f"❌ Произошла ошибка при генерации интерпретации.\n\n{interpretation}",
                parse_mode='HTML',
                reply_markup=keyboards.get_back_to_menu_keyboard()
            )
            return interpretation

    def _generate_fallback_interpretation(self, spread_type: str, cards: list, category: str, user_name: str) -> str:
        """Базовая интерпретация когда AI недоступен"""
        
        if spread_type == "one_card":
            card = cards[0]
            card_name = card['name'] if isinstance(card, dict) else card
            interpretation = (
                f"{user_name}, карта <b>{card_name}</b> указывает на важные энергии в вашей жизни сегодня. "
                f"Эта карта связана с категорией <b>{category}</b> и может говорить о новых возможностях "
                f"или вызовах, которые вам предстоит рассмотреть. Обратите внимание на знаки и совпадения "
                f"в течение дня - они могут подсказать вам правильное направление."
            )
        else:
            positions = ["Прошлое", "Настоящее", "Будущее"]
            cards_text = "\n".join([f"• {positions[i]}: {card['name'] if isinstance(card, dict) else card}" for i, card in enumerate(cards)])
            
            interpretation = (
                f"{user_name}, этот расклад показывает вашу ситуацию в динамике:\n\n"
                f"{cards_text}\n\n"
                f"В контексте <b>{category}</b> этот расклад может указывать на эволюцию вашей ситуации. "
                f"Прошлое создало основу, настоящее требует внимания к деталям, а будущее предлагает "
                f"возможности для роста. Будьте внимательны к своим интуитивным подсказкам."
            )
        
        interpretation += "\n\n🔮 <i>Базовая интерпретация (AI временно недоступен)</i>"
        return interpretation

    def generate_basic_interpretation(self, cards, spread_type):
        """Генерация базовой интерпретации без AI"""
        # Преобразуем внутренний тип в пользовательский для отображения
        spread_type_mapping = {
            'one_card': '1 карта',
            'three_card': '3 карты'
        }
        user_spread_type = spread_type_mapping.get(spread_type, spread_type)
        
        basic_text = f"📊 <b>Ваш расклад:</b> {user_spread_type}\n\n"
        
        for i, card in enumerate(cards):
            basic_text += f"<b>{i+1}. {card['name']}</b>"
            if card.get('is_reversed', False):
                basic_text += " <i>(Перевернутая)</i>"
            basic_text += "\n"

            # Используем description из данных карты
            description = card.get('description', card.get('meaning', 'N/A'))
            basic_text += f"<i>Описание:</i> {description}\n"

            # Используем keywords из данных карты
            position = card.get('position', 'upright')
            keywords = card.get('keywords', {}).get(position, [])
            if keywords:
                basic_text += f"<i>Ключевые слова:</i> {', '.join(keywords)}\n"

            basic_text += "\n"
        
        basic_text += "🔮 <i>Для более детальной интерпретации используйте AI-интерпретатор.</i>"
        return basic_text

    def format_cards_message(self, cards, spread_type, category):
        """Форматирование сообщения с картами"""
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
            text = "💫 <b>Интерпретация:</b>\n\n"
            text += f"{interpretation}\n\n"
            text += "✨ <i>Интерпретация создана с помощью AI</i>"
        else:
            text = "❌ <b>Не удалось сгенерировать интерпретацию</b>\n\n"
            text += "Попробуйте сделать расклад еще раз"
        
        return text

    def _format_date(self, date_string: str) -> str:
        """Форматирование даты в читаемый вид"""
        if not date_string:
            return "Дата недоступна"
        
        try:
            # Пробуем разные форматы дат
            formats = ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d.%m.%Y %H:%M:%S']
            for fmt in formats:
                try:
                    dt = datetime.strptime(date_string, fmt)
                    return dt.strftime('%d.%m.%Y в %H:%M')
                except ValueError:
                    continue
            return date_string  # Возвращаем как есть, если не распознан
        except Exception:
            return date_string

    async def show_main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ИСПРАВЛЕННЫЙ показ главного меню с корректной HTML-разметкой"""
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
        
        # ВАЖНО: использовать ТОЛЬКО клавиатуру из keyboards.py
        reply_markup = keyboards.get_main_menu_keyboard()
        
        try:
            if update.callback_query:
                # Если пришло из callback, отправляем новое сообщение
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
            logger.info(f"✅ Main menu shown successfully")
            
        except Exception as e:
            logger.error(f"💥 Error showing main menu: {str(e)}")
            # Fallback: отправить без HTML если есть ошибки
            fallback_text = """
🔮 Добро пожаловать в AI-Таролог "Луна"!

Я помогу вам получить инсайты с помощью карт Таро и искусственного интеллекта.

Выберите действие:
• 🎴 Карта дня - быстрый ответ на вопрос
• 🔮 3 карты - прошлое, настоящее, будущее  
• 📖 История раскладов - ваши предыдущие расклады
• 👤 Профиль - настройки профиля
• ℹ️ Помощь - инструкция по использованию

Доступные команды:
/start - главное меню
/profile - управление профилем
/history - история раскладов
/help - справка
/details номер - детали расклада (например: /details 1)
"""
            if update.callback_query:
                await update.callback_query.message.reply_text(
                    fallback_text,
                    reply_markup=reply_markup
                )
            else:
                await update.message.reply_text(
                    fallback_text,
                    reply_markup=reply_markup
                )

    async def show_spread_result(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """ОБНОВЛЕННАЯ функция показа результатов расклада с передачей имени пользователя"""
        user_id = update.effective_user.id
        spread_type = context.user_data.get('spread_type', '1 карта')
        internal_spread_type = context.user_data.get('internal_spread_type', 'one_card')
        category = context.user_data.get('category', 'Общий вопрос')
        spread_cards = context.user_data.get('spread_cards', [])
        spread_id = context.user_data.get('last_spread_id')
        
        # ✅ ПОЛУЧАЕМ ИМЯ ПОЛЬЗОВАТЕЛЯ ИЗ TELEGRAM
        user_name = update.effective_user.first_name
        if not user_name:
            # Если имени нет в Telegram, используем из базы данных
            user_profile = self.user_db.get_user_profile(user_id)
            user_name = user_profile.get('first_name', 'друг') if user_profile else 'друг'
        
        logger.info(f"👤 Имя пользователя для AI: {user_name}")
        
        if not spread_cards:
            error_text = "❌ Ошибка: данные расклада не найдены. Пожалуйста, начните заново с /start"
            if update.callback_query:
                await update.callback_query.message.reply_text(error_text)
            else:
                await update.message.reply_text(error_text)
            return
        
        try:
            # Определяем источник запроса
            if update.callback_query:
                message = update.callback_query.message
                chat_id = message.chat_id
                message_id = message.message_id
            else:
                message = update.message
                chat_id = update.effective_chat.id
                message_id = None

            # 1. Сначала выводим карты текстом
            cards_text = self.format_cards_message(spread_cards, spread_type, category)
            
            if update.callback_query:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=cards_text,
                    parse_mode='HTML'
                )
                original_message_id = message_id
            else:
                sent_message = await context.bot.send_message(
                    chat_id=chat_id,
                    text=cards_text,
                    parse_mode='HTML'
                )
                original_message_id = sent_message.message_id

            # 2. ОТПРАВЛЯЕМ ИЗОБРАЖЕНИЯ КАРТ с внутренним типом
            await self._send_card_images(message, spread_cards, internal_spread_type)

            # 3. Генерируем интерпретацию с визуализацией процесса и сохранением в БД
            # ✅ ПЕРЕДАЕМ ИМЯ ПОЛЬЗОВАТЕЛЯ В AI-ИНТЕРПРЕТАТОР
            interpretation = await self.generate_ai_interpretation(
                spread_cards, internal_spread_type, category, user_id, chat_id, original_message_id, spread_id, user_name
            )
            
            # 4. Если AI не сработал, используем базовую интерпретацию
            if not interpretation:
                interpretation = self.generate_basic_interpretation(spread_cards, internal_spread_type)
            
            # 5. Показываем финальную интерпретацию
            interpretation_text = self.format_interpretation_message(interpretation)
            await context.bot.send_message(
                chat_id=chat_id,
                text=interpretation_text,
                parse_mode='HTML'
            )
            
            # 6. Отправляем финальное сообщение с кнопкой "Задать вопрос"
            final_message = await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"✅ <b>Интерпретация завершена!</b>\n\n"
                    f"🔮 Расклад сохранен в вашей истории.\n"
                    f"💭 Вы можете задать дополнительные вопросы по этому раскладу."
                ),
                parse_mode='HTML',
                reply_markup=keyboards.get_interpretation_keyboard(spread_id)
            )
            
            logger.info(f"✅ Интерпретация успешно завершена для пользователя {user_id} ({user_name})")
            
        except (TimeoutError, Exception) as e:
            # Fallback на базовую интерпретацию
            logger.warning(f"Using fallback interpretation for user {user_id}: {str(e)}")
            
            basic_interpretation = self.generate_basic_interpretation(spread_cards, internal_spread_type)
            interpretation_text = self.format_interpretation_message(basic_interpretation)
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=interpretation_text,
                parse_mode='HTML'
            )
            
            # Добавляем сообщение о использовании базовой интерпретации
            fallback_msg = "⚠️ <i>Использована базовая интерпретация. AI-интерпретация временно недоступна.</i>"
            await context.bot.send_message(
                chat_id=chat_id,
                text=fallback_msg,
                parse_mode='HTML'
            )

    async def generate_spread(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Исправленная функция генерации расклада с преобразованием типов и детальным логированием"""
        
        user_id = update.effective_user.id
        username = update.effective_user.username or f"user_{user_id}"
        
        # Получаем пользовательские названия типов раскладов
        user_spread_type = context.user_data.get('spread_type', '1 карта')
        category = context.user_data.get('category', 'Общий вопрос')
        
        # Преобразуем пользовательские типы в внутренние типы для tarot_engine
        spread_type_mapping = {
            '1 карта': 'one_card',
            '3 карты': 'three_card'
        }
        
        internal_spread_type = spread_type_mapping.get(user_spread_type, 'one_card')
        
        try:
            logger.info(f"Generating spread: user_id={user_id}, username={username}, user_type={user_spread_type}, internal_type={internal_spread_type}, category={category}")
            
            # Используем tarot_engine.generate_spread с правильными внутренними типами
            spread_cards_data, spread_text = tarot_engine.generate_spread(internal_spread_type, category)
            
            # Логируем выпавшие карты и проверяем пути изображений
            card_names = [card['name'] for card in spread_cards_data]
            logger.info(f"Cards drawn for user {user_id}: {card_names}")
            
            # Проверяем пути изображений для каждой карты
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            for card in spread_cards_data:
                image_path = os.path.join(project_root, card['image_url'])
                if os.path.exists(image_path):
                    logger.info(f"✅ Изображение найдено: {card['name']} -> {image_path}")
                else:
                    logger.warning(f"❌ Изображение не найдено: {card['name']} -> {image_path}")
            
            # Сохраняем карты в контекст для использования в show_spread_result
            context.user_data['spread_cards'] = spread_cards_data
            context.user_data['internal_spread_type'] = internal_spread_type  # Сохраняем для _send_card_images

            # Детальное логирование данных карт перед сохранением
            logger.info(f"📦 Данные карт для сохранения в БД:")
            for i, card in enumerate(spread_cards_data):
                logger.info(f"  🎴 Карта {i}: {card.get('name', 'No name')}, "
                           f"position: {card.get('position', 'unknown')}, "
                           f"is_reversed: {card.get('is_reversed', 'unknown')}")
            
            # ДИАГНОСТИКА КАТЕГОРИИ ПЕРЕД СОХРАНЕНИЕМ
            logger.info(f"📋 Категория перед сохранением: '{category}'")

            # ✅ ПРАВИЛЬНОЕ СОХРАНЕНИЕ В БАЗУ ДАННЫХ
            spread_id = self.user_db.add_spread_to_history(
                user_id=user_id,
                username=username,
                spread_type=user_spread_type,
                category=category,  # Убедимся что передаем правильную категорию
                cards=spread_cards_data,
                interpretation=None
            )
            
            # Сохраняем spread_id в контексте для последующего обновления интерпретации
            context.user_data['last_spread_id'] = spread_id
            
            logger.info(f"💾 Расклад {spread_id} сохранен с {len(spread_cards_data)} картами")
            
            # Переходим к показу результатов
            await self.show_spread_result(update, context)
            
        except Exception as e:
            logger.error(f"Error in generate_spread for user {user_id}: {e}")
            error_text = "❌ Произошла ошибка при генерации расклада. Попробуйте еще раз."
            reply_markup = keyboards.get_back_to_menu_keyboard()
            
            if update.callback_query:
                await update.callback_query.message.reply_text(error_text, reply_markup=reply_markup)
            else:
                await update.message.reply_text(error_text, reply_markup=reply_markup)

    async def show_category_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """УНИВЕРСАЛЬНЫЙ показ выбора категории - обрабатывает оба типа callback"""
        
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        callback_data = query.data
        
        logger.info(f"🎯 CATEGORY SELECTION: User {user_id}, callback: {callback_data}")
        
        # Если это callback выбора расклада (spread_single/spread_three)
        if callback_data in ['spread_single', 'spread_three']:
            # Устанавливаем тип расклада
            if callback_data == 'spread_single':
                context.user_data['spread_type'] = '1 карта'
                spread_text = '1 карты'
            else:  # spread_three
                context.user_data['spread_type'] = '3 карты' 
                spread_text = '3 карт'
            
            # Показываем выбор категории для этого расклада
            await query.edit_message_text(
                text=(
                    f"🔮 <b>Выберите категорию для {spread_text}:</b>\n\n"
                    f"💫 Категория помогает AI точнее интерпретировать карты в контексте вашего вопроса."
                ),
                parse_mode='HTML',
                reply_markup=keyboards.get_categories_keyboard()
            )
            return
        
        # Если это прямой выбор категории (уже установлен тип расклада)
        category_map = {
            'category_love': 'Любовь и отношения',
            'category_career': 'Карьера и работа',
            'category_finance': 'Финансы и богатство',
            'category_relationships': 'Отношения',
            'category_growth': 'Личностный рост', 
            'category_general': 'Общий вопрос'
        }
        
        # Обработка кнопки "Свой вопрос"
        if callback_data == "category_custom":
            context.user_data['waiting_for_custom_question'] = True
            await query.edit_message_text(
                text=(
                    "💬 <b>Задайте свой вопрос для расклада</b>\n\n"
                    "📝 <b>Рекомендации по формулировке вопросов:</b>\n"
                    "• Будьте конкретны и четки в формулировке\n"
                    "• Фокусируйтесь на одной теме или ситуации\n"
                    "• Избегайте двусмысленных формулировок\n"
                    "• Задавайте открытые вопросы для более глубокого понимания\n\n"
                    "✨ <b>Примеры хороших вопросов:</b>\n"
                    "• «Что мне ожидать от нового проекта на работе?»\n"
                    "• «Как улучшить отношения с партнером?»\n" 
                    "• «Какие препятствия ждут меня в достижении цели?»\n"
                    "• «Как мне развивать свои творческие способности?»\n\n"
                    "❌ <b>Примеры нежелательных вопросов:</b>\n"
                    "• «Да/Нет вопросы» (лучше спросить «Как...» или «Что...»)\n"
                    "• «Когда это случится?» (таро показывает тенденции, а не сроки)\n"
                    "• Вопросы о других людях без их согласия\n\n"
                    "✍️ <b>Введите ваш вопрос:</b>"
                ),
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🏠 Отмена", callback_data="cancel_custom_question")]
                ])
            )
            return
        
        # Обработка обычных категорий
        category = category_map.get(callback_data, 'Общий вопрос')
        context.user_data['category'] = category
        
        # Запускаем генерацию расклада
        await self.generate_spread(update, context)

    async def handle_text_messages(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Исправленная обработка текстовых сообщений с новым форматом даты"""
        
        user_id = update.effective_user.id
        text = update.message.text.strip()
        
        logger.info(f"💬 Text message from user {user_id}: {text}")
        
        # Обработка пользовательского вопроса
        if context.user_data.get('waiting_for_custom_question'):
            await self.handle_custom_question(update, context)
            return
            
        # ✅ ОБРАБОТКА ВОПРОСОВ ПО РАСКЛАДАМ
        elif 'current_spread_id' in context.user_data:
            spread_id = context.user_data['current_spread_id']
            user_age = context.user_data.get('user_age')
            user_gender = context.user_data.get('user_gender')
            user_name = context.user_data.get('user_name', 'друг')
            
            logger.info(f"💬 Пользователь {user_id} задал вопрос по раскладу {spread_id}: {text}")
            logger.info(f"👤 Данные профиля для вопроса: gender={user_gender}, age={user_age}, name={user_name}")
            
            try:
                # Показываем сообщение о обработке
                processing_msg = await update.message.reply_text(
                    "🔄 Обрабатываю ваш вопрос...",
                    reply_markup=keyboards.get_back_to_menu_keyboard()
                )
                
                # ✅ ИСПРАВЛЕННЫЙ ВЫЗОВ - БЕЗ ПАРАМЕТРА spread_cards
                answer = await self.ai_interpreter.generate_question_answer(
                    spread_id=spread_id,
                    question=text,
                    user_age=user_age,
                    user_gender=user_gender,
                    user_name=user_name
                )
                
                # Удаляем сообщение о обработке
                await context.bot.delete_message(
                    chat_id=user_id,
                    message_id=processing_msg.message_id
                )
                
                if answer:
                    # Сохраняем вопрос и ответ в базу данных
                    success = self.user_db.add_question_to_spread(spread_id, text, answer)
                    
                    if success:
                        await update.message.reply_text(
                            f"💫 <b>Ответ на ваш вопрос:</b>\n\n{answer}\n\n"
                            f"✨ <i>Ответ создан с помощью AI</i>",
                            parse_mode='HTML',
                            reply_markup=keyboards.get_back_to_menu_keyboard()
                        )
                    else:
                        await update.message.reply_text(
                            "❌ Произошла ошибка при сохранении вопроса.",
                            reply_markup=keyboards.get_back_to_menu_keyboard()
                        )
                else:
                    await update.message.reply_text(
                        "❌ Не удалось сгенерировать ответ. Пожалуйста, попробуйте позже.",
                        reply_markup=keyboards.get_back_to_menu_keyboard()
                    )
                
                # Очищаем контекст
                context.user_data.pop('current_spread_id', None)
                context.user_data.pop('user_age', None)
                context.user_data.pop('user_gender', None)
                context.user_data.pop('user_name', None)
                
            except Exception as e:
                logger.error(f"❌ Ошибка обработки вопроса по раскладу: {e}")
                await update.message.reply_text(
                    "❌ Произошла ошибка при обработке вопроса.",
                    reply_markup=keyboards.get_back_to_menu_keyboard()
                )
                
                # Очищаем контекст при ошибке
                context.user_data.pop('current_spread_id', None)
                context.user_data.pop('user_age', None)
                context.user_data.pop('user_gender', None)
                context.user_data.pop('user_name', None)
            
            return
        
        # Обработка ввода даты рождения
        elif context.user_data.get('editing_profile') and context.user_data.get('editing_field') == 'birth_date':
            await self.handle_birth_date_input(update, context)
            return
        
        # ✅ ИСПРАВЛЕННАЯ ОБРАБОТКА ДАТЫ РОЖДЕНИЯ (формат ДД.ММ.ГГГГ)
        elif re.match(r'\d{2}\.\d{2}\.\d{4}', text):
            logger.info(f"📅 Пользователь {user_id} ввел дату рождения: {text}")
            
            try:
                # Валидация даты в формате ДД.ММ.ГГГГ
                birth_date = datetime.strptime(text, '%d.%m.%Y')
                today = datetime.now()
                
                # Проверяем что дата не в будущем
                if birth_date > today:
                    await update.message.reply_text(
                        "❌ Дата рождения не может быть в будущем.",
                        reply_markup=keyboards.get_back_to_menu_keyboard()
                    )
                    return
                
                # Проверяем что возраст разумный
                age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
                if age > 150:
                    await update.message.reply_text(
                        "❌ Пожалуйста, проверьте дату рождения. Возраст не должен превышать 150 лет.",
                        reply_markup=keyboards.get_back_to_menu_keyboard()
                    )
                    return
                
                # ✅ ИСПРАВЛЕНИЕ: Правильный вызов без username
                success = self.user_db.update_user_profile(
                    user_id=user_id,
                    birth_date=text,  # Сохраняем в формате ДД.ММ.ГГГГ
                    gender=None  # Не изменяем пол!
                )
                
                if success:
                    # Вычисляем возраст и знак зодиака для подтверждения
                    try:
                        day = birth_date.day
                        month = birth_date.month
                        zodiac_sign = self._calculate_zodiac_sign(day, month)
                        
                        await update.message.reply_text(
                            f"✅ Дата рождения сохранена: {text}\n"
                            f"📊 Возраст: {age} лет\n"
                            f"♈️ Знак зодиака: {zodiac_sign}\n\n"
                            f"Теперь вы можете установить пол или вернуться в меню.",
                            reply_markup=keyboards.get_back_to_menu_keyboard()
                        )
                    except Exception as e:
                        logger.error(f"❌ Ошибка расчета возраста/знака: {e}")
                        await update.message.reply_text(
                            f"✅ Дата рождения сохранена: {text}\n\n"
                            f"Теперь вы можете установить пол или вернуться в меню.",
                            reply_markup=keyboards.get_back_to_menu_keyboard()
                        )
                else:
                    await update.message.reply_text(
                        "❌ Ошибка сохранения даты рождения.",
                        reply_markup=keyboards.get_back_to_menu_keyboard()
                    )
                    
            except ValueError:
                await update.message.reply_text(
                    "❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ (например: 15.05.1990)\n\n"
                    "Убедитесь, что:\n"
                    "• День от 01 до 31\n"  
                    "• Месяц от 01 до 12\n"
                    "• Год реалистичный (не в будущем)",
                    reply_markup=keyboards.get_back_to_menu_keyboard()
                )
        
        # Обработка Reply-кнопок главного меню
        elif text == "🎴 Карта дня":
            logger.info(f"🔮 User {user_id} selected 1-card spread via text")
            context.user_data['spread_type'] = '1 карта'
            await update.message.reply_text(
                "🔮 <b>Выберите категорию для 1 карты:</b>",
                parse_mode='HTML',
                reply_markup=keyboards.get_categories_keyboard()
            )
            
        elif text == "🔮 3 карты":
            logger.info(f"🔮 User {user_id} selected 3-card spread via text")
            context.user_data['spread_type'] = '3 карты'
            await update.message.reply_text(
                "🔮 <b>Выберите категорию для 3 карт:</b>",
                parse_mode='HTML',
                reply_markup=keyboards.get_categories_keyboard()
            )
            
        elif text == "📖 История раскладов":
            logger.info(f"📖 User {user_id} requested history via text")
            await self.show_history(update, context)
            
        elif text == "👤 Профиль":
            logger.info(f"👤 User {user_id} requested profile via text")
            await self.show_profile(update, context)
            
        elif text == "ℹ️ Помощь":
            logger.info(f"ℹ️ User {user_id} requested help via text")
            await self.show_help(update, context)
            
        elif text == "🏠 Главное меню":
            logger.info(f"🏠 User {user_id} requested main menu via text")
            await self.show_main_menu(update, context)
            
        else:
            # Неизвестное сообщение
            logger.info(f"❓ Unknown text from user {user_id}: {text}")
            await update.message.reply_text(
                "Неизвестная команда. Используйте кнопки меню или команды.",
                reply_markup=keyboards.get_main_menu_keyboard()
            )

    async def handle_custom_question(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик ввода пользовательского вопроса"""
        
        user_id = update.effective_user.id
        user_question = update.message.text
        
        if not context.user_data.get('waiting_for_custom_question'):
            await self.show_main_menu(update, context)
            return
        
        # Проверяем длину вопроса
        if len(user_question) < 5:
            await update.message.reply_text(
                "❌ Вопрос слишком короткий. Пожалуйста, сформулируйте более развернутый вопрос.",
                reply_markup=keyboards.get_back_to_menu_keyboard()
            )
            return
        
        if len(user_question) > 500:
            await update.message.reply_text(
                "❌ Вопрос слишком длинный. Пожалуйста, сформулируйте вопрос короче (до 500 символов).",
                reply_markup=keyboards.get_back_to_menu_keyboard()
            )
            return
        
        # Сохраняем вопрос и запускаем генерацию расклада
        spread_type = context.user_data.get('spread_type', '1 карта')
        context.user_data['waiting_for_custom_question'] = False
        context.user_data['category'] = user_question  # Используем вопрос как категорию
        
        logger.info(f"🎯 Пользовательский вопрос от {user_id}: {user_question}")
        
        # Запускаем генерацию расклада с пользовательским вопросом
        await self.generate_spread(update, context)

    async def handle_spread_question(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик ввода вопроса по раскладу с передачей данных профиля"""
        
        user_id = update.effective_user.id
        question_text = update.message.text
        
        if not context.user_data.get('waiting_for_spread_question'):
            # Если состояние не установлено, просто выходим
            await self.show_main_menu(update, context)
            return
        
        spread_id = context.user_data.get('target_spread_id')
        
        # Сбрасываем состояние сразу, чтобы избежать повторной обработки
        context.user_data['waiting_for_spread_question'] = False
        context.user_data['target_spread_id'] = None
        
        # Проверяем вопрос
        if len(question_text) < 5:
            await update.message.reply_text(
                "❌ Вопрос слишком короткий. Пожалуйста, сформулируйте более развернутый вопрос.",
                reply_markup=keyboards.get_back_to_menu_keyboard()
            )
            return
        
        if len(question_text) > 500:
            await update.message.reply_text(
                "❌ Вопрос слишком длинный. Пожалуйста, сформулируйте вопрос короче.",
                reply_markup=keyboards.get_back_to_menu_keyboard()
            )
            return
        
        try:
            # ✅ ПОЛУЧАЕМ ДАННЫЕ ПРОФИЛЯ И ИМЯ ДЛЯ AI
            user_profile = self.user_db.get_user_profile(user_id)
            user_age = None
            user_gender = None
            user_name = update.effective_user.first_name  # Получаем имя из Telegram
            
            # Если имени нет в Telegram, используем из базы данных
            if not user_name and user_profile:
                user_name = user_profile.get('first_name', 'друг')
            
            if user_profile and user_profile.get('birth_date'):
                try:
                    birth_date_str = user_profile.get('birth_date')
                    if '.' in birth_date_str:
                        birth_date = datetime.strptime(birth_date_str, '%d.%m.%Y')
                    else:
                        birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d')
                    
                    today = datetime.now()
                    user_age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
                    logger.info(f"🎯 Расчет возраста для вопроса: {birth_date_str} -> {user_age} лет")
                except Exception as e:
                    logger.error(f"❌ Ошибка расчета возраста для вопроса: {e}")
            
            if user_profile and user_profile.get('gender'):
                user_gender = user_profile.get('gender')
            
            logger.info(f"💭 Пользователь {user_id} запросил вопрос по раскладу {spread_id}")
            logger.info(f"👤 Данные профиля для вопроса: gender={user_gender}, age={user_age}, name={user_name}")
            
            # Отправляем сообщение о начале обработки
            processing_msg = await update.message.reply_text(
                "🔄 Обрабатываю ваш вопрос...",
                reply_markup=keyboards.get_back_to_menu_keyboard()
            )
            
            # Получаем данные расклада
            history = self.user_db.get_user_history(user_id, limit=100)
            spread_data = next((spread for spread in history if spread.get('id') == spread_id), None)
            
            if not spread_data:
                # ИСПРАВЛЕНИЕ: отправляем новое сообщение вместо редактирования
                await processing_msg.delete()
                await update.message.reply_text(
                    "❌ Расклад не найден.",
                    reply_markup=keyboards.get_back_to_menu_keyboard()
                )
                return
            
            # ✅ ИСПРАВЛЕННЫЙ ВЫЗОВ AI-ИНТЕРПРЕТАТОРА ДЛЯ ВОПРОСА
            answer = await self.ai_interpreter.generate_question_answer(
                spread_id=spread_id,
                question=question_text,
                user_age=user_age,
                user_gender=user_gender,
                user_name=user_name
            )
            
            # Логируем что именно передаем
            logger.info(f"🔧 Передаем в AI для вопроса: spread_id={spread_id}, age={user_age}, gender={user_gender}, name={user_name}")
            
            # Сохраняем вопрос и ответ в базу данных
            success = self.user_db.add_question_to_spread(
                spread_id, question_text, answer
            )
            
            if success:
                # Формируем ответное сообщение
                response_text = (
                    f"💭 <b>Ваш вопрос:</b>\n{question_text}\n\n"
                    f"🔮 <b>Ответ по раскладу:</b>\n{answer}\n\n"
                    f"📚 Для просмотра всех вопросов по этому раскладу используйте /details {spread_id}"
                )
                
                # ИСПРАВЛЕНИЕ: отправляем новое сообщение вместо редактирования
                await processing_msg.delete()
                await update.message.reply_text(
                    response_text,
                    parse_mode='HTML',
                    reply_markup=keyboards.get_back_to_menu_keyboard()
                )
            else:
                # ИСПРАВЛЕНИЕ: отправляем новое сообщение вместо редактирования
                await processing_msg.delete()
                await update.message.reply_text(
                    "❌ Произошла ошибка при сохранении вопроса.",
                    reply_markup=keyboards.get_back_to_menu_keyboard()
                )
                
        except Exception as e:
            logger.error(f"❌ Ошибка обработки вопроса по раскладу: {e}")
            # Пытаемся отправить сообщение об ошибке, даже если редактирование не удалось
            try:
                await update.message.reply_text(
                    "❌ Произошла ошибка при обработке вопроса.",
                    reply_markup=keyboards.get_back_to_menu_keyboard()
                )
            except Exception as send_error:
                logger.error(f"❌ Не удалось отправить сообщение об ошибке: {send_error}")

    async def handle_ask_question_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Исправленный обработчик кнопки 'Задать вопрос по раскладу'"""
        
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        callback_data = query.data
        
        # Извлекаем ID расклада из callback_data (формат: "ask_question_1")
        try:
            spread_id = int(callback_data.split('_')[2])
            
            # ✅ ПОЛУЧАЕМ ДАННЫЕ ПРОФИЛЯ ДЛЯ AI
            user_profile = self.user_db.get_user_profile(user_id)
            user_age = None
            user_gender = None
            first_name = query.from_user.first_name or "друг"
            
            if user_profile and user_profile.get('birth_date'):
                try:
                    birth_date_str = user_profile.get('birth_date')
                    if '.' in birth_date_str:
                        birth_date = datetime.strptime(birth_date_str, '%d.%m.%Y')
                    else:
                        birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d')
                    
                    today = datetime.now()
                    user_age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
                except Exception as e:
                    logger.error(f"❌ Ошибка расчета возраста для вопроса: {e}")
            
            if user_profile and user_profile.get('gender'):
                user_gender = user_profile.get('gender')
            
            logger.info(f"💭 Пользователь {user_id} запросил вопрос по раскладу {spread_id}")
            logger.info(f"👤 Данные профиля для callback вопроса: gender={user_gender}, age={user_age}, name={first_name}")
            
            # Сохраняем данные для последующего использования
            context.user_data['current_spread_id'] = spread_id
            context.user_data['user_age'] = user_age
            context.user_data['user_gender'] = user_gender
            context.user_data['user_name'] = first_name
            
            await query.edit_message_text(
                f"💭 <b>Задайте вопрос по раскладу</b>\n\n"
                f"👤 <i>Ваши данные для персонализации:</i>\n"
                f"• Имя: {first_name}\n"
                f"• Возраст: {user_age if user_age else 'не указан'}\n"
                f"• Пол: {self._format_gender(user_gender) if user_gender else 'не указан'}\n\n"
                f"📝 Напишите ваш вопрос в чат...",
                parse_mode='HTML'
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка обработки запроса вопроса по раскладу: {e}")
            await query.edit_message_text(
                "❌ Произошла ошибка при загрузке данных расклада.",
                reply_markup=keyboards.get_back_to_menu_keyboard()
            )

    async def handle_view_questions_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Просмотр вопросов по раскладу"""
        
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        spread_id = int(query.data.split('_')[2])
        
        try:
            questions = self.user_db.get_spread_questions(spread_id)
            
            if not questions:
                await query.edit_message_text(
                    "📝 По этому раскладу еще нет заданных вопросов.",
                    reply_markup=keyboards.get_spread_details_keyboard(spread_id, False)
                )
                return
            
            questions_text = "📝 <b>Вопросы по раскладу:</b>\n\n"
            
            for i, qa in enumerate(questions, 1):
                questions_text += f"<b>{i}. Вопрос:</b>\n{qa['question']}\n\n"
                questions_text += f"<b>Ответ:</b>\n{qa['answer']}\n\n"
                questions_text += "─" * 30 + "\n\n"
            
            await query.edit_message_text(
                questions_text,
                parse_mode='HTML',
                reply_markup=keyboards.get_spread_details_keyboard(spread_id, True)
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка просмотра вопросов: {e}")
            await query.edit_message_text(
                "❌ Произошла ошибка при загрузке вопросов.",
                reply_markup=keyboards.get_back_to_menu_keyboard()
            )

    async def handle_cancel_custom_question(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик отмены пользовательского вопроса"""
        query = update.callback_query
        await query.answer()
        
        context.user_data['waiting_for_custom_question'] = False
        await self.show_main_menu(update, context)

    async def handle_cancel_spread_question(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик отмены вопроса по раскладу"""
        query = update.callback_query
        await query.answer()
        
        context.user_data['waiting_for_spread_question'] = False
        await self.show_main_menu(update, context)

    # ========== ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ ==========

    async def show_profile(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Исправленный показ профиля пользователя с новым форматом даты"""
        
        user_id = update.effective_user.id
        
        try:
            profile = self.user_db.get_user_profile(user_id)
            
            # ВЫЧИСЛЯЕМ возраст и знак зодиака на основе данных профиля
            age = None
            zodiac = None
            formatted_birth_date = None
            
            if profile and profile.get('birth_date'):
                # Обрабатываем дату в новом формате ДД.ММ.ГГГГ
                birth_date_str = profile['birth_date']
                
                # Если дата в старом формате ГГГГ-ММ-ДД, конвертируем
                if re.match(r'\d{4}-\d{2}-\d{2}', birth_date_str):
                    try:
                        birth_date_obj = datetime.strptime(birth_date_str, '%Y-%m-%d')
                        formatted_birth_date = birth_date_obj.strftime('%d.%m.%Y')
                        # Обновляем профиль с новым форматом
                        self.user_db.update_user_profile(
                            user_id=user_id,
                            birth_date=formatted_birth_date,
                            gender=None
                        )
                    except Exception as e:
                        logger.error(f"❌ Ошибка конвертации даты: {e}")
                        formatted_birth_date = birth_date_str
                else:
                    formatted_birth_date = birth_date_str
                
                # Вычисляем возраст и знак зодиака
                try:
                    if formatted_birth_date and re.match(r'\d{2}\.\d{2}\.\d{4}', formatted_birth_date):
                        birth_date_obj = datetime.strptime(formatted_birth_date, '%d.%m.%Y')
                        today = datetime.now()
                        age = today.year - birth_date_obj.year - ((today.month, today.day) < (birth_date_obj.month, birth_date_obj.day))
                        
                        # Определяем знак зодиака
                        zodiac = self._calculate_zodiac_sign(birth_date_obj.day, birth_date_obj.month)
                except Exception as e:
                    logger.error(f"❌ Ошибка вычисления возраста/знака зодиака: {e}")
            
            profile_text = "👤 <b>Ваш профиль</b>\n\n"
            
            # Дата рождения
            if formatted_birth_date:
                profile_text += f"📅 <b>Дата рождения:</b> {formatted_birth_date}\n"
                if age:
                    profile_text += f"   🎂 <i>Возраст:</i> {age} лет\n"
                if zodiac:
                    profile_text += f"   ♈️ <i>Знак зодиака:</i> {zodiac}\n"
            elif profile and profile.get('birth_date'):
                profile_text += f"📅 <b>Дата рождения:</b> {profile['birth_date']} (требуется обновление формата)\n"
            else:
                profile_text += "📅 <b>Дата рождения:</b> не указана\n"
            
            # Пол
            if profile and profile.get('gender'):
                gender_display = self._format_gender(profile['gender'])
                profile_text += f"⚧ <b>Пол:</b> {gender_display}\n"
            else:
                profile_text += "⚧ <b>Пол:</b> не указан\n"
            
            profile_text += "\n💡 <i>Эти данные помогают делать интерпретации более точными и персонализированными</i>"
            
            # ✅ ОБНОВЛЕННОЕ СООБЩЕНИЕ С НОВЫМ ФОРМАТОМ ДАТЫ
            help_text = (
                "\n\n📝 <b>Как редактировать:</b>\n"
                "• Нажмите <b>«📅 Дата рождения»</b> и введите дату в формате <b>ДД.ММ.ГГГГ</b>\n"
                "• Нажмите <b>«⚧ Пол»</b> для выбора пола\n"
                "• Нажмите <b>«🗑️ Очистить профиль»</b> чтобы удалить данные\n"
                "• Пример даты: <code>15.05.1990</code>"
            )
            
            # Используем Inline-клавиатуру для callback сообщений
            if update.callback_query:
                await update.callback_query.edit_message_text(
                    profile_text + help_text,
                    parse_mode='HTML',
                    reply_markup=keyboards.get_profile_keyboard()
                )
            else:
                # Для текстовых сообщений используем Inline-клавиатуру
                await update.message.reply_text(
                    profile_text + help_text,
                    parse_mode='HTML',
                    reply_markup=keyboards.get_profile_keyboard()
                )
            
        except Exception as e:
            logger.error(f"❌ Ошибка показа профиля для пользователя {user_id}: {e}")
            error_message = "❌ Произошла ошибка при загрузке профиля. Попробуйте позже."
            
            if update.callback_query:
                await update.callback_query.edit_message_text(
                    error_message,
                    reply_markup=keyboards.get_back_to_menu_inline_keyboard()
                )
            else:
                await update.message.reply_text(
                    error_message,
                    reply_markup=keyboards.get_back_to_menu_keyboard()
                )

    async def handle_profile_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Исправленный обработчик callback от кнопок профиля"""
        
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        callback_data = query.data
        
        try:
            if callback_data == "edit_birth_date":
                context.user_data['editing_profile'] = True
                context.user_data['editing_field'] = 'birth_date'
                
                await query.edit_message_text(
                    "📅 <b>Введите вашу дату рождения</b>\n\n"
                    "Формат: <b>ДД.ММ.ГГГГ</b>\n"
                    "Например: <code>15.05.1990</code>\n\n"
                    "💡 <i>Эта информация поможет делать интерпретации более точными</i>",
                    parse_mode='HTML',
                    reply_markup=keyboards.get_cancel_edit_keyboard()
                )
                
            elif callback_data == "edit_gender":
                await query.edit_message_text(
                    "⚧ <b>Выберите ваш пол</b>\n\n"
                    "💡 <i>Эта информация поможет адаптировать интерпретации specifically для вас</i>",
                    parse_mode='HTML',
                    reply_markup=keyboards.get_gender_selection_keyboard()
                )
                
            elif callback_data.startswith("gender_"):
                gender = callback_data.replace("gender_", "")
                
                gender_display = self._format_gender(gender)
                
                logger.info(f"⚧ Пользователь {user_id} выбрал пол: {gender_display}")
                
                # ✅ ИСПРАВЛЕНИЕ: Правильный вызов без username
                success = self.user_db.update_user_profile(
                    user_id=user_id,
                    gender=gender
                    # birth_date не передаем - сохраняется текущее значение
                )
                
                if success:
                    # Показываем обновленный профиль
                    await self.show_profile(update, context)
                else:
                    await query.edit_message_text(
                        "❌ Произошла ошибка при сохранении. Попробуйте позже.",
                        reply_markup=keyboards.get_back_to_menu_inline_keyboard()
                    )
                        
            elif callback_data == "clear_profile":
                # При очистке профиля сбрасываем оба поля
                success = self.user_db.update_user_profile(
                    user_id=user_id,
                    birth_date=None,
                    gender=None
                )
                
                if success:
                    await query.edit_message_text(
                        "✅ <b>Профиль очищен</b>\n\n"
                        "Все персональные данные удалены.",
                        parse_mode='HTML',
                        reply_markup=keyboards.get_back_to_menu_inline_keyboard()
                    )
                else:
                    await query.edit_message_text(
                        "❌ Произошла ошибка. Попробуйте позже.",
                        reply_markup=keyboards.get_back_to_menu_inline_keyboard()
                    )
                        
            elif callback_data == "cancel_edit":
                await query.edit_message_text(
                    "👤 <b>Редактирование отменено</b>",
                    parse_mode='HTML',
                    reply_markup=keyboards.get_back_to_menu_inline_keyboard()
                )
                    
        except Exception as e:
            logger.error(f"❌ Ошибка обработки callback профиля: {e}")
            await query.edit_message_text(
                "❌ Произошла ошибка. Попробуйте позже.",
                reply_markup=keyboards.get_back_to_menu_inline_keyboard()
            )

    async def handle_birth_date_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Исправленный обработчик ввода даты рождения с новым форматом"""
        
        user_id = update.effective_user.id
        text = update.message.text.strip()
        
        # Проверяем формат даты - теперь ДД.ММ.ГГГГ
        if not re.match(r'^\d{2}\.\d{2}\.\d{4}$', text):
            await update.message.reply_text(
                "❌ <b>Неверный формат даты</b>\n\n"
                "Пожалуйста, используйте формат: <b>ДД.ММ.ГГГГ</b>\n"
                "Например: <code>15.05.1990</code>",
                parse_mode='HTML',
                reply_markup=keyboards.get_cancel_edit_keyboard()
            )
            return
        
        # Проверяем валидность даты
        try:
            birth_date = datetime.strptime(text, '%d.%m.%Y')
            today = datetime.now()
            
            # Проверяем что дата не в будущем
            if birth_date > today:
                await update.message.reply_text(
                    "❌ <b>Дата рождения не может быть в будущем</b>\n\n"
                    "Пожалуйста, введите корректную дату:",
                    parse_mode='HTML',
                    reply_markup=keyboards.get_cancel_edit_keyboard()
                )
                return
                
            # Проверяем что возраст разумный (например, не больше 150 лет)
            age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
            if age > 150:
                await update.message.reply_text(
                    "❌ <b>Пожалуйста, проверьте дату рождения</b>\n\n"
                    "Возраст не должен превышать 150 лет.",
                    parse_mode='HTML',
                    reply_markup=keyboards.get_cancel_edit_keyboard()
                )
                return
                
        except ValueError:
            await update.message.reply_text(
                "❌ <b>Неверная дата</b>\n\n"
                "Пожалуйста, введите существующую дату в формате <b>ДД.ММ.ГГГГ</b>",
                parse_mode='HTML',
                reply_markup=keyboards.get_cancel_edit_keyboard()
            )
            return
        
        # ✅ ИСПРАВЛЕНИЕ: Правильный вызов без username
        success = self.user_db.update_user_profile(
            user_id=user_id,
            birth_date=text,  # Сохраняем в формате ДД.ММ.ГГГГ
            gender=None  # Не изменяем пол!
        )
        
        if success:
            # Вычисляем возраст и знак зодиака локально
            try:
                day = birth_date.day
                month = birth_date.month
                zodiac = self._calculate_zodiac_sign(day, month)
            except Exception as e:
                logger.error(f"❌ Ошибка вычисления знака зодиака: {e}")
                zodiac = None
            
            response_text = f"✅ <b>Дата рождения сохранена!</b>\n\n📅 {text}"
            if age:
                response_text += f"\n🎂 Возраст: {age} лет"
            if zodiac:
                response_text += f"\n♈️ Знак зодиака: {zodiac}"
                
            response_text += "\n\n💡 Теперь ваши интерпретации будут более точными!"
            
            await update.message.reply_text(
                response_text,
                parse_mode='HTML',
                reply_markup=keyboards.get_back_to_menu_keyboard()
            )
        else:
            await update.message.reply_text(
                "❌ Произошла ошибка при сохранении. Попробуйте позже.",
                reply_markup=keyboards.get_back_to_menu_keyboard()
            )
        
        # Сбрасываем состояние редактирования
        if 'editing_profile' in context.user_data:
            del context.user_data['editing_profile']
            del context.user_data['editing_field']

    async def show_spread_details_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показ деталей расклада при нажатии из истории (callback)"""
        
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        callback_data = query.data
        
        try:
            # Извлекаем ID расклада из callback_data (формат: "spread_1")
            spread_id = int(callback_data.split('_')[1])
            
            # Получаем историю пользователя
            history = self.user_db.get_user_history(user_id, limit=100)
            
            # Находим расклад по ID
            spread_data = None
            spread_number = None
            for i, spread in enumerate(history, 1):
                if spread['id'] == spread_id:
                    spread_data = spread
                    spread_number = i
                    break
            
            if not spread_data:
                await query.edit_message_text(
                    "❌ Расклад не найден.",
                    reply_markup=keyboards.get_back_to_menu_keyboard()
                )
                return
            
            # Получаем вопросы по этому раскладу
            questions = self.user_db.get_spread_questions(spread_id)
            
            # Формируем текст деталей
            category = spread_data.get('category', 'Общий вопрос')
            cards_display = ", ".join(spread_data.get('cards', []))
            interpretation = spread_data.get('interpretation', 'не сгенерирована')
            
            # Форматируем дату
            created_at = spread_data.get('created_at', '')
            if isinstance(created_at, str) and 'T' in created_at:
                date_part = created_at.split('T')[0]
                time_part = created_at.split('T')[1][:5]
                date_display = f"{date_part} в {time_part}"
            else:
                date_display = str(created_at)[:16]
            
            details_text = (
                f"🔮 <b>Детали расклада #{spread_number}</b>\n\n"
                f"<b>Тип расклада:</b> {spread_data['spread_type']}\n"
                f"<b>Категория:</b> {category}\n"
                f"<b>Дата:</b> {date_display}\n\n"
                f"<b>Карты в раскладе:</b>\n{cards_display}\n\n"
                f"<b>Интерпретация:</b>\n{interpretation}\n\n"
            )
            
            # Добавляем вопросы
            if questions:
                details_text += f"<b>💭 Вопросы по раскладу ({len(questions)}):</b>\n\n"
                
                for i, qa in enumerate(questions, 1):
                    question_preview = qa['question']
                    if len(question_preview) > 80:
                        question_preview = question_preview[:80] + "..."
                    
                    answer_preview = qa['answer']
                    if len(answer_preview) > 120:
                        answer_preview = answer_preview[:120] + "..."
                    
                    details_text += (
                        f"<b>{i}. Вопрос:</b> {question_preview}\n"
                        f"<b>Ответ:</b> {answer_preview}\n"
                        f"────────────────────\n\n"
                    )
            else:
                details_text += "<b>💭 Вопросы по раскладу:</b> пока нет заданных вопросов\n\n"
            
            details_text += "💡 <i>Чтобы задать новый вопрос, используйте кнопку ниже</i>"
            
            await query.edit_message_text(
                details_text,
                parse_mode='HTML',
                reply_markup=keyboards.get_spread_details_keyboard(spread_id, len(questions) > 0)
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка показа деталей расклада из callback: {e}")
            await query.edit_message_text(
                "❌ Произошла ошибка при загрузке деталей расклада.",
                reply_markup=keyboards.get_back_to_menu_keyboard()
            )

    async def show_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показ истории раскладов с кнопками для деталей"""
        
        user_id = update.effective_user.id
        logger.info(f"📖 Getting history for user {user_id}")
        
        try:
            history = self.user_db.get_user_history(user_id, limit=10)
            logger.info(f"📋 Получена история: {len(history)} записей")
            
            if not history:
                await update.message.reply_text(
                    "📜 У вас пока нет сохраненных раскладов.",
                    reply_markup=keyboards.get_back_to_menu_keyboard()
                )
                return
            
            # Создаем inline клавиатуру с раскладами
            keyboard = []
            for i, spread in enumerate(history, 1):
                spread_info = f"{i}. {spread['spread_type']} - {spread['category']}"
                
                # Проверяем наличие вопросов
                questions = self.user_db.get_spread_questions(spread['id'])
                if questions:
                    spread_info += " 💭"
                
                keyboard.append([
                    InlineKeyboardButton(
                        spread_info,
                        callback_data=f"spread_{spread['id']}"
                    )
                ])
            
            # Добавляем кнопку возврата в меню
            keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_menu")])
            
            history_text = (
                f"📜 <b>История ваших раскладов</b>\n\n"
                f"Всего раскладов: {len(history)}\n\n"
                f"💭 - есть заданные вопросы\n\n"
                f"<i>Выберите расклад для просмотра деталей:</i>"
            )
            
            await update.message.reply_text(
                history_text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка показа истории для пользователя {user_id}: {e}")
            await update.message.reply_text(
                "❌ Произошла ошибка при загрузке истории.",
                reply_markup=keyboards.get_back_to_menu_keyboard()
            )

    async def show_history_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показ истории через callback (для кнопки 'Назад к истории')"""
        
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        
        try:
            history = self.user_db.get_user_history(user_id, limit=10)
            
            if not history:
                await query.edit_message_text(
                    "📜 У вас пока нет сохраненных раскладов.",
                    reply_markup=keyboards.get_back_to_menu_keyboard()
                )
                return
            
            # Создаем inline клавиатуру с раскладами
            keyboard = []
            for i, spread in enumerate(history, 1):
                spread_info = f"{i}. {spread['spread_type']} - {spread['category']}"
                
                # Проверяем наличие вопросов
                questions = self.user_db.get_spread_questions(spread['id'])
                if questions:
                    spread_info += " 💭"
                
                keyboard.append([
                    InlineKeyboardButton(
                        spread_info,
                        callback_data=f"spread_{spread['id']}"
                    )
                ])
            
            keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_menu")])
            
            history_text = (
                f"📜 <b>История ваших раскладов</b>\n\n"
                f"Всего раскладов: {len(history)}\n\n"
                f"💭 - есть заданные вопросы\n\n"
                f"<i>Выберите расклад для просмотра деталей:</i>"
            )
            
            await query.edit_message_text(
                history_text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка показа истории (callback) для пользователя {user_id}: {e}")
            await query.edit_message_text(
                "❌ Произошла ошибка при загрузке истории.",
                reply_markup=keyboards.get_back_to_menu_keyboard()
            )

    async def handle_details_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик нажатия на кнопку деталей расклада"""
        
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        callback_data = query.data
        
        # Извлекаем номер расклада из callback_data (формат: "details_1")
        try:
            spread_number = int(callback_data.split('_')[1])
            logger.info(f"📖 User {user_id} requested details for spread {spread_number}")
            
            # Получаем историю и отображаем детали
            history = self.user_db.get_user_history(user_id, limit=100)
            
            if spread_number > len(history) or spread_number < 1:
                await query.edit_message_text(
                    f"❌ Расклад с номером {spread_number} не найден.",
                    reply_markup=keyboards.get_back_to_menu_keyboard()
                )
                return
            
            spread_data = history[spread_number - 1]
            spread_id = spread_data.get('id')
            
            # Получаем вопросы по этому раскладу
            questions = self.user_db.get_spread_questions(spread_id)
            
            # ДИАГНОСТИКА: логируем полученные данные
            logger.info(f"🔍 Детали расклада {spread_number}:")
            logger.info(f"   Категория из БД: '{spread_data.get('category')}'")
            logger.info(f"   Карты: {spread_data.get('cards')}")
            logger.info(f"   Интерпретация: {bool(spread_data.get('interpretation'))}")
            logger.info(f"   Количество вопросов: {len(questions)}")
            
            # ИСПРАВЛЕНИЕ 1: Правильное отображение категории
            category = spread_data.get('category')
            if not category or category == 'None' or category == 'null':
                category = 'Общий вопрос'
            
            # ИСПРАВЛЕНИЕ 2: Правильное отображение карт
            cards_display = "информация недоступна"
            cards_list = spread_data.get('cards', [])
            if cards_list and isinstance(cards_list, list) and len(cards_list) > 0:
                cards_display = ", ".join(cards_list)
            
            # ИСПРАВЛЕНИЕ 3: Правильное отображение интерпретации
            interpretation = spread_data.get('interpretation')
            interpretation_text = interpretation if interpretation else "не сгенерирована"
            
            # Форматируем дату
            created_at = spread_data.get('created_at', '')
            if isinstance(created_at, str) and 'T' in created_at:
                date_part = created_at.split('T')[0]
                time_part = created_at.split('T')[1][:5]
                date_display = f"{date_part} в {time_part}"
            else:
                date_display = str(created_at)[:16]
            
            # Формируем основную информацию о раскладе
            details_text = (
                f"🔮 <b>Детали расклада #{spread_number}</b>\n\n"
                f"<b>Тип расклада:</b> {spread_data['spread_type']}\n"
                f"<b>Категория:</b> {category}\n"
                f"<b>Дата:</b> {date_display}\n\n"
                f"<b>Карты в раскладе:</b>\n{cards_display}\n\n"
                f"<b>Интерпретация:</b>\n{interpretation_text}\n\n"
            )
            
            # ДОБАВЛЕНИЕ: Отображение вопросов и ответов
            if questions:
                details_text += f"<b>💭 Вопросы по раскладу ({len(questions)}):</b>\n\n"
                
                for i, qa in enumerate(questions, 1):
                    # Обрезаем длинные ответы для лучшего отображения
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
            
            # Создаем клавиатуру для возврата к истории и дополнительных действий
            keyboard = [
                [InlineKeyboardButton("📜 Назад к истории", callback_data="back_to_history")],
                [InlineKeyboardButton("💭 Задать вопрос по раскладу", callback_data=f"ask_question_{spread_id}")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                details_text,
                parse_mode='HTML',
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка обработки деталей расклада: {e}")
            await query.edit_message_text(
                "❌ Произошла ошибка при загрузке деталей расклада.",
                reply_markup=keyboards.get_back_to_menu_keyboard()
            )

    async def show_spread_details(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Исправленный показ деталей конкретного расклада с вопросами"""
        
        user_id = update.effective_user.id
        args = context.args
        
        if not args or not args[0].isdigit():
            await update.message.reply_text(
                "❌ Пожалуйста, укажите номер расклада. Например: /details 1",
                reply_markup=keyboards.get_back_to_menu_keyboard()
            )
            return
        
        spread_number = int(args[0])
        
        try:
            # Получаем историю с большим лимитом чтобы найти нужный расклад
            history = self.user_db.get_user_history(user_id, limit=100)
            
            if spread_number > len(history) or spread_number < 1:
                await update.message.reply_text(
                    f"❌ Расклад с номером {spread_number} не найден.",
                    reply_markup=keyboards.get_back_to_menu_keyboard()
                )
                return
            
            spread_data = history[spread_number - 1]
            spread_id = spread_data.get('id')
            
            # Получаем вопросы по этому раскладу
            questions = self.user_db.get_spread_questions(spread_id)
            
            # ДИАГНОСТИКА: логируем полученные данные
            logger.info(f"🔍 Детали расклада {spread_number} (ID: {spread_id}):")
            logger.info(f"   Категория из БД: '{spread_data.get('category')}'")
            logger.info(f"   Карты: {spread_data.get('cards')}")
            logger.info(f"   Интерпретация: {bool(spread_data.get('interpretation'))}")
            logger.info(f"   Количество вопросов: {len(questions)}")
            
            # ИСПРАВЛЕНИЕ 1: Правильное отображение категории
            category = spread_data.get('category')
            if not category or category == 'None' or category == 'null':
                category = 'Общий вопрос'
            
            # ИСПРАВЛЕНИЕ 2: Правильное отображение карт
            cards_display = "информация недоступна"
            cards_list = spread_data.get('cards', [])
            if cards_list and isinstance(cards_list, list) and len(cards_list) > 0:
                cards_display = ", ".join(cards_list)
            
            # ИСПРАВЛЕНИЕ 3: Правильное отображение интерпретации
            interpretation = spread_data.get('interpretation')
            interpretation_text = interpretation if interpretation else "не сгенерирована"
            
            # Форматируем дату
            created_at = spread_data.get('created_at', '')
            if isinstance(created_at, str) and 'T' in created_at:
                date_part = created_at.split('T')[0]
                time_part = created_at.split('T')[1][:5]
                date_display = f"{date_part} в {time_part}"
            else:
                date_display = str(created_at)[:16]
            
            # Формируем основную информацию о раскладе
            details_text = (
                f"🔮 <b>Детали расклада #{spread_number}</b>\n\n"
                f"<b>Тип расклада:</b> {spread_data['spread_type']}\n"
                f"<b>Категория:</b> {category}\n"
                f"<b>Дата:</b> {date_display}\n\n"
                f"<b>Карты в раскладе:</b>\n{cards_display}\n\n"
                f"<b>Интерпретация:</b>\n{interpretation_text}\n\n"
            )
            
            # ДОБАВЛЕНИЕ: Отображение вопросов и ответов
            if questions:
                details_text += f"<b>💭 Вопросы по раскладу ({len(questions)}):</b>\n\n"
                
                for i, qa in enumerate(questions, 1):
                    # Обрезаем длинные ответы для лучшего отображения
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
            
            # Используем клавиатуру с кнопкой для вопросов
            await update.message.reply_text(
                details_text,
                parse_mode='HTML',
                reply_markup=keyboards.get_spread_details_keyboard(spread_id, len(questions) > 0)
            )
            
        except Exception as e:
            logger.error(f"❌ Ошибка показа деталей расклада {spread_number} для пользователя {user_id}: {e}")
            await update.message.reply_text(
                "❌ Произошла ошибка при загрузке деталей расклада.",
                reply_markup=keyboards.get_back_to_menu_keyboard()
            )

    async def handle_back_to_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик возврата в главное меню"""
        query = update.callback_query
        await query.answer()
        
        await self.show_main_menu(update, context)

    async def handle_back_to_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик возврата к истории раскладов"""
        query = update.callback_query
        await query.answer()
        
        # Просто вызываем show_history с новым сообщением
        await self.show_history(update, context)

    async def show_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """ИСПРАВЛЕННЫЙ показ справки с корректной HTML-разметкой"""
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

<b>Как работает AI-интерпретация:</b>
Бот использует 5 различных AI-моделей через OpenRouter для генерации интерпретаций. Если одна модель недоступна, автоматически пробуется следующая.

<b>Профиль пользователя:</b>
Заполните профиль (дата рождения в формате <b>ДД.ММ.ГГГГ</b> и пол), чтобы получать более точные и персонализированные интерпретации, учитывающие ваш возраст, знак зодиака и другие характеристики.

<b>Дополнительные возможности:</b>
• 💭 <b>Задать вопрос по раскладу</b> - получите дополнительную интерпретацию по уже существующему раскладу
• 📝 <b>Просмотр вопросов</b> - посмотрите все заданные вопросы и ответы по раскладу

<b>Доступные команды:</b>
/start - главное меню
/profile - управление профилем
/history - история раскладов
/help - справка  
/details номер - детали расклада (например: /details 1)

<b>Поддержка:</b>
Если возникли проблемы, попробуйте перезапустить бота командой /start
"""
        
        # ДОБАВЛЯЕМ КЛАВИАТУРУ ВОЗВРАТА
        reply_markup = keyboards.get_back_to_menu_keyboard()
        
        try:
            if update.callback_query:
                await update.callback_query.message.reply_text(
                    help_text,
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
            else:
                await update.message.reply_text(
                    help_text,
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
        except Exception as e:
            logger.error(f"💥 Error showing help: {str(e)}")
            # Fallback без HTML
            fallback_help = """
🔮 Помощь по использованию бота Таро

Основные функции:
• 🎴 Карта дня - быстрый расклад на текущую ситуацию
• 🔮 3 карты - расклад "Прошлое-Настоящее-Будущее"  
• 📖 История раскладов - ваши предыдущие расклады
• 👤 Профиль - настройки профиля для персонализации
• ℹ️ Помощь - эта справка

Категории вопросов:
• 💖 Любовь - отношения, чувства, семья
• 💼 Карьера - работа, бизнес, профессиональный рост
• 💰 Финансы - деньги, инвестиции, материальные вопросы
• 👥 Отношения - общение, дружба, социальные связи
• 🔮 Личностный рост - развитие, обучение, самопознание
• ❓ Общий вопрос - без специфической тематики
• 💬 Свой вопрос - задайте любой вопрос для расклада

Как работает AI-интерпретация:
Бот использует 5 различных AI-моделей через OpenRouter для генерации интерпретаций.

Профиль пользователя:
Заполните профиль (дата рождения в формате ДД.ММ.ГГГГ и пол), чтобы получать более точные и персонализированные интерпретации.

Дополнительные возможности:
• 💭 Задать вопрос по раскладу - получите дополнительную интерпретацию по уже существующему раскладу
• 📝 Просмотр вопросов - посмотрите все заданные вопросы и ответы по раскладу

Доступные команды:
/start - главное меню
/profile - управление профилем
/history - история раскладов
/help - справка  
/details номер - детали расклада (например: /details 1)

Поддержка:
Если возникли проблемы, попробуйте перезапустить бота командой /start
"""
            if update.callback_query:
                await update.callback_query.message.reply_text(fallback_help, reply_markup=reply_markup)
            else:
                await update.message.reply_text(fallback_help, reply_markup=reply_markup)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        user = update.effective_user
        user_id = user.id
        
        logger.info(f"🚀 User {user_id} started the bot")
        
        # Регистрируем/обновляем пользователя в БД
        self.user_db.add_user({
            'user_id': user_id,
            'username': user.username,
            'first_name': user.first_name,
            'last_name': user.last_name
        })
        
        # Показываем главное меню
        await self.show_main_menu(update, context)

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """УЛУЧШЕННЫЙ обработчик ошибок с диагностикой HTML"""
        logger.error(f"💥 Exception while handling an update: {context.error}")
        
        # Детальная диагностика для HTML ошибок
        if "Can't parse entities" in str(context.error):
            logger.error("🔄 HTML parsing error detected - likely malformed HTML tags")
            
            # Пытаемся получить текст сообщения который вызвал ошибку
            if update and update.effective_message:
                logger.error(f"📝 Problematic message text: {update.effective_message.text}")
        
        # Отправляем пользователю сообщение об ошибке
        if update and update.effective_chat:
            try:
                # Отправляем без HTML чтобы избежать повторной ошибки
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="❌ Произошла ошибка отображения. Попробуйте еще раз или используйте /start для перезапуска."
                )
            except Exception as e:
                logger.error(f"💥 Failed to send error message: {e}")

    def setup_handlers(self):
        """Обновленная настройка обработчиков с поддержкой профиля"""
        
        # ОЧИСТКА СУЩЕСТВУЮЩИХ ОБРАБОТЧИКОВ
        if hasattr(self.application, 'handlers'):
            for handler_group in self.application.handlers.values():
                handler_group.clear()
        
        # 1. ОБРАБОТЧИКИ КОМАНД
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("history", self.show_history))
        self.application.add_handler(CommandHandler("help", self.show_help))
        self.application.add_handler(CommandHandler("details", self.show_spread_details))
        self.application.add_handler(CommandHandler("profile", self.show_profile))  # НОВАЯ КОМАНДА
        
        # 2. ОБРАБОТЧИКИ CALLBACK-ЗАПРОСОВ ДЛЯ INLINE-КЛАВИАТУР
        
        # Выбор типа расклада
        self.application.add_handler(CallbackQueryHandler(
            self.show_category_selection,
            pattern="^(spread_single|spread_three)$"
        ))
        
        # Выбор категории вопроса
        self.application.add_handler(CallbackQueryHandler(
            self.show_category_selection,
            pattern="^(category_love|category_career|category_finance|category_relationships|category_growth|category_general|category_custom)$"
        ))

        # НОВЫЙ ОБРАБОТЧИК: callback из истории раскладов
        self.application.add_handler(CallbackQueryHandler(
            self.show_spread_details_callback, 
            pattern="^spread_"
        ))

        # Обработчик для кнопок деталей раскладов
        self.application.add_handler(CallbackQueryHandler(
            self.handle_details_callback, 
            pattern="^details_"
        ))
        
        # Обработчик для кнопки возврата в меню
        self.application.add_handler(CallbackQueryHandler(
            self.handle_back_to_menu, 
            pattern="^back_to_menu$"
        ))

        # Обработчик для кнопки возврата к истории
        self.application.add_handler(CallbackQueryHandler(
            self.handle_back_to_history, 
            pattern="^back_to_history$"
        ))

        # Новые обработчики для системы вопросов
        self.application.add_handler(CallbackQueryHandler(
            self.handle_ask_question_callback, 
            pattern="^ask_question_"
        ))
        
        self.application.add_handler(CallbackQueryHandler(
            self.handle_view_questions_callback, 
            pattern="^view_questions_"
        ))
        
        self.application.add_handler(CallbackQueryHandler(
            self.handle_cancel_custom_question, 
            pattern="^cancel_custom_question$"
        ))
        
        self.application.add_handler(CallbackQueryHandler(
            self.handle_cancel_spread_question, 
            pattern="^cancel_spread_question$"
        ))
        
        # НОВЫЕ ОБРАБОТЧИКИ ДЛЯ ПРОФИЛЯ
        self.application.add_handler(CallbackQueryHandler(
            self.handle_profile_callback, 
            pattern="^edit_|^gender_|^clear_profile|^cancel_edit"
        ))
        
        # 3. ОБРАБОТЧИК ТЕКСТОВЫХ СООБЩЕНИЙ ДЛЯ REPLY-КЛАВИАТУР
        self.application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            self.handle_text_messages
        ))
        
        # 4. ОБРАБОТЧИК ОШИБОК
        self.application.add_error_handler(self.error_handler)
        
        logger.info("✅ Unified handlers setup completed")

    def main(self):
        """Синхронная основная функция инициализации и запуска бота"""
        logger.info("Starting Tarot Bot initialization...")
        
        # Загружаем конфигурацию
        bot_token = config.TELEGRAM_BOT_TOKEN
        if not bot_token:
            logger.error("TELEGRAM_BOT_TOKEN not found in configuration")
            raise ValueError("TELEGRAM_BOT_TOKEN not found in configuration")
        
        # База данных инициализируется автоматически при импорте user_database
        logger.info("Database initialized successfully")
        
        # Создаем приложение
        self.application = (
            ApplicationBuilder()
            .token(bot_token)
            .concurrent_updates(True)
            .build()
        )
        
        # Настраиваем обработчики
        self.setup_handlers()
        logger.info("Handlers setup completed")
        
        # Запускаем бота - СИНХРОННЫЙ ЗАПУСК
        logger.info("Bot started polling with AI interpreter...")
        self.application.run_polling()


# Глобальный экземпляр бота
tarot_bot = TarotBot()

def main():
    """Синхронная точка входа для запуска бота"""
    tarot_bot.main()

if __name__ == "__main__":
    main()