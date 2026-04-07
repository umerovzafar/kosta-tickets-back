# Подключение Kanban-доски (todos) к фронтенду

Инструкция для **tickets-front**: как ходить к API личной доски (колонки, карточки, фон, порядок). Общая схема gateway, env и `apiFetch` — в **`Docs/FRONTEND_CONNECTION.md`** (или **`docs/FRONTEND_CONNECTION.md`**).

---

## 1. Куда слать запросы

| Режим | Как собирать URL |
|-------|------------------|
| **Локально (Vite)** | Относительные пути: `apiFetch('/api/v1/todos/board')`. В `.env`: `VITE_PROXY_TARGET=http://127.0.0.1:<порт-gateway>`, **`VITE_API_BASE_URL` не задавать** (или пусто). |
| **Продакшен** | База: `https://<хост-gateway>` **без** `/api/v1` в переменной; в коде — `'/api/v1/todos/...'`. |

Все запросы идут в **gateway**, не на порт сервиса `todos` напрямую.

**Префикс раздела:** `/api/v1/todos/board`

**Авторизация:** заголовок **`Authorization: Bearer <access_token>`** (как в остальном приложении — удобно через общий **`apiFetch`** из `@shared/api`).

---

## 2. Модель данных

- У каждого пользователя **одна доска** (`user_id` на стороне API определяется по токену).
- При **первом** `GET /api/v1/todos/board` создаётся доска и **три колонки по умолчанию** (как на макете):

  | Заголовок | Цвет (`color`) |
  |-----------|----------------|
  | Сегодня | `#7c3aed` |
  | На этой неделе | `#2563eb` |
  | Позже | `#ea580c` |

- У колонки есть **`position`** (0…n−1) — порядок слева направо; после drag-and-drop отправляйте **`PUT .../columns/reorder`**.
- У карточки в колонке тоже **`position`**; для смены порядка — **`PUT .../columns/{id}/cards/reorder`** или **`PATCH .../cards/{id}`** с `column_id` / `position`.

Поля в JSON — **snake_case** (`background_url`, `ordered_column_ids`, `task_count`, …).

---

## 3. Эндпоинты

Замените `{columnId}` и `{cardId}` на числовые id из ответа `GET`.

| Назначение | Метод и путь |
|------------|----------------|
| Получить доску (при отсутствии — создать с колонками по умолчанию) | `GET /api/v1/todos/board` |
| Фон (URL картинки или сброс) | `PATCH /api/v1/todos/board` |
| Добавить колонку | `POST /api/v1/todos/board/columns` |
| Переименовать / цвет колонки | `PATCH /api/v1/todos/board/columns/{columnId}` |
| Удалить колонку | `DELETE /api/v1/todos/board/columns/{columnId}` |
| **Сохранить порядок колонок** (после DnD) | `PUT /api/v1/todos/board/columns/reorder` |
| Добавить карточку | `POST /api/v1/todos/board/columns/{columnId}/cards` |
| Изменить / перенести карточку | `PATCH /api/v1/todos/board/cards/{cardId}` |
| Удалить карточку | `DELETE /api/v1/todos/board/cards/{cardId}` |
| Порядок карточек в колонке | `PUT /api/v1/todos/board/columns/{columnId}/cards/reorder` |

---

## 4. Тела запросов (кратко)

| Эндпоинт | Тело JSON |
|----------|-----------|
| `PATCH /board` | `{ "background_url": "https://..." }` или `{ "background_url": null }` — пустое тело → **400**. |
| `POST /board/columns` | `{ "title": "...", "color": "#hex", "insert_at": 0 }` — `color` и `insert_at` опционально. |
| `PATCH /board/columns/{id}` | `{ "title": "..." }` и/или `{ "color": "#hex" }` |
| `PUT /board/columns/reorder` | `{ "ordered_column_ids": [2, 1, 3] }` — **полный** список id колонок в новом порядке. |
| `POST .../columns/{id}/cards` | `{ "title": "...", "body": "...", "insert_at": 0 }` — `body` и `insert_at` опционально. |
| `PATCH /board/cards/{id}` | опционально: `title`, `body`, `column_id`, `position`. |
| `PUT .../columns/{id}/cards/reorder` | `{ "ordered_card_ids": [10, 11, 12] }` — полный список id карточек **в этой колонке**. |

---

## 5. Ответ `GET /api/v1/todos/board` (черновик типов)

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

Сортировка колонок и карточек на UI: по возрастанию **`position`**.

---

## 6. Примеры (TypeScript)

Предполагается **`apiFetch(url, options)`** с подстановкой Bearer.

### Загрузить доску

```ts
const board = await apiFetch('/api/v1/todos/board')
```

### Задать фон

```ts
await apiFetch('/api/v1/todos/board', {
  method: 'PATCH',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    background_url: 'https://example.com/bg.jpg',
  }),
})
```

### После перетаскивания колонок

```ts
const newOrder = [3, 1, 2, 4]
await apiFetch('/api/v1/todos/board/columns/reorder', {
  method: 'PUT',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ ordered_column_ids: newOrder }),
})
```

### Новая колонка

```ts
await apiFetch('/api/v1/todos/board/columns', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    title: 'Бэклог',
    color: '#64748b',
  }),
})
```

### Карточка в колонке

```ts
await apiFetch(`/api/v1/todos/board/columns/${columnId}/cards`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ title: 'Задача' }),
})
```

---

## 7. Ошибки и отладка

| Симптом | Что проверить |
|---------|----------------|
| **401** | Нет или просрочен токен; см. **`Docs/FRONTEND_CONNECTION.md`**. |
| **400** на `reorder` | Список id не совпадает с колонками доски. |
| **404** на колонку/карточку | Чужой `id` или уже удалено. |
| **503** | Не настроен `TODOS_SERVICE_URL` на gateway или сервис todos недоступен. |

---

## 8. Связанные файлы в репозитории

| Файл | Содержание |
|------|------------|
| `Docs/FRONTEND_CONNECTION.md` | Env, Vite proxy, прод, CORS, `apiFetch` |
| `Docs/FRONTEND_TODOS_BOARD.md` | Краткая таблица эндпоинтов |
| `todos/presentation/routes/board_routes.py` | Реализация API |

Каноничный текст: **`docs/FRONTEND_TODOS_BOARD_CONNECTION.md`**.
