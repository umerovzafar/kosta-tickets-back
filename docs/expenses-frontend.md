# Подключение фронтенда к модулю «Расходы»

> **Дубль для фронт-репозитория:** `tickets-front/docs/expenses-api-connection.md` и ТЗ контракта `tickets-front/TZ-expenses-backend.md`. При правках этого файла по возможности синхронизируйте копию во фронте.

Фронтенд **не** обращается к микросервису `expenses` напрямую (порт 1242 доступен только внутри Docker-сети). Все запросы идут через **gateway** по публичному URL API.

---

## 1. Архитектура

```
Браузер (SPA)  →  https://<ваш-api-домен>  →  gateway :1234  →  http://expenses:1242
```

- Базовый путь API на gateway: **`/api/v1`**
- Расходы: **`/api/v1/expenses`**, справочники: **`/api/v1/expense-types`**, **`/api/v1/projects`**, **`/api/v1/exchange-rates?date=YYYY-MM-DD`** (и др. — см. `gateway/presentation/routes/expenses_routes.py`)

---

## 2. Переменные окружения бэкенда (gateway)

В `.env` репозитория `tickets-back` для gateway должны быть согласованы с тем, откуда открывается SPA:

| Переменная | Назначение |
|------------|------------|
| **`GATEWAY_BASE_URL`** | Публичный URL API (OAuth redirect, ссылки). Прод: `https://ticketsback.kostalegal.com` |
| **`FRONTEND_URL`** | Origin SPA для **CORS**. Прод: `https://tickets.kostalegal.com` |
| **`EXPENSES_SERVICE_URL`** | Внутри Docker: `http://expenses:1242` (не подставлять в фронт) |

После изменения `.env` перезапустите gateway: `docker compose up -d gateway`.

Если CORS блокирует запросы — проверьте, что **`FRONTEND_URL`** точно совпадает с origin в браузере (схема, хост, порт, без лишнего слэша).

---

## 3. Настройка фронтенда (Vite / env)

**Вариант A — прямой URL API** (удобно без прокси):

В `.env` фронта (или `.env.production`):

```env
VITE_API_URL=https://ticketsback.kostalegal.com
```

В коде запросов использовать этот base URL + пути `/api/v1/expenses`, …

**Вариант B — прокси в `vite.config`**: запросы с dev-сервера идут на `http://127.0.0.1:1234`, в браузере остаётся `localhost:5173` — см. комментарии в `.env.example` бэкенда (`vite.config.example.ts` в корне монорепо, если есть).

---

## 4. Авторизация

Все эндпоинты расходов на gateway **требуют** заголовок:

```http
Authorization: Bearer <access_token>
```

Токен тот же, что для остального приложения (вход через Azure AD / ваш auth). Без токена — **401**.

---

## 5. Примеры URL (production)

Если API: `https://ticketsback.kostalegal.com`:

- Список: `GET https://ticketsback.kostalegal.com/api/v1/expenses?skip=0&limit=50`
- Создание: `POST https://ticketsback.kostalegal.com/api/v1/expenses`
- Типы: `GET https://ticketsback.kostalegal.com/api/v1/expense-types`
- Курс: `GET https://ticketsback.kostalegal.com/api/v1/exchange-rates?date=2026-04-02`

Контракт полей (camelCase / деньги) согласован с ТЗ и нормализацией на фронте (`coerceExpense.ts` и см. `TZ-expenses-backend.md` во фронт-репозитории).

### Автор заявки

В ответах списка и карточки заявки добавлено поле **`createdBy`** (объект):

- `id` — тот же смысл, что и `createdByUserId`
- `displayName`, `email`, опционально `picture`, `position` — подтягиваются из **auth** (`GET /users/{id}` тем же Bearer-токеном)

Если auth недоступен или профиль не найден, `createdBy` всё равно есть: заполняется **`id`**, остальные поля могут быть `null`.

**Фронт (SPA):** поле нормализуется в `expenseAuthor.ts` / `coerceExpense.ts`; отображается в **карточках** списка заявок (сетка), в боковой панели заявки и в Excel-отчёте (репозиторий `tickets-front`).

### Почта модераторам

Письма рассылает микросервис **`expenses`** (SMTP и все перечисленные переменные — в **окружении контейнера/процесса `expenses`**, не gateway). Подробные комментарии и примеры — в **`tickets-back/.env.example`**, код — `expenses/infrastructure/expense_submit_mail.py`.

