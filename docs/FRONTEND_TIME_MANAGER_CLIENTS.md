# Фронтенд: клиенты Time Manager (задачи и категории расходов)

Отдельный чеклист по разделу **клиентов** в учёте времени: что сделать в UI и как ходить в API. Общая схема подключения к gateway: **`docs/FRONTEND_CONNECTION.md`**. Полная таблица эндпоинтов учёта времени: **`docs/TIME_TRACKING_FRONTEND.md`**.

База путей для этого раздела: **`/api/v1/time-tracking`**. Микросервис `time_tracking` с браузера **не** вызывается напрямую.

---

## 1. Обязательная инфраструктура на фронте

| Задача | Детали |
|--------|--------|
| Базовый URL | Локально: относительные пути + Vite proxy на gateway. Прод: `VITE_API_BASE_URL` = origin gateway **без** суффикса `/api/v1`. |
| Авторизация | Все запросы с **`Authorization: Bearer`** (как в остальном приложении, например через `apiFetch`). |
| Префикс API | Строки вида `'/api/v1/time-tracking/clients'` и вложенные пути (см. ниже). |

---

## 2. Права (роли)

| Действие в UI | Кто может |
|---------------|-----------|
| Просмотр списка клиентов, карточки клиента, задач, категорий расходов | Главный администратор, Администратор, Партнёр, IT отдел, Офис-менеджер |
| Создание / редактирование / удаление клиента, задач, категорий расходов | Главный администратор, Администратор, Партнёр |

**На фронте:** скрывайте кнопки «Создать / Сохранить / Удалить / Архивировать», если роль не из второй строки; при **403** показывайте понятное сообщение (текст из `detail` в ответе, если есть).

---

## 3. Клиенты (CRUD)

### Чеклист экранов и действий

| № | Что сделать | API |
|---|-------------|-----|
| 1 | Страница или блок **списка клиентов** (сортировка по имени удобна; на бэке порядок не зафиксирован — можно сортировать на клиенте). | `GET /api/v1/time-tracking/clients` |
| 2 | **Создание** клиента (форма «New client»): имя, адрес, валюта, режим счёта и срок оплаты, налоги и скидка. | `POST /api/v1/time-tracking/clients` |
| 3 | **Просмотр / редактирование** одного клиента. | `GET` и `PATCH /api/v1/time-tracking/clients/{clientId}` |
| 4 | **Удаление** клиента (подтверждение в UI). Успех: **204** без тела. | `DELETE /api/v1/time-tracking/clients/{clientId}` |
| 5 | После **POST** сохранить **`id`** (UUID строка) — нужен для перехода к задачам и категориям расходов. | из тела ответа |

### Поля формы (ответ — `snake_case`, тело запроса — удобно `camelCase`)

| UI | Ответ | Тело запроса |
|----|-------|--------------|
| Название | `name` | `name` |
| Адрес | `address` | `address` |
| Валюта | `currency` | `currency` (ISO 4217) |
| Счёт: режим и дни | `invoice_due_mode`, `invoice_due_days_after_issue` | `invoiceDueMode`, `invoiceDueDaysAfterIssue` |
| Налог 1 / 2, скидка % | `tax_percent`, `tax2_percent`, `discount_percent` | `taxPercent`, `tax2Percent`, `discountPercent` |

Сценарий «Custom + N дней после даты счёта»: `invoiceDueMode: "custom"`, `invoiceDueDaysAfterIssue: <число>`.

### Ошибки

| Код | Что сделать в UI |
|-----|------------------|
| 403 | Нет прав — только просмотр или скрыть раздел. |
| 404 | Клиент не найден (устаревший `clientId` в URL) — редирект на список или сообщение. |

---

## 4. Задачи по клиенту (вложенный справочник)

Задачи **привязаны к клиенту**: у каждого клиента свой список. Сначала пользователь выбирает клиента (`clientId`), затем загружаются задачи.

| № | Что сделать | API |
|---|-------------|-----|
| 1 | Список задач на экране клиента или отдельной вкладке. | `GET /api/v1/time-tracking/clients/{clientId}/tasks` |
| 2 | Создание задачи (форма «New task»). | `POST /api/v1/time-tracking/clients/{clientId}/tasks` |
| 3 | Редактирование задачи. | `PATCH /api/v1/time-tracking/clients/{clientId}/tasks/{taskId}` |
| 4 | Удаление задачи. Успех: **204**. | `DELETE /api/v1/time-tracking/clients/{clientId}/tasks/{taskId}` |
| 5 | (Опционально) Загрузка одной задачи по id. | `GET .../tasks/{taskId}` |

### Поля задачи

