"""
Tarot Engine - ядро системы для работы с картами Таро
Отвечает за перемешивание, вытаскивание карт и управление раскладами
"""

import json
import random
import logging
from typing import List, Dict, Tuple, Optional

# Настройка логирования
logger = logging.getLogger(__name__)


class TarotCard:
    """Представление одной карты Таро с новой структурой данных"""
    
    def __init__(self, card_data: Dict):
        self.id = card_data.get('id', '')
        self.name = card_data.get('name', '')
        self.type = card_data.get('type', '')  # major/minor
        self.suit = card_data.get('suit', '')  # для младших арканов
        self.description = card_data.get('description', '')
        self.meaning_upright = card_data.get('meaning_upright', {})
        self.meaning_reversed = card_data.get('meaning_reversed', {})
        self.keywords = card_data.get('keywords', {})
        self.image_url = card_data.get('image_url', '')
        self.is_reversed = False
        self.position = 'upright'  # Добавляем поле position
    
    def __str__(self):
        status = "перевернутая" if self.is_reversed else "прямая"
        return f"{self.name} ({status})"
    
    def get_meaning(self) -> Dict:
        """Возвращает значения карты с учетом положения"""
        if self.is_reversed:
            return {
                'meaning': self.meaning_reversed,
                'keywords': self.keywords.get('reversed', []),
                'description': f"Перевернутая: {self.description}"
            }
        else:
            return {
                'meaning': self.meaning_upright,
                'keywords': self.keywords.get('upright', []),
                'description': self.description
            }
    
    def to_dict(self) -> Dict:
        """Возвращает карту в виде словаря с полной информацией"""
        return {
            'id': self.id,
            'name': self.name,
            'type': self.type,
            'suit': self.suit,
            'description': self.description,
            'is_reversed': self.is_reversed,
            'position': self.position,
            'image_url': self.image_url,
            'meaning': self.get_meaning()
        }
    
    def copy(self) -> 'TarotCard':
        """Создает копию карты"""
        card_copy = TarotCard({
            'id': self.id,
            'name': self.name,
            'type': self.type,
            'suit': self.suit,
            'description': self.description,
            'meaning_upright': self.meaning_upright,
            'meaning_reversed': self.meaning_reversed,
            'keywords': self.keywords,
            'image_url': self.image_url
        })
        card_copy.is_reversed = self.is_reversed
        card_copy.position = self.position
        return card_copy


