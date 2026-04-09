# Расходы: статусы, вложения и согласование с фронтом

Каноника для сервиса `expenses` и gateway `/api/v1/expenses/*`. Сверка с фронтом: `tickets-front` (`expenseStatusPolicy.ts`, `ExpensesPage.tsx`, `ExpensesFormPanel.tsx`).

## Статусы заявки

Используются коды: `draft`, `pending_approval`, `revision_required`, `approved`, `rejected`, `paid`, `closed`, `not_reimbursable`, `withdrawn`.

## Вложения: `attachmentKind`

| Значение            | Назначение              |
|---------------------|-------------------------|
| `payment_document`  | Документ для оплаты     |
| `payment_receipt`   | Квитанция / чек оплаты  |

### Квитанция (`payment_receipt`)

Разрешена в статусах: **draft**, **revision_required**, **pending_approval**, **approved**, **paid**, **not_reimbursable** — чтобы фронт мог грузить файлы сразу после `POST`/`PUT` (до submit) и в просмотре заявки.

Запрещена в: **rejected**, **closed**, **withdrawn** (новые загрузки).

После статуса **paid** добавлять можно **только** `payment_receipt` (не `payment_document`).

### Документ для оплаты (`payment_document`)

Разрешён в: **draft**, **revision_required**, **pending_approval**, **approved**.

Для статуса **not_reimbursable** загрузка `payment_document` не предусмотрена (невозмещаемая заявка).

### Кто может грузить / удалять

- **Автор** — по правилам статуса и вида вложения.
- **Модератор** — в статусах **pending_approval**, **approved**, **paid**, **not_reimbursable** (в т.ч. квитанция), с проверкой «не своя заявка» (`ensure_not_moderating_own_expense`).
- **Редактор-админ** (роль из deps) — без ограничений по статусу.

## Отправка на согласование (`submit`)

- **Возмещаемый** (`isReimbursable: true`): обязательны **projectId**, документ для оплаты (или старое вложение без kind), для типа **other** — **comment**. Квитанция на submit **не** обязательна.
- **Невозмещаемый** (`isReimbursable: false`): **projectId**, обязательный `payment_document` и **comment** для **other** **не** требуются.

## Тип `partner_expense`

Обязателен **expenseSubtype** из whitelist:

`partner_fuel`, `partner_air`, `partner_meetings_food`, `partner_shop`, `partner_misc`

Тип добавлен в справочник `GET /expense-types` при сидировании БД; для уже существующих БД запись появится при следующем запуске сида (идемпотентно).
