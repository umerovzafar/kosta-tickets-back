# Подключение фронтенда к API (Kosta Tickets)

Каноничный текст для команды. Зеркальная копия с ориентацией на код фронта: **`tickets-front/docs/FRONTEND_CONNECTION.md`**.

Фронтенд (**tickets-front**, Vite + React) ходит только в **gateway** — единую точку входа (`/api/v1/...`). Прямые вызовы на порты микросервисов из браузера в проде не используются.

## Базовый URL

- Все маршруты API: префикс **`/api/v1`**.
- Клиент: **`apiFetch`** из `@shared/api` + **`getApiBaseUrl()`** из `@shared/config` (`tickets-front/src/shared/config/env.ts`).

### Пустой `VITE_API_BASE_URL` (локально через прокси Vite)

- **`apiFetch('/api/v1/...')`** → относительный путь на origin SPA; Vite проксирует **`/api`** на **`VITE_PROXY_TARGET`** (gateway).
- OAuth и admin-login URL строятся как **`/api/v1/auth/...`** на том же origin.
- WebSocket к API — на **`ws(s)://<host SPA>/api/v1/...`** (нужен upgrade через gateway при использовании WS с dev-сервера).

## Локальная разработка

1. Запустите **gateway** (например `http://127.0.0.1:1234`).
2. В корне **tickets-front** создайте `.env` или `.env.local` по образцу **`.env.example`**:
   - задайте **`VITE_PROXY_TARGET=http://127.0.0.1:1234`** (или фактический адрес gateway);
   - **не задавайте** `VITE_API_BASE_URL` (или оставьте пустым).
3. При пустом `VITE_API_BASE_URL` запросы идут на тот же origin, что и страница (`localhost:5173`), а Vite проксирует **`/api`** на `VITE_PROXY_TARGET` (`vite.config.ts`).

Если видите **503** с текстом про недоступность шлюза — gateway не запущен или неверный `VITE_PROXY_TARGET`.

## Продакшен / отдельный домен API

В сборке задайте:

```env
VITE_API_BASE_URL=https://ticketsback.kostalegal.com
```

Только **origin**, без `/api/v1`. Тогда `apiFetch('/api/v1/...')` уйдёт на полный URL.

## Авторизация и CORS

- Токен: **`getAccessToken()`** → заголовок **`Authorization: Bearer`** (ставит `apiFetch`).
- При **401** — редирект на **`getAzureLoginUrl()`** (см. `tickets-front/src/shared/api/client.ts`).
- CORS настраивается на gateway (**`FRONTEND_URL`** и др. в env контейнера gateway) — см. `.env.example` в **tickets-back**.

## Фон рабочего стола (`desktop_background`)

В **`/users/me`** приходит относительный путь вида **`desktop_backgrounds/{user_id}/{uuid}.png`**. Картинку отдаёт **gateway** по тому же origin, что и API:

**`https://<хост-gateway>/desktop_backgrounds/{user_id}/{filename}`** — без префикса **`/api/v1`** (удобно для `<img src>`).

Убедитесь, что каталог **`MEDIA_PATH`** в контейнере gateway смонтирован на постоянное хранилище (см. `docker-compose`). Если файл на диске отсутствует — будет **404** (перезалейте фото).

Локально во **Vite** прокси обычно настроен только на **`/api`**. Добавьте прокси **`/desktop_backgrounds`** на тот же адрес gateway, что и **`/api`**, иначе превью с `localhost:5173/desktop_backgrounds/...` не дойдут до бэкенда.

Альтернатива без отдельного прокси: собирать URL как **`${VITE_API_BASE_URL}/desktop_backgrounds/...`** (при заданном base).

## Учёт времени (примеры путей)

| Назначение | Путь |
|------------|------|
| Загрузка команды | `GET /api/v1/time-tracking/team-workload?from=…&to=…` |
| Пользователи TT | `GET /api/v1/time-tracking/users` |
| Почасовые ставки | `GET /api/v1/time-tracking/users/{id}/hourly-rates?kind=billable` и т.д. |

Подробности во фронте: **`tickets-front/docs/TIME_TRACKING.md`**.

## Сервис todos (Kanban + календарь Outlook)

Префикс **`/api/v1/todos/...`**. Полная инструкция для фронта в одном файле: **`Docs/FRONTEND_TODOS.md`** (копия: `docs/FRONTEND_TODOS.md`).

## Проверка

1. `GET` health gateway, например `http://127.0.0.1:1234/health`.
2. С фронта с токеном: `GET /api/v1/users/me`.

## Шпаргалка переменных

| Переменная | Когда |
|------------|--------|
| `VITE_PROXY_TARGET` | Локально, dev + прокси Vite |
| `VITE_API_BASE_URL` | Прод или API на другом origin без прокси |
| `VITE_ATTENDANCE_API_BASE` | Только если нужен отдельный base для посещаемости |
