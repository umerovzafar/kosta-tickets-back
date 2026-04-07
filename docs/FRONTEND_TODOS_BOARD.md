# Kanban-доска (todos): краткая справка

**Полная инструкция для подключения фронта:** **`Docs/FRONTEND_TODOS_BOARD_CONNECTION.md`**

Сервис **todos** через **gateway**. Префикс: **`/api/v1/todos/board`**. Доска **одна на пользователя**; при первом `GET` создаётся доска с колонками по умолчанию («Сегодня», «На этой неделе», «Позже»).

**Авторизация:** `Authorization: Bearer <token>`.

| Действие | Метод и путь |
|----------|----------------|
| Доска | `GET /api/v1/todos/board` |
| Фон | `PATCH /api/v1/todos/board` |
| Колонки CRUD + порядок | `POST/PATCH/DELETE .../board/columns...`, `PUT .../columns/reorder` |
| Карточки | `POST .../columns/{id}/cards`, `PATCH/DELETE .../board/cards/{id}`, `PUT .../cards/reorder` |

Общее подключение к API: **`Docs/FRONTEND_CONNECTION.md`**.
