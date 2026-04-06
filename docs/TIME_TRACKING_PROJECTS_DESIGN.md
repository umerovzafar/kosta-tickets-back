# Проекты в Time Tracker: модель и связь с клиентом

## 1. Контекст в репозитории

| Что уже есть | Заметка |
|--------------|---------|
| **`time_tracking_clients`** | Клиенты Time Manager (`GET/POST/PATCH/DELETE …/clients`). |
| **`time_tracking_entries.project_id`** | Поле `VARCHAR(36)` без FK — ссылка на проект задумана, сущности «проект» пока нет. |
| **Микросервис `projects/`** | Отдельная БД `kosta_projects`, **пока без доменных таблиц** (только health). |
| **Модуль `expenses`** | Справочник `GET /api/v1/projects` для заявок — **другой** контекст (проекты расходов), не смешивать с Time Manager без явного решения продукта. |

**Вывод:** связь «клиент ↔ проект» для учёта времени и выбора в формах должна жить **в той же БД, что и клиенты** — в **`time_tracking`**. Тогда:

- FK `project.client_id → time_tracking_clients.id` выполним технически;
- при желании позже добавить FK `time_tracking_entries.project_id → projects.id` (или оставить только проверку в сервисе).

Отдельный микросервис `projects` можно использовать позже для **кросс-модульного** каталога, если понадобится единый ID по всей компании; для текущего экрана Time Manager достаточно таблицы в `time_tracking`.

---

## 2. Доменная сущность «Проект» (по макету)

Проект **принадлежит ровно одному клиенту** Time Manager.

| Поле | Тип | Обязательность | Поведение |
|------|-----|------------------|-----------|
| `id` | UUID (строка 36) | да | PK |
| `client_id` | UUID | да | FK → `time_tracking_clients.id` |
| `name` | string, напр. до 500 символов | да | Название проекта |
| `code` | string, напр. до 64 символов | нет | Код вроде `NSS-05`; лучше **уникален в рамках клиента** среди непустых (без учёта регистра / с trim — по согласованию) |
| `start_date` | date | нет | «Starts on» — **не** жёсткий фильтр для списания времени (как на макете) |
| `end_date` | date | нет | «Ends on» — аналогично |
| `notes` | text | нет | Заметки; видимость по ролям — на стороне UI/политик, в БД храним текст |
| `report_visibility` | enum | да, default | Видимость отчёта по проекту (см. ниже) |
| `created_at`, `updated_at` | timestamptz | да / нет | Аудит |

**Биллинг и бюджет (настройки проекта по макетам):**

| Поле | Тип | Примечание |
|------|-----|------------|
| `project_type` | `time_and_materials` \| `fixed_fee` \| `non_billable` | Вкладки типа проекта |
| `billable_rate_type` | string, nullable | Напр. `person_billable_rate` (дропдаун «Billable rates») |
| `budget_type` | string, nullable | Напр. `no_budget`, `total_project_fees`, `total_project_hours` |
| `budget_amount` | decimal, nullable | Сумма бюджета (валюта клиента / отображение на фронте) |
| `budget_hours` | decimal, nullable | Опционально, если бюджет в часах |
| `budget_resets_every_month` | bool | «Budget resets every month» |
| `budget_includes_expenses` | bool | Расходы в бюджете |
| `send_budget_alerts` | bool | Email-алерты при превышении |
| `budget_alert_threshold_percent` | decimal, nullable | Порог, % (напр. 80) |
| `fixed_fee_amount` | decimal, nullable | Сумма для вкладки Fixed fee («project fees») |

Логика писем и списаний по бюджету на бэкенде не реализована — хранятся настройки для UI и будущих задач.

### Видимость отчёта (`report_visibility`)

Соответствие радиокнопкам на макете:

| Значение | Смысл |
|----------|--------|
| `managers_only` | Отчёт по проекту: администраторам и тем, кто **управляет** проектом (см. раздел «Участники»). |
| `all_assigned` | Отчёт виден **всем, кто на проекте** (назначен). |

Пока **нет** таблицы участников проекта, флаг задаёт **намерение** для UI и будущих проверок; правила «кто управляет» можно уточнить отдельно (роль, membership).

---

## 3. Таблица БД (предложение)

Имя, например: **`time_tracking_client_projects`**.

- Индекс по `client_id` для списков.
- Уникальность **`(client_id, lower(trim(code)))`** для строк с **`code IS NOT NULL`** (PostgreSQL partial unique index), либо мягкая проверка в сервисе.
- При удалении клиента: **`ON DELETE CASCADE`** по проектам — либо запрет удаления клиента с проектами — **решение продукта**.

Связь с временем:

