# Инструкция по подключению фронтенда к API (Kosta Tickets)

Фронтенд (**tickets-front**, Vite + React) ходит только в **gateway** — единую точку входа с префиксом **`/api/v1`**. Прямые запросы из браузера к микросервисам (`auth`, `expenses`, `time_tracking` и т.д.) в продакшене не используются.

**Связанные документы**

| Документ | Назначение |
|----------|------------|
| **`docs/TIME_TRACKING_FRONTEND.md`** | Time Manager: клиенты, задачи, team-workload, профиль, примеры TS |
| **`docs/FRONTEND_CONNECTION.md`** | Этот файл — базовое подключение и env |

Копия для удобства: **`Docs/FRONTEND_CONNECTION.md`** (тот же текст).

---

## Быстрый старт (локально)

1. Запустите **gateway** из **tickets-back** (Docker Compose или локально), чтобы API слушало, например **`http://127.0.0.1:1234`**.
2. В **tickets-front** в `.env` или `.env.local` задайте:
   ```env
   VITE_PROXY_TARGET=http://127.0.0.1:1234
   ```
3. **`VITE_API_BASE_URL` не задавайте** (пусто) — запросы пойдут через прокси Vite.
4. В коде используйте **`apiFetch('/api/v1/...')`** из `@shared/api` (подставляется `Authorization: Bearer`).
5. Проверка: в браузере откройте `http://127.0.0.1:1234/health` — ответ от gateway; затем с залогиненного фронта — `GET /api/v1/users/me`.

---

## 1. Базовый URL API

| Что | Значение |
|-----|----------|
| Префикс всех публичных маршрутов | **`/api/v1`** |
| Полный URL в проде | **`https://<хост-gateway>/api/v1/...`** |

Примеры путей:

- `GET /api/v1/users/me`
- `GET /api/v1/time-tracking/team-workload?from=2026-04-01&to=2026-04-07`
- `GET /api/v1/time-tracking/clients`

---

## 2. Локальная разработка (Vite + прокси)

### Как это устроено

1. Gateway слушает на **`VITE_PROXY_TARGET`** (например `http://127.0.0.1:1234`).
2. Dev-сервер фронта (например `http://localhost:5173`) отдаёт SPA.
3. При **пустом** `VITE_API_BASE_URL` функция `getApiBaseUrl()` возвращает пустую строку. Запрос вида `apiFetch('/api/v1/users/me')` идёт **на тот же origin**, что и страница (`localhost:5173`).
4. В **`vite.config.ts`** настроен прокси: путь **`/api`** пересылается на **`VITE_PROXY_TARGET`**.

Итог: в деве URL запроса к API — **`/api/v1/...`** относительно dev-сервера, прокси пересылает на gateway.

### Переменные

```env
VITE_PROXY_TARGET=http://127.0.0.1:1234
```

Порт и хост подставьте под ваш запуск gateway.

### 503 «шлюз недоступен» / прокси не отвечает

- Gateway не запущен или **неверный** `VITE_PROXY_TARGET`.
- Проверьте процесс/контейнер и URL в `.env`.

---

## 3. Продакшен (другой домен API)

Когда SPA на одном домене (`https://tickets.kostalegal.com`), а API на другом (`https://ticketsback.kostalegal.com`), в **сборке** фронта задайте:

```env
VITE_API_BASE_URL=https://ticketsback.kostalegal.com
```

- Указывайте **origin без** `/api/v1` (нормализация уже в коде фронта).
- Запросы уйдут на **`https://ticketsback.kostalegal.com/api/v1/...`.**

---

## 4. Авторизация

| Требование | Описание |
|------------|----------|
| Токен | После входа (Azure AD и т.д.) токен должен быть доступен так же, как ожидает **`getAccessToken()`** в `@shared/lib`. |
| Заголовок | `apiFetch` добавляет **`Authorization: Bearer <access_token>`**. |
| 401 | Обычно перенаправление на вход — см. `apiFetch` в `src/shared/api/client.ts`. |

---

## 5. CORS

Gateway настроен на ожидаемые origin’ы фронта (в т.ч. `localhost:5173`) и при необходимости частные сети. Если новый origin блокируется:

- добавьте его в окружение gateway: **`FRONTEND_URL`**, **`ADMIN_FRONTEND_URL`** и т.д.

---

## 6. Nginx / reverse proxy

Если перед gateway стоит nginx:

- Должен проксироваться весь префикс **`/api/`** (или как минимум `/api/v1/...`) на gateway.
- Часть эндпоинтов учёта времени продублирована под **`/api/v1/users/{id}/...`** (ставки и time-entries); пути **`/api/v1/time-tracking/...`** (в т.ч. **clients**, **tasks**, **team-workload**) должны доходить до gateway — иначе будет **404**.

**Важно:** в `location` не используйте `proxy_pass http://gateway:1234/api/v1/;` с **URI** после порта — так nginx **отрезает** префикс location от пути, и запрос к gateway может стать не тем (например, без сегмента `time-tracking`). Предпочтительно:

```nginx
location /api/ {
    proxy_pass http://gateway:1234;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

Gateway дополнительно переписывает **`/api/v1/clients/...` → `/api/v1/time-tracking/clients/...`**, если reverse proxy всё же отдал путь без `time-tracking` (совместимость со старыми конфигами).

---

## 7. Учёт времени (Time Manager)

Детальная инструкция по эндпоинтам, полям, правам и примерам TypeScript:

**`docs/TIME_TRACKING_FRONTEND.md`**

Дополнительно по бэкенду: **`docs/TIME_TRACKING_TEAM_WORKLOAD.md`**, **`docs/TIME_TRACKING_HOURLY_RATES.md`**.

---

## 8. Проверка связки

| Шаг | Действие | Ожидание |
|-----|----------|----------|
| 1 | `GET http://<gateway>:<port>/health` | 200 и JSON со статусом |
| 2 | С фронта с токеном: `GET /api/v1/users/me` | 200, профиль пользователя |
| 3 | (опционально) `GET /api/v1/time-tracking/clients` при нужной роли | 200, список или 403 |

---

## 9. Шпаргалка по переменным окружения (tickets-front)

| Переменная | Когда нужна | Пример |
|------------|-------------|--------|
| `VITE_PROXY_TARGET` | Локально, dev-сервер Vite | `http://127.0.0.1:1234` |
| `VITE_API_BASE_URL` | Прод или API на другом origin без прокси | `https://ticketsback.kostalegal.com` |
| `VITE_ATTENDANCE_API_BASE` | Только если посещаемость на отдельном базовом URL | по необходимости |

`.env` в **tickets-front** в git обычно не коммитят; ориентируйтесь на `.env.example` фронта.

---

## 10. Бэкенд (tickets-back)

Переменные Docker и сервисов — в **`tickets-back/.env.example`**. Gateway и URL фронта настраиваются в окружении контейнера gateway (`FRONTEND_URL`, `ADMIN_FRONTEND_URL` и т.д.).
