"""
Клавиатуры для Telegram бота AI-Таролог
Единый API для inline-клавиатур
"""

from telegram import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Dict, Optional
import re

# ==================== ОСНОВНОЙ ПУБЛИЧНЫЙ API ====================

def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Главная inline-клавиатура меню"""
    keyboard = [
        [InlineKeyboardButton("🎴 Карта дня", callback_data="spread_single"), 
         InlineKeyboardButton("🔮 3 карты", callback_data="spread_three")],
        [InlineKeyboardButton("📖 История раскладов", callback_data="show_history"), 
         InlineKeyboardButton("👤 Профиль", callback_data="profile")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_back_to_menu_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура возврата в главное меню"""
    keyboard = [
        [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_card_selection_keyboard(
    session_id: str, 
    current_position: int = 1, 
    total_positions: int = 1
) -> InlineKeyboardMarkup:
    """Клавиатура выбора карты"""
    keyboard = []
    
    # Создаем строки с кнопками выбора
    row = []
    for i in range(1, 6):
        callback_data = f"card_choice:{session_id}:{current_position}:{i}"
        # Проверяем длину callback_data (макс 64 байта)
        if len(callback_data.encode('utf-8')) > 64:
            raise ValueError(f"Callback data too long: {callback_data}")
            
        row.append(InlineKeyboardButton(f"{i}️⃣", callback_data=callback_data))
        if len(row) == 3:  # Первые 3 кнопки в первой строке
            keyboard.append(row)
            row = []
    if row:  # Оставшиеся 2 кнопки во второй строке
        keyboard.append(row)
    
    # Кнопка возврата для three раскладов (кроме первой позиции)
    if current_position > 1:
        callback_data = f"back_to_select:{session_id}:{current_position-1}"
        if len(callback_data.encode('utf-8')) > 64:
            raise ValueError(f"Callback data too long: {callback_data}")
            
        keyboard.append([InlineKeyboardButton("🔄 Выбрать другую карту", 
                      callback_data=callback_data)])
    
    return InlineKeyboardMarkup(keyboard)

def get_history_keyboard(
    current_page: int, 
    total_pages: int, 
    spreads: List[Dict]
) -> InlineKeyboardMarkup:
    """Клавиатура истории раскладов с пагинацией и деталями"""
    keyboard = []
    
    # Кнопки деталей раскладов
    spreads_to_show = spreads[:10]  # Ограничиваем 10 раскладами
    
    for i in range(0, len(spreads_to_show), 2):
        row = []
        # Первая кнопка в строке
        spread = spreads_to_show[i]
        row.append(InlineKeyboardButton(
            f"📖 Детали {i+1}", 
            callback_data=f"spread_{spread['id']}"  # ИСПОЛЬЗУЕМ spread_ ВМЕСТО details_
        ))
        
        # Вторая кнопка в строке (если есть)
        if i + 1 < len(spreads_to_show):
            spread = spreads_to_show[i + 1]
            row.append(InlineKeyboardButton(
                f"📖 Детали {i+2}", 
                callback_data=f"spread_{spread['id']}"  # ИСПОЛЬЗУЕМ spread_ ВМЕСТО details_
            ))
        
        keyboard.append(row)
    
    # Кнопки пагинации
    nav_buttons = []
    
    if current_page > 1:
        nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"history_page_{current_page - 1}"))
    
    nav_buttons.append(InlineKeyboardButton(f"{current_page}/{total_pages}", callback_data="history_info"))
    
    if current_page < total_pages:
        nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"history_page_{current_page + 1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # Дополнительные кнопки
    if spreads:
        keyboard.append([InlineKeyboardButton("🗑️ Очистить историю", callback_data="clear_history")])
    
    keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")])
    
    return InlineKeyboardMarkup(keyboard)