| Вопрос | Ответ |
|--------|--------|
| **Когда уходит письмо** | Только при **`POST /api/v1/expenses/{id}/submit`** (заявка переходит на согласование). При **`POST /api/v1/expenses`** (черновик) письмо **не** отправляется. |
| **Вкл/выкл** | **`EXPENSE_NOTIFY_ON_SUBMIT`** (по умолчанию `true`). |
| **Кому** | **`EXPENSE_NOTIFY_TO`** — один или несколько адресов через **запятую**. |
| **SMTP** | Нужны **`EXPENSE_SMTP_HOST`**, **`EXPENSE_SMTP_USER`**, **`EXPENSE_SMTP_PASSWORD`** (и при необходимости порт **`EXPENSE_SMTP_PORT`**, **`EXPENSE_SMTP_USE_TLS`**). Отправитель: **`EXPENSE_MAIL_FROM`** или учётная запись SMTP. Без полного набора в логах `expenses` будет предупреждение `expense notify:` и письмо не уйдёт. |
| **Ссылка «открыть в приложении»** | **`FRONTEND_URL`** — тот же origin, что и для CORS SPA (без лишнего слэша в конце). Опционально **`EXPENSE_NOTIFY_LINK_TEMPLATE`**: плейсхолдеры `{frontend_url}`, `{expense_id}` (для hash-router, например: `{frontend_url}/#/expenses/{expense_id}`). |
| **Кнопки без входа в SPA** | Задайте публичный URL API **`GATEWAY_BASE_URL`** (как в браузере, без завершающего `/`) и секрет **`EXPENSE_EMAIL_ACTION_SECRET`**. В письме — кнопки **Утвердить** / **Отклонить** → **`GET /api/v1/expenses/{id}/email-action?token=...&confirm=1`** (первый шаг: экран подтверждения на сервере, **не** SPA) → второй запрос **`.../email-action?token=...`** выполняет действие; ответ — короткая HTML-страница («можно закрыть вкладку»). Отключить экран подтверждения: **`EXPENSE_EMAIL_ACTION_CONFIRM_STEP=false`** — тогда одно нажатие сразу меняет статус. Срок токена: **`EXPENSE_EMAIL_ACTION_TTL_SECONDS`**. |
| **Вложения в письме** | В теле письма — блок с файлами: превью **jpeg/png/gif/webp** (до ~2 MB каждый), остальное — ссылка **`GET /api/v1/expenses/{id}/attachments/{attachmentId}/email-file?token=...`** (без `Authorization`) и при необходимости файл как **вложение** MIME. Без **`GATEWAY_BASE_URL`** + секрета ссылки на файлы в письме не строятся. |
| **Если секрет/API не заданы** | В письме **нет** кнопок «утвердить через фронт» — только предупреждение и опциональная ссылка «открыть в приложении» по **`FRONTEND_URL`**. |
| **Тест SMTP** | В репозитории `tickets-back`: скрипт **`expenses/send_expense_smtp_test.py`** (см. комментарии в файле). |

**Фронтенд:** маршрут к заявке должен совпадать с **`FRONTEND_URL`** / **`EXPENSE_NOTIFY_LINK_TEMPLATE`** для опциональной ссылки «открыть в приложении». Согласование по письму идёт через **API** (`email-action`), не через SPA. Встроенные действия внутри окна Outlook без браузера (Actionable Messages) **не** реализованы.

---

## 6. Вложения: квитанция на оплату и чек оплаты

Для **возмещаемых** заявок в API два типа файлов — в `POST /api/v1/expenses/{id}/attachments` передаётся поле формы **`attachmentKind`** (camelCase в JSON не используется; это `multipart/form-data`).

**Порядок по бизнес-правилам (и для UI):**

1. **Сначала** загружается **квитанция на оплату** — основание/документ **для** оплаты (счёт, накладная и т.п.). В API: **`attachmentKind=payment_document`**. В форме фронта это блок «Документ для оплаты».
2. **Затем** загружается **чек оплаты** — подтверждение **факта** оплаты. В API: **`attachmentKind=payment_receipt`**. В форме фронта — «Квитанция об оплате».