- Вариант A: добавить FK **`time_tracking_entries.project_id` → `time_tracking_client_projects.id`** (nullable остаётся).
- Вариант B: оставить без FK, проверять существование в use-case — проще для поэтапного внедрения.

---

## 4. API (REST, стиль как у задач и категорий расходов)

Префикс микросервиса: **`/clients`**, gateway: **`/api/v1/time-tracking`**.

| Действие | Метод и путь |
|----------|----------------|
| Список проектов клиента | `GET /clients/{client_id}/projects` |
| Один проект | `GET /clients/{client_id}/projects/{project_id}` |
| Создать | `POST /clients/{client_id}/projects` |
| Изменить | `PATCH /clients/{client_id}/projects/{project_id}` |
| Удалить | `DELETE /clients/{client_id}/projects/{project_id}` → **204** (если на проект ссылаются записи времени — **409** или soft-delete — по политике) |
| Подсказка «последний код» | `GET /clients/{client_id}/projects/code-hint` или поле в ответе списка — см. ниже |

Тела запросов — **camelCase** на gateway, в сервисе — snake_case (как у клиентов).

**Подсказка кода:** ответ, например:

```json
{ "last_code": "NSS-05", "suggested_next": "NSS-06" }
```

Логика «следующий» — предмет согласования (инкремент суффикса только если коды однотипны); минимально достаточно вернуть **`last_code`** по последнему созданному/обновлённому проекту клиента с непустым `code`.

---

## 5. Права доступа

Согласовать с остальным Time Manager:

- Просмотр списка/карточки — те же роли, что на **`GET …/clients`** и вложенные ресурсы (см. `docs/TIME_TRACKING_FRONTEND.md`).
- Создание / правка / удаление — как у **`require_manage_role`** для клиентов и задач.

Ограничение «заметки видят только админы и менеджеры проекта» — **в первой версии** можно реализовать только на фронте; сервер отдаёт `notes` только при подходящей роли, если решите усилить это позже.

---

## 6. Фронтенд (чеклист)

1. В форме проекта — **выбор клиента** (`clientId` из `GET /api/v1/time-tracking/clients`); кнопка «+ New client» ведёт на создание клиента, после успеха — подставить `id` в форму проекта.
2. Перед вводом кода — опционально запрос **`code-hint`** для подписи «Last project code: …».
3. Даты и заметки — опциональные поля; валидация `start_date <= end_date`, если оба заданы.
4. Радиокнопки — маппинг в `reportVisibility`: `managersOnly` | `allAssigned` (точные имена — в Pydantic-схемах).
5. После создания проекта сохранять **`project.id`** для привязки записей времени и отчётов.

Документ по клиентам для фронта: **`docs/FRONTEND_TIME_MANAGER_CLIENTS.md`**.

---

## 7. Связь с пустым микросервисом `projects`

Сейчас **`projects`** не содержит бизнес-логики. Варианты на будущее:

- Оставить каталог проектов только в **`time_tracking`**;
- Или синхронизировать событиями в общий каталог — когда появится домен в `kosta_projects`.

До принятия решения **не** дублировать проекты в двух БД без процесса синхронизации.

---

## 8. Внедрение на бэкенде (сделано в репозитории)

1. Модель `TimeManagerClientProjectModel`, таблица `time_tracking_client_projects`, патч `apply_client_projects_schema_patch`, скрипт **`scripts/add_time_tracking_client_projects.sql`**.
2. Репозиторий `ClientProjectRepository`: уникальность `code` по клиенту, подсчёт записей времени для `usage_count` / запрета удаления.
3. Роуты **`time_tracking/presentation/routes/client_projects.py`**, регистрация в **`api.py`** (роутер с вложенными путями до `GET /clients/{client_id}`).
4. Прокси в **gateway** — **`gateway/presentation/routes/time_tracking_routes.py`**, схемы — **`gateway/presentation/schemas/time_manager_client_projects.py`**.
5. Документация: раздел **5.2** в **`docs/TIME_TRACKING_FRONTEND.md`**.
6. FK из **`time_tracking_entries.project_id`** в проекты **не** добавлен (возможны старые «висячие» id); удаление проекта с записями времени — **409**. Связь записи с клиентом — через проект (`project_id` → строка проекта → `client_id`).

---

## 9. Открытые вопросы к продукту

- Удаление клиента: каскадно удалять проекты или блокировать удаление?
- Удаление проекта при наличии **time entries**: запрет, архив или обнуление `project_id`?
- Нужны ли **участники проекта** (кто «на проекте» и кто «управляет») в первой версии API или достаточно флага `report_visibility`?

После ответов можно зафиксировать финальные правила **409**/**DELETE** и схему прав для `notes` и отчётов.
