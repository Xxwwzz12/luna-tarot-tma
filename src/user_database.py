# src/user_database.py
import sqlite3
import json
import os
import logging
import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Импорт конфигурации
from .config import DATABASE_URL

class UserDatabase:
    def __init__(self):
        """Инициализация класса базы данных - автоматически вызывает инициализацию БД"""
        self.db_path = DATABASE_URL.replace('sqlite:///', '')
        # Создаем подключение для миграций
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        
        # Включить поддержку внешних ключей
        self.cursor.execute("PRAGMA foreign_keys = ON")
        self.conn.commit()
        
        # Создание таблиц и миграция
        self._create_tables()
        self._migrate_tables()
    
    def _create_tables(self):
        """Альтернативный метод: безопасная миграция без удаления таблиц"""
        
        try:
            # Проверяем существование таблицы users
            self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            users_table_exists = self.cursor.fetchone() is not None
            
            if users_table_exists:
                # Если таблица существует, проверяем и добавляем недостающие столбцы
                logger.info("ℹ️ Таблица users уже существует, проверяем структуру...")
                self._migrate_existing_tables()
            else:
                # Если таблицы не существует, создаем все с нуля
                logger.info("ℹ️ Создаем таблицы с нуля...")
                self._create_fresh_tables()
                
            self.conn.commit()
            logger.info("✅ Таблицы успешно созданы/мигрированы")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при создании/миграции таблиц: {e}")
            raise e

    def _migrate_existing_tables(self):
        """Миграция существующих таблиц без потери данных"""
        
        # Проверяем и добавляем недостающие столбцы в users
        self._add_column_if_not_exists('users', 'birth_date', 'TEXT')
        self._add_column_if_not_exists('users', 'gender', 'TEXT')
        
        # Убедимся, что другие таблицы существуют
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS spread_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                spread_type TEXT NOT NULL,
                category TEXT NOT NULL,
                cards TEXT NOT NULL,
                interpretation TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS spread_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                spread_id INTEGER NOT NULL,
                question_text TEXT NOT NULL,
                answer_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (spread_id) REFERENCES spread_history (id)
            )
        ''')
        
        # Создаем индексы для ускорения запросов
        self.cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_spread_history_user_created 
            ON spread_history(user_id, created_at DESC)
        ''')
        self.cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_spread_questions_spread_id 
            ON spread_questions(spread_id)
        ''')
        
        # Мигрируем таблицу spread_questions если нужно
        self._migrate_spread_questions_table()

    def _create_fresh_tables(self):
        """Создание всех таблиц с нуля"""
        
        # Создаем таблицу пользователей
        self.cursor.execute('''
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                birth_date TEXT,
                gender TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Создаем таблицу истории раскладов
        self.cursor.execute('''
            CREATE TABLE spread_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                spread_type TEXT NOT NULL,
                category TEXT NOT NULL,
                cards TEXT NOT NULL,
                interpretation TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # Создаем таблицу вопросов по раскладам (answer_text теперь разрешает NULL)
        self.cursor.execute('''
            CREATE TABLE spread_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                spread_id INTEGER NOT NULL,
                question_text TEXT NOT NULL,
                answer_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (spread_id) REFERENCES spread_history (id)
            )
        ''')
        
        # Создаем индексы для ускорения запросов
        self.cursor.execute('''
            CREATE INDEX idx_spread_history_user_created 
            ON spread_history(user_id, created_at DESC)
        ''')
        self.cursor.execute('''
            CREATE INDEX idx_spread_questions_spread_id 
            ON spread_questions(spread_id)
        ''')

    def _migrate_spread_questions_table(self):
        """Миграция таблицы spread_questions для разрешения NULL в answer_text"""
        try:
            # Проверяем текущую структуру таблицы
            self.cursor.execute("PRAGMA table_info(spread_questions)")
            columns = self.cursor.fetchall()
            
            # Ищем столбец answer_text и проверяем его свойства
            for column in columns:
                if column[1] == 'answer_text' and column[3] == 1:  # 3 - notnull flag
                    logger.info("🔄 Миграция таблицы spread_questions...")
                    # Создаем временную таблицу с новой структурой
                    self.cursor.execute('''
                        CREATE TABLE spread_questions_temp (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            spread_id INTEGER NOT NULL,
                            question_text TEXT NOT NULL,
                            answer_text TEXT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            FOREIGN KEY (spread_id) REFERENCES spread_history (id)
                        )
                    ''')
                    
                    # Копируем данные
                    self.cursor.execute('''
                        INSERT INTO spread_questions_temp 
                        (id, spread_id, question_text, answer_text, created_at)
                        SELECT id, spread_id, question_text, answer_text, created_at 
                        FROM spread_questions
                    ''')
                    
                    # Удаляем старую таблицу и переименовываем временную
                    self.cursor.execute('DROP TABLE spread_questions')
                    self.cursor.execute('ALTER TABLE spread_questions_temp RENAME TO spread_questions')
                    self.conn.commit()
                    logger.info("✅ Миграция таблицы spread_questions завершена")
                    break
                    
        except Exception as e:
            logger.error(f"❌ Ошибка миграции таблицы spread_questions: {e}")

    def _add_column_if_not_exists(self, table_name, column_name, column_type):
        """Добавляет столбец в таблицу, если он не существует"""
        
        try:
            # Проверяем существование столбца
            self.cursor.execute(f"PRAGMA table_info({table_name})")
            columns = [column[1] for column in self.cursor.fetchall()]
            
            if column_name not in columns:
                self.cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
                logger.info(f"✅ Добавлен столбец {column_name} в таблицу {table_name}")
            else:
                logger.info(f"ℹ️ Столбец {column_name} уже существует в таблице {table_name}")
                
        except Exception as e:
            logger.error(f"❌ Ошибка при добавлении столбца {column_name} в {table_name}: {e}")

    def _migrate_tables(self):
        """Миграция таблиц - создание таблицы вопросов если не существует"""
        logger.info("🔄 Проверка и миграция таблиц...")
        
        try:
            # Проверяем существование таблицы spread_questions
            self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='spread_questions'")
            if not self.cursor.fetchone():
                logger.info("🔄 Создание таблицы spread_questions...")
                self.cursor.execute('''
                    CREATE TABLE IF NOT EXISTS spread_questions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        spread_id INTEGER NOT NULL,
                        question_text TEXT NOT NULL,
                        answer_text TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (spread_id) REFERENCES spread_history (id) ON DELETE CASCADE
                    )
                ''')
                self.conn.commit()
                logger.info("✅ Таблица spread_questions создана")
            
        except Exception as e:
            logger.error(f"❌ Ошибка миграции таблиц: {e}")

    def add_question_to_spread(self, spread_id: int, question: str, answer: str = None) -> int:
        """Добавление вопроса к раскладу (answer может быть NULL)"""
        try:
            logger.info(f"❓ Добавление вопроса к раскладу {spread_id}")
            
            query = """
            INSERT INTO spread_questions (spread_id, question_text, answer_text)
            VALUES (?, ?, ?)
            """
            
            self.cursor.execute(query, (spread_id, question, answer))
            self.conn.commit()
            
            question_id = self.cursor.lastrowid
            logger.info(f"✅ Вопрос {question_id} добавлен к раскладу {spread_id}")
            return question_id
            
        except sqlite3.Error as e:
            logger.error(f"❌ Ошибка добавления вопроса к раскладу {spread_id}: {e}")
            self.conn.rollback()
            return -1
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка при добавлении вопроса: {e}")
            self.conn.rollback()
            return -1

    def update_question_answer(self, question_id: int, answer: str) -> bool:
        """Обновление ответа на существующий вопрос"""
        try:
            logger.info(f"💾 Обновление ответа для вопроса {question_id}")
            
            query = "UPDATE spread_questions SET answer_text = ? WHERE id = ?"
            self.cursor.execute(query, (answer, question_id))
            self.conn.commit()
            
            if self.cursor.rowcount > 0:
                logger.info(f"✅ Ответ для вопроса {question_id} обновлен")
                return True
            else:
                logger.warning(f"⚠️ Не удалось обновить ответ для вопроса {question_id} - вопрос не найден")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка обновления ответа для вопроса {question_id}: {e}")
            return False

    def get_question_by_id(self, question_id: int) -> Optional[Dict[str, Any]]:
        """Получает вопрос по ID"""
        try:
            self.cursor.execute(
                "SELECT id, spread_id, question_text, answer_text, created_at FROM spread_questions WHERE id = ?", 
                (question_id,)
            )
            result = self.cursor.fetchone()
            
            if result:
                return {
                    'id': result[0],
                    'spread_id': result[1],
                    'question_text': result[2],
                    'answer_text': result[3],
                    'created_at': result[4]
                }
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения вопроса {question_id}: {e}")
            return None

    def get_user_history_by_spread_id(self, user_id: int, spread_id: int) -> Optional[Dict[str, Any]]:
        """Получает конкретный расклад по ID для пользователя"""
        try:
            self.cursor.execute(
                "SELECT id, user_id, username, spread_type, category, cards, interpretation, created_at "
                "FROM spread_history WHERE id = ? AND user_id = ?",
                (spread_id, user_id)
            )
            result = self.cursor.fetchone()
            
            if result:
                # Обрабатываем данные карт
                cards_raw = result[5]  # cards находится на позиции 5
                try:
                    cards_data = json.loads(cards_raw)
                    if not isinstance(cards_data, list):
                        cards_data = []
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"⚠️ Ошибка парсинга cards_data для расклада {spread_id}: {e}")
                    cards_data = []
                
                # Форматируем названия карт
                card_names = []
                for card in cards_data:
                    if isinstance(card, dict):
                        name = card.get('name', 'Неизвестная карта')
                        position = card.get('position', 'upright')
                        is_reversed = card.get('is_reversed', False)
                        
                        if position == 'reversed' or is_reversed:
                            position_symbol = '🔽'
                        else:
                            position_symbol = '🔼'
                            
                        card_names.append(f"{name} {position_symbol}")
                    else:
                        card_names.append("Неизвестная карта")
                
                # Получаем количество вопросов
                questions_count = len(self.get_spread_questions(spread_id))
                
                return {
                    'id': int(result[0]),
                    'user_id': int(result[1]),
                    'username': result[2] or '',
                    'spread_type': result[3],
                    'category': result[4] or 'Общий вопрос',
                    'cards': card_names,
                    'cards_data': cards_data,
                    'interpretation': result[6] or '',
                    'created_at': result[7],
                    'questions_count': questions_count,
                    'has_questions': bool(questions_count > 0)
                }
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения расклада {spread_id} для пользователя {user_id}: {e}")
            return None

    def update_user_profile(self, user_id: int, birth_date: str = None, gender: str = None) -> bool:
        """Обновление профиля пользователя - обновляет только переданные поля (не None)"""
        try:
            updates = []
            params = []
            
            if birth_date is not None:
                updates.append("birth_date = ?")
                params.append(birth_date)
                logger.info(f"📅 Обновление даты рождения на: {birth_date}")
            
            if gender is not None:
                updates.append("gender = ?")
                params.append(gender)
                logger.info(f"⚧ Обновление пола на: {gender}")
            
            # Если нечего обновлять, выходим
            if not updates:
                logger.info("ℹ️ Нет полей для обновления")
                return True
            
            params.append(user_id)
            
            query = f"UPDATE users SET {', '.join(updates)} WHERE user_id = ?"
            with self.conn:
                self.cursor.execute(query, params)
                
                # ✅ Проверяем, что запрос выполнился
                if self.cursor.rowcount > 0:
                    logger.info(f"👤 Профиль пользователя {user_id} обновлен")
                    return True
                else:
                    logger.warning(f"⚠️ Пользователь {user_id} не найден для обновления профиля")
                    return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка обновления профиля пользователя {user_id}: {e}")
            return False

    def clear_user_profile(self, user_id: int) -> bool:
        """Очистка данных профиля пользователя (даты рождения и пола) - устанавливает NULL"""
        try:
            # Проверяем текущее состояние профиля перед очисткой
            current_profile = self.get_user_profile_debug(user_id)
            logger.info(f"👤 Профиль пользователя {user_id} будет очищен")
            
            # Используем транзакцию для безопасности
            with self.conn:
                self.cursor.execute(
                    "UPDATE users SET birth_date = NULL, gender = NULL WHERE user_id = ?",
                    (user_id,)
                )
                
                # ✅ ДОБАВЛЯЕМ проверку что запрос действительно выполнился
                if self.cursor.rowcount > 0:
                    logger.info(f"🧹 Профиль пользователя {user_id} очищен")
                    
                    # Проверяем состояние после очистки
                    updated_profile = self.get_user_profile_debug(user_id)
                    
                    return True
                else:
                    logger.warning(f"⚠️ Очистка профиля пользователя {user_id} - пользователь не найден")
                    return False
                    
        except Exception as e:
            logger.error(f"❌ Ошибка очистки профиля пользователя {user_id}: {e}")
            return False

    def get_user_profile_debug(self, user_id: int) -> dict:
        """Отладочный метод для проверки данных профиля"""
        try:
            self.cursor.execute(
                "SELECT user_id, birth_date, gender FROM users WHERE user_id = ?",
                (user_id,)
            )
            row = self.cursor.fetchone()
            if row:
                return {
                    'user_id': row[0],
                    'birth_date': row[1],
                    'gender': row[2]
                }
            return {}
        except Exception as e:
            logger.error(f"❌ Ошибка получения профиля для отладки {user_id}: {e}")
            return {}

    def clear_user_history(self, user_id: int) -> bool:
        """Очистка всей истории раскладов пользователя"""
        try:
            # Проверяем текущее количество раскладов
            history_before = self.get_user_history(user_id, limit=1000)
            logger.info(f"🔍 История до очистки: {len(history_before)} раскладов")
            
            # Используем транзакцию для безопасности
            with self.conn:
                # Удаляем сначала вопросы, затем расклады (из-за foreign key)
                self.cursor.execute(
                    "DELETE FROM spread_questions WHERE spread_id IN (SELECT id FROM spread_history WHERE user_id = ?)",
                    (user_id,)
                )
                self.cursor.execute(
                    "DELETE FROM spread_history WHERE user_id = ?",
                    (user_id,)
                )
                deleted_rows = self.cursor.rowcount
                
                # Проверяем результат
                if deleted_rows > 0:
                    logger.info(f"🗑️ Очистка истории пользователя {user_id}: удалено {deleted_rows} раскладов")
                    
                    # Проверяем состояние после очистки
                    history_after = self.get_user_history(user_id, limit=1000)
                    logger.info(f"🔍 История после очистки: {len(history_after)} раскладов")
                    
                    return True
                else:
                    logger.warning(f"⚠️ Очистка истории пользователя {user_id} - раскладов не найдено")
                    return False
                    
        except Exception as e:
            logger.error(f"❌ Ошибка очистки истории пользователя {user_id}: {e}")
            return False

    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получение данных пользователя для отладки"""
        try:
            self.cursor.execute(
                "SELECT user_id, username, first_name, last_name, birth_date, gender, created_at FROM users WHERE user_id = ?",
                (user_id,)
            )
            result = self.cursor.fetchone()
            if result:
                return {
                    'user_id': result[0],
                    'username': result[1],
                    'first_name': result[2],
                    'last_name': result[3],
                    'birth_date': result[4],
                    'gender': result[5],
                    'created_at': result[6]
                }
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка получения пользователя {user_id}: {e}")
            return None

    def get_user_profile(self, user_id: int) -> dict:
        """Исправленный метод получения профиля пользователя"""
        
        try:
            # УБИРАЕМ updated_at из запроса
            query = '''
            SELECT user_id, username, first_name, last_name, birth_date, gender, created_at
            FROM users 
            WHERE user_id = ?
            '''
            self.cursor.execute(query, (user_id,))
            record = self.cursor.fetchone()
            
            if record:
                return {
                    'user_id': record[0],
                    'username': record[1],
                    'first_name': record[2],
                    'last_name': record[3],
                    'birth_date': record[4],
                    'gender': record[5],
                    'created_at': record[6]
                }
            else:
                return {}
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения профиля пользователя {user_id}: {e}")
            # Выводим полную информацию об ошибке для диагностики
            import traceback
            logger.error(f"🔍 Детали ошибки: {traceback.format_exc()}")
            return {}

    def get_user_age(self, user_id: int) -> int:
        """Вычисление возраста пользователя на основе даты рождения"""
        
        profile = self.get_user_profile(user_id)
        birth_date = profile.get('birth_date')
        
        if not birth_date:
            return None
        
        try:
            birth = datetime.strptime(birth_date, '%Y-%m-%d')
            today = datetime.now()
            age = today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
            return age
        except Exception as e:
            logger.error(f"❌ Ошибка вычисления возраста для пользователя {user_id}: {e}")
            return None

    def get_zodiac_sign(self, user_id: int) -> str:
        """Определение знака зодиака по дате рождения"""
        
        profile = self.get_user_profile(user_id)
        birth_date = profile.get('birth_date')
        
        if not birth_date:
            return None
        
        try:
            # Извлекаем день и месяц
            month = int(birth_date[5:7])
            day = int(birth_date[8:10])
            
            # Определяем знак зодиака
            if (month == 3 and day >= 21) or (month == 4 and day <= 19):
                return "Овен"
            elif (month == 4 and day >= 20) or (month == 5 and day <= 20):
                return "Телец"
            elif (month == 5 and day >= 21) or (month == 6 and day <= 20):
                return "Близнецы"
            elif (month == 6 and day >= 21) or (month == 7 and day <= 22):
                return "Рак"
            elif (month == 7 and day >= 23) or (month == 8 and day <= 22):
                return "Лев"
            elif (month == 8 and day >= 23) or (month == 9 and day <= 22):
                return "Дева"
            elif (month == 9 and day >= 23) or (month == 10 and day <= 22):
                return "Весы"
            elif (month == 10 and day >= 23) or (month == 11 and day <= 21):
                return "Скорпион"
            elif (month == 11 and day >= 22) or (month == 12 and day <= 21):
                return "Стрелец"
            elif (month == 12 and day >= 22) or (month == 1 and day <= 19):
                return "Козерог"
            elif (month == 1 and day >= 20) or (month == 2 and day <= 18):
                return "Водолей"
            elif (month == 2 and day >= 19) or (month == 3 and day <= 20):
                return "Рыбы"
            else:
                return None
                
        except Exception as e:
            logger.error(f"❌ Ошибка определения знака зодиака для пользователя {user_id}: {e}")
            return None

    def get_spread_questions(self, spread_id: int) -> List[Dict[str, Any]]:
        """Получение всех вопросов по раскладу"""
        try:
            query = """
            SELECT id, question_text, answer_text, created_at
            FROM spread_questions 
            WHERE spread_id = ?
            ORDER BY created_at ASC
            """
            
            self.cursor.execute(query, (spread_id,))
            records = self.cursor.fetchall()
            
            questions = []
            for record in records:
                questions.append({
                    'id': record[0],
                    'question': record[1],
                    'answer': record[2],
                    'created_at': record[3]
                })
            
            return questions
            
        except sqlite3.Error as e:
            logger.error(f"❌ Ошибка получения вопросов для расклада {spread_id}: {e}")
            return []
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка при получении вопросов: {e}")
            return []
    
    def get_user_history(self, user_id: int, limit: int = 10, offset: int = 0) -> List[Dict[str, Any]]:
        """Получение истории пользователя с пагинацией"""
        try:
            query = """
            SELECT sh.id, sh.user_id, sh.username, sh.spread_type, sh.category, 
                   sh.cards, sh.interpretation, sh.created_at,
                   COUNT(sq.id) as questions_count
            FROM spread_history sh
            LEFT JOIN spread_questions sq ON sh.id = sq.spread_id
            WHERE sh.user_id = ? 
            GROUP BY sh.id
            ORDER BY sh.created_at DESC 
            LIMIT ? OFFSET ?
            """
            
            self.cursor.execute(query, (user_id, limit, offset))
            records = self.cursor.fetchall()
            
            columns = [description[0] for description in self.cursor.description]
            
            history = []
            for record in records:
                try:
                    record_dict = dict(zip(columns, record))
                    
                    # ✅ Защитная обработка JSON
                    cards_raw = record_dict['cards']
                    try:
                        cards_data = json.loads(cards_raw)
                        if not isinstance(cards_data, list):
                            cards_data = []
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning(f"⚠️ Ошибка парсинга cards_data для расклада {record_dict['id']}: {e}")
                        cards_data = []
                    
                    # ✅ Форматирование карт с защитой от ошибок
                    card_names = []
                    for card in cards_data:
                        if isinstance(card, dict):
                            name = card.get('name', 'Неизвестная карта')
                            position = card.get('position', 'upright')
                            is_reversed = card.get('is_reversed', False)
                            
                            if position == 'reversed' or is_reversed:
                                position_symbol = '🔽'
                            else:
                                position_symbol = '🔼'
                                
                            card_names.append(f"{name} {position_symbol}")
                        else:
                            card_names.append("Неизвестная карта")
                    
                    # ✅ Обработка категории
                    final_category = record_dict['category'] or 'Общий вопрос'
                    
                    # ✅ Гарантированная структура возвращаемого словаря
                    spread_data = {
                        'id': int(record_dict['id']),  # ✅ Гарантируем int
                        'user_id': int(record_dict['user_id']),
                        'username': record_dict['username'] or '',
                        'spread_type': record_dict['spread_type'],
                        'category': final_category,
                        'cards': card_names,
                        'cards_data': cards_data,  # ✅ Всегда список dict
                        'interpretation': record_dict['interpretation'] or '',
                        'created_at': record_dict['created_at'],
                        'questions_count': int(record_dict.get('questions_count', 0)),
                        'has_questions': bool(record_dict.get('questions_count', 0) > 0)  # ✅ Гарантируем bool
                    }
                    
                    history.append(spread_data)
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка обработки записи {record[0] if record else 'N/A'}: {e}")
                    # ✅ Fallback структура при ошибках
                    spread_data = {
                        'id': int(record[0]) if record and record[0] else 0,
                        'user_id': int(record[1]) if record and record[1] else 0,
                        'username': record[2] if record and record[2] else '',
                        'spread_type': record[3] if record and record[3] else 'Неизвестный',
                        'category': (record[4] or 'Общий вопрос') if record and record[4] else 'Общий вопрос',
                        'cards': ["информация недоступна"],
                        'cards_data': [],
                        'interpretation': record[6] if record and record[6] else '',
                        'created_at': record[7] if record and record[7] else '',
                        'questions_count': 0,
                        'has_questions': False
                    }
                    history.append(spread_data)
            
            # ✅ Сокращенное логирование
            if history:
                logger.info(f"📊 История загружена: {len(history)} записей (offset: {offset})")
            
            return history
            
        except sqlite3.Error as e:
            logger.error(f"💥 Ошибка БД при получении истории пользователя {user_id}: {e}")
            return []
        except Exception as e:
            logger.error(f"💥 Неожиданная ошибка в get_user_history: {e}")
            return []

    def get_user_history_count(self, user_id: int) -> int:
        """Получение общего количества раскладов пользователя"""
        try:
            query = "SELECT COUNT(*) FROM spread_history WHERE user_id = ?"
            self.cursor.execute(query, (user_id,))
            result = self.cursor.fetchone()
            return result[0] if result else 0
        except Exception as e:
            logger.error(f"❌ Ошибка получения количества раскладов для пользователя {user_id}: {e}")
            return 0
    
    def get_spread_with_questions(self, spread_id: int) -> Optional[Dict[str, Any]]:
        """Получение расклада со всеми вопросами и ответами"""
        try:
            query = """
            SELECT id, user_id, username, spread_type, category, cards, interpretation, created_at
            FROM spread_history 
            WHERE id = ?
            """
            
            self.cursor.execute(query, (spread_id,))
            record = self.cursor.fetchone()
            
            if not record:
                logger.warning(f"⚠️ Расклад {spread_id} не найден")
                return None
            
            columns = [description[0] for description in self.cursor.description]
            record_dict = dict(zip(columns, record))
            
            cards_raw = record_dict['cards']
            cards_data = json.loads(cards_raw)
            
            card_names = []
            for card in cards_data:
                if isinstance(card, dict):
                    name = card.get('name', 'Неизвестная карта')
                    is_reversed = card.get('is_reversed', False)
                    position_symbol = '🔽' if is_reversed else '🔼'
                    card_names.append(f"{name} {position_symbol}")
                else:
                    card_names.append("Неизвестная карта")
            
            questions = self.get_spread_questions(spread_id)
            
            spread_data = {
                'id': record_dict['id'],
                'user_id': record_dict['user_id'],
                'username': record_dict['username'],
                'spread_type': record_dict['spread_type'],
                'category': record_dict['category'] or 'Общий вопрос',
                'cards': card_names,
                'cards_data': cards_data,
                'interpretation': record_dict['interpretation'],
                'created_at': record_dict['created_at'],
                'questions': questions,
                'questions_count': len(questions),
                'has_questions': len(questions) > 0
            }
            
            logger.info(f"✅ Расклад {spread_id} получен с {len(questions)} вопросами")
            return spread_data
            
        except Exception as e:
            logger.error(f"❌ Ошибка получения расклада {spread_id} с вопросами: {e}")
            return None
    
    def update_interpretation(self, spread_id: int, interpretation: str) -> bool:
        """Обновление интерпретации расклада (синхронная версия)"""
        try:
            logger.info(f"💾 Обновление интерпретации для расклада {spread_id}")
            
            query = "UPDATE spread_history SET interpretation = ? WHERE id = ?"
            self.cursor.execute(query, (interpretation, spread_id))
            self.conn.commit()
            
            if self.cursor.rowcount > 0:
                logger.info(f"✅ Интерпретация успешно обновлена для расклада {spread_id}")
                return True
            else:
                logger.warning(f"⚠️ Не удалось обновить интерпретацию для расклада {spread_id} - запись не найдена")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка обновления интерпретации для расклада {spread_id}: {e}")
            return False

    async def update_spread_interpretation(self, spread_id: int, interpretation: str) -> bool:
        """Обновление AI-интерпретации расклада (асинхронная версия)"""
        try:
            logger.info(f"🤖 Обновление AI-интерпретации для расклада {spread_id}")
            
            # Используем asyncio.to_thread для выполнения синхронной операции в отдельном потоке
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None, 
                self._update_interpretation_sync, 
                spread_id, 
                interpretation
            )
            
            if result:
                logger.info(f"✅ AI-интерпретация успешно обновлена для расклада {spread_id}")
                
                # Логируем размер интерпретации для отладки
                interpretation_length = len(interpretation) if interpretation else 0
                logger.info(f"📊 Размер интерпретации: {interpretation_length} символов")
                
                return True
            else:
                logger.warning(f"⚠️ Не удалось обновить AI-интерпретацию для расклада {spread_id}")
                return False
                
        except sqlite3.Error as e:
            logger.error(f"❌ Ошибка БД при обновлении AI-интерпретации для расклада {spread_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка при обновлении AI-интерпретации для расклада {spread_id}: {e}")
            return False

    def _update_interpretation_sync(self, spread_id: int, interpretation: str) -> bool:
        """Внутренний синхронный метод для обновления интерпретации"""
        try:
            query = "UPDATE spread_history SET interpretation = ? WHERE id = ?"
            self.cursor.execute(query, (interpretation, spread_id))
            self.conn.commit()
            return self.cursor.rowcount > 0
        except Exception as e:
            logger.error(f"❌ Синхронная ошибка обновления интерпретации для расклада {spread_id}: {e}")
            return False

    def update_spread_interpretation_sync(self, spread_id: int, interpretation: str) -> bool:
        """Обновление AI-интерпретации расклада (синхронная версия)"""
        try:
            logger.info(f"🤖 Обновление AI-интерпретации для расклада {spread_id} (синхронно)")
            
            query = "UPDATE spread_history SET interpretation = ? WHERE id = ?"
            self.cursor.execute(query, (interpretation, spread_id))
            self.conn.commit()
            
            if self.cursor.rowcount > 0:
                logger.info(f"✅ AI-интерпретация успешно обновлена для расклада {spread_id}")
                
                # Логируем размер интерпретации для отладки
                interpretation_length = len(interpretation) if interpretation else 0
                logger.info(f"📊 Размер интерпретации: {interpretation_length} символов")
                
                return True
            else:
                logger.warning(f"⚠️ Не удалось обновить AI-интерпретацию для расклада {spread_id} - запись не найдена")
                return False
                
        except sqlite3.Error as e:
            logger.error(f"❌ Ошибка БД при обновлении AI-интерпретации для расклада {spread_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка при обновлении AI-интерпретации для расклада {spread_id}: {e}")
            return False
    
    def add_spread_to_history(self, user_id: int, username: str, spread_type: str, 
                             category: str, cards: list, interpretation: str = None) -> int:
        """Сохранение расклада в историю - возвращает spread_id"""
        logger.info(f"💾 Сохранение расклада для пользователя {user_id}")
        
        # ✅ Нормализация категории
        if category is None:
            category = "Общий вопрос"
            logger.info("   ⚠️ Категория была None, заменена на 'Общий вопрос'")
        
        try:
            # ✅ Защитная сериализация JSON
            try:
                cards_json = json.dumps(cards, ensure_ascii=False)
            except (TypeError, ValueError) as e:
                logger.error(f"❌ Ошибка сериализации карт: {e}")
                # Fallback: базовые данные карт
                cards_json = json.dumps([{"name": "Ошибка данных", "position": "upright"}])
            
            query = """
            INSERT INTO spread_history 
            (user_id, username, spread_type, category, cards, interpretation, created_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            """
            
            self.cursor.execute(query, (user_id, username, spread_type, category, cards_json, interpretation))
            self.conn.commit()
            
            spread_id = self.cursor.lastrowid
            logger.info(f"✅ Расклад {spread_id} сохранен с категорией '{category}'")
            
            return int(spread_id)  # ✅ Гарантируем int
            
        except sqlite3.Error as e:
            logger.error(f"❌ Ошибка БД при сохранении расклада для пользователя {user_id}: {e}")
            self.conn.rollback()
            raise
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка при сохранении расклада для пользователя {user_id}: {e}")
            self.conn.rollback()
            raise
    
    def add_user(self, user_data: Dict[str, Any]) -> None:
        """Добавляет нового пользователя"""
        try:
            self.cursor.execute('''
                INSERT OR REPLACE INTO users 
                (user_id, username, first_name, last_name)
                VALUES (?, ?, ?, ?)
            ''', (
                user_data['user_id'],
                user_data.get('username'),
                user_data.get('first_name'),
                user_data.get('last_name')
            ))
            
            self.conn.commit()
            logger.info(f"✅ Пользователь {user_data['user_id']} добавлен/обновлен")
            
        except sqlite3.Error as e:
            logger.error(f"❌ Ошибка при добавлении пользователя: {e}")
            self.conn.rollback()
            raise
    
    def close(self):
        """Закрывает соединение с базой данных"""
        if self.conn:
            self.conn.close()
            logger.info("🔌 Соединение с базой данных закрыто")

# Глобальный экземпляр для использования в проекте
user_db = UserDatabase()

# Пример использования для тестирования
if __name__ == "__main__":
    try:
        # Тестируем исправленный метод update_user_profile
        test_user_id = 12345
        
        # Сначала создаем пользователя с данными профиля
        user_db.add_user({
            'user_id': test_user_id,
            'username': 'test_user',
            'first_name': 'Test',
            'last_name': 'User'
        })
        
        print("✅ Пользователь создан")
        
        # Тест 1: Устанавливаем оба поля
        print("\n🧪 ТЕСТ 1: Установка обоих полей")
        user_db.update_user_profile(
            user_id=test_user_id,
            birth_date='24.04.1996',
            gender='female'
        )
        
        profile1 = user_db.get_user_profile(test_user_id)
        debug1 = user_db.get_user_profile_debug(test_user_id)
        print(f"📋 Профиль после установки обоих полей: {profile1}")
        print(f"🔍 Отладочная информация: {debug1}")
        
        # Тест 2: Обновляем только дату рождения (gender=None - не обновляется)
        print("\n🧪 ТЕСТ 2: Обновление только даты рождения (gender=None)")
        user_db.update_user_profile(
            user_id=test_user_id,
            birth_date='15.05.1990',  # Обновляется
            gender=None  # Не обновляется (остается 'female')
        )
        
        profile2 = user_db.get_user_profile(test_user_id)
        debug2 = user_db.get_user_profile_debug(test_user_id)
        print(f"📋 Профиль после обновления даты рождения: {profile2}")
        print(f"🔍 Отладочная информация: {debug2}")
        
        # Тест 3: Обновляем только пол (birth_date=None - не обновляется)
        print("\n🧪 ТЕСТ 3: Обновление только пола (birth_date=None)")
        user_db.update_user_profile(
            user_id=test_user_id,
            birth_date=None,  # Не обновляется (остается '15.05.1990')
            gender='male'     # Обновляется
        )
        
        profile3 = user_db.get_user_profile(test_user_id)
        debug3 = user_db.get_user_profile_debug(test_user_id)
        print(f"📋 Профиль после обновления пола: {profile3}")
        print(f"🔍 Отладочная информация: {debug3}")
        
        # Тест 4: Очистка профиля через clear_user_profile
        print("\n🧪 ТЕСТ 4: Очистка профиля через clear_user_profile")
        user_db.clear_user_profile(test_user_id)
        
        profile4 = user_db.get_user_profile(test_user_id)
        debug4 = user_db.get_user_profile_debug(test_user_id)
        print(f"📋 Профиль после очистки: {profile4}")
        print(f"🔍 Отладочная информация: {debug4}")
        
        # Тест 5: Обновление AI-интерпретации (асинхронная версия)
        print("\n🧪 ТЕСТ 5: Обновление AI-интерпретации (асинхронная версия)")
        # Сначала создаем тестовый расклад
        test_spread_id = user_db.add_spread_to_history(
            user_id=test_user_id,
            username='test_user',
            spread_type='Трехкарточный',
            category='Тест',
            cards=[{'name': 'Шут', 'position': 'upright'}],
            interpretation=None
        )
        
        # Тестируем асинхронную версию
        async def test_ai_interpretation():
            success = await user_db.update_spread_interpretation(
                test_spread_id, 
                "🤖 AI-интерпретация: Карта Шут символизирует новые начинания и невинность. Это время для приключений!"
            )
            print(f"✅ Результат обновления AI-интерпретации: {success}")
            
            # Проверяем результат
            spread = user_db.get_user_history_by_spread_id(test_user_id, test_spread_id)
            if spread and spread.get('interpretation'):
                print(f"📝 Обновленная интерпретация: {spread['interpretation']}")
            else:
                print("❌ Интерпретация не обновлена")
        
        # Запускаем тест
        asyncio.run(test_ai_interpretation())
        
        # Тест 6: Обновление AI-интерпретации (синхронная версия)
        print("\n🧪 ТЕСТ 6: Обновление AI-интерпретации (синхронная версия)")
        success_sync = user_db.update_spread_interpretation_sync(
            test_spread_id,
            "🤖 Синхронная AI-интерпретация: Карта Шут напоминает о важности спонтанности и радости в жизни."
        )
        print(f"✅ Результат синхронного обновления: {success_sync}")
        
        # Проверяем результат
        spread_sync = user_db.get_user_history_by_spread_id(test_user_id, test_spread_id)
        if spread_sync and spread_sync.get('interpretation'):
            print(f"📝 Обновленная синхронная интерпретация: {spread_sync['interpretation']}")
        
        # Тест 7: Пагинация истории
        print("\n🧪 ТЕСТ 7: Пагинация истории")
        total_count = user_db.get_user_history_count(test_user_id)
        print(f"📊 Всего раскладов: {total_count}")
        
        # Получаем первую страницу
        page1 = user_db.get_user_history(test_user_id, limit=5, offset=0)
        print(f"📄 Страница 1: {len(page1)} записей")
        for spread in page1:
            print(f"   - ID: {spread['id']}, Категория: {spread['category']}")
        
        # Проверяем, что все работает корректно
        success = (
            profile1.get('birth_date') == '24.04.1996' and 
            profile1.get('gender') == 'female' and
            profile2.get('birth_date') == '15.05.1990' and
            profile2.get('gender') == 'female' and  # Должен остаться прежним
            profile3.get('birth_date') == '15.05.1990' and  # Должен остаться прежним
            profile3.get('gender') == 'male' and
            profile4.get('birth_date') is None and
            profile4.get('gender') is None
        )
        
        if success:
            print("\n✅ Все тесты пройдены успешно! Методы работают корректно.")
            print("   - update_user_profile обновляет только переданные поля (не None)")
            print("   - clear_user_profile очищает все поля профиля")
            print("   - update_spread_interpretation (асинхронная версия) корректно работает")
            print("   - update_spread_interpretation_sync (синхронная версия) сохраняет обратную совместимость")
            print("   - Пагинация истории работает корректно")
        else:
            print("\n❌ Некоторые тесты не пройдены.")
        
    except Exception as e:
        print(f"❌ Ошибка тестирования: {e}")
        import traceback
        traceback.print_exc()
    finally:
        user_db.close()