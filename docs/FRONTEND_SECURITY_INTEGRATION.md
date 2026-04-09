# Интеграция с tickets-back (безопасность и авторизация)

Документ описывает **фактический** контракт между **tickets-front** и **tickets-back** (gateway + auth) по состоянию кода. При смене схемы (например переход на HttpOnly cookie) обновляйте и бэкенд, и этот файл.

## REST API

- Gateway проксирует запросы в auth и сервисы. Пользователь определяется заголовком **`Authorization: Bearer <jwt>`** (`gateway/infrastructure/auth_upstream.py` → `GET {auth}/users/me`).
- Фронт хранит JWT в **`localStorage['access_token']`** и подставляет Bearer в **`apiFetch`** (`src/shared/api/client.ts`).
- Ответ **401** на обычных маршрутах: фронт очищает токен и редиректит на **`/api/v1/auth/azure/login`**.

## OAuth (Azure)

1. **`GET /api/v1/auth/azure/login`** → редирект в auth-сервис, далее Microsoft.
2. После успеха gateway **`GET /api/v1/auth/azure/callback`** редиректит на **`{FRONTEND_URL}/auth/callback#access_token=<jwt>`** (или `/auth/callback.html` для отдельного admin UI).
3. Роут **`/auth/callback`** в React парсит hash/query, вызывает **`setAccessToken`**, переходит на **`/home`**.

## Мост SPA при другом хосте

Если redirect URI в Azure указывает на **gateway**, а SPA на другом origin, открывается **`GET https://<gateway>/auth/callback`** — отдаётся HTML из **`spa_auth_callback.py`**, который переносит hash на **`FRONTEND_URL/auth/callback`** или пишет токен в `localStorage` и ведёт на `/home`.

## WebSocket

| Фича | Ожидание gateway |
|------|------------------|
| Тикеты | `wss://…/api/v1/tickets/ws/tickets?token=<jwt>` (`_get_ws_user` в `tickets.py`) |
| Уведомления | В каждом JSON-сообщении поле **`token`**: **`Bearer <jwt>`** (`notifications.py`) |

## Что не совпадает с «идеальной» схемой

- JWT в **localStorage** и в **URL hash** уязвим для XSS / утечек через Referer; перенос сессии в **HttpOnly cookie** требует доработки auth-сервиса, gateway и этого фронта.
