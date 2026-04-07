# Сервис todos: полная инструкция для фронтенда

Один документ по работе с **todos** из **tickets-front**: личная Kanban-доска (колонки, карточки, фон) и интеграция **календаря Outlook** (Microsoft Graph). Все запросы идут в **gateway** с префиксом **`/api/v1/todos`**, не на порт микросервиса напрямую.

**Общая инструкция по микросервису (запуск, env, БД, gateway):** **`docs/TODOS.md`**.

Общая схема env, Vite proxy, прод, CORS, `apiFetch` — **`docs/FRONTEND_CONNECTION.md`**.

---

## Содержание

0. [Чеклист: что сделать на фронте](#0-чеклист-что-сделать-на-фронте) (в т.ч. §0.6 — 503, §0.8 — консоль и `response.ok`)  
1. [Подключение и авторизация](#1-подключение-и-авторизация)  
2. [Kanban-доска: API, типы, примеры](#2-kanban-доска-api-типы-примеры)  
3. [Колонки: логика UI и сохранение порядка](#3-колонки-логика-ui-и-сохранение-порядка)  
4. [Календарь Outlook](#4-календарь-outlook)  
5. [Ошибки и отладка](#5-ошибки-и-отладка)  
6. [Код в репозитории](#6-код-в-репозитории)

---

## 0. Чеклист: что сделать на фронте

Репозиторий UI: **tickets-front**. Все шаги ниже — в нём (или в общем `@shared/api`).

### 0.1 Окружение и базовый URL

1. **Локально:** в `.env` / `.env.local` задайте **`VITE_PROXY_TARGET=http://127.0.0.1:<порт-gateway>`** (часто `1234`). **`VITE_API_BASE_URL` не задавайте** (пусто) — запросы пойдут через прокси Vite на gateway (см. **`docs/FRONTEND_CONNECTION.md`**).
2. **Продакшен:** в сборке задайте **`VITE_API_BASE_URL=https://ticketsback.kostalegal.com`** (только origin, **без** `/api/v1`).
3. Убедитесь, что **`apiFetch`** подставляет **`Authorization: Bearer`** из вашего хранилища токена (как для остальных модулей).

### 0.2 Первый экран Kanban

1. При входе на страницу todos вызовите **`GET /api/v1/todos/board`** через `apiFetch('/api/v1/todos/board')`.
2. Положите ответ в state (React Query / Zustand / контекст — как принято в проекте).
3. Отрисуйте **`columns`** по **`position`**, внутри колонки — **`cards`** по **`position`**.
4. Используйте из ответа **`board_labels`** для выбора/создания меток; у каждой **карточки** — **`labels`**, **`checklist`**, **`participant_user_ids`**, **`attachments`**, **`comments`**, **`due_at`**, **`is_completed`**; у **колонки** — **`is_collapsed`**, **`task_count`** и т.д. (типы — [§2.4](#24-типы-ответ-get-board)).

### 0.3 Мутации (сохранение на сервере)

1. После **любой** успешной мутации бэкенд возвращает **доску целиком** — проще всего **заменить state** ответом (не клеить вручную).
2. **Колонки:** создание / переименование / цвет / **`PATCH` с `isCollapsed`** для свёрнутой колонки; **`PUT .../columns/reorder`** после DnD колонок.
3. **Карточки:** **`POST .../columns/{id}/cards`**, **`PATCH .../cards/{id}`** (перенос: `columnId` + `position`), **`PUT .../columns/{id}/cards/reorder`** после DnD внутри колонки.
4. **Метки доски:** `POST/PATCH/DELETE .../board/labels`; на карточке — **`PATCH` с `labelIds`** (полный список id меток с доски).
5. **Чеклист / вложения / комментарии** — отдельные эндпоинты из [таблицы §2.2](#22-таблица-эндпоинтов); после каждого — снова полная доска в ответе.

### 0.4 Вложения и картинки

1. Загрузка: **`POST .../cards/{cardId}/attachments`**, тело **`multipart/form-data`**, поле файла **`file`**, размер до **15 МБ**.
2. Ссылка для скачивания/превью: **`attachment.media_url`** — путь вида `/api/v1/media/...`; для `<img>` или `fetch` используйте **тот же origin**, что и API, и **Bearer** (если открываете через `fetch`, не через публичный URL без токена).

### 0.5 Календарь Outlook (если нужен на странице)

1. **`GET /api/v1/todos/calendar/status`** — показать, подключён ли календарь.
2. Подключение: **`GET /api/v1/todos/calendar/connect`** → в ответе **`{ url }`** — **не** `fetch` редиректом; открыть **`window.location.href = url`** (см. §4).
3. События: **`GET/POST .../calendar/events`** по документации ниже.

### 0.6 Ошибки и 503

1. **401** — обработать как в остальном приложении (обновление токена / редирект на логин).
2. **503** на **`/api/v1/todos/...`** (в т.ч. **`.../board`**, **`.../calendar/status`**) — это **не баг фронтенда**: gateway не получил ответ от микросервиса **todos** или не настроен прокси. На UI достаточно нейтрального текста («Сервис временно недоступен»); разбор — у DevOps.

   В теле JSON ответа gateway обычно различают:

   | `detail` (типично) | Смысл |
   |--------------------|--------|
   | **`TODOS_SERVICE_URL not configured`** | У контейнера **gateway** пустая или не задана переменная **`TODOS_SERVICE_URL`**. |
   | **`Todos service unavailable`** | URL задан, но до сервиса todos **нет соединения** (выключен, неверный хост/порт, другая Docker-сеть и т.д.). В ответе может быть поле **`hint`** с подсказкой. |

   **Диагностика без токена:** **`GET https://<gateway>/health/todos`** (на том же origin, что и API). Эндпоинт на gateway проверяет наличие **`TODOS_SERVICE_URL`** и делает **`GET {TODOS_SERVICE_URL}/health`** к todos; при проблемах отдаёт **503** с пояснением (например **`Todos unreachable from gateway`**, если TCP не установился). Подробный чеклист деплоя: **`docs/TODOS.md`**, раздел **«Gateway»**; для разработчиков SPA — **`docs/FRONTEND_CONNECTION.md`** (подраздел про todos и 503).

### 0.7 CORS

Origin фронта должен быть разрешён в **gateway** (**`FRONTEND_URL`** и т.д.). Если 403/ CORS только у todos — сверьте с **`docs/FRONTEND_CONNECTION.md`**.

### 0.8 Консоль браузера: 503, `content.js` и разбор `fetch`

**503 на** `.../api/v1/todos/board` или `.../calendar/status` **не лечится кодом в tickets-back на фронте** — запрос обрабатывает **gateway**; ответ означает отсутствие или недоступность сервиса **todos** за gateway (см. **§0.6**, **`docs/TODOS.md`** → Gateway).

**Стек вроде `content.js`** в DevTools чаще всего идёт от **расширения браузера** (перехват страницы), а не от вашего бандла. Для изоляции проверьте в окне инкогнито без расширений или другой профиль.

**На фронте:** не вызывайте **`response.json()`** и не разбирайте тело как успешные **`data`**, пока не убедились, что запрос успешен (**`response.ok`** или **`response.status === 200`** для ожидаемого сценария). После **503** тело часто JSON с полем **`detail`**, но если ваш код всегда ожидает форму «доски» и без проверки статуса лезет в поля ответа — получите **`TypeError`** (это уже ошибка обработчика на клиенте, а не «магия» API).

Пример: один раз прочитать тело как текст, затем разобрать JSON:

```ts
async function loadBoard(token: string) {
  const res = await fetch('/api/v1/todos/board', {
    headers: { Authorization: `Bearer ${token}` },
  })
  const text = await res.text()
  if (!res.ok) {
    let msg = `HTTP ${res.status}`
    try {
      const err = JSON.parse(text) as { detail?: unknown }
      if (typeof err.detail === 'string') msg = err.detail
    } catch {
      /* тело не JSON */
    }
    throw new Error(msg)
  }
  return JSON.parse(text) as /* ваш тип доски */
}
```

Если используете обёртку вроде **`apiFetch`**, реализуйте там же проверку **`res.ok`** до разбора тела или возвращайте **`Response`**, чтобы вызывающий код явно обрабатывал ошибки.

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

- Колонки и карточки имеют **`position`** (0…n−1). У колонки есть **`is_collapsed`** — свёрнуто ли узкое представление (сохраняется в БД). В JSON ответа поля в **snake_case**; в телах запросов допустим **camelCase** (например `isCollapsed`, `labelIds`, `participantUserIds`) — Pydantic принимает оба варианта.

### 2.2 Таблица эндпоинтов

| Назначение | Метод и путь |
|------------|----------------|
| Доска (создать при необходимости) | `GET /api/v1/todos/board` |
| Фон доски | `PATCH /api/v1/todos/board` |
| Метки доски (справочник для карточек) | `POST/ PATCH/ DELETE /api/v1/todos/board/labels` и `.../labels/{labelId}` |
| Новая колонка | `POST /api/v1/todos/board/columns` |
| Изменить колонку | `PATCH /api/v1/todos/board/columns/{columnId}` |
| Удалить колонку | `DELETE /api/v1/todos/board/columns/{columnId}` |
| Порядок колонок (после DnD) | `PUT /api/v1/todos/board/columns/reorder` |
| Новая карточка | `POST /api/v1/todos/board/columns/{columnId}/cards` |
| Изменить / перенести карточку | `PATCH /api/v1/todos/board/cards/{cardId}` |
| Удалить карточку | `DELETE /api/v1/todos/board/cards/{cardId}` |
| Порядок карточек в колонке | `PUT /api/v1/todos/board/columns/{columnId}/cards/reorder` |
| Чеклист | `POST .../cards/{cardId}/checklist/items`, `PATCH .../items/{itemId}`, `DELETE .../items/{itemId}`, `PUT .../cards/{cardId}/checklist/reorder` |
| Вложение файла (до **15 МБ**) | `POST .../cards/{cardId}/attachments` — `multipart/form-data`, поле `file` |
| Удалить вложение | `DELETE .../cards/{cardId}/attachments/{attachmentId}` |
| Комментарий | `POST .../cards/{cardId}/comments` — JSON `{ "body": "..." }` |

`{columnId}` и `{cardId}` — числовые id из ответа `GET`.

**Вложения:** после загрузки в ответе карточки есть **`media_url`** вида `/api/v1/media/<storage_key>`. Открывайте с **Bearer** тем же `apiFetch`, что и для API (как в других сервисах с вложениями). На сервисе **todos** задайте **`MEDIA_PATH`** (общий том с **gateway**, как в `FRONTEND_CONNECTION` для фонов).

### 2.3 Тела запросов

| Эндпоинт | Тело |
|----------|------|
| `PATCH /board` | `{ "background_url": "<url>" }` или `{ "background_url": null }`. Пустое тело → **400**. |
| `POST /board/labels` | `{ "title": "...", "color": "#hex" }` |
| `PATCH /board/labels/{id}` | `{ "title": "..." }`, `{ "color": "#hex" }` |
| `POST /board/columns` | `{ "title": "...", "color": "#hex", "insert_at": 0, "is_collapsed": false }` — опционально `color`, `insert_at`, **`is_collapsed`** / **`isCollapsed`**. |
| `PATCH /board/columns/{id}` | `{ "title": "..." }`, `{ "color": "#hex" }`, **`{ "is_collapsed": true }`** или **`{ "isCollapsed": false }`** — только нужные поля. |
| `PUT /board/columns/reorder` | `{ "ordered_column_ids": [2, 1, 3] }` — **полный** список id колонок в новом порядке слева направо. |
| `POST .../columns/{id}/cards` | `{ "title": "...", "body": "...", "insert_at": 0, "due_at": "<ISO8601>" }` — опционально `body`, `insert_at`, **`due_at`** / **`dueAt`** (дедлайн). |
| `PATCH /board/cards/{id}` | опционально: `title`, `body`, **`column_id` / `columnId`**, `position`, **`due_at` / `dueAt`**, **`is_completed` / `isCompleted`**, **`is_archived` / `isArchived`**, **`label_ids` / `labelIds`** (полная замена набора меток на карточке), **`participant_user_ids` / `participantUserIds`** (полная замена участников). |
| `PUT .../columns/{id}/cards/reorder` | `{ "ordered_card_ids": [...] }` — полный список id карточек **в этой колонке** (без архивных). |
| `POST .../checklist/items` | `{ "title": "...", "insert_at": 0 }` |
| `PATCH .../checklist/items/{itemId}` | `{ "title": "..." }`, `{ "is_done": true }` / **`isDone`** |
| `PUT .../checklist/reorder` | `{ "orderedItemIds": [1, 2, 3] }` — полный список id пунктов в чеклисте |

Мутации возвращают **обновлённую доску целиком** — удобно подставлять в state.

### 2.4 Типы (ответ `GET /board`)

```ts
interface TodoBoardLabel {
  id: number
  title: string
  color: string
  position: number
}

interface TodoBoardCardLabel {
  id: number
  title: string
  color: string
}

interface TodoChecklistItem {
  id: number
  title: string
  is_done: boolean
  position: number
}

interface TodoCardAttachment {
  id: number
  original_filename: string
  mime_type: string | null
  size_bytes: number
  media_url: string // GET /api/v1/media/... с Bearer
}

interface TodoCardComment {
  id: number
  user_id: number
  body: string
  created_at: string // ISO
}

interface TodoBoardCard {
  id: number
  title: string
  body: string | null
  position: number
  due_at: string | null // ISO
  is_completed: boolean
  is_archived: boolean
  labels: TodoBoardCardLabel[]
  checklist: TodoChecklistItem[]
  participant_user_ids: number[]
  attachments: TodoCardAttachment[]
  comments: TodoCardComment[]
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
  board_labels: TodoBoardLabel[]
  columns: TodoBoardColumn[]
}
```

Отрисовка: сортировать колонки и карточки по **`position`** по возрастанию. **Архивные** карточки (`is_archived: true`) в колонках **не** встречаются — в списке колонки только активные карточки; архивирование через `PATCH` с `is_archived: true`.

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

Один **`GET /api/v1/todos/board`** — **`board_labels`** (справочник меток доски), массив **`columns`** с полями **`id`**, **`title`**, **`color`**, **`position`**, **`is_collapsed`**, **`task_count`**, **`cards`**. У каждой карточки — расширенные поля (дедлайн, метки, чеклист, участники, вложения, комментарии).

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
| **401** | Токен; см. **`docs/FRONTEND_CONNECTION.md`**. |
| **400** на `reorder` | `ordered_column_ids` не совпадает с колонками на сервере. |
| **400** на `PATCH .../cards` | Неверные **`label_ids`** / **`labelIds`** (метка не с этой доски). |
| **413** на загрузку вложения | Файл больше **15 МБ** (лимит сервиса `todos`, `max_upload_mb`). |
| **403** на calendar | Календарь не подключён. |
| **503** на **`/api/v1/todos/board`**, **`.../calendar/status`** и др. | Не ошибка SPA: см. **§0.6 «Ошибки и 503»** выше и **`docs/TODOS.md`** → **Gateway**. Кратко: пустой **`TODOS_SERVICE_URL`** у gateway (`detail`: **`TODOS_SERVICE_URL not configured`**) или todos недоступен по сети (`detail`: **`Todos service unavailable`** на прокси). |
| **503** на **`GET /health/todos`** (gateway) | Та же линия диагностики: не задан URL, либо **`Todos unreachable from gateway`** / **`Todos /health not OK`** — смотрите JSON тела. |
| **503** на `/calendar/connect` | Часто те же причины, что выше (todos недоступен); отдельно — не заданы OAuth-переменные в сервисе todos. |
| **`TypeError`** после запроса к todos, стек **`content.js`** | Часто: разбор ответа без проверки **`response.ok`** (тело при **503** — не доска); или шум от **расширения браузера** — см. **§0.8**. |

Остальные пути **`/api/v1/todos/*`** на gateway проксируются в сервис **todos** с тем же методом и телом.

---

## 6. Код в репозитории

### Backend (`tickets-back`)

| Путь | Содержание |
|------|------------|
| `todos/presentation/routes/board_routes.py` | Kanban API |
| `todos/presentation/routes/calendar_routes.py` | Outlook: connect, callback, status, events |
| `todos/presentation/dependencies.py` | `get_current_user_id` (Bearer → auth) |
| `gateway/presentation/routes/todos_routes.py` | Прокси `/api/v1/todos/*` + явные маршруты calendar |
| `gateway/presentation/routes/health.py` | В т.ч. **`GET /health/todos`** — проверка связи gateway → todos |

### Frontend (`tickets-front`)

| Путь | Содержание |
|------|------------|
| `src/pages/todo/api/boardApi.ts` | Доска, колонки, карточки, метки, чеклист, вложения, комментарии |
| `src/pages/todo/services/calendarApi.ts` | Календарь: status, connect, events |
| `src/pages/todo/services/boardMapper.ts` | Разбор `GET /board` → state UI |
| `docs/FRONTEND_CONNECTION.md` | Proxy, прод, **503 на todos** |

- **Фронтенд (описание API):** **`docs/FRONTEND_TODOS.md`** (этот файл).
- **Сервис целиком (запуск, env, БД, gateway):** **`docs/TODOS.md`**.

Старые раздельные файлы (`FRONTEND_TODOS_BOARD*.md`) сведены сюда: для UI используйте **`FRONTEND_TODOS.md`** как источник правды по API.