Допустимые значения `attachmentKind`: только `payment_document` и `payment_receipt`.

В ответах списка и карточки заявки приходят флаги **`paymentDocumentUploaded`** и **`paymentReceiptUploaded`** — есть ли среди вложений файлы с соответствующим типом.

При отправке возмещаемой заявки на согласование, если автор уже помечает вложения типами (есть хотя бы одно с `payment_document` или `payment_receipt`), **нужны оба типа**. Текст ошибки на бэкенде: *«Для возмещаемого расхода нужны оба вложения: документ для оплаты и квитанция об оплате»* — см. `validate_submit_fields` в `expenses/application/expense_service.py`. Если типизированных вложений нет, для возмещаемого расхода достаточно **хотя бы одного** вложения без типа (legacy). Порядок загрузки на сервере не фиксируется технически, но продуктово и в интерфейсе соблюдайте цепочку: **сначала документ на оплату, потом чек оплаты**.

---

## 7. Дата расхода и курсы ЦБ (форма SPA)

Поведение **репозитория `tickets-front`** (модуль расходов); в API по-прежнему обязательное поле **`expenseDate`** в формате **YYYY-MM-DD**.

### Создание заявки

- Отдельного поля выбора даты в форме **нет**: в тело `POST`/`PATCH` при сохранении черновика и отправке уходит **`expenseDate` = текущий календарный день** в **локальной** таймзоне пользователя.
- Перед сохранением дата вычисляется заново (на случай, если форма открыта через полночь), чтобы в заявке не осталась «вчерашняя» дата.
- Курс **UZS за 1 USD** и кросс-курсы для ввода суммы не в UZS подставляются из JSON API ЦБ РУз (**cbu.uz**) **на эту же (текущую) дату** — см. `fetchCbuParsedForDate` / `cbuRates.ts` на фронте.

### Редактирование и просмотр

- Дата расхода с сервера **не редактируется**; в интерфейсе показывается только для чтения (значение из заявки).

### CORS и dev (Vite)

- В **режиме разработки** запросы к ЦБ по умолчанию идут на **`/cbu-json`** относительно origin dev-сервера — в `vite.config` нужен **proxy** на `https://cbu.uz` (путь к JSON см. в `cbuRates.ts`).
- В **production** при блокировке прямых запросов к cbu.uz с origin SPA задайте **`VITE_CBU_ORIGIN`** на URL **того же** origin, который проксирует cbu.uz (как в комментариях в `cbuRates.ts`).

---

## 8. Частые проблемы

| Симптом | Что проверить |
|---------|----------------|
| CORS error | `FRONTEND_URL` на gateway, совпадение origin с SPA |
| 503 на `/api/v1/expenses` | Контейнер `expenses` запущен, `EXPENSES_SERVICE_URL` в env gateway |
| **500** на `/api/v1/expenses` | Смотрите логи **`docker compose logs expenses --tail 100`** (или Portainer → Logs). Частая причина после обновления кода — **в БД не хватает колонки** (например `payment_deadline`); в актуальном образе expenses при старте выполняется `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`. Пересоберите и перезапустите `expenses`. Если ошибка остаётся — пришлите traceback из логов. |
| Нет писем модераторам после submit | Переменные **`EXPENSE_SMTP_*`**, **`EXPENSE_NOTIFY_TO`** должны быть заданы в **Environment контейнера `expenses`** (Portainer / compose), а не только в локальном `.env`, если он не попадает в образ. Проверьте **`EXPENSE_NOTIFY_ON_SUBMIT`**. Логи: **`docker compose logs expenses --tail 200`** — строки `expense notify:` (пропуск из‑за env или ошибка SMTP). |
| 401 | Передаётся ли `Authorization`, не истёк ли токен |
| 403 | Роль пользователя (раздел расходов / модерация) |

---

## 9. Локальная разработка

- Gateway: `http://localhost:1234` (или порт из `GATEWAY_PORT`).
- Фронт: `http://localhost:5173` — укажите этот origin в `FRONTEND_URL` на бэкенде.
- Микросервисы поднимайте через `docker compose up` или укажите в gateway `EXPENSES_SERVICE_URL=http://host.docker.internal:1242`, если `expenses` запущен на хосте.

---

*См. также: деплой и переменные БД — в общей документации стека (`docker-compose.yml`, `.env.example`).*
