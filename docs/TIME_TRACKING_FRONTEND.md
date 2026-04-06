# Инструкция для фронтенда: Time Manager / учёт времени

Все запросы идут на **gateway** с префиксом **`/api/v1`**. Микросервис `time_tracking` с браузера **не** вызывается напрямую.

**Оглавление**

1. [Базовый URL и авторизация](#1-базовый-url-и-авторизация)  
2. [Профиль: часы в неделю (нагрузка)](#2-профиль-часы-в-неделю-нагрузка)  
3. [Сводная таблица эндпоинтов](#3-сводная-таблица-эндпоинтов)  
4. [Клиенты time manager (форма «New client»)](#4-клиенты-time-manager-форма-new-client)  
5. [Задачи по клиентам (New task)](#5-задачи-по-клиентам-new-task)  
6. [Примеры TypeScript](#6-примеры-typescript)  
7. [Алиасы `/api/v1/users/...`](#7-алиасы-apiv1users)  
8. [Права по ролям](#8-права-по-ролям)  
9. [Ошибки и отладка](#9-ошибки-и-отладка)  
10. [Документы в репозитории](#10-документы-в-репозитории)

---

## 1. Базовый URL и авторизация

| Режим | Переменные (tickets-front) | Как собирать запрос |
|-------|----------------------------|---------------------|
| Локально (Vite) | `VITE_PROXY_TARGET=http://127.0.0.1:<порт-gateway>`; **`VITE_API_BASE_URL` не задавать** | Относительные пути: `apiFetch('/api/v1/time-tracking/...')` — Vite проксирует `/api` → gateway. |
| Продакшен | `VITE_API_BASE_URL=https://<хост-gateway>` **без** суффикса `/api/v1` | `getApiBaseUrl()` + `'/api/v1/...'`. |

- Используйте **`apiFetch`** из `@shared/api` — подставляется **`Authorization: Bearer`**.
- Идентификатор пользователя в путях учёта времени — **`auth_user_id`**, это тот же **`id`**, что в **`GET /api/v1/users/me`**.

---

## 2. Профиль: часы в неделю (нагрузка)

| Поле в ответе | Где приходит | Поведение UI |
|---------------|--------------|--------------|
| `weekly_capacity_hours` | `GET /api/v1/users/me`, `GET /api/v1/users/{id}` | `number \| null`. Если **`null`** — пользователь ещё не в БД учёта времени; показывайте подсказку **35** ч/нед. |

**Сохранение** (только свой профиль, любой авторизованный пользователь):

```http
PATCH /api/v1/users/me/weekly-capacity-hours
Content-Type: application/json

{"weekly_capacity_hours": 40}
```

Ограничение: **0 < значение ≤ 168**. При первом сохранении gateway создаёт запись в учёте времени.

---

## 3. Сводная таблица эндпоинтов

База для раздела учёта времени: **`/api/v1/time-tracking`**.

| Назначение | Метод и путь |
|------------|----------------|
| Пользователи TT — список | `GET /api/v1/time-tracking/users` |
| Пользователи TT — синхронизация | `POST /api/v1/time-tracking/users` |
| Пользователи TT — удалить | `DELETE /api/v1/time-tracking/users/{auth_user_id}` |
| Загрузка команды | `GET /api/v1/time-tracking/team-workload?from=YYYY-MM-DD&to=YYYY-MM-DD` |
| Архивные в отчёте | добавить `&includeArchived=true` |
| Почасовые ставки | `GET/POST/PATCH/DELETE` … `/users/{id}/hourly-rates` (query `kind=billable` \| `cost` где нужно) |
| Записи времени | `GET/POST/PATCH/DELETE` … `/users/{id}/time-entries` |
| **Клиенты** — список | `GET /api/v1/time-tracking/clients` |
| **Клиенты** — один | `GET /api/v1/time-tracking/clients/{clientId}` |
| **Клиенты** — создать | `POST /api/v1/time-tracking/clients` |
| **Клиенты** — изменить | `PATCH /api/v1/time-tracking/clients/{clientId}` |
| **Клиенты** — удалить | `DELETE /api/v1/time-tracking/clients/{clientId}` → **204** без тела |
| **Задачи клиента** — список | `GET /api/v1/time-tracking/clients/{clientId}/tasks` |
| **Задачи клиента** — одна | `GET /api/v1/time-tracking/clients/{clientId}/tasks/{taskId}` |
| **Задачи клиента** — создать | `POST /api/v1/time-tracking/clients/{clientId}/tasks` |
| **Задачи клиента** — изменить | `PATCH /api/v1/time-tracking/clients/{clientId}/tasks/{taskId}` |
| **Задачи клиента** — удалить | `DELETE /api/v1/time-tracking/clients/{clientId}/tasks/{taskId}` → **204** |

Ответы API в основном в **snake_case**. В **телах запросов** gateway часто принимает **camelCase** (см. примеры ниже).

---

## 4. Клиенты time manager (форма «New client»)

Поля формы и соответствие API:

| Поле на UI | Поле в API (ответ, snake_case) | Поле в теле запроса (удобно camelCase) |
|------------|--------------------------------|--------------------------------------|
| Client name | `name` | `name` |
| Address | `address` | `address` |
| Preferred currency | `currency` | `currency` (ISO 4217, напр. `USD`) |
| Invoice due (режим + N дней) | `invoice_due_mode`, `invoice_due_days_after_issue` | `invoiceDueMode`, `invoiceDueDaysAfterIssue` |
| Tax % | `tax_percent` | `taxPercent` (0–100) |
| Second tax % | `tax2_percent` | `tax2Percent` (0–100, опционально) |
| Discount % | `discount_percent` | `discountPercent` (0–100) |

- Режим счёта: для сценария «Custom + N дней после даты счёта» задайте **`invoiceDueMode`: `"custom"`** и **`invoiceDueDaysAfterIssue`**: число (например **15**).
- После **`POST`** в ответ приходит созданный объект с полем **`id`** (UUID строкой) — сохраните для списка и для **`PATCH`/`DELETE`**.

---

## 5. Задачи по клиентам (New task)

Задачи **разделены по клиентам**: у каждого клиента свой список (`client_id` в БД).

| Назначение | Метод и путь |
|------------|----------------|
| Список задач | `GET /api/v1/time-tracking/clients/{clientId}/tasks` |
| Одна задача | `GET /api/v1/time-tracking/clients/{clientId}/tasks/{taskId}` |
| Создать | `POST /api/v1/time-tracking/clients/{clientId}/tasks` |
| Изменить | `PATCH /api/v1/time-tracking/clients/{clientId}/tasks/{taskId}` |
| Удалить | `DELETE /api/v1/time-tracking/clients/{clientId}/tasks/{taskId}` → **204** |

**Поля** (форма «New task» ↔ API):

| Поле в UI | Ответ (snake_case) | Тело запроса (camelCase) |
|-----------|---------------------|---------------------------|
| Task name | `name` | `name` |
| Default billable rate ($/час) | `default_billable_rate` | `defaultBillableRate` (≥ 0) |
| This task is billable by default | `billable_by_default` | `billableByDefault` |
| Common task → все будущие проекты | `common_for_future_projects` | `commonForFutureProjects` |
| Добавить ко всем существующим проектам | `add_to_existing_projects` | `addToExistingProjects` |

Флаги хранятся в БД. Отдельной сущности «проект» в этом сервисе нет: при появлении интеграции с проектами логику «добавить ко всем проектам» можно выполнить по этим полям.

**Пример:**

```ts
await apiFetch(`/api/v1/time-tracking/clients/${clientId}/tasks`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    name: 'Contract review',
    defaultBillableRate: 150,
    billableByDefault: true,
    commonForFutureProjects: false,
    addToExistingProjects: false,
  }),
})
```

На экране списка задач сначала выберите **клиента** (`clientId` из `GET /clients`), затем грузите **`GET .../clients/{clientId}/tasks`**.

---

## 6. Примеры TypeScript

### Загрузка команды

```ts
const from = '2026-04-01'
const to = '2026-04-07'
const q = new URLSearchParams({ from, to })
await apiFetch(`/api/v1/time-tracking/team-workload?${q}`)
```

### Запись времени (create) — camelCase

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

### Почасовая ставка (create)

Подробности полей — `docs/TIME_TRACKING_HOURLY_RATES.md`.

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

### Клиенты — список и создание

```ts
// Список
const clients = await apiFetch('/api/v1/time-tracking/clients')

// Создание (как форма New client)
await apiFetch('/api/v1/time-tracking/clients', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    name: 'Acme Corp',
    address: '123 Main St',
    currency: 'USD',
    invoiceDueMode: 'custom',
    invoiceDueDaysAfterIssue: 15,
    taxPercent: 10,
    tax2Percent: null,
    discountPercent: 5,
  }),
})
```

### Клиенты — черновик типов

```ts
export interface TimeManagerClient {
  id: string
  name: string
  address: string | null
  currency: string
  invoice_due_mode: string
  invoice_due_days_after_issue: number | null
  tax_percent: string | number | null
  tax2_percent: string | number | null
  discount_percent: string | number | null
  created_at: string
  updated_at: string | null
}

export type WeeklyCapacityHours = number | null

export interface UserMeWithCapacity {
  id: number
  email: string
  weekly_capacity_hours: WeeklyCapacityHours
  // …остальные поля профиля из auth
}
```

*(Проценты с бэка могут приходить как строки из `Decimal` — при необходимости приведите к `Number`.)*

### Профиль — сохранить часы в неделю

```ts
await apiFetch('/api/v1/users/me/weekly-capacity-hours', {
  method: 'PATCH',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ weekly_capacity_hours: 40 }),
})
```

---

## 7. Алиасы `/api/v1/users/...`

Если nginx не отдаёт `/time-tracking`, часть операций продублирована:

| Канонический путь | Алиас |
|-------------------|--------|
| `…/time-tracking/users/{id}/hourly-rates…` | `…/users/{id}/hourly-rates…` |
| `…/time-tracking/users/{id}/time-entries…` | `…/users/{id}/time-entries…` |

**`team-workload`**, **`/clients`** и **`/clients/.../tasks`** доступны **только** под **`/api/v1/time-tracking/...`**.

---

## 8. Права по ролям

| Действие | Кто может |
|----------|-----------|
| Просмотр списка пользователей TT, team-workload, billable-ставок, записей времени, **клиентов**, **задач клиентов** | Главный администратор, Администратор, Партнёр, IT, Офис-менеджер |
| Ставки **cost** (себестоимость) — просмотр и CRUD | Только Главный администратор и Администратор |
| Создание / изменение / удаление billable-ставок, записей времени, **клиентов**, **задач клиентов** | Главный администратор, Администратор, Партнёр |
| **`PATCH /users/me/weekly-capacity-hours`** | Любой авторизованный пользователь (свой профиль) |

---

## 9. Ошибки и отладка

| Симптом | Что проверить |
|---------|----------------|
| 503 от dev-сервера | Запущен ли gateway, верный ли `VITE_PROXY_TARGET` |
| 401 | Токен, срок действия |
| 403 | Роль (см. таблицу выше) |
| 404 на `/time-tracking/...` | Nginx проксирует весь `/api/`; для ставок/записей можно алиас `/api/v1/users/...` |
| 503 с текстом про БД / `weekly_capacity_hours` | На сервере должны быть задеплоены **gateway + time_tracking** и применена схема БД (при старте `time_tracking` таблицы поднимаются сами; при сомнениях — `scripts/` в репозитории) |
| Пустые ставки у пользователя | Пользователь не синхронизирован в учёт времени — `POST /api/v1/time-tracking/users` (или процесс на бэкенде) |

Показывайте пользователю **`detail`** из JSON ответа ошибки, если оно есть — там часто краткая причина.

---

## 10. Документы в репозитории

| Файл | Содержание |
|------|------------|
| `docs/TIME_TRACKING_HOURLY_RATES.md` | Почасовые ставки, интервалы, права |
| `docs/TIME_TRACKING_TEAM_WORKLOAD.md` | Поля ответа team-workload, ёмкость |
| `docs/FRONTEND_CONNECTION.md` | Общая связка фронта с API (не только TT) |
| `docs/TIME_TRACKING_FRONTEND.md` | Эта инструкция (копия: `Docs/time_tracking_frontend.md`) |
