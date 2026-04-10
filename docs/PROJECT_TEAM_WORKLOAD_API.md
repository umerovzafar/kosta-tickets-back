# API загрузки команды по проекту (экран как «Учёт времени → Сотрудники»)

Документ описывает **все запросы и данные** для UI с четырьмя карточками (всего часов, ёмкость команды, оплачиваемые, неоплачиваемые), полосой «Загрузка команды» и таблицей сотрудников (часы, загрузка %, ёмкость, оплачиваемые часы).

## 1. Глобальная загрузка (все проекты)

Уже реализовано.

| Метод | Путь (gateway) | Назначение |
|--------|----------------|------------|
| GET | `/api/v1/time-tracking/team-workload` | Команда целиком за период |

**Query (обязательные):**

- `from` — дата начала периода, `YYYY-MM-DD`
- `to` — дата конца периода включительно, `YYYY-MM-DD`

**Query (опционально):**

- `includeArchived` — `true` / `false` (по умолчанию `false`): включать архивных пользователей TT в строки и ёмкость

**Ответ:** объект `TeamWorkloadOut` (см. §3). Поля `project_id`, `client_id`, `project_name` — **null** / отсутствуют.

**Правила:**

- Часы суммируются по **всем** записям времени пользователя за период (все проекты).
- Ёмкость строки: `weekly_capacity_hours × (дней в периоде / 7)` из профиля пользователя в TT.
- `% загрузки` строки: `total_hours / capacity_hours`, не выше 100%.
- Итоги карточек — суммы по отфильтрованным строкам таблицы.

---

## 2. Загрузка по одному проекту

Нужно для вкладки **«Команда»** на странице проекта и любых отчётов «кто работал на проекте X».

| Метод | Путь (gateway) |
|--------|----------------|
| GET | `/api/v1/time-tracking/clients/{clientId}/projects/{projectId}/team-workload` |

**Query:** те же `from`, `to`, опционально `includeArchived`.

**Проверки:**

- Клиент существует; при архивном клиенте чтение разрешено (как для карточки проекта).
- Проект принадлежит этому `clientId`. Иначе **404** `Project not found`.
- `to` не раньше `from` — иначе **400**.

**Ответ:** тот же контракт `TeamWorkloadOut`, плюс контекст проекта:

- `project_id` — UUID проекта  
- `client_id` — UUID клиента  
- `project_name` — название проекта  

**Состав строк таблицы (`members`):**

1. Все пользователи, у которых в `time_tracking_user_project_access` есть пара `(auth_user_id, project_id)`.
2. Плюс все пользователи, у которых за период `[from, to]` есть хотя бы одна запись времени с `project_id` (даже если доступа в матрице нет — чтобы не терять фактические часы).

Дальше применяются те же фильтры, что и глобально: не заблокированные; архивные TT исключаются, если `includeArchived=false`. Пользователи без строки в `time_tracking_users` (только id в access) в таблицу **не попадают**.

**Часы в строке:** только суммы по записям с **этим** `project_id` за период.  
**Ёмкость и % загрузки:** считаются так же, как в глобальном отчёте (ёмкость за весь период, не «только дни с часами»).

**Карточки и полоса:** агрегаты только по этим часам и ёмкостям участников списка (не по всей фирме).

---

## 3. Контракт JSON (`TeamWorkloadOut`)

Имена полей — как в ответе FastAPI (snake_case). При необходимости фронт мапит в camelCase.

```json
{
  "date_from": "2026-04-01",
  "date_to": "2026-04-30",
  "period_days": 30,
  "summary": {
    "total_hours": "120.5",
    "team_capacity_hours": "175.0",
    "billable_hours": "100.0",
    "non_billable_hours": "20.5",
    "team_workload_percent": 69
  },
  "members": [
    {
      "auth_user_id": 42,
      "display_name": "Иван Иванов",
      "email": "ivan@example.com",
      "picture": "https://…",
      "capacity_hours": "35.0",
      "total_hours": "24.0",
      "billable_hours": "20.0",
      "non_billable_hours": "4.0",
      "workload_percent": 69
    }
  ],
  "project_id": "uuid-or-null",
  "client_id": "uuid-or-null",
  "project_name": "Название или null"
}
```

- Числовые поля с часами сериализуются как **строки с десятичной частью** (Decimal), фронт приводит к `number`.
- `picture` — URL аватара из профиля TT; может быть `null`.
- `team_workload_percent` в `summary` — отношение суммарных часов к суммарной ёмкости команды (как на полосе «Загрузка команды»).

---

## 4. Связь с другими эндпоинтами

| Задача UI | Запрос |
|-----------|--------|
| Список проектов клиента | `GET …/clients/{clientId}/projects` |
| Карточка проекта | `GET …/clients/{clientId}/projects/{projectId}` |
| Дашборд проекта (графики, задачи, счета) | `GET …/projects/{projectId}/dashboard` |
| Команда проекта за период | `GET …/projects/{projectId}/team-workload?from=&to=` |
| Редактирование «кому доступен проект» | `GET/PUT …/users/{authUserId}/project-access` (список `project_ids`) |

Период `from`/`to` на экране команды проекта нужно задавать явно (например текущий месяц, квартал, произвольный диапазон) и передавать в query.

---

## 5. Реализация в репозитории

- `TimeEntryRepository.aggregate_by_user_for_project(from, to, project_id)`
- `TimeEntryRepository.list_auth_users_with_entries_on_project(from, to, project_id)`
- `UserProjectAccessRepository.list_auth_user_ids_for_project(project_id)`
- Сервис: `time_tracking/application/project_team_workload.py` → `compute_project_team_workload`
- Роут: `time_tracking/presentation/routes/client_projects.py`
- Прокси gateway: `gateway/presentation/routes/time_tracking_routes.py`
