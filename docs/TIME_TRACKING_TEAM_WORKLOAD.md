# Загрузка команды (карточки + таблица)

## Данные

- **Ёмкость** сотрудника: поле `weekly_capacity_hours` у пользователя учёта времени (по умолчанию **35** часов в неделю). Задаётся при синхронизации (`POST /api/v1/time-tracking/users`, поле `weekly_capacity_hours`) или в БД.
- **Записи времени** — таблица `time_tracking_entries`: дата, часы, признак `is_billable` (оплачиваемые / неоплачиваемые).

Ёмкость **за выбранный период** считается как  
`weekly_capacity_hours × (число дней в периоде / 7)`.

## API (gateway)

### Агрегат для страницы

```http
GET /api/v1/time-tracking/team-workload?from=YYYY-MM-DD&to=YYYY-MM-DD
Authorization: Bearer …
```

Query:

| Параметр | Описание |
|----------|----------|
| `from` | Начало периода (включительно) |
| `to` | Конец периода (включительно) |
| `includeArchived` | Опционально `true` — включить архивных в таблицу |

Права: те же, что на просмотр списка пользователей учёта времени (администраторы, партнёр, IT, офис-менеджер).

**Ответ** (JSON, snake_case):

- `date_from`, `date_to`, `period_days`
- `summary`: `total_hours`, `team_capacity_hours`, `billable_hours`, `non_billable_hours`, `team_workload_percent` (0–100)
- `members[]`: по каждому сотруднику — `auth_user_id`, `display_name`, `email`, `capacity_hours`, `total_hours`, `billable_hours`, `non_billable_hours`, `workload_percent`

Архивные и заблокированные по умолчанию в расчёт **не** входят.

### Записи времени (CRUD)

Базовый путь (через gateway):

```http
GET    /api/v1/time-tracking/users/{auth_user_id}/time-entries?from=…&to=…
POST   /api/v1/time-tracking/users/{auth_user_id}/time-entries
PATCH  /api/v1/time-tracking/users/{auth_user_id}/time-entries/{entry_id}
DELETE /api/v1/time-tracking/users/{auth_user_id}/time-entries/{entry_id}
```

Те же пути доступны под алиасом **`/api/v1/users/{id}/...`**, если удобнее для nginx.

- **GET** — просмотр (роли как у списка пользователей).
- **POST / PATCH / DELETE** — роли модерации (главный администратор, администратор, партнёр).

Тело **POST** (можно camelCase с фронта):

```json
{
  "workDate": "2026-04-01",
  "hours": "8.0",
  "isBillable": true,
  "projectId": null,
  "description": null
}
```

## Миграция БД

Если база уже создана до этой фичи, выполните скрипт:

`scripts/add_time_tracking_team_workload.sql`

Новые развёртывания поднимают таблицы через `create_all` при старте сервиса `time_tracking`.
