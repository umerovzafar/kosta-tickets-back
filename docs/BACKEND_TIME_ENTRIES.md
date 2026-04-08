# Записи времени по проектам (бэкенд)

Согласовано с `tickets-front/BACKEND_TIME_ENTRIES.md`. Для фронта см. **`docs/FRONTEND_TIME_TRACKING.md`**. Ниже — кратко по реализации в `tickets-back`.

## Gateway (`/api/v1/time-tracking/...` и зеркало `/api/v1/users/...`)

- **GET** списка записей: свой `auth_user_id` — любой авторизованный пользователь; чужие — роли офиса (как раньше для просмотра TT) или **менеджер** учёта времени в сервисе TT.
- **POST / PATCH / DELETE**: свой `auth_user_id` — любой авторизованный пользователь (сохранение времени с **projectId** в теле запроса); чужие — **Главный администратор / Администратор / Партнер** или **менеджер** TT.

Так фронт может вызывать `createTimeEntry` / `patchTimeEntry` с `projectId` для текущего пользователя без админской роли в auth.

## Сервис `time_tracking`

- Тело POST/PATCH принимает **camelCase** (`workDate`, `projectId`, `isBillable`, …) и **snake_case**.
- Если передан непустой `project_id`: проект **должен существовать** в `time_tracking_client_projects`; **архивные** проекты отклоняются (**400**).
- Далее — проверка **project-access**: `project_id` должен быть в выданном списке (**403** при отказе).
- Пустая строка в `projectId` приводится к отсутствию проекта (`null`).

## Связанные файлы

- Gateway: `gateway/presentation/routes/time_tracking_routes.py` (`require_time_entry_read` / `require_time_entry_write`), алиас `time_tracking_users_hourly_alias.py`.
- TT: `time_tracking/presentation/routes/time_entries.py`, схемы `TimeEntryCreateBody` / `TimeEntryPatchBody`.
- Доступ к проектам: `docs/time-tracking-project-access-frontend.md`.
