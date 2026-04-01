# Фронтенд: продакшен (tickets.kostalegal.com + ticketsback.kostalegal.com)

SPA: **`https://tickets.kostalegal.com`**  
API (gateway): **`https://ticketsback.kostalegal.com`**

На бэкенде обязательно разделить **origin фронта** и **origin API** — см. ниже и `.env.example`.

---

## 1. Базовый URL API (фронт)

В проекте `tickets-front` используется **`VITE_API_BASE_URL`** (см. `src/shared/config/env.ts`):

```text
VITE_API_BASE_URL=https://ticketsback.kostalegal.com
```

Без хвоста `/api/v1` — он подставляется в коде. Дальше все REST и WebSocket (`getTicketsWsUrl` и т.д.) строятся от этого origin.

В **dev** на Vite (`localhost:5173`) можно оставить `http://localhost:1234` или прокси `/api` — см. `vite.config.ts`.

---

## 2. Авторизация: переменные на бэкенде (важно)

Сервисы **auth** и **gateway** читают из окружения:

| Переменная | Значение для продакшена | Назначение |
|------------|-------------------------|------------|
| **`FRONTEND_URL`** | `https://tickets.kostalegal.com` | Origin SPA: после входа Azure пользователь редиректится на **`FRONTEND_URL/auth/callback#access_token=...`**. Не указывайте сюда `ticketsback`, если SPA отдаётся только с `tickets.kostalegal.com`. |
| **`GATEWAY_BASE_URL`** | `https://ticketsback.kostalegal.com` | Публичный URL gateway (ссылки, WS и т.д.). |
| **`AZURE_REDIRECT_URI`** | `https://ticketsback.kostalegal.com/api/v1/auth/azure/callback` | Должен **побайтно совпадать** с URI в Microsoft Entra (раздел «URI перенаправления»). Это callback **на API**, не на фронт. В auth: `AUTH_REDIRECT_URI=${AZURE_REDIRECT_URI}`. |

Если **`FRONTEND_URL`** ошибочно равен `https://ticketsback.kostalegal.com`, браузер после входа открывает **тот же хост, что и API**, а у FastAPI нет страницы SPA → `404` на `/auth/callback`. На gateway добавлен маршрут **`GET /auth/callback`**: отдаётся небольшая HTML-страница, которая либо переносит на `FRONTEND_URL/auth/callback` с тем же `#access_token`, либо при совпадении хоста кладёт токен в `localStorage` и ведёт на `/home`. Надёжнее всё же задать **`FRONTEND_URL`** на реальный SPA.

---

## 3. Вход Microsoft (Azure)

- Кнопка «Войти через Microsoft» — **полный переход браузера** (`window.location` / `<a href>`), **не** `fetch`:

  `GET https://ticketsback.kostalegal.com/api/v1/auth/azure/login`

- Опционально для админки:  
  `GET .../api/v1/auth/azure/login?state=admin`

- После успеха пользователь попадает на фронт с токеном в **fragment**:

  `https://tickets.kostalegal.com/auth/callback#access_token=...`

- В приложении нужен маршрут **`/auth/callback`**: прочитать `access_token` из `window.location.hash` (fallback — из query), сохранить в `localStorage` (`access_token`), перейти в приложение (например `/home`). Реализация: `AuthCallbackPage` в `tickets-front`.

- При `state=admin` редирект идёт на **`/auth/callback.html#access_token=...`** — отдельная страница админки, если `ADMIN_FRONTEND_URL` указывает на другой origin.

- Ошибка входа: редирект на `/login?error=auth_failed` (или для admin — на `index.html?error=auth_failed`).

### Типичные ошибки

- **`AADSTS50011` (redirect URI mismatch)** — в запросе к Entra уходит не тот `redirect_uri`, что в регистрации приложения. Проверьте **`AZURE_REDIRECT_URI`** на сервере и список URI в Azure.
- **`{"detail":"Not Found"}` на `https://ticketsback.kostalegal.com/auth/callback`** — см. раздел 2: **`FRONTEND_URL`** и маршрут gateway **`GET /auth/callback`**.

---

## 4. Выход

Полный переход:

`GET https://ticketsback.kostalegal.com/api/v1/auth/azure/logout`

Дальше — редиректы Microsoft и возврат на страницу входа фронта (`FRONTEND_URL` + `/login` на бэкенде).

---

## 5. Календарь Outlook

1. С заголовком **`Authorization: Bearer <access_token>`**:

   `GET https://ticketsback.kostalegal.com/api/v1/todos/calendar/connect`

2. Ответ: JSON **`{ "url": "..." }`** — открыть `url` через **`window.location.href`** (не `fetch` следом за редиректом на Microsoft — CORS).

3. В сервисе **todos** задайте **`MICROSOFT_REDIRECT_URI`**:  
   `https://ticketsback.kostalegal.com/api/v1/todos/calendar/callback` — тот же URI в Entra.

4. После OAuth календаря бэкенд редиректит на фронт с query:

   `https://tickets.kostalegal.com/?calendar=connected` или `?calendar=error`  
   (задаётся **`CALENDAR_CONNECTED_REDIRECT_URL`** на todos).

---

## 6. Прочие API

Все запросы с **`Authorization: Bearer`** — на **`https://ticketsback.kostalegal.com`**, пути вида `/api/v1/...`.

---

## 7. CORS

На gateway в **`FRONTEND_URL`** должен быть origin SPA: **`https://tickets.kostalegal.com`**. Дополнительная настройка CORS на фронте не требуется.

---

## 8. Reverse-proxy (опционально)

Если на `tickets.kostalegal.com` nginx проксирует **`/api`** на `ticketsback`, можно использовать **`VITE_API_BASE_URL=`** пустым и относительные пути `/api` — тогда база совпадает с origin SPA. Иначе оставьте полный URL на `ticketsback`.

---

## 9. Microsoft Entra (кратко)

В регистрации приложения (Web) добавьте redirect URI **ровно** такие:

- `https://ticketsback.kostalegal.com/api/v1/auth/azure/callback` — вход в приложение (Azure AD / auth).
- `https://ticketsback.kostalegal.com/api/v1/todos/calendar/callback` — календарь Outlook (todos).

Подробнее — комментарии в `.env.example` и `docker-compose.yml`.

---

## 10. Чеклист

| Проверка | Ожидание |
|----------|----------|
| Открыть в браузере URL логина API | Редирект на Microsoft |
| После входа | `https://tickets.kostalegal.com/auth/callback#access_token=...` (при корректном `FRONTEND_URL`) |
| `fetch`/axios к API | `VITE_API_BASE_URL=https://ticketsback.kostalegal.com`, заголовок Bearer |
| Переменные auth | `AZURE_REDIRECT_URI` и Entra совпадают; `FRONTEND_URL` = origin SPA |