| UI | Ответ | Тело (camelCase) |
|----|-------|-------------------|
| Название задачи | `name` | `name` |
| Ставка по умолчанию ($/час) | `default_billable_rate` | `defaultBillableRate` |
| Billable по умолчанию | `billable_by_default` | `billableByDefault` |
| Общая задача для будущих проектов | `common_for_future_projects` | `commonForFutureProjects` |
| Добавить к существующим проектам | `add_to_existing_projects` | `addToExistingProjects` |

### Ошибки

| Код | Поведение |
|-----|-----------|
| 404 | `Client not found` — клиента нет в БД учёта времени; проверить `clientId` и что клиент создан через `POST /clients`. |
| 400 на PATCH | Пустое тело обновления — не отправлять пустой `PATCH`. |

---

## 5. Категории расходов по клиенту

Справочник для биллинга: **название**, флаг **цена за единицу**, **архив**, удаление только если нет использований.

| № | Что сделать | API |
|---|-------------|-----|
| 1 | Список для выпадающих списков / форм (только активные). | `GET .../expense-categories` без query или `includeArchived=false` |
| 2 | Экран настроек с архивными: показать архивные строки. | `GET .../expense-categories?includeArchived=true` |
| 3 | Создание категории («New category»). | `POST .../expense-categories` |
| 4 | Редактирование (включая перевод в архив: `isArchived: true`). | `PATCH .../expense-categories/{categoryId}` |
| 5 | Удаление — только если кнопка активна (`deletable === true`). | `DELETE .../expense-categories/{categoryId}` |

Полный путь:  
`/api/v1/time-tracking/clients/{clientId}/expense-categories`  
и при необходимости `/{categoryId}`.

### Поля

| UI | Ответ | Тело (camelCase) |
|----|-------|------------------|
| Название | `name` | `name` |
| «Есть цена за единицу» | `has_unit_price` | `hasUnitPrice` |
| Архив | `is_archived` | `isArchived` (в `PATCH`) |
| Порядок сортировки | `sort_order` | `sortOrder` |
| Сколько раз использована (для кнопки Delete) | `usage_count` | — |
| Можно ли удалить | `deletable` | — |

Если **`usage_count > 0`**, бэкенд вернёт **409** на `DELETE` — в UI кнопку «Удалить» лучше отключать при `!deletable`.

Конфликт имени у двух активных категорий одного клиента — **409** (и при создании, и при снятии с архива).

---

## 6. Маршрутизация SPA (рекомендация)

| Маршрут | Назначение |
|---------|------------|
| `/time-manager/clients` или аналог | Список клиентов |
| `/time-manager/clients/new` | Создание |
| `/time-manager/clients/:clientId` | Карточка / редактирование |
| `/time-manager/clients/:clientId/tasks` | Задачи (или вкладка в карточке) |
| `/time-manager/clients/:clientId/expense-categories` | Категории расходов (или вкладка) |

Имена путей на ваше усмотрение; важно хранить **`clientId`** из API.

---

## 7. Типы TypeScript (черновик)

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

export interface TimeManagerClientTask {
  id: string
  client_id: string
  name: string
  default_billable_rate: string | number | null
  billable_by_default: boolean
  common_for_future_projects: boolean
  add_to_existing_projects: boolean
  created_at: string
  updated_at: string | null
}

export interface TimeManagerClientExpenseCategory {
  id: string
  client_id: string
  name: string
  has_unit_price: boolean
  is_archived: boolean
  sort_order: number | null
  usage_count: number
  deletable: boolean
  created_at: string
  updated_at: string | null
}
```

Проценты и денежные поля с бэка иногда приходят строками из `Decimal` — при необходимости нормализуйте в числа на границе API.

---

## 8. Отладка

| Симптом | Проверка |
|---------|----------|
| 404 на `.../clients/.../tasks` | Прокси nginx: путь до gateway должен сохранять `/api/v1/time-tracking/...` (см. **`docs/FRONTEND_CONNECTION.md`**, раздел про nginx). На gateway есть перепись `/api/v1/clients/...` → `.../time-tracking/...` для старых конфигов. |
| 404 + `Client not found` | Клиент не создан в учёте времени или неверный UUID. |
| 503 | Не настроен или недоступен сервис учёта времени на gateway (`TIME_TRACKING_SERVICE_URL`). |

---

## 9. Краткий список «всё по клиентам»

1. Подключить вызовы к **`/api/v1/time-tracking`** с Bearer-токеном.  
2. Реализовать **список / создание / просмотр / правка / удаление** клиента.  
3. Для выбранного **`clientId`** — **задачи**: список, CRUD.  
4. Для того же **`clientId`** — **категории расходов**: список (с опцией архива), создание, правка (включая архив), удаление с учётом `deletable`.  
5. Ограничить действия по **ролям** (просмотр vs управление).  
6. Обработать **403 / 404 / 409** и показывать `detail` пользователю.

После реализации имеет смысл прогнать сценарии под учётными записями с ролями «Офис-менеджер» (только чтение по таблице) и «Администратор» (полный CRUD).
