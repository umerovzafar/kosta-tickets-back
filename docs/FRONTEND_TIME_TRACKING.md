# Подключение фронта к учёту времени (Time Tracking)

Единая точка входа для интеграции UI с **gateway** и сервисом учёта времени. Базовый префикс API: **`/api/v1`**. Все запросы — с заголовком:

```http
Authorization: Bearer <access_token>
```

При недоступности сервиса TT gateway отвечает **503**.

---

## 1. Два префикса URL (эквивалентны)

| Вариант | Пример |
|--------|--------|
| A | `/api/v1/time-tracking/...` |
| B | `/api/v1/users/...` (часть путей зеркалирует TT, см. gateway) |

Используйте один стиль в проекте; nginx может проксировать только один из вариантов.

---

## 2. Пользователь в учёте времени

Перед ставками, записями времени и доступом к проектам пользователь должен быть в БД TT.

- **POST** `/api/v1/time-tracking/users`  
  Тело: см. регламент синхронизации (поля вроде `authUserId`, `email`, …).  
  На gateway обычно нужна роль управления TT; детали — в коде gateway.

Если пользователя нет, операции с записями времени могут вернуть **404** («Пользователь не найден») — фронту имеет смысл вызывать upsert до первой записи.

---

## 3. Доступ к проектам (project access)

Менеджер/админ задаёт, **на какие проекты** сотрудник может списывать время.

| Метод | Путь |
|--------|------|
| GET | `/api/v1/time-tracking/users/{authUserId}/project-access` |
| PUT | `/api/v1/time-tracking/users/{authUserId}/project-access` |

**GET** — ответ:

```json
{ "projectIds": ["uuid-1", "uuid-2"] }
```

**PUT** — полная замена списка (пустой массив = ни один проект недоступен для выбора при списании):

```json
{ "projectIds": ["uuid-1", "uuid-2"] }
```

Поле `grantedByAuthUserId` **не отправлять** — подставляет gateway.

**Права (кратко):**

- **GET**: свой список; чужой — офис/админы или **manager** в TT.
- **PUT**: Главный администратор / Администратор / Партнер или **manager** в TT.

Подробнее по правам и ошибкам: см. также `docs/time-tracking-project-access-frontend.md`.

---

## 4. Записи времени (time entries)

Контракт тел и полей согласован с `tickets-front/BACKEND_TIME_ENTRIES.md`.

| Метод | Путь | Query / тело |
|--------|------|----------------|
| GET | `/api/v1/time-tracking/users/{authUserId}/time-entries` | `from=YYYY-MM-DD`, `to=YYYY-MM-DD` |
| POST | то же | JSON тело |
| PATCH | `.../time-entries/{entryId}` | JSON тело (частичное) |
| DELETE | `.../time-entries/{entryId}` | — |

**Тело POST / PATCH (как шлёт фронт, camelCase):**

| Поле | Описание |
|------|-----------|
| `workDate` | Дата `YYYY-MM-DD` |
| `hours` | Часы (number или string) |
| `isBillable` | boolean, по умолчанию true |
| `projectId` | UUID проекта или `null` |
| `description` | строка или `null` |

Ответы — в основном **snake_case** (`project_id`, `work_date`, …), как в типе `TimeEntryRow` на фронте.

**Права на gateway:**

- **Свой** `authUserId` (совпадает с пользователем из токена): чтение и **создание/правка/удаление** своих записей — **любой** авторизованный пользователь (в том числе со `projectId` в теле).
- **Чужой** `authUserId`: просмотр — офис/роли просмотра TT или **manager** TT; изменение — админы партнёрства или **manager** TT.

**Правила на сервисе TT:**

- Непустой `projectId` → проект должен **существовать** и **не быть в архиве** (**400**).
- Проект должен входить в **project-access** пользователя (**403**).
- Пустая строка в `projectId` обрабатывается как отсутствие проекта.

Детали реализации на бэкенде: `docs/BACKEND_TIME_ENTRIES.md`.

---

## 5. Типовые сценарии UI

1. **Сотрудник ведёт учёт времени**  
   Синхронизация пользователя в TT → **GET** `project-access` для себя → ограничить выбор проекта списком `projectIds` → **POST**/**PATCH** time-entries с выбранным `projectId`.

2. **Менеджер выдаёт доступ**  
   Экран пользователя → **PUT** `project-access` с полным списком разрешённых UUID проектов.

3. **Ошибка 403 на запись с проектом**  
   Обновить **GET** `project-access` и подсказать пользователю запросить доступ у менеджера.

---

## 6. Справка в репозитории фронта

- `BACKEND_TIME_ENTRIES.md` — модель записи и валидация.
- `docs/TIME_TRACKING.md`, `src/entities/time-tracking/api.ts` — при наличии, актуальные пути и типы.

---

## 7. Код на бэкенде (для отладки)

- Gateway: `gateway/presentation/routes/time_tracking_routes.py`, `time_tracking_users_hourly_alias.py`, `time_tracking_te_proxy.py`.
- Сервис TT: `time_tracking/presentation/routes/time_entries.py`, `project_access.py`.
