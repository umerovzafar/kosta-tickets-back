# Сервис todos — инструкция

Микросервис **todos** в монорепозитории `tickets-back`: личная Kanban-доска (колонки, карточки с метками, дедлайнами, чеклистом, участниками, вложениями, комментариями) и интеграция **календаря Outlook** (Microsoft Graph). Снаружи сервис не вызывают напрямую — только через **gateway** (`TODOS_SERVICE_URL`).

| Документ | Назначение |
|----------|------------|
| **Этот файл (`docs/TODOS.md`)** | Запуск, окружение, архитектура, интеграция с gateway и медиа |
| **`docs/FRONTEND_TODOS.md`** | Полное описание API и типов для фронтенда (Kanban + календарь) |
| **`docs/FRONTEND_CONNECTION.md`** | Общая схема подключения SPA к gateway, CORS, proxy |

---

## Назначение и маршруты

- HTTP API префикс внутри сервиса: **`/api/v1/todos`** (например `GET /api/v1/todos/board`).
- На gateway внешний путь тот же: **`https://<gateway>/api/v1/todos/...`** (прокси в `gateway/presentation/routes/todos_routes.py`).
- Проверка пользователя: Bearer → `auth` **`/users/me`** (`AUTH_SERVICE_URL`).

---

## Запуск

### Docker Compose (рекомендуется)

Сервис **`todos`** в `docker-compose.yml` (порт **1240** внутри сети). Зависимости: **`todos_db`**, **`auth`**.

Обязательные переменные для БД: **`TODOS_DATABASE_URL`** (или значение по умолчанию в compose).

Для вложений карточек и согласованности с **`GET /api/v1/media/...`** на gateway нужен **общий каталог медиа**:

- **`MEDIA_PATH`** (по умолчанию в compose: `/app/media`)
- Том **`media_storage:/app/media`** — тот же named volume, что у **gateway**

Лимит размера файла вложений: **`MAX_UPLOAD_MB`** (по умолчанию **15**).

### Локально без Docker

Из каталога **`todos/`**:

1. Виртуальное окружение, `pip install -r requirements.txt`.
2. Файл **`.env`** в `todos/` или переменные окружения:

   - **`DATABASE_URL`** или **`TODOS_DATABASE_URL`** — строка async PostgreSQL (см. `todos/infrastructure/database.py`).
   - **`AUTH_SERVICE_URL`** — URL сервиса auth (по умолчанию `http://auth:1236` в коде).
   - **`MEDIA_PATH`** — корень для файлов вложений (локально можно `./media`).
   - Для календаря Outlook: **`MICROSOFT_CLIENT_ID`**, **`MICROSOFT_TENANT_ID`**, **`MICROSOFT_CLIENT_SECRET`**, **`MICROSOFT_REDIRECT_URI`**, **`CALENDAR_CONNECTED_REDIRECT_URL`** — см. `docs/FRONTEND_TODOS.md`, раздел календаря.

3. Запуск: `uvicorn main:app --host 0.0.0.0 --port 1240` (как в `Dockerfile`).

---

## Структура кода в репозитории

| Путь | Содержание |
|------|------------|
| `todos/presentation/api.py` | FastAPI, lifespan, `create_all` + SQL-патчи схемы |
| `todos/presentation/routes/board_routes.py` | Kanban API |
| `todos/presentation/routes/calendar_routes.py` | Outlook: connect, callback, status, events |
| `todos/presentation/dependencies.py` | `get_current_user_id` |
| `todos/infrastructure/models.py` | Модели SQLAlchemy |
| `todos/infrastructure/repositories.py` | `KanbanRepository` и др. |
| `todos/infrastructure/schema_patches.py` | Идемпотентные `ALTER` для существующих БД |
| `todos/infrastructure/file_storage.py` | Сохранение вложений карточек под `MEDIA_PATH` |

---

## База данных

- PostgreSQL; таблицы создаются при старте через **`create_all`**, дополнительно применяются **`schema_patches`** (для уже существующих инсталляций).
- Скрипт-референс структуры: **`scripts/add_todos_kanban_tables.sql`**.

После обновления схемы перезапустите сервис **todos**, чтобы патчи выполнились.

---

## Gateway

- В `gateway` задайте **`TODOS_SERVICE_URL`** (например `http://todos:1240` в Docker).
- Загрузка файлов (`multipart`) и длинные запросы проксируются общим catch-all **`/api/v1/todos/{path}`** — тело и заголовки передаются дальше.

### 503 на проде (`GET .../todos/board`, `.../calendar/status`)

В консоли браузера **503** на `https://<gateway>/api/v1/todos/...` значит: **gateway не достучался до микросервиса todos** или **не задан `TODOS_SERVICE_URL`**.

**Самая частая ошибка:** в Portainer у gateway указано `TODOS_SERVICE_URL=http://127.0.0.1:1240` или `localhost` — **внутри контейнера gateway** `localhost` — это сам gateway, а не сервис todos. Нужно **`http://todos:1240`** (имя сервиса из `docker-compose`, одна Docker-сеть со stack).

**Быстрая проверка без авторизации:** откройте в браузере или curl:

`https://<ваш-gateway>/health/todos`

- **200** и `"todos": "reachable"` — до todos с gateway доступ есть; ищите другую причину.
- **503** — в JSON будут поля **`todos_service_url`**, **`upstream_message`**, **`hint`** (после обновления gateway с репозитория).

Ответ **503** на `/api/v1/todos/*` теперь тоже может содержать **`hint`**, **`todos_service_url`**, **`upstream_message`** — смотрите вкладку **Response** в DevTools.

| Что проверить | Действие |
|---------------|----------|
| Сервис **todos** в stack | В compose должен быть сервис **`todos`**, порт **1240**, БД **`todos_db`**. Без этого контейнера будет 503. |
| **`TODOS_SERVICE_URL` у gateway** | `http://todos:1240`, не `localhost`. |
| Логи контейнера **todos** | Падение при старте (неверный `DATABASE_URL`, нет миграций/БД) — процесс не слушает порт → 503. |
| Сеть | `docker exec -it <gateway> wget -qO- http://todos:1240/health` (имена контейнеров подставьте свои). |

После правки env перезапустите **gateway** (и убедитесь, что **todos** запущен).

---

## Клиенты (фронтенд)

Полная таблица эндпоинтов, типы TypeScript, примеры `apiFetch`, календарь Outlook и типичные ошибки — в **`docs/FRONTEND_TODOS.md`**.

Старые короткие файлы `FRONTEND_TODOS_BOARD*.md` помечены как устаревшие; используйте **`FRONTEND_TODOS.md`**.
