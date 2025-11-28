tma_spreads

id INTEGER PRIMARY KEY AUTOINCREMENT

user_id INTEGER NOT NULL

spread_type TEXT NOT NULL — "one" / "three"

category TEXT NULL

user_question TEXT NULL

cards_json TEXT NOT NULL — JSON-массив карт

interpretation TEXT NULL

created_at TEXT NOT NULL — ISO-строка

tma_spread_questions

id INTEGER PRIMARY KEY AUTOINCREMENT

spread_id INTEGER NOT NULL

user_id INTEGER NOT NULL

question TEXT NOT NULL

answer TEXT NULL

status TEXT NOT NULL — "pending"/"ready"/"failed"

created_at TEXT NOT NULL