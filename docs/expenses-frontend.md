# Расходы: API и фронт

- Подробные правила статусов и вложений: **[expenses-frontend-statuses.md](./expenses-frontend-statuses.md)**.
- Интеграция после усиления auth/CORS: **[FRONTEND_SECURITY_INTEGRATION.md](./FRONTEND_SECURITY_INTEGRATION.md)**.

## Базовые пути (через gateway)

- Заявки: `/api/v1/expenses`, `/api/v1/expenses/{id}`, `POST .../submit`, модерация, вложения.
- Справочники (корень `/api/v1`): `/expense-types`, `/departments`, `/projects`, `/exchange-rates`.

## Тело создания / обновления

Поля в camelCase или snake_case (см. Pydantic-схемы). Для **`partner_expense`** всегда передавайте **`expenseSubtype`** из whitelist из документа по статусам.

## Вложения

`POST /api/v1/expenses/{id}/attachments` — multipart, поле **`attachmentKind`**: `payment_document` | `payment_receipt`.
