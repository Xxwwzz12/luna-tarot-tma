````markdown
# Telegram Mini App HTTP API

Этот документ описывает контракт HTTP-API для Telegram Mini App версии Таро-бота.  
Он служит основной спецификацией для:

- реализации backend’а (FastAPI);
- фронтенда Mini App;
- Postman-коллекции и интеграционных тестов.

Backend предполагается как надстройка над уже существующей БД и сервисами Telegram-бота (ProfileService, HistoryService, AI-сервис и т.д.), но понимание их реализации для работы с этим документом не требуется.

---

## Авторизация (initData)

### Общая идея

Авторизация пользователя происходит через механизм `Telegram.WebApp.initData`:

1. WebApp на клиенте получает сырую строку `initData` из `Telegram.WebApp.initData`.
2. Эта строка **отправляется на сервер как есть**, без модификаций.
3. Сервер:
   - валидирует подпись по официальной схеме Telegram (HMAC-SHA256 с использованием `BOT_TOKEN`);
   - извлекает объект `user` из `initData`;
   - по `user.id` определяет/создаёт пользователя в нашей системе.

### Способы передачи initData

Поддерживаются два варианта:

1. **Рекомендуемый вариант — HTTP-заголовок**:

   ```http
   X-Telegram-Init-Data: <raw initData>
````

2. **Альтернативный вариант — поле в JSON-теле** (для POST-запросов):

   ```json
   {
     "initData": "<raw initData>",
     "...": "другие поля"
   }
   ```

**Рекомендация:** во всех запросах Mini App использовать заголовок `X-Telegram-Init-Data`. Передача через тело (`initData` в JSON) может использоваться как fallback/на период миграции.

### Режимы авторизации

#### Режим 1 — простой (без собственного токена)

* Каждый запрос к защищённому эндпоинту содержит заголовок:

  ```http
  X-Telegram-Init-Data: <raw initData>
  ```

* Сервер на **каждый запрос**:

  * валидирует подпись `initData`;
  * извлекает `user` и его `id`;
  * связывает текущий запрос с пользователем.

Плюсы: отсутствие отдельного токена, простая модель на фронте.
Минусы: повторная криптографическая валидация на каждом запросе.

#### Режим 2 — через наш JWT

1. Фронт один раз обращается к эндпоинту авторизации:

   ```http
   POST /auth/telegram
   Content-Type: application/json
   ```

   ```json
   {
     "initData": "<raw initData>"
   }
   ```

2. Сервер:

   * валидирует `initData` по схеме Telegram;
   * извлекает `user`;
   * создаёт/обновляет пользователя в БД по `user.id`;
   * генерирует наш токен (например, JWT).

3. Ответ (успех):

   ```json
   {
     "ok": true,
     "data": {
       "user": {
         "id": 123456789,
         "username": "user",
         "first_name": "Имя",
         "last_name": "Фамилия"
       },
       "token": "<our_jwt_token_or_session_token>"
     }
   }
   ```

   * `token` — строка JWT/сессионного токена, который фронт затем использует в заголовке `Authorization`.
   * `user` — данные, извлечённые из Telegram initData (могут дополняться нашим профилем в будущем).

4. Далее все защищённые запросы отправляются с нашим токеном:

   ```http
   Authorization: Bearer <our_jwt_token>
   ```

   Опционально можно продолжать отправлять `X-Telegram-Init-Data` для плавной миграции, но в продвинутом режиме **основным источником авторизации считается наш токен**.

#### Пример ошибки при неверном initData

```json
{
  "ok": false,
  "error": {
    "code": "unauthorized",
    "message": "Invalid Telegram initData signature",
    "details": {
      "reason": "signature_mismatch"
    }
  }
}
```

### Требования по безопасности

* Без авторизации доступны только технические/служебные эндпоинты, например:

  * `GET /health`
  * `GET /docs`
  * `GET /openapi.json`
* Все остальные эндпоинты требуют **либо**:

  * валидный заголовок `X-Telegram-Init-Data` (простой режим), **либо**
  * валидный `Authorization: Bearer <token>` (режим с JWT).
* Валидация `initData` выполняется строго по официальной схеме Telegram:

  * формируется строка `check_string` из параметров (кроме `hash`), отсортированных по ключу;
  * вычисляется HMAC-SHA256 с секретом, основанным на `BOT_TOKEN`;
  * результат сравнивается с `hash` из `initData`.
* При любых проблемах с авторизацией (`initData`/токен отсутствует, протух, невалиден) — сервер возвращает ошибку формата:

  ```json
  {
    "ok": false,
    "error": {
      "code": "unauthorized",
      "message": "Authorization required",
      "details": null
    }
  }
  ```

---

## Общий формат ответов и ошибок

Все ответы API обёрнуты в единую структуру.

### Успешный ответ

```json
{
  "ok": true,
  "data": { ... }
}
```

* В `data` может быть:

  * объект (например, профиль);
  * список/массив объектов;
  * объект с полями `items`, `page`, `total_pages`, `total_items` (для пагинации);
  * служебная информация операции (например, `{ "deleted": true }`).

### Ошибочный ответ

```json
{
  "ok": false,
  "error": {
    "code": "validation_error",
    "message": "Поле question слишком короткое",
    "details": {
      "field": "question",
      "min_length": 10
    }
  }
}
```

* `code` — машинно читаемый код ошибки.
* `message` — человекочитаемое сообщение, пригодное для логов/отладки (на UI может показываться в упрощённом виде).
* `details` — произвольный объект с дополнительной информацией (например, проблемное поле, ожидаемые значения, ограничения по длине и т.д.). Может быть `null`.

### Возможные значения `error.code`

* `unauthorized` — не прошла авторизация (нет/неверный initData или Bearer-токен).
* `forbidden` — доступ к ресурсу запрещён (например, попытка прочитать чужой расклад).
* `not_found` — ресурс не найден (профиль, расклад, вопрос и т.д.).
* `validation_error` — ошибка валидации входных данных (неверный формат даты, слишком короткий текст, некорректный enum и т.п.).
* `internal_error` — внутренняя ошибка сервера (исключение, ошибка БД и т.п.; детали в логи, не в ответ).
* `rate_limited` — превышен лимит запросов (зарезервировано на будущее).

---

## Эндпоинты профиля

Профиль отражает расширенные данные пользователя (дата рождения, пол и вычисляемые поля).
Вся работа идёт от лица **текущего авторизованного пользователя**.

### GET /profile

**Назначение:** вернуть профиль текущего пользователя.

**Пример запроса (JWT-режим):**

```http
GET /profile
Authorization: Bearer <token>
```

**Пример запроса (простой режим initData):**

```http
GET /profile
X-Telegram-Init-Data: <raw initData>
```

**Пример успешного ответа:**

```json
{
  "ok": true,
  "data": {
    "user_id": 123456789,
    "username": "user",
    "first_name": "Имя",
    "last_name": "Фамилия",
    "birth_date": "1990-01-01",
    "gender": "male",
    "age": 34,
    "zodiac": "♒️ Водолей"
  }
}
```

* `birth_date` — **всегда** в формате `YYYY-MM-DD` (ISO-8601, без времени).
* `gender` — одно из:

  * `"male"`,
  * `"female"`,
  * `"other"`,
  * `null` (если ещё не указан).
* `age` и `zodiac` вычисляются на сервере на основе `birth_date`.

Если профиль ещё не заполнен:

```json
{
  "ok": true,
  "data": {
    "user_id": 123456789,
    "username": "user",
    "first_name": "Имя",
    "last_name": "Фамилия",
    "birth_date": null,
    "gender": null,
    "age": null,
    "zodiac": null
  }
}
```

### POST /profile

**Назначение:** создать/обновить профиль текущего пользователя.

**Входной JSON:**

```json
{
  "birth_date": "1990-01-01",
  "gender": "female"
}
```

* `birth_date` — строка в формате `YYYY-MM-DD` (можно разрешить `null` для «очистки» даты).
* `gender` — `"male" | "female" | "other" | null`.

**Пример успешного ответа:**

```json
{
  "ok": true,
  "data": {
    "user_id": 123456789,
    "username": "user",
    "first_name": "Имя",
    "last_name": "Фамилия",
    "birth_date": "1990-01-01",
    "gender": "female",
    "age": 35,
    "zodiac": "♓️ Рыбы"
  }
}
```

#### Примеры ошибок валидации

**Неверный формат даты:**

```json
{
  "ok": false,
  "error": {
    "code": "validation_error",
    "message": "Неверный формат даты рождения",
    "details": {
      "field": "birth_date",
      "expected_format": "YYYY-MM-DD",
      "value": "01.01.1990"
    }
  }
}
```

**Недопустимое значение gender:**

```json
{
  "ok": false,
  "error": {
    "code": "validation_error",
    "message": "Недопустимое значение gender",
    "details": {
      "field": "gender",
      "allowed_values": ["male", "female", "other", null],
      "value": "unknown"
    }
  }
}
```

### DELETE /profile

**Назначение:** очистить профиль текущего пользователя (аналог `clear_user_profile`).

**Пример запроса:**

```http
DELETE /profile
Authorization: Bearer <token>
```

**Пример ответа:**

```json
{
  "ok": true,
  "data": {
    "deleted": true
  }
}
```

Повторный вызов может возвращать, например:

```json
{
  "ok": true,
  "data": {
    "deleted": false
  }
}
```

---

## Эндпоинты раскладов (spreads)

Эти эндпоинты работают с историей и детальной информацией по раскладам пользователя.

### GET /spreads?page=1&limit=10

**Назначение:** вернуть историю раскладов текущего пользователя с пагинацией.

**Параметры query:**

* `page` — номер страницы (1-based), по умолчанию `1`.
* `limit` — количество элементов на странице, по умолчанию `10`, максимум (например) `50`.

**Пример запроса:**

```http
GET /spreads?page=1&limit=10
Authorization: Bearer <token>
```

**Пример успешного ответа:**

```json
{
  "ok": true,
  "data": {
    "items": [
      {
        "id": 42,
        "spread_type": "single",
        "category": "love",
        "created_at": "2025-11-21T12:34:56Z",
        "short_preview": "Краткое описание...",
        "has_questions": true
      }
    ],
    "page": 1,
    "total_pages": 3,
    "total_items": 15
  }
}
```

Если раскладов нет:

```json
{
  "ok": true,
  "data": {
    "items": [],
    "page": 1,
    "total_pages": 0,
    "total_items": 0
  }
}
```

### GET /spreads/{id}

**Назначение:** вернуть детальную информацию по одному раскладу текущего пользователя.

* Если расклад не найден — `not_found`.
* Если расклад принадлежит другому пользователю — `forbidden`.

**Пример запроса:**

```http
GET /spreads/42
Authorization: Bearer <token>
```

**Пример успешного ответа:**

```json
{
  "ok": true,
  "data": {
    "id": 42,
    "spread_type": "three",
    "category": "career",
    "created_at": "2025-11-21T12:34:56Z",
    "cards": [
      {
        "position": 1,
        "name": "Башня",
        "is_reversed": false
      },
      {
        "position": 2,
        "name": "Солнце",
        "is_reversed": true
      },
      {
        "position": 3,
        "name": "Императрица",
        "is_reversed": false
      }
    ],
    "interpretation": "Полный текст интерпретации расклада...",
    "questions": [
      {
        "id": 10,
        "question": "Что будет если...",
        "answer": "AI-ответ или null, если ещё в процессе",
        "status": "ready",
        "created_at": "2025-11-21T13:00:00Z",
        "answered_at": "2025-11-21T13:05:00Z"
      }
    ]
  }
}
```

* `cards` — массив карт:

  * `position` — порядковый номер позиции в раскладе (1, 2, 3, ...).
  * `name` — название карты.
  * `is_reversed` — `true`, если карта в перевёрнутой позиции.

* `questions` — массив вопросов к этому раскладу:

  * `status` ∈ `"pending" | "ready" | "failed"`.

### POST /spreads

**Назначение:** создать новый расклад.

**Входной JSON (общий):**

```json
{
  "spread_type": "three",
  "category": "love",
  "question": "Мой текстовый вопрос",
  "mode": "auto"
}
```

* `spread_type` — обязательное поле (например, `"single"`, `"three"` и т.п.).
* `category` — обязательное поле (одна из заранее определённых категорий).
* `question` — опциональное поле (основной вопрос к раскладу).
* `mode` — `"auto"` или `"interactive"`. По умолчанию можно считать `"auto"`.

#### Ответ для mode = "auto"

Сервер автоматически:

* выбирает карты;
* запускает генерацию интерпретации;
* создаёт запись расклада в БД.

**Пример запроса:**

```http
POST /spreads
Authorization: Bearer <token>
Content-Type: application/json
```

```json
{
  "spread_type": "three",
  "category": "love",
  "question": "Как будут развиваться отношения?",
  "mode": "auto"
}
```

**Пример успешного ответа (интерпретация готова сразу):**

```json
{
  "ok": true,
  "data": {
    "id": 43,
    "status": "ready",
    "spread_type": "three",
    "category": "love",
    "created_at": "2025-11-21T12:40:00Z",
    "cards": [
      {
        "position": 1,
        "name": "Башня",
        "is_reversed": false
      },
      {
        "position": 2,
        "name": "Солнце",
        "is_reversed": true
      },
      {
        "position": 3,
        "name": "Императрица",
        "is_reversed": false
      }
    ],
    "interpretation": "Готовая интерпретация расклада..."
  }
}
```

**Пример успешного ответа (интерпретация ещё генерируется):**

```json
{
  "ok": true,
  "data": {
    "id": 43,
    "status": "pending",
    "spread_type": "three",
    "category": "love",
    "created_at": "2025-11-21T12:40:00Z",
    "cards": [
      {
        "position": 1,
        "name": "Башня",
        "is_reversed": false
      },
      {
        "position": 2,
        "name": "Солнце",
        "is_reversed": true
      },
      {
        "position": 3,
        "name": "Императрица",
        "is_reversed": false
      }
    ],
    "interpretation": null
  }
}
```

Фронт может:

* либо периодически опрашивать `GET /spreads/{id}`,
* либо ждать пуш-сообщение от Telegram-бота.

#### Ответ для mode = "interactive"

В интерактивном режиме расклад создаётся через сессию выбора карт.

**Пример запроса:**

```http
POST /spreads
Authorization: Bearer <token>
Content-Type: application/json
```

```json
{
  "spread_type": "three",
  "category": "love",
  "mode": "interactive"
}
```

**Пример ответа:**

```json
{
  "ok": true,
  "data": {
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "awaiting_selection",
    "spread_type": "three",
    "category": "love",
    "total_positions": 3,
    "selected_cards": {}
  }
}
```

* `session_id` — идентификатор интерактивной сессии выбора карт.
* `total_positions` — количество карт в раскладе.
* `selected_cards` — объект вида `{ "<position>": { "name": "...", "is_reversed": false }, ... }` (пока пустой).

### POST /spreads/session/{session_id}/select_card (опционально)

**Назначение:** выбрать карту в интерактивной сессии.

**Входной JSON:**

```json
{
  "position": 1,
  "choice_index": 3
}
```

* `position` — номер позиции в раскладе (1, 2, 3, ...).
* `choice_index` — индекс выбранной карты из набора предложенных вариантов (внутренняя логика).

**Пример промежуточного ответа (ещё есть позиции для выбора):**

```json
{
  "ok": true,
  "data": {
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "awaiting_selection",
    "spread_type": "three",
    "category": "love",
    "total_positions": 3,
    "selected_cards": {
      "1": {
        "name": "Башня",
        "is_reversed": false
      }
    }
  }
}
```

**Пример финального ответа (после выбора последней карты):**

```json
{
  "ok": true,
  "data": {
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "completed",
    "spread_id": 44,
    "spread_type": "three",
    "category": "love",
    "cards": [
      {
        "position": 1,
        "name": "Башня",
        "is_reversed": false
      },
      {
        "position": 2,
        "name": "Солнце",
        "is_reversed": true
      },
      {
        "position": 3,
        "name": "Императрица",
        "is_reversed": false
      }
    ],
    "interpretation": "Полный текст интерпретации расклада..."
  }
}
```

* `spread_id` — идентификатор финального расклада, с которым затем работают эндпоинты `/spreads/{id}` и `/spreads/{id}/questions`.

---

## Эндпоинты вопросов к раскладам (questions)

Вопросы всегда привязаны к конкретному раскладу (`spread_id`).
AI-ответ генерируется асинхронно фоновым воркером.

Статус вопроса:

* `"pending"` — ответ в процессе генерации;
* `"ready"` — ответ успешно сгенерирован;
* `"failed"` — при генерации произошла ошибка.

### POST /spreads/{id}/questions

**Назначение:** создать новый вопрос к раскладу с идентификатором `{id}`.

**Входной JSON:**

```json
{
  "question": "Текст вопроса"
}
```

* Можно задать минимальную длину вопроса (например, ≥ 10 символов).

**Пример успешного ответа:**

```json
{
  "ok": true,
  "data": {
    "id": 101,
    "spread_id": 42,
    "question": "Текст вопроса",
    "answer": null,
    "status": "pending",
    "created_at": "2025-11-21T13:10:00Z",
    "answered_at": null
  }
}
```

**Пример ошибки валидации (слишком короткий вопрос):**

```json
{
  "ok": false,
  "error": {
    "code": "validation_error",
    "message": "Поле question слишком короткое",
    "details": {
      "field": "question",
      "min_length": 10,
      "value_length": 5
    }
  }
}
```

### GET /spreads/{id}/questions

**Назначение:** вернуть список всех вопросов по раскладу `{id}` текущего пользователя.

**Пример запроса:**

```http
GET /spreads/42/questions
Authorization: Bearer <token>
```

**Пример успешного ответа:**

```json
{
  "ok": true,
  "data": {
    "items": [
      {
        "id": 101,
        "spread_id": 42,
        "question": "Текст вопроса",
        "answer": "Готовый AI-ответ",
        "status": "ready",
        "created_at": "2025-11-21T13:10:00Z",
        "answered_at": "2025-11-21T13:12:00Z"
      },
      {
        "id": 102,
        "spread_id": 42,
        "question": "Ещё один вопрос",
        "answer": null,
        "status": "pending",
        "created_at": "2025-11-21T13:15:00Z",
        "answered_at": null
      }
    ]
  }
}
```

### GET /questions/{question_id}

**Назначение:** вернуть один конкретный вопрос и его ответ (для детального просмотра/обновления статуса на фронте).

**Пример запроса:**

```http
GET /questions/101
Authorization: Bearer <token>
```

**Пример успешного ответа:**

```json
{
  "ok": true,
  "data": {
    "id": 101,
    "spread_id": 42,
    "question": "Текст вопроса",
    "answer": "Готовый AI-ответ",
    "status": "ready",
    "created_at": "2025-11-21T13:10:00Z",
    "answered_at": "2025-11-21T13:12:00Z"
  }
}
```

Если вопрос не найден:

```json
{
  "ok": false,
  "error": {
    "code": "not_found",
    "message": "Question not found",
    "details": {
      "question_id": 999
    }
  }
}
```

Если вопрос принадлежит другому пользователю:

```json
{
  "ok": false,
  "error": {
    "code": "forbidden",
    "message": "Access to this question is forbidden",
    "details": {
      "question_id": 101
    }
  }
}
```

---

## Примеры последовательностей (use-cases)

### 1. Открыть приложение и посмотреть историю раскладов

1. **Получить initData на фронте**

   * Mini App получает строку `Telegram.WebApp.initData`.

2. **Авторизация (JWT-режим)**

   ```http
   POST /auth/telegram
   Content-Type: application/json
   ```

   ```json
   {
     "initData": "<raw initData>"
   }
   ```

   **Ответ:**

   ```json
   {
     "ok": true,
     "data": {
       "user": {
         "id": 123456789,
         "username": "user",
         "first_name": "Имя",
         "last_name": "Фамилия"
       },
       "token": "<our_jwt_token>"
     }
   }
   ```

3. **Загрузить историю раскладов**

   ```http
   GET /spreads?page=1&limit=10
   Authorization: Bearer <our_jwt_token>
   ```

   **Ответ (фрагмент):**

   ```json
   {
     "ok": true,
     "data": {
       "items": [
         {
           "id": 42,
           "spread_type": "single",
           "category": "love",
           "created_at": "2025-11-21T12:34:56Z",
           "short_preview": "Краткое описание...",
           "has_questions": true
         }
       ],
       "page": 1,
       "total_pages": 3,
       "total_items": 15
     }
   }
   ```

4. **Посмотреть конкретный расклад**

   ```http
   GET /spreads/42
   Authorization: Bearer <our_jwt_token>
   ```

   **Ответ (фрагмент):**

   ```json
   {
     "ok": true,
     "data": {
       "id": 42,
       "spread_type": "three",
       "category": "career",
       "created_at": "2025-11-21T12:34:56Z",
       "cards": [...],
       "interpretation": "Полный текст...",
       "questions": [...]
     }
   }
   ```

---

### 2. Сделать расклад на 3 карты (mode="auto")

1. **Пользователь выбирает тип расклада и категорию**

   ```http
   POST /spreads
   Authorization: Bearer <our_jwt_token>
   Content-Type: application/json
   ```

   ```json
   {
     "spread_type": "three",
     "category": "love",
     "question": "Как будут развиваться отношения?",
     "mode": "auto"
   }
   ```

2. **Сервер создаёт расклад**

   Вариант A — интерпретация готова сразу:

   ```json
   {
     "ok": true,
     "data": {
       "id": 43,
       "status": "ready",
       "spread_type": "three",
       "category": "love",
       "created_at": "2025-11-21T12:40:00Z",
       "cards": [...],
       "interpretation": "Готовая интерпретация..."
     }
   }
   ```

   Вариант B — интерпретация генерируется асинхронно:

   ```json
   {
     "ok": true,
     "data": {
       "id": 43,
       "status": "pending",
       "spread_type": "three",
       "category": "love",
       "created_at": "2025-11-21T12:40:00Z",
       "cards": [...],
       "interpretation": null
     }
   }
   ```

3. **Поведение фронта**

   * Если `status = "ready"` — сразу показываем карты и интерпретацию.
   * Если `status = "pending"` — показываем карты и индикатор ожидания, периодически запрашиваем:

     ```http
     GET /spreads/43
     Authorization: Bearer <our_jwt_token>
     ```

---

### 3. Задать вопрос к раскладу

1. **Пользователь открывает расклад с id = 42** (через `GET /spreads/42`).

2. **Пользователь вводит текст вопроса**

   ```http
   POST /spreads/42/questions
   Authorization: Bearer <our_jwt_token>
   Content-Type: application/json
   ```

   ```json
   {
     "question": "Что будет, если я последую совету этого расклада?"
   }
   ```

3. **Сервер создаёт запись вопроса и запускает AI**

   ```json
   {
     "ok": true,
     "data": {
       "id": 101,
       "spread_id": 42,
       "question": "Что будет, если я последую совету этого расклада?",
       "answer": null,
       "status": "pending",
       "created_at": "2025-11-21T13:10:00Z",
       "answered_at": null
     }
   }
   ```

4. **Получение готового ответа**

   Вариант A — фронт опрашивает `GET /questions/{question_id}`:

   ```http
   GET /questions/101
   Authorization: Bearer <our_jwt_token>
   ```

   **Когда ответ готов:**

   ```json
   {
     "ok": true,
     "data": {
       "id": 101,
       "spread_id": 42,
       "question": "Что будет, если я последую совету этого расклада?",
       "answer": "Расширенный AI-ответ по картам расклада...",
       "status": "ready",
       "created_at": "2025-11-21T13:10:00Z",
       "answered_at": "2025-11-21T13:12:00Z"
     }
   }
   ```

   Вариант B — фронт периодически опрашивает `GET /spreads/42/questions` и обновляет список вопросов.

5. **Опционально — пуш от Telegram-бота**

   При смене статуса вопроса на `"ready"` backend может инициировать отправку сообщения пользователю от Telegram-бота (уведомление и/или ссылка на Mini App).

```
```