def load_deck() -> List[TarotCard]:
    """Загрузка колоды из JSON файла с оптимизированным логированием"""
    try:
        with open('data/tarot_deck.json', 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        cards = []
        
        # Загружаем Старшие Арканы
        if 'major_arcana' in data:
            if isinstance(data['major_arcana'], list):
                for i, card_data in enumerate(data['major_arcana']):
                    if not isinstance(card_data, dict):
                        print(f"⚠️ Ошибка в старшем аркане {i}: данные не являются словарем")
                        continue
                    cards.append(TarotCard(card_data))
            else:
                print("❌ Структура major_arcana не является списком")
        else:
            print("⚠️ В JSON отсутствует раздел 'major_arcana'")
        
        # Загружаем Младшие Арканы
        if 'minor_arcana' in data:
            if isinstance(data['minor_arcana'], list):
                for card_data in data['minor_arcana']:
                    if not isinstance(card_data, dict):
                        print(f"⚠️ Пропущена карта: данные не являются словарем")
                        continue
                    cards.append(TarotCard(card_data))
            else:
                print("❌ Структура minor_arcana не является списком карт")
        else:
            print("⚠️ В JSON отсутствует раздел 'minor_arcana'")
        
        total_cards = len(cards)
        
        if total_cards != 78:
            print(f"⚠️ Предупреждение: ожидалось 78 карт, загружено {total_cards}")
            if total_cards < 78:
                print("🔄 Используем резервную колоду...")
                return create_fallback_deck()
        
        print("✅ Колода карт загружена успешно")
        return cards
        
    except json.JSONDecodeError as e:
        print(f"❌ Ошибка декодирования JSON: {e}")
        print(f"📍 Позиция ошибки: строка {e.lineno}, столбец {e.colno}")
        return create_fallback_deck()
    except Exception as e:
        print(f"❌ Ошибка загрузки колоды: {e}")
        import traceback
        print(f"📋 Детали ошибки: {traceback.format_exc()}")
        return create_fallback_deck()


def create_fallback_deck() -> List[TarotCard]:
    """Создает базовую колоду из 78 карт при проблемах с JSON"""
    print("🔄 Создание резервной колоды...")
    cards = []
    
    # Старшие Арканы (0-21)
    major_names = ["Шут", "Маг", "Верховная Жрица", "Императрица", "Император", 
                  "Иерофант", "Влюбленные", "Колесница", "Сила", "Отшельник",
                  "Колесо Фортуны", "Справедливость", "Повешенный", "Смерть", 
                  "Умеренность", "Дьявол", "Башня", "Звезда", "Луна", "Солнце", 
                  "Суд", "Мир"]
    
    for i, name in enumerate(major_names):
        cards.append(TarotCard({
            "id": str(i),
            "name": name,
            "type": "major",
            "suit": None,
            "description": f"Старший Аркан: {name}",
            "meaning_upright": {"general": "Прямое значение"},
            "meaning_reversed": {"general": "Перевернутое значение"}, 
            "keywords": {"upright": ["ключ"], "reversed": ["ключ"]},
            "image_url": f"images/major/{name.lower()}.jpg"
        }))
    
    # Младшие Арканы (56 карт)
    suits = {
        'wands': 'Жезлы',
        'cups': 'Кубки', 
        'swords': 'Мечи',
        'pentacles': 'Пентакли'
    }
    
    card_names = ["Туз", "Двойка", "Тройка", "Четверка", "Пятерка", "Шестерка",
                 "Семерка", "Восьмерка", "Девятка", "Десятка", "Паж", "Рыцарь",
                 "Королева", "Король"]
    
    for suit_key, suit_name in suits.items():
        for i, card_name in enumerate(card_names):
            full_name = f"{card_name} {suit_name}"
            cards.append(TarotCard({
                "id": f"{suit_key}_{i}",
                "name": full_name,
                "type": "minor", 
                "suit": suit_key,
                "description": f"Младший Аркан: {full_name}",
                "meaning_upright": {"general": "Прямое значение"},
                "meaning_reversed": {"general": "Перевернутое значение"},
                "keywords": {"upright": ["ключ"], "reversed": ["ключ"]},
                "image_url": f"images/minor/{suit_key}_{i}.jpg"
            }))
    
    print(f"✅ Создана резервная колода из {len(cards)} карт")
    return cards


class TarotDeck:
    """Управление всей колодой Таро"""
    
    def __init__(self):
        self.cards: List[TarotCard] = []
        self.discard_pile: List[TarotCard] = []
        self.load_deck()
        self.shuffle_deck()  # Перемешиваем колоду при инициализации
    
    def load_deck(self) -> bool:
        """Загрузка колоды в класс"""
        self.cards = load_deck()
        
        # Проверка уникальности карт в колоде
        unique_ids = set(card.id for card in self.cards)
        if len(unique_ids) != len(self.cards):
            print(f"⚠️ В колоде есть дубликаты! Уникальных карт: {len(unique_ids)}, всего: {len(self.cards)}")
        
        return len(self.cards) > 0
    
    def shuffle_deck(self) -> None:
        """Перемешивание колоды"""
        random.shuffle(self.cards)
    
    def reset_deck(self) -> None:
        """Сброс колоды - возврат всех карт и перемешивание"""
        self.cards.extend(self.discard_pile)
        self.discard_pile.clear()
        
        if not self.cards:
            print("⚠️ Колода пуста, создаем новую...")
            self.cards = create_fallback_deck()
        
        self.shuffle_deck()
    
    def draw_cards(self, count: int = 1) -> List[Dict]:
        """
        Исправленный выбор карт с гарантией уникальности в рамках одного расклада
        
        Args:
            count: количество карт для вытаскивания
            
        Returns:
            List[Dict]: список словарей с данными карт
        """
        if count > len(self.cards):
            self.reset_deck()
        
        drawn_cards = []
        drawn_ids = set()  # Для отслеживания уникальности карт в этом раскладе
        
        while len(drawn_cards) < count:
            if not self.cards:
                self.reset_deck()
                drawn_ids.clear()  # Сбрасываем отслеживание при сбросе колоды
            
            card = self.cards.pop()
            
            # Пропускаем карту, если она уже есть в этом раскладе
            if card.id in drawn_ids:
                # Возвращаем карту в конец колоды и продолжаем
                self.cards.insert(0, card)
                continue
                
            drawn_ids.add(card.id)
            
            # Определение положения карты с увеличенной вероятностью перевернутых
            position = random.choices(
                ['upright', 'reversed'], 
                weights=[0.6, 0.4],
                k=1
            )[0]
            
            # Создаем копию карты с обновленными данными
            card_copy = card.copy()
            card_copy.position = position
            card_copy.is_reversed = (position == 'reversed')
            
            # Конвертируем в словарь для возврата
            card_dict = card_copy.to_dict()
            drawn_cards.append(card_dict)
            
            # Добавляем оригинальную карту в discard_pile
            self.discard_pile.append(card)
        
        # Проверка на повторяющиеся карты в раскладе
        card_names = [card['name'] for card in drawn_cards]
        if len(card_names) != len(set(card_names)):
            logger.warning(f"⚠️ В раскладе есть повторяющиеся карты: {card_names}")
        
        return drawn_cards
    
    def return_cards(self, cards: List[TarotCard]) -> None:
        """Возврат карт в колоду"""
        for card in cards:
            card.is_reversed = False
            card.position = 'upright'
            if card in self.discard_pile:
                self.discard_pile.remove(card)
            self.cards.append(card)
    
    def get_deck_status(self) -> Dict:
        """Статус колоды"""
        return {
            'total_cards': len(self.cards) + len(self.discard_pile),
            'remaining': len(self.cards),
            'discarded': len(self.discard_pile)
        }


class TarotSpread:
    """Представление расклада Таро"""
    
    SPREAD_SCHEMES = {
        'single': {
            'name': 'Карта дня',
            'positions': ['Карта дня'],
            'description': 'Одна карта, отражающая энергию текущего дня'
        },
        'situation_action_result': {
            'name': 'Ситуация → Действие → Результат',
            'positions': ['Ситуация', 'Действие', 'Результат'],
            'description': 'Анализ текущей ситуации и возможных последствий'
        },
        'past_present_future': {
            'name': 'Прошлое → Настоящее → Будущее',
            'positions': ['Прошлое', 'Настоящее', 'Будущее'],
            'description': 'Временная перспектива развития событий'
        },
        'mind_body_spirit': {
            'name': 'Разум → Тело → Дух',
            'positions': ['Разум', 'Тело', 'Дух'],
            'description': 'Баланс ментального, физического и духовного'
        }
    }
    
    def __init__(self, spread_type: str, question_category: str = "general"):
        self.spread_type = spread_type
        self.question_category = question_category
        self.scheme = self.SPREAD_SCHEMES.get(spread_type, self.SPREAD_SCHEMES['single'])
        self.cards = []
        self.positions = {}
    
    def add_card(self, card: TarotCard, position: str) -> None:
        """Добавление карты в позицию расклада"""
        self.cards.append(card)
        self.positions[position] = card
    
    def __str__(self):
        return f"Расклад '{self.scheme['name']}' ({len(self.cards)} карт)"
    
    def get_cards_with_images(self) -> List[Dict]:
        """Возвращает список карт с информацией об изображениях"""
        return [card.to_dict() for card in self.cards]


def shuffle_deck(deck: TarotDeck) -> None:
    """Перемешивание колоды"""
    deck.shuffle_deck()


def create_spread(spread_type: str, question_category: str = "general") -> TarotSpread:
    """
    Создание расклада указанного типа
    
    Args:
        spread_type: тип расклада ('single', 'situation_action_result', etc.)
        question_category: категория вопроса ('love', 'career', 'health', etc.)
    
    Returns:
        TarotSpread: готовый расклад
    """
    deck = TarotDeck()
    
    spread = TarotSpread(spread_type, question_category)
    card_count = len(spread.scheme['positions'])
    
    drawn_cards = deck.draw_cards(card_count)
    
    for i, position in enumerate(spread.scheme['positions']):
        card_data = drawn_cards[i]
        card = TarotCard(card_data)
        card.is_reversed = card_data['is_reversed']
        card.position = card_data['position']
        spread.add_card(card, position)
    
    print(f"✅ Создан расклад: {spread}")
    return spread


def generate_spread(spread_type: str, category: str = "general") -> Tuple[List[Dict], str]:
    """
    Генерация расклада с возвратом полных данных карт (включая изображения)
    
    Args:
        spread_type: тип расклада ('one_card', 'three_card')
        category: категория вопроса
        
    Returns:
        Tuple[List[Dict], str]: данные карт с изображениями и текстовое описание
    """
    deck = TarotDeck()
    
    if spread_type == "one_card":
        num_cards = 1
    elif spread_type == "three_card":
        num_cards = 3
    else:
        num_cards = 1
        logger.warning(f"Неизвестный тип расклада: {spread_type}, используем 1 карту")
    
    cards = deck.draw_cards(num_cards)
    
    if spread_type == "one_card":
        card = cards[0]
        position_text = "прямая" if card['position'] == 'upright' else "перевернутая"
        spread_text = f"Карта дня: {card['name']} ({position_text})"
    else:
        positions = ["Прошлое", "Настоящее", "Будущее"]
        spread_parts = []
        for i, card in enumerate(cards):
            position_text = "прямая" if card['position'] == 'upright' else "перевернутая"
            spread_parts.append(f"{positions[i]}: {card['name']} ({position_text})")
        spread_text = " • ".join(spread_parts)
    
    logger.info(f"🔮 Сгенерирован расклад: {spread_text}")
    
    return cards, spread_text


def get_card_meaning(card: TarotCard, position: str, is_reversed: bool) -> Dict:
    """
    Базовые значения карты для интерпретации
    
    Args:
        card: карта Таро
        position: позиция в раскладе
        is_reversed: перевернутое положение
    
    Returns:
        Dict: структурированные данные для интерпретации
    """
    card.is_reversed = is_reversed
    meaning_data = card.get_meaning()
    
    return {
        'card_name': card.name,
        'card_id': card.id,
        'type': card.type,
        'suit': card.suit,
        'position': position,
        'is_reversed': is_reversed,
        'keywords': meaning_data['keywords'],
        'meaning': meaning_data['meaning'],
        'description': meaning_data['description'],
        'image_url': card.image_url
    }


def get_spread_interpretation_data(spread: TarotSpread) -> Dict:
    """
    Подготовка структурированных данных для ИИ-интерпретатора
    
    Args:
        spread: расклад для интерпретации
    
    Returns:
        Dict: данные для интерпретации
    """
    interpretation_data = {
        'spread_name': spread.scheme['name'],
        'spread_type': spread.spread_type,
        'question_category': spread.question_category,
        'positions': [],
        'cards': []
    }
    
    for position, card in spread.positions.items():
        card_data = get_card_meaning(card, position, card.is_reversed)
        interpretation_data['cards'].append(card_data)
        interpretation_data['positions'].append({
            'position': position,
            'card_name': card.name,
            'card_id': card.id,
            'is_reversed': card.is_reversed,
            'image_url': card.image_url
        })
    
    return interpretation_data


# Глобальный экземпляр колоды для использования в боте
global_deck = TarotDeck()

def draw_cards(count: int) -> List[Dict]:
    """Упрощенная функция для вытаскивания карт из глобальной колоды"""
    return global_deck.draw_cards(count)


# Пример использования и тестирование
if __name__ == "__main__":
    print("=== ТЕСТИРОВАНИЕ TAROT ENGINE ===\n")
    
    # Тест уникальности карт в раскладе
    print("1. Тест уникальности карт в раскладе:")
    deck = TarotDeck()
    cards = draw_cards(3)
    card_names = [card['name'] for card in cards]
    print(f"   Карты в раскладе: {card_names}")
    print(f"   Уникальных карт: {len(set(card_names))} из {len(card_names)}")
    
    # Тест многократной генерации раскладов
    print("\n2. Тест многократной генерации раскладов:")
    for i in range(3):
        cards_data, spread_text = generate_spread("three_card", "career")
        card_names = [card['name'] for card in cards_data]
        print(f"   Расклад {i+1}: {spread_text}")
        print(f"   Уникальные карты: {len(set(card_names))} из {len(card_names)}")
    
    print("\n=== ТЕСТИРОВАНИЕ ЗАВЕРШЕНО ===")