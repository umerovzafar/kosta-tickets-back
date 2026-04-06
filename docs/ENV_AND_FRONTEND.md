# Переменные окружения и подключение фронтенда

## База данных проектов (`kosta_projects`)

В корневом `.env` для Docker заданы:

| Переменная | Назначение |
|------------|------------|
| `PROJECTS_DB_USER` | пользователь PostgreSQL (по умолчанию `projects`) |
| `PROJECTS_DB_PASSWORD` | пароль пользователя БД (локально в вашем `.env` — `123456`, совпадает с `POSTGRES_PASSWORD` в контейнере `projects_db`) |
| `PROJECTS_DB_NAME` | имя базы (по умолчанию `kosta_projects`) |
| `PROJECTS_DATABASE_URL` | полная строка подключения для сервиса `projects`: `postgresql://projects:123456@projects_db:5432/kosta_projects` |

Сервис `projects` в `docker-compose` получает `DATABASE_URL` из `PROJECTS_DATABASE_URL` и ждёт готовности `projects_db`.

Пересборка после смены `.env`:

```bash
docker compose up -d --build projects_db projects
```

Если том `projects_db_data` уже создан с другим паролем, смените пароль в PostgreSQL или удалите том (данные БД пропадут): `docker compose down` и затем удалите volume `projects_db_data` в Docker Desktop / Portainer.

---

## Шлюз (gateway) и URL микросервиса

В `.env` добавлено:

```env
PROJECTS_SERVICE_URL=http://projects:1243
```

Gateway использует его, когда для сервиса проектов появятся прокси-маршруты в коде.

---

## Фронтенд (`tickets-front`)

### Локальная разработка (Vite)

1. Запустите gateway (и при необходимости остальные сервисы), чтобы API было доступно, например на `http://127.0.0.1:1234`.
2. В фронте в `.env` / `.env.local` задайте цель прокси (см. `vite.config.ts`):

   ```env
   VITE_PROXY_TARGET=http://127.0.0.1:1234
   ```

3. Если **`VITE_API_BASE_URL` не задан** (или пустой), запросы к API идут относительными путями `/api/v1/...`, и Vite проксирует их на gateway.

4. Используйте общий клиент **`apiFetch`** из `@shared/api` — он подставляет заголовок `Authorization: Bearer <токен>`.

### Продакшен / отдельный API

Задайте origin gateway без суффикса `/api/v1`:

```env
VITE_API_BASE_URL=https://ticketsback.kostalegal.com
```

---

## Важно: два разных «проекта» в API

| URL | Что это |
|-----|---------|
| `GET /api/v1/projects` | Справочник проектов **для модуля расходов** (прокси на сервис **expenses**). Уже используется на фронте в контексте заявок. |
| Микросервис **projects** (`:1243`, БД `kosta_projects`) | Отдельный сервис; публичные маршруты через gateway добавляются по мере готовности API. |

Не путайте эти два источника при разработке новых экранов.

---

## Безопасность

- Файл `.env` с реальными паролями **не коммитьте** в git (он должен быть в `.gitignore`).
- Для продакшена используйте сложные пароли и секреты в оркестраторе (Portainer, Kubernetes secrets и т.д.).
- В репозитории ориентируйтесь на `.env.example` с плейсхолдерами (`YOUR_PROJECTS_PASSWORD` и т.д.).