def get_spread_details_keyboard(
    spread_id: int, 
    has_questions: bool = False
) -> InlineKeyboardMarkup:
    """Клавиатура деталей расклада"""
    keyboard = []
    
    # Кнопка задать вопрос
    keyboard.append([InlineKeyboardButton(
        "💭 Задать вопрос по раскладу", 
        callback_data=f"ask_question_{spread_id}"
    )])
    
    # Если есть вопросы, показываем кнопку просмотра
    if has_questions:
        keyboard.append([InlineKeyboardButton(
            "📋 Просмотреть вопросы", 
            callback_data=f"view_questions_{spread_id}"
        )])
    
    keyboard.extend([
        [InlineKeyboardButton("📖 Назад к истории", callback_data="back_to_history")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
    ])
    
    return InlineKeyboardMarkup(keyboard)

def get_interpretation_keyboard(spread_id: int) -> InlineKeyboardMarkup:
    """Клавиатура после завершения расклада"""
    keyboard = [
        [InlineKeyboardButton("💭 Задать вопрос по раскладу", callback_data=f"ask_question_{spread_id}")],
        [InlineKeyboardButton("📖 История раскладов", callback_data="show_history")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ==================== АЛИАСЫ ДЛЯ ОБРАТНОЙ СОВМЕСТИМОСТИ ====================

def get_main_menu_inline_keyboard() -> InlineKeyboardMarkup:
    """Алиас для обратной совместимости"""
    return get_main_menu_keyboard()

def get_history_list_keyboard(spreads: List[Dict]) -> InlineKeyboardMarkup:
    """Алиас для обратной совместимости"""
    return get_history_keyboard(current_page=1, total_pages=1, spreads=spreads)

# ==================== ДОПОЛНИТЕЛЬНЫЕ КЛАВИАТУРЫ ====================

def get_categories_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора категорий"""
    keyboard = [
        [InlineKeyboardButton("💖 Любовь", callback_data="category_love")],
        [InlineKeyboardButton("💼 Карьера", callback_data="category_career")],
        [InlineKeyboardButton("💰 Финансы", callback_data="category_finance")],
        [InlineKeyboardButton("👥 Отношения", callback_data="category_relationships")],
        [InlineKeyboardButton("🌱 Личностный рост", callback_data="category_growth")],
        [InlineKeyboardButton("🔮 Общий вопрос", callback_data="category_general")],
        [InlineKeyboardButton("💭 Свой вопрос", callback_data="category_custom")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_cancel_question_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура отмены ввода вопроса"""
    keyboard = [
        [InlineKeyboardButton("❌ Отменить ввод", callback_data="cancel_custom_question")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_profile_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура управления профилем"""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✏️ Редактировать дату", callback_data="edit_birth_date"),
            InlineKeyboardButton("⚧ Изменить пол", callback_data="edit_gender")
        ],
        [InlineKeyboardButton("🗑️ Очистить профиль", callback_data="clear_profile")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
    ])

# ==================== REPLY-КЛАВИАТУРЫ (ОТДЕЛЬНЫЙ КОНТРАКТ) ====================

def get_main_menu_reply_keyboard() -> ReplyKeyboardMarkup:
    """Главная reply-клавиатура (для текстовых сообщений)"""
    keyboard = [
        ["🎴 Карта дня", "🔮 3 карты"],
        ["📖 История раскладов", "👤 Профиль"],
        ["ℹ️ Помощь", "🏠 Главное меню"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_back_to_menu_reply_keyboard() -> ReplyKeyboardMarkup:
    """Reply-клавиатура возврата в меню"""
    return ReplyKeyboardMarkup([["🏠 Главное меню"]], resize_keyboard=True)

def get_cancel_reply_keyboard() -> ReplyKeyboardMarkup:
    """Reply-клавиатура отмены операций"""
    keyboard = [['❌ Отмена']]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ==================== UNIT TESTS И ПРОВЕРКА CALLBACK_DATA ====================

# Паттерны обработчиков из bot_main (должны соответствовать callback_data)
EXPECTED_HANDLER_PATTERNS = {
    'main_menu': r'^main_menu$',
    'profile': r'^profile$',
    'spread_single': r'^spread_single$',
    'spread_three': r'^spread_three$',
    'show_history': r'^show_history$',
    'spread_details': r'^spread_\d+$',  # ИЗМЕНЕНО: был details_, теперь spread_
    'history_page': r'^history_page_\d+$',
    'history_info': r'^history_info$',
    'clear_history': r'^clear_history$',
    'back_to_history': r'^back_to_history$',
    'ask_question': r'^ask_question_\d+$',
    'view_questions': r'^view_questions_\d+$',
    'category_love': r'^category_love$',
    'category_career': r'^category_career$',
    'category_finance': r'^category_finance$',
    'category_relationships': r'^category_relationships$',
    'category_growth': r'^category_growth$',
    'category_general': r'^category_general$',
    'category_custom': r'^category_custom$',
    'edit_birth_date': r'^edit_birth_date$',
    'edit_gender': r'^edit_gender$',
    'clear_profile': r'^clear_profile$',
    'cancel_custom_question': r'^cancel_custom_question$',
    'card_choice': r'^card_choice:[^:]+:\d+:\d+$',
    'continue_select': r'^continue_select:[^:]+:\d+$',
    'back_to_select': r'^back_to_select:[^:]+:\d+$',
}

def _extract_callback_data(keyboard: InlineKeyboardMarkup) -> List[str]:
    """Извлекает все callback_data из клавиатуры"""
    callback_data_list = []
    for row in keyboard.inline_keyboard:
        for button in row:
            if hasattr(button, 'callback_data') and button.callback_data:
                callback_data_list.append(button.callback_data)
    return callback_data_list

def _test_callback_data_compatibility():
    """Тест соответствия callback_data зарегистрированным обработчикам"""
    tests_passed = 0
    tests_failed = 0
    mismatches = []

    # Тестируемые клавиатуры
    test_keyboards = [
        ('main_menu', get_main_menu_keyboard()),
        ('back_to_menu', get_back_to_menu_keyboard()),
        ('card_selection', get_card_selection_keyboard('test_session', 1, 1)),
        ('history', get_history_keyboard(1, 1, [{'id': 123}, {'id': 456}])),
        ('spread_details', get_spread_details_keyboard(123)),
        ('interpretation', get_interpretation_keyboard(123)),
        ('categories', get_categories_keyboard()),
        ('profile', get_profile_keyboard()),
        ('cancel_question', get_cancel_question_keyboard()),
    ]

    for keyboard_name, keyboard in test_keyboards:
        callback_data_list = _extract_callback_data(keyboard)
        
        for callback_data in callback_data_list:
            matched = False
            for pattern_name, pattern in EXPECTED_HANDLER_PATTERNS.items():
                if re.match(pattern, callback_data):
                    matched = True
                    break
            
            if matched:
                tests_passed += 1
            else:
                tests_failed += 1
                mismatches.append(f"{keyboard_name}: '{callback_data}' не соответствует ни одному обработчику")

    print(f"\n📊 Тест совместимости callback_data:")
    print(f"✅ Пройдено: {tests_passed}")
    print(f"❌ Провалено: {tests_failed}")
    
    if mismatches:
        print("\n🔍 Несоответствия:")
        for mismatch in mismatches:
            print(f"   - {mismatch}")

    return tests_failed == 0, mismatches

def _test_main_menu_profile_button():
    """Тест наличия кнопки профиля в главном меню"""
    keyboard = get_main_menu_keyboard()
    callback_data_list = _extract_callback_data(keyboard)
    
    has_profile = any('profile' in data for data in callback_data_list)
    if has_profile:
        print("✅ Кнопка профиля присутствует в главном меню")
        return True
    else:
        print("❌ Кнопка профиля отсутствует в главном меню")
        return False

def _test_spread_id_consistency():
    """Тест единообразия использования spread_ вместо details_"""
    test_spreads = [{'id': 123}, {'id': 456}]
    keyboard = get_history_keyboard(1, 1, test_spreads)
    callback_data_list = _extract_callback_data(keyboard)
    
    # Проверяем, что используются spread_ префиксы
    spread_buttons = [data for data in callback_data_list if data.startswith('spread_')]
    details_buttons = [data for data in callback_data_list if data.startswith('details_')]
    
    if spread_buttons and not details_buttons:
        print("✅ Все кнопки используют spread_ префикс")
        return True
    elif details_buttons:
        print(f"❌ Обнаружены кнопки с details_ префиксом: {details_buttons}")
        return False
    else:
        print("ℹ️ В тестовой клавиатуре нет кнопок с spread_ префиксом")
        return True

def _test_keyboards():
    """Внутренние тесты клавиатур"""
    tests_passed = 0
    tests_failed = 0
    
    print("🧪 Запуск тестов клавиатур...")
    
    # Тест 1: Главное меню
    try:
        keyboard = get_main_menu_keyboard()
        assert hasattr(keyboard, 'inline_keyboard'), "Главное меню должно быть inline-клавиатурой"
        assert len(keyboard.inline_keyboard) > 0, "Главное меню не должно быть пустым"
        print("✅ Тест главного меню пройден")
        tests_passed += 1
    except Exception as e:
        print(f"❌ Тест главного меню провален: {e}")
        tests_failed += 1
    
    # Тест 2: Кнопка профиля в главном меню
    if _test_main_menu_profile_button():
        tests_passed += 1
    else:
        tests_failed += 1
    
    # Тест 3: Единообразие spread_ префикса
    if _test_spread_id_consistency():
        tests_passed += 1
    else:
        tests_failed += 1
    
    # Тест 4: Наличие main_menu в основных клавиатурах
    test_functions = [
        get_main_menu_keyboard,
        get_back_to_menu_keyboard,
        lambda: get_history_keyboard(1, 1, [{'id': 1}]),
        lambda: get_spread_details_keyboard(1),
        lambda: get_interpretation_keyboard(1),
        get_categories_keyboard,
        get_profile_keyboard
    ]
    
    for func in test_functions:
        try:
            keyboard = func()
            has_main_menu = any(
                any('main_menu' in str(button.callback_data) for button in row)
                for row in keyboard.inline_keyboard
            )
            assert has_main_menu, f"Клавиатура {func.__name__} должна содержать main_menu"
            tests_passed += 1
        except Exception as e:
            print(f"❌ Тест main_menu в {func.__name__} провален: {e}")
            tests_failed += 1
    
    # Тест 5: Совместимость callback_data с обработчиками
    compatibility_passed, mismatches = _test_callback_data_compatibility()
    if compatibility_passed:
        tests_passed += 1
    else:
        tests_failed += 1
    
    print(f"\n📊 Итоговые результаты тестирования: {tests_passed} пройдено, {tests_failed} провалено")
    return tests_failed == 0

# ==================== ЭКСПОРТ ПУБЛИЧНОГО API ====================

__all__ = [
    # Основной API
    'get_main_menu_keyboard',
    'get_back_to_menu_keyboard', 
    'get_card_selection_keyboard',
    'get_history_keyboard',
    'get_spread_details_keyboard',
    'get_interpretation_keyboard',
    
    # Алиасы для обратной совместимости
    'get_main_menu_inline_keyboard',
    'get_history_list_keyboard',
    
    # Дополнительные клавиатуры
    'get_categories_keyboard',
    'get_cancel_question_keyboard',
    'get_profile_keyboard',
    
    # Reply-клавиатуры
    'get_main_menu_reply_keyboard',
    'get_back_to_menu_reply_keyboard', 
    'get_cancel_reply_keyboard',
    
    # Тестовые утилиты
    '_test_callback_data_compatibility',
    '_test_keyboards',
]

# Запуск тестов при прямом выполнении файла
if __name__ == "__main__":
    success = _test_keyboards()
    if success:
        print("✅ Все тесты клавиатур пройдены успешно!")
    else:
        print("❌ Некоторые тесты клавиатур провалены!")
        exit(1)