# Подключение раздела «Расходы» (expenses)

## 1. Что должно работать в Docker

В одном стеке `docker compose` должны быть как минимум:

| Сервис | Роль |
|--------|------|
| **expenses** | микросервис расходов, порт **1242** внутри сети |
| **expenses_db** | PostgreSQL с БД `kosta_expenses` |
| **auth** | проверка JWT (`/users/me`) — expenses без него не авторизует |
| **gateway** | единая точка API для фронта, прокси на `http://expenses:1242` |

Запуск всего стека:

```bash
docker compose up -d --build
```

Пересборка только расходов после правок кода:

```bash
docker compose build expenses && docker compose up -d expenses
```

---

## 2. Переменные в `.env` (корень репозитория)

**База расходов** — пароль в URL и в `EXPENSES_DB_PASSWORD` должен совпадать:

```env
EXPENSES_DB_USER=expenses
EXPENSES_DB_PASSWORD=ваш_пароль
EXPENSES_DB_NAME=kosta_expenses
EXPENSES_DATABASE_URL=postgresql://expenses:ваш_пароль@expenses_db:5432/kosta_expenses
```

**Gateway → expenses** (внутри Docker-сети имя сервиса `expenses`):

```env
EXPENSES_SERVICE_URL=http://expenses:1242
AUTH_SERVICE_URL=http://auth:1236
```

**Опционально:**

```env
EXPENSES_LOG_LEVEL=info
# EXPENSE_AMOUNT_LIMIT_UZS=...   # лимит суммы заявки в сумах
```

**CORS для SPA:** `FRONTEND_URL` и `GATEWAY_BASE_URL` в `.env` должны соответствовать реальным URL фронта и API (как у остальных разделов).

---

## 3. Как ходит фронт (через gateway)

Клиент **не** обращается к `expenses:1242` напрямую с браузера. Нужен **публичный URL gateway**, например `https://ticketsback.kostalegal.com`.

- Заголовок: **`Authorization: Bearer <JWT>`** (тот же токен, что для остального API).
- Примеры путей (все под префиксом gateway):

  - заявки: `GET/POST /api/v1/expenses`, `GET/PUT/DELETE /api/v1/expenses/...`
  - справочники: `GET /api/v1/expense-types`, `GET /api/v1/departments` и др. (см. `gateway/presentation/routes/expenses_routes.py`)

Если gateway отвечает **503** с текстом про expenses — контейнер `expenses` не запущен, не в той же сети, или неверный `EXPENSES_SERVICE_URL`.

---

## 4. Проверка после деплоя

```bash
docker compose ps expenses
docker compose logs -f expenses
```

Health внутри контейнера (если порт 1242 проброшен на хост):

```bash
curl -s http://localhost:1242/health
```

Иначе проверяйте из другого контейнера в той же сети или через gateway.

---

## 5. Локальный запуск без Docker

- В `EXPENSES_DATABASE_URL` вместо `expenses_db` укажите **`127.0.0.1`** и порт, проброшенный с Postgres.
- `AUTH_SERVICE_URL` — URL, где доступен auth (например `http://127.0.0.1:1236`).
- Gateway на хосте: в `.env` для gateway задайте `EXPENSES_SERVICE_URL=http://127.0.0.1:1242`, если expenses запущены локально на порту 1242.

---

## 6. Права пользователей

Роли проверяются в сервисе (см. `expenses/presentation/deps.py`): например «Сотрудник» видит только свои заявки; модерация — у админских ролей. У тестового пользователя в auth должна быть нужная **роль**.

---

## 7. Отдельный стек / Portainer

Если gateway и expenses в **разных** стеках — нужна общая Docker-сеть (`external`) или явный `EXPENSES_SERVICE_URL` на доступный с хоста gateway адрес (например `http://host.docker.internal:1242` при пробросе порта).
