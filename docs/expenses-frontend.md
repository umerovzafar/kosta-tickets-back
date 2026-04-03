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

Значения **`FRONTEND_URL`** и **`GATEWAY_BASE_URL`** на gateway часто **дублируют** (или согласуются с) одноимёнными переменными в env **сервиса `expenses`**, чтобы ссылки в письмах и CORS указывали на те же URL.

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

Для маршрутов **`/api/v1/expenses/...`** на gateway в обычном случае нужен заголовок:

```http
Authorization: Bearer <access_token>
```

Токен тот же, что для остального приложения (вход через Azure AD / ваш auth). Без токена типичный ответ — **401**.

**Исключения (без `Authorization`):** два публичных **GET** (подписанный токен только в query):

- **`GET /api/v1/expenses/{id}/email-action?token=...`** — одноразовое утверждение / отклонение из письма (параметр **`confirm=1`** и шаг подтверждения — в таблице **«Почта модераторам»** ниже).
- **`GET /api/v1/expenses/{id}/attachments/{attachment_id}/email-file?token=...`** — скачивание / просмотр вложения по токену из письма.

Остальные маршруты **`/api/v1/expenses/...`** по-прежнему требуют Bearer.

---

## 5. Примеры URL (production)

Если API: `https://ticketsback.kostalegal.com`:

- Список: `GET https://ticketsback.kostalegal.com/api/v1/expenses?skip=0&limit=50`
- Создание: `POST https://ticketsback.kostalegal.com/api/v1/expenses`
- Типы: `GET https://ticketsback.kostalegal.com/api/v1/expense-types`
- Курс: `GET https://ticketsback.kostalegal.com/api/v1/exchange-rates?date=2026-04-02`

Контракт полей (camelCase / деньги) согласован с ТЗ и нормализацией на фронте (`coerceExpense.ts`, `expenseAuthor.ts`; см. **`TZ-expenses-backend.md`** во фронт-репозитории).

Переменные **gateway** — в **§2**. Отдельно в **окружении контейнера `expenses`** задаются SMTP, ссылки в письмах и публичный URL API — см. **«Почта модераторам»** ниже и **`tickets-back/.env.example`**.

### Автор заявки

В ответах списка и карточки заявки добавлено поле **`createdBy`** (объект):

- `id` — тот же смысл, что и `createdByUserId`
- `displayName`, `email`, опционально `picture`, `position` — подтягиваются из **auth** (`GET /users/{id}` тем же Bearer-токеном)

Если auth недоступен или профиль не найден, `createdBy` всё равно есть: заполняется **`id`**, остальные поля могут быть `null`.

**Фронт (SPA):** поле нормализуется в `expenseAuthor.ts` / `coerceExpense.ts`; отображается в **карточках** списка заявок (сетка), в боковой панели заявки и в Excel-отчёте (репозиторий `tickets-front`).

### Почта модераторам

Письма рассылает микросервис **`expenses`** (SMTP и перечисленные ниже переменные — в **окружении контейнера/процесса `expenses`**). Полный список и комментарии — **`tickets-back/.env.example`**, код письма — `expenses/infrastructure/expense_submit_mail.py`, публичные GET — `expenses/presentation/routes/expense_email_action.py`. Имена полей настроек в коде — `expenses/infrastructure/config.py` (алиасы переменных окружения см. там же).

| Вопрос | Ответ |
|--------|-------|
| **Когда уходит письмо** | Только при **`POST /api/v1/expenses/{id}/submit`** (заявка переходит на согласование). При **`POST /api/v1/expenses`** (черновик) письмо **не** отправляется. |
| **Вкл/выкл** | **`EXPENSE_NOTIFY_ON_SUBMIT`** (по умолчанию `true`). |
| **Кому** | **`EXPENSE_NOTIFY_TO`** — один или несколько адресов через **запятую**. |
| **SMTP** | **`EXPENSE_SMTP_HOST`**, **`EXPENSE_SMTP_USER`**, **`EXPENSE_SMTP_PASSWORD`**; опционально **`EXPENSE_SMTP_PORT`**, **`EXPENSE_SMTP_USE_TLS`**. Допустимы укороченные имена **`SMTP_HOST`**, **`SMTP_USER`**, **`SMTP_PASSWORD`**, **`SMTP_PORT`**, **`SMTP_USE_TLS`** (те же поля настроек). Отправитель: **`EXPENSE_MAIL_FROM`** или **`EXPENSE_SMTP_FROM`**, иначе подставляется SMTP-user. Без host/user/password в логах будет **`expense notify:`** и письмо не уйдёт. |
| **Ссылка «открыть в приложении»** | **`FRONTEND_URL`** или **`EXPENSES_FRONTEND_URL`** — origin SPA (без `/` в конце). Шаблон пути: **`EXPENSE_NOTIFY_LINK_TEMPLATE`** с плейсхолдерами `{frontend_url}`, `{expense_id}`; по умолчанию в коде `{frontend_url}/expenses/{expense_id}`. Для hash-router, например: `{frontend_url}/#/expenses/{expense_id}`. |
| **Публичный URL API (одноразовые ссылки)** | **`GATEWAY_BASE_URL`** или **`PUBLIC_API_BASE_URL`** или **`EXPENSES_PUBLIC_API_BASE_URL`** — тот же базовый URL gateway, что видит браузер (`https://…` **без** завершающего `/`). Нужен вместе с **`EXPENSE_EMAIL_ACTION_SECRET`** для кнопок «Утвердить сразу» / «Отклонить сразу» и ссылок на файлы. |
| **Одноразовое согласование** | **`GET /api/v1/expenses/{id}/email-action?token=...`** через gateway, **без** `Authorization`. Срок токена: **`EXPENSE_EMAIL_ACTION_TTL_SECONDS`**. Если **`EXPENSE_EMAIL_ACTION_CONFIRM_STEP=true`** (по умолчанию), первая ссылка из письма с **`confirm=1`** открывает страницу подтверждения; кнопка на ней ведёт на **`https://…/api/v1/expenses/{id}/email-action?token=...`** (публичный URL **собирается из `GATEWAY_BASE_URL`**, заданного в env **сервиса `expenses`**, не из внутреннего адреса Docker). Если **`false`**, одно открытие ссылки из письма сразу выполняет approve/reject. |
| **Вложения в письме** | Для каждого файла может быть ссылка **`GET /api/v1/expenses/{id}/attachments/{attachment_id}/email-file?token=...`** (**без** Bearer) — выдача файла по подписанному токену. |
| **Кнопки с входом в SPA** | Если секрет или базовый URL API не заданы, в ссылки на фронт добавляется **`EXPENSE_NOTIFY_INTENT_PARAM`** (по умолчанию `intent`) со значениями **`approve`** / **`reject`**; для hash-router — во **fragment** URL. |
| **Прочее (expenses)** | **`EXPENSE_ALLOW_SELF_MODERATION`** — может ли модератор утверждать/отклонять **свою** заявку (по умолчанию `true`). **`EXPENSE_AMOUNT_LIMIT_UZS`** — при превышении суммы ошибка при create/submit (опционально). |
| **Тест SMTP** | **`expenses/send_expense_smtp_test.py`** в репозитории `tickets-back`. |

**Фронтенд:** маршрут к заявке должен совпадать с шаблоном ссылки; при необходимости обработайте **`intent`**. Встроенные действия Outlook без браузера (Actionable Messages) **не** реализованы.

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
