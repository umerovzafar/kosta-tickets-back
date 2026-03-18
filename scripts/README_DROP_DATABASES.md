# Очистка всех баз данных

Во всех БД проекта удаляются **только таблицы** (данные). Сами базы и тома не удаляются. После перезапуска сервисов таблицы создаются заново с актуальной схемой (create_all при старте).

## Быстрый способ (Docker Compose)

Из корня репозитория, при **запущенных** контейнерах:

```bash
bash scripts/drop_all_databases.sh
```

Затем перезапустите сервисы приложений:

```bash
docker compose restart auth tickets notifications inventory attendance todos time_tracking gateway
```

## Ручной способ (по одной БД)

Подставьте свои имя контейнера, пользователя и БД (по умолчанию — из docker-compose.yml):

| Сервис БД        | Контейнер         | Пользователь   | БД                 |
|------------------|-------------------|----------------|--------------------|
| users_db         | users_db          | gateway        | kosta_users        |
| tickets_db       | tickets_db        | tickets        | kosta_tickets      |
| notifications_db | notifications_db  | notifications  | kosta_notifications |
| inventory_db     | inventory_db      | inventory      | kosta_inventory    |
| attendance_db    | attendance_db     | attendance     | kosta_attendance   |
| todos_db         | todos_db          | todos          | kosta_todos        |
| time_tracking_db | time_tracking_db  | time_tracking  | kosta_time_tracking |

Пример (users_db):

```bash
cat scripts/drop_users_db_tables.sql | docker compose exec -T users_db psql -U gateway -d kosta_users
```

## Windows (PowerShell)

Если `docker compose exec` недоступен, выполните SQL вручную в каждой БД (через pgAdmin, DBeaver или `docker compose exec users_db psql -U gateway -d kosta_users` и вставьте содержимое соответствующего `.sql` из папки `scripts/`).

Или в Git Bash: `bash scripts/drop_all_databases.sh`.

## Что удаляется

- **users_db**: roles, role_permissions, users (auth)
- **tickets_db**: ticket_comments, tickets
- **notifications_db**: notifications
- **inventory_db**: inventory_items, inventory_categories
- **attendance_db**: attendance_settings
- **todos_db**: outlook_calendar_tokens
- **time_tracking_db**: time_tracking_users

После очистки нужно заново войти (Microsoft или admin-login), создать тикеты и т.д.
