# Доступ к проектам (frontend)

Полная инструкция по подключению фронта ко всему учёту времени: **`docs/FRONTEND_TIME_TRACKING.md`**.

## API (через gateway)

- **GET** `/api/v1/time-tracking/users/{auth_user_id}/project-access`  
  Ответ: `{ "projectIds": ["uuid", ...] }` (допустим также `project_ids`).

- **PUT** `/api/v1/time-tracking/users/{auth_user_id}/project-access`  
  Тело: `{ "projectIds": ["uuid", ...] }` — **полная замена** списка.  
  `grantedByAuthUserId` подставляет gateway.

Права см. `require_view_project_access` / `require_manage_project_access` в `gateway/presentation/routes/time_tracking_routes.py`.

## Реализация в tickets-front

- Методы: `getUserProjectAccess`, `putUserProjectAccess`, `listAllClientProjectsForPicker` в `@entities/time-tracking`.
- UI: страница учёта времени → таблица сотрудников → **Действия** → **Доступ к проектам** (`TimeUserProjectAccessModal`).
- Сохранение доступно, если `canManageUserProjectAccess(role, time_tracking_role)` — админы/партнёр или роль **manager** в учёте времени.
