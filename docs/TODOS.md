# Сервис todos — инструкция

Микросервис **todos** в монорепозитории `tickets-back`: личная Kanban-доска (колонки, карточки с метками, дедлайнами, чеклистом, участниками, вложениями, комментариями) и интеграция **календаря Outlook** (Microsoft Graph). Снаружи сервис не вызывают напрямую — только через **gateway** (`TODOS_SERVICE_URL`).

| Документ | Назначение |
|----------|------------|
| **Этот файл (`docs/TODOS.md`)** | Запуск, окружение, архитектура, интеграция с gateway и медиа |
| **`docs/FRONTEND_TODOS.md`** | Полное описание API и типов для фронтенда (Kanban + календарь) |
| **`docs/FRONTEND_CONNECTION.md`** | Общая схема подключения SPA к gateway, CORS, proxy; во **tickets-front** — дубль с подразделом про **503 на todos** |

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

### Быстрый запуск через Docker Desktop (Windows)

1. Запустите **Docker Desktop** и дождитесь «Running».
2. В корне **`tickets-back`** скопируйте **`.env.example`** → **`.env`**, заполните пароли БД (хотя бы для `users` / `todos`).
3. Выполните:

   ```powershell
   .\scripts\todos_dev_up.ps1
   ```

   Скрипт поднимает **`users_db`**, **`todos_db`**, **`auth`**, **`todos`** и пробрасывает **`http://127.0.0.1:1240`** на сервис todos (файл **`docker-compose.todos-dev.yml`**).

4. Проверка: **`curl http://127.0.0.1:1240/health`** — должен быть JSON со **`status`**.

5. Чтобы фронт ходил **как в проде** (через gateway):

   ```powershell
   docker compose up -d gateway
   ```

   Затем **`http://127.0.0.1:1234/health/todos`** — должно быть **`"todos": "reachable"`**. Далее **`GET http://127.0.0.1:1234/api/v1/todos/board`** с заголовком **`Authorization`** (токен пользователя).

На **продакшене** (`ticketsback.kostalegal.com`) **503** не исправляется скриптом на ПК: в stack должен быть задеплоен сервис **`todos`**, у **gateway** — **`TODOS_SERVICE_URL=http://todos:1240`**, см. чеклист ниже.

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
| `gateway/presentation/routes/todos_routes.py` | Прокси **`/api/v1/todos/*`**, ответы **503** при недоступном todos |
| `gateway/presentation/routes/health.py` | В т.ч. **`GET /health/todos`** — проверка **`TODOS_SERVICE_URL`** и **`GET …/health`** у сервиса todos |

---

## База данных

- PostgreSQL; таблицы создаются при старте через **`create_all`**, дополнительно применяются **`schema_patches`** (для уже существующих инсталляций).
- Скрипт-референс структуры: **`scripts/add_todos_kanban_tables.sql`**.

После обновления схемы перезапустите сервис **todos**, чтобы патчи выполнились.

---

## Gateway

- В контейнере **gateway** задайте **`TODOS_SERVICE_URL`** без завершающего слэша (например **`http://todos:1240`** в Docker Compose — имя сервиса как в stack; в **Kubernetes** — внутренний URL сервиса и порт **1240**).
- Загрузка файлов (`multipart`) и длинные запросы проксируются общим catch-all **`/api/v1/todos/{path}`** — тело и заголовки передаются дальше.
- После изменения переменных **перезапустите gateway**.

Это **не ошибка фронтенда**: при **503** на `https://<gateway>/api/v1/todos/...` пользователь SPA ни при чём. Кратко для UI — **`docs/FRONTEND_TODOS.md`** (§0.6) и дубль во **tickets-front**: **`docs/FRONTEND_CONNECTION.md`**.

### Два типа ответов на прокси `/api/v1/todos/*`

Код: **`gateway/presentation/routes/todos_routes.py`**. В теле JSON обычно поле **`detail`**:

| `detail` | Когда |
|----------|--------|
| **`TODOS_SERVICE_URL not configured`** | Переменная **`TODOS_SERVICE_URL`** у gateway **пустая или не задана** (в т.ч. переопределение в Portainer пустой строкой). |
| **`Todos service unavailable`** | URL задан, но **нет TCP/ответа** от todos (сервис выключен, неверный хост/порт, контейнеры в **разных** сетях). Дополнительно могут быть **`hint`**, **`todos_service_url`**, **`upstream_error`**, **`upstream_message`**. |

**Самая частая ошибка в Docker:** `TODOS_SERVICE_URL=http://127.0.0.1:1240` или **`localhost`** — **внутри контейнера gateway** `localhost` — это сам gateway, не todos. Нужно **`http://todos:1240`** (или фактическое имя сервиса в compose).

### Диагностика: `GET /health/todos` (без авторизации)

Код: **`gateway/presentation/routes/health.py`**. Полный URL: **`https://<gateway>/health/todos`** (тот же хост, что и API).

| HTTP | Смысл |
|------|--------|
| **200**, в теле **`"todos": "reachable"`** | **`TODOS_SERVICE_URL`** задан, с gateway до **`{URL}/health`** сервиса todos запрос прошёл. Если при этом всё ещё 503 на конкретном маршруте — смотрите логи todos и тело ответа прокси. |
| **503**, **`detail`: `TODOS_SERVICE_URL not configured`** | Как в таблице выше — задайте URL и перезапустите gateway. |
| **503**, **`detail`: `Todos unreachable from gateway`** | TCP/сеть до **`TODOS_SERVICE_URL`** не удалась (см. **`upstream_message`**, **`hint`**). |
| **503**, **`detail`: `Todos /health not OK`** | Соединение есть, но todos ответил не **200** на **`/health`** (сервис падает, другой процесс на порту и т.д.). |

### Чеклист (Portainer / Compose / Kubernetes)

1. Контейнер или под **todos** **запущен** и слушает **1240** (`docker compose ps`, логи `todos`).
2. У **gateway** в env **`TODOS_SERVICE_URL=http://todos:1240`** (или ваш сервисный DNS и порт).
3. **Gateway** и **todos** в **одной** сети stack / namespace.
4. Проверка с хоста сети или из контейнера gateway: **`GET http://todos:1240/health`** (имя **`todos`** замените на своё, если другое).
5. Если сервис **todos** на прод **ещё не выкатывали** или **не добавили в stack** — его нужно задеплоить; иначе gateway стабильно отдаёт **503** на пути todos.

| Что проверить | Действие |
|---------------|----------|
| Сервис **todos** в stack | В compose — сервис **`todos`**, порт **1240**, БД **`todos_db`** (или ваша схема). |
| **`TODOS_SERVICE_URL` у gateway** | Внутри Docker: **`http://<имя_сервиса>:1240`**, не `localhost` / `127.0.0.1`. |
| Логи **todos** | Ошибка старта (БД, env) — процесс не слушает порт → 503 на прокси. |
| Сеть | `docker exec -it <gateway> wget -qO- http://todos:1240/health` (подставьте имена контейнеров/сервисов). |

После правки env перезапустите **gateway** и при необходимости **todos**.

---

## Клиенты (фронтенд)

Полная таблица эндпоинтов, типы TypeScript, примеры `apiFetch`, календарь Outlook и типичные ошибки — в **`docs/FRONTEND_TODOS.md`** (в т.ч. **§0.6** про **503** и **`GET /health/todos`**). В репозитории **tickets-front** см. **`docs/FRONTEND_CONNECTION.md`**.

Старые короткие файлы `FRONTEND_TODOS_BOARD*.md` помечены как устаревшие; используйте **`FRONTEND_TODOS.md`**.
