# src/models/user_context.py
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime

@dataclass
class SpreadData:
    """Данные расклада"""
    spread_id: Optional[int] = None
    spread_type: str = ""
    category: str = ""
    cards: List[Dict[str, Any]] = None
    interpretation: Optional[str] = None
    created_at: Optional[str] = None

    def __post_init__(self):
        if self.cards is None:
            self.cards = []

@dataclass
class ProfileData:
    """Данные профиля пользователя"""
    user_id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    birth_date: Optional[str] = None
    gender: Optional[str] = None

@dataclass
class InteractiveSession:
    """Модель для хранения данных интерактивной сессии выбора карт"""
    session_id: str
    user_id: int
    spread_type: str  # 'single' | 'three'
    category: str
    selected_cards: Dict[int, Any] = field(default_factory=dict)  # позиция -> карта
    current_position: int = 1  # текущая позиция для three раскладов
    created_at: datetime = field(default_factory=datetime.now)
    status: str = 'active'  # 'active' | 'completed' | 'cancelled'
    # 🔧 ДОБАВЛЕННЫЕ ПОЛЯ:
    chat_id: Optional[int] = None
    context: Optional[Any] = None
    bot: Optional[Any] = None
    
    def to_dict(self) -> dict:
        """Конвертирует сессию в словарь для сериализации"""
        return {
            'session_id': self.session_id,
            'user_id': self.user_id,
            'spread_type': self.spread_type,
            'category': self.category,
            'selected_cards': self.selected_cards,
            'current_position': self.current_position,
            'created_at': self.created_at.isoformat(),
            'status': self.status,
            'chat_id': self.chat_id,
            # context и bot не сериализуем для избежания циклических ссылок
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'InteractiveSession':
        """Создает сессию из словаря"""
        return cls(
            session_id=data['session_id'],
            user_id=data['user_id'],
            spread_type=data['spread_type'],
            category=data['category'],
            selected_cards=data.get('selected_cards', {}),
            current_position=data.get('current_position', 1),
            created_at=datetime.fromisoformat(data['created_at']),
            status=data.get('status', 'active'),
            chat_id=data.get('chat_id')
            # context и bot не восстанавливаем из словаря
        )

@dataclass
class UserContext:
    """Контекст пользователя для управления состоянием"""
    user_id: int
    current_state: str = "main_menu"
    current_spread_id: Optional[int] = None
    current_session_id: Optional[str] = None  # ID активной интерактивной сессии
    waiting_for_input: bool = False
    input_type: Optional[str] = None  # 'birth_date', 'custom_question', 'spread_question'
    
    def reset_state(self):
        """Сброс состояния пользователя"""
        self.current_state = "main_menu"
        self.current_spread_id = None
        self.current_session_id = None
        self.waiting_for_input = False
        self.input_type = None
    
    def set_waiting_for_input(self, input_type: str):
        """Установка состояния ожидания ввода"""
        self.waiting_for_input = True
        self.input_type = input_type
        self.current_state = f"waiting_{input_type}"
    
    def set_active_session(self, session_id: str):
        """Установка активной интерактивной сессии"""
        self.current_session_id = session_id
    
    def clear_session(self):
        """Очистка активной сессии"""
        self.current_session_id = None
    
    def __str__(self):
        return (f"UserContext(user_id={self.user_id}, state={self.current_state}, "
                f"waiting={self.waiting_for_input}, session_id={self.current_session_id})")