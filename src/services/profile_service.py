# src/services/profile_service.py
import logging
import re
from datetime import datetime

logger = logging.getLogger(__name__)

class ProfileService:
    def __init__(self, user_db):
        self.user_db = user_db

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
            'other': 'Другой ⚧'
        }
        return gender_map.get(gender, 'не указан')

    def _calculate_age(self, birth_date_str: str) -> tuple:
        """Вычисление возраста и знака зодиака по дате рождения"""
        age = None
        zodiac = None
        
        try:
            if '.' in birth_date_str:
                birth_date = datetime.strptime(birth_date_str, '%d.%m.%Y')
            else:
                birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d')
            
            today = datetime.now()
            age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
            
            # Определяем знак зодиака
            zodiac = self._calculate_zodiac_sign(birth_date.day, birth_date.month)
            
        except Exception as e:
            logger.error(f"❌ Ошибка вычисления возраста/знака зодиака: {e}")
        
        return age, zodiac

    def _ensure_emoji_support(self, text: str) -> str:
        """Проверка и коррекция эмодзи для Telegram"""
        # Telegram поддерживает эмодзи, проблема может быть в кодировке файла
        return text

    def format_profile_text(self, user_data: dict) -> str:
        """Форматирование текста профиля с учетом возможного отсутствия данных"""
        
        text = "👤 <b>Ваш профиль</b>\n\n"
        
        # Проверяем наличие данных профиля
        has_birth_date = user_data.get('birth_date') not in [None, '']
        has_gender = user_data.get('gender') not in [None, '']
        
        if not has_birth_date and not has_gender:
            text += "📝 <i>Профиль не заполнен</i>\n\n"
            text += "💡 Заполните профиль для персонализированных интерпретаций!"
            return self._ensure_emoji_support(text)
        
        if has_birth_date:
            birth_date = user_data['birth_date']
            
            # Форматируем дату, если она в старом формате
            formatted_birth_date = birth_date
            if re.match(r'\d{4}-\d{2}-\d{2}', birth_date):
                try:
                    birth_date_obj = datetime.strptime(birth_date, '%Y-%m-%d')
                    formatted_birth_date = birth_date_obj.strftime('%d.%m.%Y')
                except Exception as e:
                    logger.error(f"❌ Ошибка конвертации даты: {e}")
            
            text += f"📅 <b>Дата рождения:</b> {formatted_birth_date}\n"
            
            # Расчет возраста и знака зодиака
            try:
                age, zodiac = self._calculate_age(formatted_birth_date)
                if age:
                    text += f"   🎂 <b>Возраст:</b> {age} лет\n"
                if zodiac:
                    text += f"   ♈️ <b>Знак зодиака:</b> {zodiac}\n"
            except Exception as e:
                logger.error(f"❌ Ошибка расчета данных из даты рождения {formatted_birth_date}: {e}")
        
        if has_gender:
            gender_display = self._format_gender(user_data['gender'])
            text += f"⚧ <b>Пол:</b> {gender_display}\n"
        
        text += "\n💡 Эти данные помогают делать интерпретации более точными и персонализированными"
        
        return self._ensure_emoji_support(text)

    def validate_birth_date(self, birth_date_str: str) -> tuple:
        """Валидация даты рождения"""
        if not re.match(r'^\d{2}\.\d{2}\.\d{4}$', birth_date_str):
            return False, "Неверный формат даты. Используйте ДД.ММ.ГГГГ (например: 15.05.1990)"
        
        try:
            birth_date = datetime.strptime(birth_date_str, '%d.%m.%Y')
            today = datetime.now()
            
            # Проверяем что дата не в будущем
            if birth_date > today:
                return False, "Дата рождения не может быть в будущем."
                
            # Проверяем что возраст разумный
            age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
            if age > 150:
                return False, "Пожалуйста, проверьте дату рождения. Возраст не должен превышать 150 лет."
                
            return True, birth_date
            
        except ValueError:
            return False, "Неверная дата. Пожалуйста, введите существующую дату в формате ДД.ММ.ГГГГ"

    def update_user_profile(self, user_id: int, birth_date: str = None, gender: str = None) -> bool:
        """Обновление профиля пользователя"""
        try:
            success = self.user_db.update_user_profile(
                user_id=user_id,
                birth_date=birth_date,
                gender=gender
            )
            return success
        except Exception as e:
            logger.error(f"❌ Ошибка обновления профиля для пользователя {user_id}: {e}")
            return False

    def clear_user_profile(self, user_id: int) -> bool:
        """Очистка профиля пользователя через сервис"""
        try:
            return self.user_db.clear_user_profile(user_id)
        except Exception as e:
            logger.error(f"❌ Ошибка очистки профиля через сервис для пользователя {user_id}: {e}")
            return False

    def get_user_profile_data(self, user_id: int):
        """Получение данных профиля пользователя"""
        try:
            profile = self.user_db.get_user_profile(user_id)
            return profile
        except Exception as e:
            logger.error(f"❌ Ошибка получения профиля для пользователя {user_id}: {e}")
            return None

    def get_user_profile_for_ai(self, user_id: int) -> tuple:
        """Получение данных профиля для AI-интерпретации"""
        profile = self.get_user_profile_data(user_id)
        user_age = None
        user_gender = None
        
        if profile and profile.get('birth_date'):
            try:
                birth_date_str = profile.get('birth_date')
                if '.' in birth_date_str:
                    birth_date = datetime.strptime(birth_date_str, '%d.%m.%Y')
                else:
                    birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d')
                
                today = datetime.now()
                user_age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
                
                logger.info(f"🔮 Расчет возраста для AI: {birth_date_str} -> {user_age} лет")
                
            except Exception as e:
                logger.error(f"❌ Ошибка расчета возраста из {profile.get('birth_date')}: {e}")

        if profile and profile.get('gender'):
            user_gender = profile.get('gender')
            logger.info(f"🔮 Передаем пол в AI: {user_gender}")
        
        return user_age, user_gender