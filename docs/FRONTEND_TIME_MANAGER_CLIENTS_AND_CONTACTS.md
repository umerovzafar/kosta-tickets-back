# Time Manager: клиенты и контакты — подключение с фронтенда

Инструкция описывает, как вызывать API **клиентов** (billing / time manager) и **дополнительных контактов** через **gateway** (с аутентификацией). Прямые вызовы микросервиса `time_tracking` возможны только в инфраструктурных сценариях; для UI используйте gateway.

---

## Базовые URL

| Вариант | Путь к клиентам |
|--------|------------------|
| **Рекомендуется** | `{GATEWAY}/api/v1/time-tracking/clients` |
| Совместимость с nginx | `{GATEWAY}/api/v1/clients` — middleware gateway переписывает путь на `/api/v1/time-tracking/clients...` |

Подставьте базовый URL вашего gateway (например `https://api.example.com`).

Микросервис `time_tracking` (без gateway): корень сервиса + `/clients` (например `http://time-tracking:8000/clients`). Схемы те же, авторизация на сервисе не дублирует роли gateway.

---

## Права доступа (gateway)

| Операция | Роли |
|----------|------|
| Просмотр: список/карточка клиента, список/карточка контакта | Главный администратор, Администратор, Партнер, IT отдел, Офис менеджер |
| Создание, изменение, удаление клиентов и контактов | Главный администратор, Администратор, Партнер |

При недостаточных правах — **403**.

Передавайте те же заголовки/cookies авторизации, что и для остальных запросов к gateway.

---

## Клиенты

### Модель данных (смысл полей)

- **Идентификация и биллинг**: `id`, `name`, `address`, `currency`, `invoiceDueMode`, `invoiceDueDaysAfterIssue`, налоги/скидки (`taxPercent`, `tax2Percent`, `discountPercent`).
- **Контакты «на карточке клиента»** (одно основное лицо + телефон/почта организации): `phone`, `email`, `contactName`, `contactPhone`, `contactEmail` — хранятся **в самой записи клиента**.
- **Дополнительные контакты** — отдельная сущность; в ответе `GET /clients/{id}` и после create/patch клиента приходят в массиве **`extraContacts`** (полный список по клиенту).
- **Архив**: `isArchived` (`true` — клиент в архиве). Список по умолчанию архивных **не показывает**; см. query ниже.

Имена в JSON ориентируйтесь на **camelCase** (как в OpenAPI у полей с alias). Где в схеме включён `populate_by_name`, сервер также может принимать snake_case.

### Список клиентов

`GET /api/v1/time-tracking/clients`

| Query | По умолчанию | Описание |
|-------|----------------|----------|
| `includeArchived` | `false` | `true` — включить архивных клиентов в список |

Ответ: массив объектов клиента. У записи списка **может не быть** развёрнутого `extraContacts` (зависит от эндпоинта сервиса: список отдаётся без подгрузки контактов). Для полной карточки с контактами используйте `GET .../clients/{clientId}`.

### Карточка клиента

`GET /api/v1/time-tracking/clients/{clientId}`

Ответ включает **`extraContacts`**: все дополнительные контакты клиента.

### Создание клиента

`POST /api/v1/time-tracking/clients`  
Тело JSON — поля из схемы создания (обязательно как минимум `name`). Опционально `isArchived` (по умолчанию `false`).

### Изменение клиента

`PATCH /api/v1/time-tracking/clients/{clientId}`  
Частичное обновление: только передаваемые поля. Для архивации/разархивации: `{ "isArchived": true }` или `false`.

### Удаление клиента

`DELETE /api/v1/time-tracking/clients/{clientId}` — ответ **204** без тела.

### Ошибки

- **404** — клиент не найден.
- **400** — нет полей для обновления (`PATCH` с пустым набором полей).

---

## Архив клиента и вложенные сущности

Если у клиента **`isArchived: true`**:

- **Чтение** разрешено: проекты, задачи, категории расходов, список/карточка доп. контактов, экспорт и т.д.
- **Любые изменения** вложенных ресурсов под этим `clientId` (в т.ч. **POST/PATCH/DELETE доп. контактов**, проектов, задач, категорий расходов) возвращают **400** с пояснением: нужно разархивировать клиента через `PATCH .../clients/{id}` с `isArchived: false`.

Саму карточку клиента (включая `isArchived` и поля биллинга) по-прежнему можно менять через `PATCH /clients/{id}` — это точка, где исправляют архивный статус.

---

## Дополнительные контакты

Отдельный REST-ресурс под клиентом (не путать с полями `contactName` / `contactPhone` / `contactEmail` на клиенте).

| Метод | Путь | Назначение |
|-------|------|------------|
| GET | `/api/v1/time-tracking/clients/{clientId}/contacts` | Список |
| GET | `/api/v1/time-tracking/clients/{clientId}/contacts/{contactId}` | Одна запись |
| POST | `/api/v1/time-tracking/clients/{clientId}/contacts` | Создание |
| PATCH | `/api/v1/time-tracking/clients/{clientId}/contacts/{contactId}` | Изменение |
| DELETE | `/api/v1/time-tracking/clients/{clientId}/contacts/{contactId}` | Удаление (204) |

Тело **создания** (типичные поля): `name` (обязательно), опционально `phone`, `email`, `sortOrder`.  
**PATCH** — только нужные поля; пустой PATCH даёт **400** на стороне сервиса.

Для POST/PATCH/DELETE контактов архивный клиент блокируется (см. раздел выше).

---

## Рекомендуемый порядок работы в UI

1. **Список клиентов** — `GET .../clients` (при переключателе «показать архив» — `includeArchived=true`).
2. **Экран клиента** — `GET .../clients/{id}`: отображаете биллинг, основной контакт с карточки и таблицу **`extraContacts`**.
3. **Редактирование основного контакта и реквизитов** — `PATCH .../clients/{id}` (поля `contactName`, `phone`, и т.д.).
4. **CRUD доп. контактов** — отдельные запросы к `.../contacts` и `.../contacts/{contactId}`; после изменений можно обновить карточку клиента или локально обновить кэш списка `extraContacts`.
5. **Архивация** — `PATCH .../clients/{id}` с `isArchived: true`; скрыть клиента из основного списка или оставить видимым только при `includeArchived=true`. Перед операциями «добавить проект / контакт / …» проверяйте `isArchived` и при `true` не давайте сохранять без разархивации (сервер всё равно вернёт 400).

---

## Где смотреть контракт в коде бэкенда

- Сервис `time_tracking`: роуты `presentation/routes/clients.py`, `presentation/routes/client_contacts.py`, схемы `presentation/schemas.py`.
- Gateway: префикс роутера `presentation/routes/time_tracking_routes.py` (`/api/v1/time-tracking`), схемы тел запросов `gateway/presentation/schemas/time_manager_clients.py`, `time_manager_client_contacts.py`.
- Перепись пути `/api/v1/clients` → time-tracking: `gateway/presentation/middleware/time_tracking_clients_rewrite.py`.

При изменении полей на бэкенде сверяйте типы и обязательность с этими файлами и с OpenAPI (`/docs` у gateway и у сервиса).
