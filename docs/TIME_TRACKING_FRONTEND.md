# Инструкция для фронтенда: учёт времени (time tracking)

Все запросы идут на **gateway** с префиксом **`/api/v1`**. Микросервис `time_tracking` с браузера **не** вызывается напрямую.

**Содержание:** [URL и env](#как-пробрасывать-url-на-фронте) · [Профиль (нагрузка)](#профиль-норма-часов-в-неделю) · [Эндпоинты TT](#канонические-пути) · [Примеры TypeScript](#примеры-typescript) · [Алиасы](#алиасы-под-apiv1users) · [Права](#права) · [Ошибки](#типичные-ошибки) · [Ссылки](#дополнительная-документация-в-репозитории)

---

## Как пробрасывать URL на фронте

Тот же механизм, что и для остального приложения:

| Режим | Переменная в tickets-front | Как формируется URL |
|-------|----------------------------|----------------------|
| Локально (Vite) | `VITE_PROXY_TARGET=http://127.0.0.1:<порт-gateway>`. **`VITE_API_BASE_URL` не задавайте.** | Запросы вида `apiFetch('/api/v1/...')` → dev-сервер, Vite проксирует `/api` → gateway. |
| Продакшен | `VITE_API_BASE_URL=https://<хост-gateway>` **без** `/api/v1` | `getApiBaseUrl()` + путь `/api/v1/...`. |

- Клиент: **`apiFetch`** из `@shared/api` — подставляет **`Authorization: Bearer`**.
- В путях **`{id}`** = **`auth_user_id`**, тот же **`id`**, что в **`GET /api/v1/users/me`**.

---

## Профиль: норма часов в неделю

В ответах **`GET /api/v1/users/me`** и **`GET /api/v1/users/{id}`** есть поле **`weekly_capacity_hours`**: `number | null`.

| Ситуация | Поведение на фронте |
|----------|---------------------|
| `null` | Пользователь ещё не в БД учёта времени; в поле ввода можно показать подсказку **35** (часов в неделю). |
| число | Отобразить как текущую норму. |

**Сохранить только себе** (любой авторизованный пользователь):

```http
PATCH /api/v1/users/me/weekly-capacity-hours
Content-Type: application/json

{"weekly_capacity_hours": 40}
```

Ограничения: **0 < weekly_capacity_hours ≤ 168**. При первом сохранении gateway сам создаёт запись в учёте времени по данным из auth.

```ts
await apiFetch('/api/v1/users/me/weekly-capacity-hours', {
  method: 'PATCH',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ weekly_capacity_hours: 40 }),
})
```

---

## Канонические пути

База: **`/api/v1/time-tracking`**.

| Назначение | Метод и путь |
|------------|----------------|
| Список пользователей учёта времени | `GET /api/v1/time-tracking/users` |
| Синхронизация (сервис / админ) | `POST /api/v1/time-tracking/users` |
| Удалить из списка | `DELETE /api/v1/time-tracking/users/{auth_user_id}` |
| Загрузка команды (карточки + таблица) | `GET /api/v1/time-tracking/team-workload?from=YYYY-MM-DD&to=YYYY-MM-DD` |
| Включить архивных в отчёт | `&includeArchived=true` |
| Почасовые ставки (список) | `GET .../users/{id}/hourly-rates?kind=billable` или `kind=cost` |
| Одна ставка | `GET .../users/{id}/hourly-rates/{rateId}` |
| CRUD ставок | `POST`, `PATCH`, `DELETE` на те же ветки пути |
| Записи времени (список за период) | `GET .../users/{id}/time-entries?from=…&to=…` |
| CRUD записей | `POST`, `PATCH`, `DELETE` … `/time-entries` и `…/time-entries/{entryId}` |
| Клиенты time manager (список) | `GET /api/v1/time-tracking/clients` |
| Один клиент | `GET /api/v1/time-tracking/clients/{clientId}` |
| Создать клиента | `POST /api/v1/time-tracking/clients` |
| Изменить клиента | `PATCH /api/v1/time-tracking/clients/{clientId}` |
| Удалить клиента | `DELETE /api/v1/time-tracking/clients/{clientId}` |

**Поля клиента** (в ответе — snake_case; в теле запроса можно **camelCase**): `name`, `address`, `currency` (ISO, напр. `USD`), `invoice_due_mode` / `invoiceDueMode` (напр. `custom`), `invoice_due_days_after_issue` / `invoiceDueDaysAfterIssue` (дней после выставления счёта), `tax_percent` / `taxPercent`, `tax2_percent` / `tax2Percent`, `discount_percent` / `discountPercent` (проценты 0–100).

Ответы по сущностям учёта времени в основном в **snake_case** (как в `time_tracking`).

---

## Примеры TypeScript

### Загрузка команды

```ts
const from = '2026-04-01'
const to = '2026-04-07'
const q = new URLSearchParams({ from, to })
await apiFetch(`/api/v1/time-tracking/team-workload?${q}`)
```

### Запись времени (создание)

Gateway принимает тело с **camelCase**-алиасами (удобно для фронта):

```ts
await apiFetch(`/api/v1/time-tracking/users/${userId}/time-entries`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    workDate: '2026-04-02',
    hours: 7.5,
    isBillable: true,
    projectId: null,
    description: null,
  }),
})
```

### Почасовая ставка (создание)

Тело с `rateKind`, `validFrom`, `validTo` (см. `docs/TIME_TRACKING_HOURLY_RATES.md`).

```ts
await apiFetch(`/api/v1/time-tracking/users/${userId}/hourly-rates`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    rateKind: 'billable',
    amount: '150.00',
    currency: 'USD',
    validFrom: null,
    validTo: null,
  }),
})
```

### Черновик типов (по желанию)

```ts
type WeeklyCapacityHours = number | null

interface UserMeWithCapacity {
  id: number
  email: string
  // … остальные поля профиля из auth
  weekly_capacity_hours: WeeklyCapacityHours
}
```

---

## Алиасы под `/api/v1/users/...`

Если nginx не проксирует `/time-tracking`, часть операций доступна под **`/api/v1/users/{id}/...`**:

| Канон | Алиас |
|-------|--------|
| `…/time-tracking/users/{id}/hourly-rates…` | `…/users/{id}/hourly-rates…` |
| `…/time-tracking/users/{id}/time-entries…` | `…/users/{id}/time-entries…` |

**`team-workload`** только по **`GET /api/v1/time-tracking/team-workload`** — алиаса под `/users` нет.

---

## Права

- **Просмотр** списка пользователей учёта времени, **team-workload**, списков ставок **billable**, **записей времени**, **списка и карточки клиентов**: главный администратор, администратор, партнёр, IT, офис-менеджер.
- **Ставки cost** (себестоимость): просмотр и CRUD — **только** главный администратор и администратор.
- **Создание / изменение / удаление** billable-ставок, **записей времени** и **клиентов**: главный администратор, администратор, партнёр.

---

## Типичные ошибки

| Симптом | Что проверить |
|---------|----------------|
| 503 от Vite «шлюз недоступен» | Запущен ли gateway, верный ли `VITE_PROXY_TARGET`. |
| 401 | Токен, срок действия. |
| 403 | Роль пользователя. |
| 404 на `/time-tracking/...` | Деплой gateway, nginx (должен проксироваться весь `/api/`); для ставок/записей попробовать алиас `/api/v1/users/...`. |
| Пустые ставки у пользователя из auth | Не синхронизирован в учёт времени — нужен `POST /api/v1/time-tracking/users` (или операция на бэкенде). |

---

## Дополнительная документация в репозитории

| Файл | Содержание |
|------|------------|
| `docs/TIME_TRACKING_HOURLY_RATES.md` | Почасовые ставки, интервалы, права |
| `docs/TIME_TRACKING_TEAM_WORKLOAD.md` | Поля ответа team-workload, ёмкость |
| `docs/FRONTEND_CONNECTION.md` | Общая связка фронта с API (не только TT) |
