# src/services/history_service.py
import logging
import json
import re
from datetime import datetime

logger = logging.getLogger(__name__)

class HistoryService:
    def __init__(self, user_db):
        self.user_db = user_db
        self.PAGE_SIZE = 5  # Количество раскладов на страницу

    def add_question_to_spread(self, spread_id: int, user_id: int, question_text: str) -> bool:
        """
        Сохраняет вопрос пользователя, связанный со spread_id.
        Возвращает True при успехе.
        """
        try:
            if not question_text or len(question_text.strip()) < 3:
                logger.warning("add_question_to_spread: question too short")
                return False

            # Если user_db имеет метод add_spread_question — используем его
            if hasattr(self.user_db, 'add_spread_question'):
                self.user_db.add_spread_question(spread_id=spread_id, user_id=user_id, question=question_text)
                logger.info(f"✅ Вопрос добавлен к раскладу {spread_id} через user_db.add_spread_question")
                return True

            # Иначе выполняем SQL-инсерт прямо через user_db
            query = "INSERT INTO spread_questions (spread_id, user_id, question, created_at) VALUES (?, ?, ?, datetime('now'))"
            self.user_db.conn.execute(query, (spread_id, user_id, question_text))
            self.user_db.conn.commit()
            logger.info(f"✅ Вопрос добавлен к раскладу {spread_id} через прямой SQL")
            return True
        except Exception as e:
            logger.error(f"❌ add_question_to_spread error: {e}")
            try:
                self.user_db.conn.rollback()
            except Exception:
                pass
            return False

    def get_user_spreads(self, user_id: int, page: int = 1) -> tuple:
        """
        Возвращает расклады пользователя для указанной страницы.
        Совместимость с handle_back_to_history.
        
        Возвращает: (spreads, current_page, total_pages)
        """
        try:
            # Загружаем всю историю (TODO: оптимизировать для больших объемов)
            history = self.user_db.get_user_history(user_id, limit=1000)
            logger.info(f"📖 Загружено {len(history)} записей истории для пользователя {user_id}")
            logger.debug(f"🔍 История (первые 5): {history[:5]}")
            
            if not history:
                logger.debug("📭 История пуста, возвращаем ([], 0, 0)")
                return [], 0, 0  # Пустой список, 0 страниц
            
            # ПАГИНАЦИЯ: расчет параметров
            total_spreads = len(history)
            total_pages = max(1, (total_spreads + self.PAGE_SIZE - 1) // self.PAGE_SIZE)
            current_page = min(max(page, 1), total_pages)  # Ограничиваем page в допустимых пределах
            
            # ВЫБОРКА ДАННЫХ для текущей страницы
            start_idx = (current_page - 1) * self.PAGE_SIZE
            end_idx = start_idx + self.PAGE_SIZE
            page_spreads = history[start_idx:end_idx]
            
            logger.debug(f"📊 Пагинация: страница {current_page}/{total_pages}, записи {start_idx+1}-{end_idx} из {total_spreads}")
            return page_spreads, current_page, total_pages  # ✅ ГАРАНТИЯ: правильные возвращаемые значения
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения раскладов для пользователя {user_id}: {e}")
            return [], 0, 0  # Возвращаем пустые значения при ошибке

    def build_history_keyboard(self, page: int = 1, total_pages: int = 1, spreads: list = None, user_id: int = None) -> object:
        """
        Создает клавиатуру для истории. Совместимость с handle_back_to_history.
        
        Обязательные параметры:
        - Либо spreads (предпочтительно для handle_back_to_history)
        - Либо user_id (если spreads недоступен)
        
        Возвращает: InlineKeyboardMarkup или пустую клавиатуру при ошибке
        """
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        
        try:
            # ✅ ГАРАНТИЯ: spreads должен передаваться из handle_back_to_history
            if spreads is None:
                if user_id is None:
                    logger.error("❌ build_history_keyboard: не передан ни spreads, ни user_id")
                    return InlineKeyboardMarkup([])
                
                # Загружаем данные через get_user_spreads если передан только user_id
                spreads, current_page, total_pages = self.get_user_spreads(user_id, page)
                if not spreads:
                    logger.debug("📭 Нет раскладов для построения клавиатуры")
                    return InlineKeyboardMarkup([])
            else:
                # Используем переданные параметры
                current_page = page
            
            keyboard = []
            
            # Кнопки выбора расклада
            for i, spread in enumerate(spreads, 1):
                global_index = (current_page - 1) * self.PAGE_SIZE + i
                spread_id = spread.get('id')
                
                if not spread_id:
                    logger.error(f"❌ Отсутствует spread_id для расклада: {spread}")
                    continue
                    
                spread_type = self._localize_spread_type(spread.get('spread_type', ''))
                category = spread.get('category', 'Расклад')
                button_text = f"{global_index}. {spread_type} - {category}"
                
                keyboard.append([
                    InlineKeyboardButton(
                        button_text,
                        callback_data=f"details_{spread_id}"
                    )
                ])
            
            # Кнопки пагинации
            if total_pages > 1:
                nav_buttons = []
                if current_page > 1:
                    nav_buttons.append(InlineKeyboardButton(
                        "⬅️ Назад", 
                        callback_data=f"history_page_{current_page - 1}"
                    ))
                
                nav_buttons.append(InlineKeyboardButton(
                    f"{current_page}/{total_pages}", 
                    callback_data="history_info"
                ))
                
                if current_page < total_pages:
                    nav_buttons.append(InlineKeyboardButton(
                        "Вперед ➡️", 
                        callback_data=f"history_page_{current_page + 1}"
                    ))
                
                keyboard.append(nav_buttons)
            
            # Кнопка возврата
            keyboard.append([InlineKeyboardButton(
                "🏠 Главное меню", 
                callback_data="main_menu"
            )])
            
            logger.info(f"🔘 Построена клавиатура истории: {len(spreads)} раскладов, страница {current_page}")
            return InlineKeyboardMarkup(keyboard)
            
        except Exception as e:
            logger.error(f"❌ Ошибка построения клавиатуры истории: {e}")
            return InlineKeyboardMarkup([])

    def _localize_spread_type(self, spread_type: str) -> str:
        """Локализация типа расклада"""
        normalized_type = spread_type.lower().strip() if spread_type else ''
        
        spread_type_map = {
            'single': '1 карта',
            'three': '3 карты',
            'three_card': '3 карты',
            'one_card': '1 карта', 
            'three_card_spread': '3 карты',
            'single_card': '1 карта',
            '1 карта': '1 карта',
            '3 карты': '3 карты',
            'card_of_the_day': '1 карта',
            'daily_card': '1 карта',
        }
        return spread_type_map.get(normalized_type, spread_type)

    def _format_date(self, date_string: str) -> str:
        """Форматирование даты в читаемый вид"""
        if not date_string:
            return "Дата недоступна"
        
        try:
            formats = ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%d.%m.%Y %H:%M:%S']
            for fmt in formats:
                try:
                    dt = datetime.strptime(date_string, fmt)
                    return dt.strftime('%d.%m.%Y в %H:%M')
                except ValueError:
                    continue
            return date_string
        except Exception:
            return date_string

    def _truncate_interpretation(self, interpretation: str, max_length: int = 2000) -> str:
        """Обрезание длинной интерпретации"""
        if not interpretation:
            return "не сгенерирована"
        
        if len(interpretation) <= max_length:
            return interpretation
        
        truncated = interpretation[:max_length]
        last_period = truncated.rfind('.')
        last_question = truncated.rfind('?')
        last_exclamation = truncated.rfind('!')
        
        end_pos = max(last_period, last_question, last_exclamation)
        if end_pos > max_length * 0.8:
            return truncated[:end_pos + 1] + "\n\n... (сообщение сокращено)"
        else:
            return truncated + "\n\n... (сообщение сокращено)"

    def _format_history_short(self, spreads: list, current_page: int, total_pages: int, total_spreads: int) -> str:
        """Форматирует краткий список истории раскладов"""
        try:
            if not spreads:
                return "📭 На этой странице нет раскладов."
            
            text_parts = []
            
            text_parts.append(f"<b>📖 Ваша история раскладов</b>")
            text_parts.append(f"Страница {current_page} из {total_pages} (всего {total_spreads} раскладов)\n")
            
            for i, spread in enumerate(spreads, 1):
                global_index = (current_page - 1) * self.PAGE_SIZE + i
                
                spread_type = self._localize_spread_type(spread.get('spread_type', ''))
                category = spread.get('category', 'Общий вопрос')
                
                text_parts.append(f"<b>{global_index}. {spread_type} - {category}</b>")
                
                created_at = spread.get('created_at', '')
                date_display = self._format_date(created_at)
                text_parts.append(f"📅 {date_display}")
                
                cards_data = spread.get('cards', [])
                cards_preview = []
                
                if cards_data and isinstance(cards_data, list):
                    for card_info in cards_data[:2]:
                        if isinstance(card_info, dict):
                            card_name = card_info.get('name', 'Неизвестная карта')
                            cards_preview.append(card_name)
                        else:
                            cards_preview.append(str(card_info))
                
                if cards_preview:
                    cards_text = ", ".join(cards_preview)
                    if len(cards_data) > 2:
                        cards_text += f" ... (+{len(cards_data) - 2})"
                    text_parts.append(f"🎴 {cards_text}")
                else:
                    text_parts.append(f"🎴 карты не указаны")
                
                interpretation = spread.get('interpretation', '')
                if interpretation:
                    text_parts.append("💫 Есть интерпретация")
                else:
                    text_parts.append("⏳ Интерпретация генерируется...")
                
                spread_id = spread.get('id')
                if spread_id:
                    questions_count = self.get_spread_questions_count(spread_id)
                    if questions_count > 0:
                        text_parts.append(f"💭 Вопросов: {questions_count}")
                
                text_parts.append("")
            
            if total_pages > 1:
                text_parts.append(f"<i>Используйте кнопки ниже для навигации по страницам</i>")
            
            return "\n".join(text_parts)
            
        except Exception as e:
            logger.error(f"❌ Ошибка форматирования краткой истории: {e}")
            return "❌ Произошла ошибка при форматировании истории."

    def _create_history_keyboard(self, spreads: list, current_page: int, total_pages: int):
        """Создает клавиатуру для истории с реальными spread_id"""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        
        keyboard = []
        
        for i, spread in enumerate(spreads, 1):
            global_index = (current_page - 1) * self.PAGE_SIZE + i
            
            spread_id = spread.get('id')
            if not spread_id:
                logger.error(f"❌ Отсутствует spread_id для расклада: {spread}")
                continue
                
            spread_type = self._localize_spread_type(spread.get('spread_type', ''))
            category = spread.get('category', 'Расклад')
            button_text = f"{global_index}. {spread_type} - {category}"
            
            keyboard.append([
                InlineKeyboardButton(
                    button_text,
                    callback_data=f"details_{spread_id}"
                )
            ])
        
        if total_pages > 1:
            nav_buttons = []
            if current_page > 1:
                nav_buttons.append(InlineKeyboardButton(
                    "⬅️ Назад", 
                    callback_data=f"history_page_{current_page - 1}"
                ))
            
            nav_buttons.append(InlineKeyboardButton(
                f"{current_page}/{total_pages}", 
                callback_data="history_info"
            ))
            
            if current_page < total_pages:
                nav_buttons.append(InlineKeyboardButton(
                    "Вперед ➡️", 
                    callback_data=f"history_page_{current_page + 1}"
                ))
            
            keyboard.append(nav_buttons)
        
        keyboard.append([InlineKeyboardButton(
            "🏠 Главное меню", 
            callback_data="main_menu"
        )])
        
        logger.info(f"🔘 Создана клавиатура истории с {len(spreads)} раскладами, страница {current_page}")
        return InlineKeyboardMarkup(keyboard)

    def create_spread_details_keyboard(self, spread_id: int, current_page: int = 1):
        """Создает клавиатуру для деталей расклада"""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        
        logger.info(f"🔘 Создана клавиатура деталей для расклада {spread_id}, страница истории {current_page}")
        
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "📖 Назад к истории", 
                callback_data=f"history_page_{current_page}"
            )],
            [InlineKeyboardButton(
                "💭 Задать вопрос", 
                callback_data=f"ask_question_{spread_id}"
            )],
            [InlineKeyboardButton(
                "🏠 Главное меню", 
                callback_data="main_menu"
            )]
        ])

    def get_user_history_formatted(self, user_id: int, page: int = 1, page_size: int = None) -> tuple:
        """Получение краткого списка истории с пагинацией и кнопками"""
        if page_size is None:
            page_size = self.PAGE_SIZE
            
        try:
            # Используем get_user_spreads для единообразия возвращаемых значений
            page_spreads, current_page, total_pages = self.get_user_spreads(user_id, page)
            
            if not page_spreads:
                return "📜 У вас пока нет сохраненных раскладов.", None, 0, 0
            
            history_text = self._format_history_short(page_spreads, current_page, total_pages, len(page_spreads))
            keyboard = self._create_history_keyboard(page_spreads, current_page, total_pages)
            
            logger.info(f"📋 Сформирована история: {len(page_spreads)} раскладов на странице {current_page}")
            
            return history_text, keyboard, current_page, total_pages
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки истории для пользователя {user_id}: {e}")
            return "❌ Произошла ошибка при загрузке истории.", None, 0, 0

    def format_spread_details(self, spread: dict) -> str:
        """Форматирует детали расклада с вопросами"""
        try:
            text_parts = []
            
            spread_type = self._localize_spread_type(spread.get('spread_type', ''))
            category = spread.get('category', 'Общий вопрос')
            
            if '3 карты' in spread_type:
                display_type = f"🔮 {spread_type}"
            else:
                display_type = f"🎴 {spread_type}"
                
            text_parts.append(f"<b>{display_type} - {category}</b>")
            
            created_at = spread.get('created_at', '')
            date_display = self._format_date(created_at) if created_at else 'Неизвестная дата'
            text_parts.append(f"📅 {date_display}\n")
            
            cards_data = spread.get('cards_data', [])
            if isinstance(cards_data, str):
                try:
                    cards_data = json.loads(cards_data)
                except:
                    cards_data = []
            
            if not cards_data:
                cards_data = spread.get('cards', [])
            
            text_parts.append("<b>🎴 Выпавшие карты:</b>")
            
            if cards_data and len(cards_data) > 0:
                for i, card_info in enumerate(cards_data, 1):
                    if isinstance(card_info, dict):
                        card_name = card_info.get('name', 'Неизвестная карта')
                        is_reversed = card_info.get('is_reversed', False)
                        position = card_info.get('position', '')
                        
                        card_line = f"{i}. {card_name}"
                        if is_reversed:
                            card_line += " 🔄 (перевернутая)"
                        if position:
                            card_line += f" - {position}"
                        
                        text_parts.append(card_line)
                    else:
                        text_parts.append(f"{i}. {card_info}")
            else:
                text_parts.append("❌ Информация о картах недоступна")
            
            text_parts.append("")
            
            interpretation = spread.get('interpretation', '')
            if interpretation:
                text_parts.append("<b>💫 Интерпретация:</b>")
                if len(interpretation) > 1500:
                    interpretation = interpretation[:1500] + "..."
                text_parts.append(interpretation)
            else:
                text_parts.append("⏳ Интерпретация генерируется...")
            
            spread_id = spread.get('id')
            questions = []
            
            if spread_id:
                try:
                    questions = self.user_db.get_spread_questions(spread_id)
                except Exception as e:
                    logger.error(f"❌ Ошибка получения вопросов для расклада {spread_id}: {e}")
            
            if not questions and spread.get('questions'):
                questions = spread.get('questions', [])
            
            if questions:
                text_parts.append(f"\n<b>💭 Вопросы по раскладу ({len(questions)}):</b>")
                for i, question in enumerate(questions, 1):
                    question_text = question.get('question', '') or question.get('question_text', '')
                    if not question_text:
                        question_text = "Вопрос без текста"
                    
                    if len(question_text) > 50:
                        question_text = question_text[:50] + "..."
                    text_parts.append(f"{i}. {question_text}")
            
            logger.info(f"📄 Отформатированы детали расклада {spread_id}")
            return "\n".join(text_parts)
            
        except Exception as e:
            logger.error(f"❌ Ошибка форматирования деталей расклада: {e}")
            logger.error(f"🔍 Данные расклада: {spread}")
            return "❌ Произошла ошибка при форматировании деталей расклада."

    def get_spread_with_questions(self, user_id: int, spread_id: int) -> dict:
        """Получение расклада с вопросами и ответами"""
        try:
            history = self.user_db.get_user_history(user_id, limit=100)
            
            spread_data = None
            spread_number = None
            for i, spread in enumerate(history, 1):
                if spread['id'] == spread_id:
                    spread_data = spread
                    spread_number = i
                    break
            
            if not spread_data:
                logger.warning(f"⚠️ Расклад {spread_id} не найден в истории пользователя {user_id}")
                return None
            
            questions = self.user_db.get_spread_questions(spread_id)
            
            logger.info(f"✅ Получен расклад {spread_id} с {len(questions) if questions else 0} вопросами")
            return {
                'spread_data': spread_data,
                'spread_number': spread_number,
                'questions': questions
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения расклада с вопросами: {e}")
            return None

    def format_questions_for_display(self, questions) -> str:
        """Форматирование вопросов и ответов для отображения"""
        if not questions:
            return "📝 По этому раскладу еще нет заданных вопросов."
        
        questions_text = "📝 <b>Вопросы по раскладу:</b>\n\n"
        
        for i, qa in enumerate(questions, 1):
            question = qa['question']
            if len(question) > 500:
                question = question[:500] + "..."
            
            answer = qa['answer']
            if len(answer) > 1000:
                answer = answer[:1000] + "..."
            
            questions_text += f"<b>{i}. Вопрос:</b>\n{question}\n\n"
            questions_text += f"<b>Ответ:</b>\n{answer}\n\n"
            questions_text += "─" * 30 + "\n\n"
        
        return questions_text

    def get_total_pages(self, user_id: int, page_size: int = None) -> int:
        """Получение общего количества страниц истории"""
        if page_size is None:
            page_size = self.PAGE_SIZE
            
        try:
            history = self.user_db.get_user_history(user_id, limit=1000)
            total_spreads = len(history)
            pages = max(1, (total_spreads + page_size - 1) // page_size)
            logger.info(f"📄 Рассчитано {pages} страниц для пользователя {user_id}")
            return pages
        except Exception as e:
            logger.error(f"❌ Ошибка подсчета страниц для пользователя {user_id}: {e}")
            return 1

    def find_spread_by_number(self, user_id: int, spread_number: int) -> dict:
        """Поиск расклада по номеру в истории"""
        try:
            history = self.user_db.get_user_history(user_id, limit=100)
            
            if spread_number > len(history) or spread_number < 1:
                logger.warning(f"⚠️ Неверный номер расклада {spread_number} для пользователя {user_id}")
                return None
            
            spread_data = history[spread_number - 1]
            spread_id = spread_data.get('id')
            logger.info(f"🔍 Найден расклад {spread_id} по номеру {spread_number}")
            
            return {
                'spread_data': spread_data,
                'spread_number': spread_number,
                'spread_id': spread_id
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка поиска расклада по номеру: {e}")
            return None

    def get_spread_questions_count(self, spread_id: int) -> int:
        """Получение количества вопросов по раскладу"""
        try:
            questions = self.user_db.get_spread_questions(spread_id)
            count = len(questions) if questions else 0
            logger.debug(f"📊 Расклад {spread_id} имеет {count} вопросов")
            return count
        except Exception as e:
            logger.error(f"❌ Ошибка получения количества вопросов: {e}")
            return 0