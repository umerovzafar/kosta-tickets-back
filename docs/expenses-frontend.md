# Подключение фронтенда к модулю «Расходы»

> **Дубль для фронт-репозитория:** `tickets-front/docs/expenses-api-connection.md` и ТЗ контракта `tickets-front/TZ-expenses-backend.md`. При правках этого файла по возможности синхронизируйте копию во фронте.

Фронтенд **не** обращается к микросервису `expenses` напрямую (порт 1242 доступен только внутри Docker-сети). Все запросы идут через **gateway** по публичному URL API.

---

## 1. Архитектура

```
Браузер (SPA)  →  https://<ваш-api-домен>  →  gateway :1234  →  http://expenses:1242
```

- Базовый путь API на gateway: **`/api/v1`**
- Расходы: **`/api/v1/expenses`**, справочники: **`/api/v1/expense-types`**, **`/api/v1/projects`**, **`/api/v1/exchange-rates?date=YYYY-MM-DD`** (и др. — см. `gateway/presentation/routes/expenses_routes.py`)

---

## 2. Переменные окружения бэкенда (gateway)

В `.env` репозитория `tickets-back` для gateway должны быть согласованы с тем, откуда открывается SPA:

| Переменная | Назначение |
|------------|------------|
| **`GATEWAY_BASE_URL`** | Публичный URL API (OAuth redirect, ссылки). Прод: `https://ticketsback.kostalegal.com` |
| **`FRONTEND_URL`** | Origin SPA для **CORS**. Прод: `https://tickets.kostalegal.com` |
| **`EXPENSES_SERVICE_URL`** | Внутри Docker: `http://expenses:1242` (не подставлять в фронт) |

После изменения `.env` перезапустите gateway: `docker compose up -d gateway`.

Если CORS блокирует запросы — проверьте, что **`FRONTEND_URL`** точно совпадает с origin в браузере (схема, хост, порт, без лишнего слэша).

---

## 3. Настройка фронтенда (Vite / env)

**Вариант A — прямой URL API** (удобно без прокси):

В `.env` фронта (или `.env.production`):

```env
VITE_API_URL=https://ticketsback.kostalegal.com
```

В коде запросов использовать этот base URL + пути `/api/v1/expenses`, …

**Вариант B — прокси в `vite.config`**: запросы с dev-сервера идут на `http://127.0.0.1:1234`, в браузере остаётся `localhost:5173` — см. комментарии в `.env.example` бэкенда (`vite.config.example.ts` в корне монорепо, если есть).

---

## 4. Авторизация

Все эндпоинты расходов на gateway **требуют** заголовок:

```http
Authorization: Bearer <access_token>
```

Токен тот же, что для остального приложения (вход через Azure AD / ваш auth). Без токена — **401**.

---

## 5. Примеры URL (production)

Если API: `https://ticketsback.kostalegal.com`:

- Список: `GET https://ticketsback.kostalegal.com/api/v1/expenses?skip=0&limit=50`
- Создание: `POST https://ticketsback.kostalegal.com/api/v1/expenses`
- Типы: `GET https://ticketsback.kostalegal.com/api/v1/expense-types`
- Курс: `GET https://ticketsback.kostalegal.com/api/v1/exchange-rates?date=2026-04-02`

Контракт полей (camelCase / деньги) согласован с ТЗ и нормализацией на фронте (`coerceExpense.ts` и см. `TZ-expenses-backend.md` во фронт-репозитории).

### Автор заявки

В ответах списка и карточки заявки добавлено поле **`createdBy`** (объект):

- `id` — тот же смысл, что и `createdByUserId`
- `displayName`, `email`, опционально `picture`, `position` — подтягиваются из **auth** (`GET /users/{id}` тем же Bearer-токеном)

Если auth недоступен или профиль не найден, `createdBy` всё равно есть: заполняется **`id`**, остальные поля могут быть `null`.

---

## 6. Частые проблемы

| Симптом | Что проверить |
|---------|----------------|
| CORS error | `FRONTEND_URL` на gateway, совпадение origin с SPA |
| 503 на `/api/v1/expenses` | Контейнер `expenses` запущен, `EXPENSES_SERVICE_URL` в env gateway |
| **500** на `/api/v1/expenses` | Смотрите логи **`docker compose logs expenses --tail 100`** (или Portainer → Logs). Частая причина после обновления кода — **в БД не хватает колонки** (например `payment_deadline`); в актуальном образе expenses при старте выполняется `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`. Пересоберите и перезапустите `expenses`. Если ошибка остаётся — пришлите traceback из логов. |
| 401 | Передаётся ли `Authorization`, не истёк ли токен |
| 403 | Роль пользователя (раздел расходов / модерация) |

---

## 7. Локальная разработка

- Gateway: `http://localhost:1234` (или порт из `GATEWAY_PORT`).
- Фронт: `http://localhost:5173` — укажите этот origin в `FRONTEND_URL` на бэкенде.
- Микросервисы поднимайте через `docker compose up` или укажите в gateway `EXPENSES_SERVICE_URL=http://host.docker.internal:1242`, если `expenses` запущен на хосте.

---

*См. также: деплой и переменные БД — в общей документации стека (`docker-compose.yml`, `.env.example`).*
