# Kosta Legal — backend (gateway + микросервисы)

Монорепозиторий: **gateway** (единая точка входа `/api/v1/...`), микросервисы **auth**, **tickets**, **todos**, **time_tracking**, **expenses**, **vacation**, **call_schedule** и др., общий пакет **backend_common**.

## Быстрый старт (Docker)

1. Скопируйте `.env.example` → `.env`, задайте **`JWT_SECRET`** (≥32 символов, одинаково на gateway и auth) и пароли БД.
2. Запуск:
   ```bash
   docker compose up -d --build
   ```
3. Gateway: `http://localhost:1234` (порт из `GATEWAY_PORT`).
4. Проверки:
   - Liveness (без БД): `GET http://localhost:1234/live`
   - Health (с проверкой users_db через use case): `GET http://localhost:1234/health`
   - Readiness (БД обязательна): `GET http://localhost:1234/ready`
   - Метрики (текст): `GET http://localhost:1234/metrics`

## Сервисы в compose

Все сервисы из `docker-compose.yml` должны собираться из репозитория (контекст сборки — корень проекта, см. `dockerfile` у каждого сервиса). Зависимости **Microsoft Graph** используются в **call_schedule** (переменные `MICROSOFT_*` / `CALL_SCHEDULE_*`).

## Планировщик (Celery Beat)

Авто-сдача прошлой ISO-недели в time tracking:

- Контейнеры: **`redis`**, **`time_tracking_celery_worker`**, **`time_tracking_celery_beat`** (включены в `docker-compose.yml` по умолчанию).
- Расписание: `WEEKLY_SUBMIT_TZ`, `WEEKLY_SUBMIT_HOUR`, `WEEKLY_SUBMIT_MINUTE`, `WEEKLY_SUBMIT_DOW` (см. `.env.example`).
- Без Redis/worker/beat задача не выполняется.

## Авторизация

- **JWT** access (и refresh, если включено в auth) — заголовок `Authorization: Bearer ...`.
- Сессия: HttpOnly-cookie (см. gateway `AUTH_SESSION_COOKIE_*`).
- Роли и права: сервис **auth** + проверки на gateway / в сервисах.

Подробнее: [docs/API.md](docs/API.md), OpenAPI у gateway: `http://localhost:1234/docs` (если включено).

## Миграции БД

Введён **Alembic** для сервиса **auth** (каталог `auth/alembic/`). Остальные сервисы пока могут использовать `create_all` + schema patches — план переноса: [docs/MIGRATIONS.md](docs/MIGRATIONS.md).

## Тесты

```bash
pip install -r requirements-dev.txt -r requirements-ci.txt
pytest tests/ -q
```

См. [docs/TESTING.md](docs/TESTING.md).

## Деплой и прод

- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)
- Пример override: `docker-compose.prod.yml` (переменные `ENVIRONMENT=production` и т.д.)

## Дорожная карта production

Полный чеклист (миграции всех сервисов, 60%+ покрытие тестами, rate limit, единый рефакторинг слоёв) — [docs/BACKEND_PRODUCTION_ROADMAP.md](docs/BACKEND_PRODUCTION_ROADMAP.md).

## Документы

| Файл | Содержание |
|------|------------|
| [.env.example](.env.example) | Шаблон переменных окружения |
| [docs/API.md](docs/API.md) | Версии API и префиксы |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Docker, env, health |
| [docs/MIGRATIONS.md](docs/MIGRATIONS.md) | Alembic |
| [docs/TESTING.md](docs/TESTING.md) | Pytest, CI |
| [docs/frontend-time-tracking-reports.md](docs/frontend-time-tracking-reports.md) | Отчёты для фронта |
