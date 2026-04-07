# Сервис todos: полная инструкция для фронтенда

Один документ по работе с **todos** из **tickets-front**: личная Kanban-доска (колонки, карточки, фон) и интеграция **календаря Outlook** (Microsoft Graph). Все запросы идут в **gateway** с префиксом **`/api/v1/todos`**, не на порт микросервиса напрямую.

Общая схема env, Vite proxy, прод, CORS, `apiFetch` — **`Docs/FRONTEND_CONNECTION.md`** (или **`docs/FRONTEND_CONNECTION.md`**).

---

## Содержание

1. [Подключение и авторизация](#1-подключение-и-авторизация)  
2. [Kanban-доска: API, типы, примеры](#2-kanban-доска-api-типы-примеры)  
3. [Колонки: логика UI и сохранение порядка](#3-колонки-логика-ui-и-сохранение-порядка)  
4. [Календарь Outlook](#4-календарь-outlook)  
5. [Ошибки и отладка](#5-ошибки-и-отладка)  
6. [Код в репозитории](#6-код-в-репозитории)

---

## 1. Подключение и авторизация

| Режим | Как собирать URL |
|-------|------------------|
| **Локально (Vite)** | `apiFetch('/api/v1/todos/...')`. В `.env`: `VITE_PROXY_TARGET=http://127.0.0.1:<порт-gateway>`, **`VITE_API_BASE_URL` не задавать** (или пусто). |
| **Продакшен** | База: `https://<хост-gateway>` без `/api/v1` в переменной; в коде пути вида `'/api/v1/todos/...'`. |

**Авторизация:** заголовок **`Authorization: Bearer <access_token>`** (обычно через общий **`apiFetch`** из `@shared/api`).

На стороне сервиса `todos` пользователь определяется по токену (запрос к auth **`/users/me`**), `user_id` — целое число.

---

## 2. Kanban-доска: API, типы, примеры

### 2.1 Модель

- У каждого пользователя **одна доска**.
- Первый **`GET /api/v1/todos/board`** создаёт доску и **три колонки по умолчанию**:

| Заголовок | `color` |
|-----------|---------|
| Сегодня | `#7c3aed` |
| На этой неделе | `#2563eb` |
| Позже | `#ea580c` |

- Колонки и карточки имеют **`position`** (0…n−1). У колонки есть **`is_collapsed`** — свёрнуто ли узкое представление (сохраняется в БД). В JSON поля в **snake_case**; в телах запросов допустим **camelCase** `isCollapsed` (Pydantic).

### 2.2 Таблица эндпоинтов

| Назначение | Метод и путь |
|------------|----------------|
| Доска (создать при необходимости) | `GET /api/v1/todos/board` |
| Фон доски | `PATCH /api/v1/todos/board` |
| Новая колонка | `POST /api/v1/todos/board/columns` |
| Изменить колонку | `PATCH /api/v1/todos/board/columns/{columnId}` |
| Удалить колонку | `DELETE /api/v1/todos/board/columns/{columnId}` |
| Порядок колонок (после DnD) | `PUT /api/v1/todos/board/columns/reorder` |
| Новая карточка | `POST /api/v1/todos/board/columns/{columnId}/cards` |
| Изменить / перенести карточку | `PATCH /api/v1/todos/board/cards/{cardId}` |
| Удалить карточку | `DELETE /api/v1/todos/board/cards/{cardId}` |
| Порядок карточек в колонке | `PUT /api/v1/todos/board/columns/{columnId}/cards/reorder` |

`{columnId}` и `{cardId}` — числовые id из ответа `GET`.

### 2.3 Тела запросов

| Эндпоинт | Тело |
|----------|------|
| `PATCH /board` | `{ "background_url": "<url>" }` или `{ "background_url": null }`. Пустое тело → **400**. |
| `POST /board/columns` | `{ "title": "...", "color": "#hex", "insert_at": 0, "is_collapsed": false }` — опционально `color`, `insert_at`, **`is_collapsed`** / **`isCollapsed`**. |
| `PATCH /board/columns/{id}` | `{ "title": "..." }`, `{ "color": "#hex" }`, **`{ "is_collapsed": true }`** или **`{ "isCollapsed": false }`** — только нужные поля. |
| `PUT /board/columns/reorder` | `{ "ordered_column_ids": [2, 1, 3] }` — **полный** список id колонок в новом порядке слева направо. |
| `POST .../columns/{id}/cards` | `{ "title": "...", "body": "...", "insert_at": 0 }` — `body` и `insert_at` опционально. |
| `PATCH /board/cards/{id}` | опционально: `title`, `body`, `column_id`, `position`. |
| `PUT .../columns/{id}/cards/reorder` | `{ "ordered_card_ids": [...] }` — полный список id карточек **в этой колонке**. |

Мутации возвращают **обновлённую доску целиком** — удобно подставлять в state.

### 2.4 Типы (черновик)

```ts
interface TodoBoardCard {
  id: number
  title: string
  body: string | null
  position: number
}

interface TodoBoardColumn {
  id: number
  title: string
  position: number
  color: string
  is_collapsed: boolean
  task_count: number
  cards: TodoBoardCard[]
}

interface TodoBoard {
  id: number
  user_id: number
  background_url: string | null
  columns: TodoBoardColumn[]
}
```

Отрисовка: сортировать колонки и карточки по **`position`** по возрастанию.

### 2.5 Примеры `apiFetch`

```ts
const board = await apiFetch('/api/v1/todos/board')

await apiFetch('/api/v1/todos/board', {
  method: 'PATCH',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ background_url: 'https://example.com/bg.jpg' }),
})

await apiFetch('/api/v1/todos/board/columns/reorder', {
  method: 'PUT',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ ordered_column_ids: [3, 1, 2, 4] }),
})

await apiFetch('/api/v1/todos/board/columns', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ title: 'Бэклог', color: '#64748b' }),
})

await apiFetch(`/api/v1/todos/board/columns/${columnId}/cards`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ title: 'Задача' }),
})

// Свернуть / развернуть колонку (сохраняется на сервере)
await apiFetch(`/api/v1/todos/board/columns/${columnId}`, {
  method: 'PATCH',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ isCollapsed: true }),
})
```

---

## 3. Колонки: логика UI и сохранение порядка

### 3.1 Загрузка

Один **`GET /api/v1/todos/board`** — массив **`columns`** с полями **`id`**, **`title`**, **`color`**, **`position`**, **`is_collapsed`**, **`task_count`**, **`cards`**.

Сортируйте колонки по **`position`**; не полагайтесь только на порядок полей в JSON.

### 3.2 Добавление / переименование / удаление

- **Добавить:** `POST /board/columns` с `title`; опционально `color`, **`insert_at`**, **`is_collapsed`**.
- **Изменить:** `PATCH .../columns/{id}` — заголовок, цвет, **`is_collapsed`** (свернуть/развернуть).
- **Удалить:** `DELETE .../columns/{id}` — карточки в колонке удаляются вместе с ней.

### 3.3 Смена порядка (DnD)

Вызывайте **`PUT .../columns/reorder`** после **завершения** перетаскивания (drop / end drag), не на каждый кадр preview.

Тело:

```json
{ "ordered_column_ids": [3, 1, 2, 5] }
```

- Массив — это **`id` колонок** слева направо, как на экране.
- Длина = числу колонок; набор id = **все** колонки доски, без дубликатов и пропусков.

Сборка: после DnD превратите визуальный порядок колонок в массив их **`id`** и отправьте. Несовпадение с сервером → **400**.

После успеха обновите state из ответа или сделайте повторный `GET`.

### 3.4 Чеклист UI ↔ API

| Действие пользователя | Запрос |
|----------------------|--------|
| Открыл доску | `GET .../board` → колонки по `position` |
| Перетащил колонку | `PUT .../columns/reorder` |
| Новая колонка | `POST .../board/columns` |
| Переименовал / цвет | `PATCH .../columns/{id}` |
| Свернул / развернул колонку | `PATCH .../columns/{id}` с `is_collapsed` или `isCollapsed` |
| Удалил колонку | `DELETE .../columns/{id}` |

---

## 4. Календарь Outlook

Префикс: **`/api/v1/todos/calendar`**. Нужны OAuth Microsoft (переменные в **сервисе todos**: `MICROSOFT_CLIENT_ID`, `MICROSOFT_REDIRECT_URI` и др.; `MICROSOFT_REDIRECT_URI` должен указывать на **gateway**, например `http://localhost:1234/api/v1/todos/calendar/callback`, а не на порт Vite).

### 4.1 Подключение

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/api/v1/todos/calendar/connect` | Ответ **JSON** `{"url": "..."}` — URL входа Microsoft. **Не** следовать редиректу через `fetch` (CORS). Открыть в браузере: `window.location = data.url`. |
| `GET` | `/api/v1/todos/calendar/callback?code=...&state=...` | Callback от Microsoft (обычно редирект браузера). Обрабатывает бэкенд, редирект на фронт с query `calendar=connected` или `calendar=error`. |
| `GET` | `/api/v1/todos/calendar/status` | JSON `{"connected": true\|false}` — подключён ли календарь. |

На gateway для этих путей есть **явные** маршруты (до общего прокси), чтобы всегда отдавался JSON там, где нужно.

### 4.2 События

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/api/v1/todos/calendar/events?start=...&end=...` | События Outlook за период (ISO datetime query). Ответ: `{"value": [...]}` |
| `POST` | `/api/v1/todos/calendar/events` | Создать событие. Тело: `subject`, `start`, `end`, опционально `body` (datetime в ISO). |

Без подключённого календаря — **403** `Calendar not connected`.

---

## 5. Ошибки и отладка

| Симптом | Что проверить |
|---------|----------------|
| **401** | Токен; см. **`Docs/FRONTEND_CONNECTION.md`**. |
| **400** на `reorder` | `ordered_column_ids` не совпадает с колонками на сервере. |
| **403** на calendar | Календарь не подключён. |
| **503** | Не настроен **`TODOS_SERVICE_URL`** на gateway или сервис todos недоступен. |
| **503** на `/calendar/connect` | Не заданы OAuth-переменные в сервисе todos. |

Остальные пути **`/api/v1/todos/*`** на gateway проксируются в сервис **todos** с тем же методом и телом.

---

## 6. Код в репозитории

| Путь | Содержание |
|------|------------|
| `todos/presentation/routes/board_routes.py` | Kanban API |
| `todos/presentation/routes/calendar_routes.py` | Outlook: connect, callback, status, events |
| `todos/presentation/dependencies.py` | `get_current_user_id` (Bearer → auth) |
| `gateway/presentation/routes/todos_routes.py` | Прокси + явные маршруты calendar |

Каноничный текст: **`docs/FRONTEND_TODOS.md`**.

Старые раздельные файлы (`FRONTEND_TODOS_BOARD*.md`) сведены сюда: используйте **только этот документ** как источник правды по todos для фронта.
