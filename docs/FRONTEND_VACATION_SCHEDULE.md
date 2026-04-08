# График отсутствий (Vacation / absence schedule) — инструкция для фронта

Данные приходят из **gateway** (тот же origin, что и остальной API). Микросервис **vacation** за gateway не вызывать напрямую с браузера.

**Базовый префикс:** `/api/v1/vacations`

Заголовок (для всех методов):

```http
Authorization: Bearer <access_token>
```

- Чтение графика — **GET**.  
- Загрузка Excel — **POST** `schedule/import` (см. раздел 4.4), только для ограниченного набора ролей.

При недоступности сервиса vacation gateway отвечает **503**.

---

## 1. Права (роли)

Доступ к маршрутам `/api/v1/vacations/*` есть у ролей:

- Главный администратор  
- Администратор  
- Партнер  
- IT отдел  
- Офис менеджер  
- Сотрудник  

Иные роли получают **403** (`Only authenticated staff roles can view the absence schedule`).

**Загрузка Excel** (`POST .../schedule/import`) допускается только для:

- Главный администратор  
- Администратор  
- Партнер  
- Офис менеджер  

Остальные роли получают **403** (`Only administrators, partners and office managers can upload the absence schedule`).

---

## 2. Источник данных

- График попадает в БД из **Excel**: через **API загрузки** или скрипт/DevOps.  
- При импорте **перезаписываются только данные выбранного года**; другие годы в БД не удаляются.  
- Даты в колонках файла должны быть **того же календарного года**, что и параметр `year` (иначе **400**).  
- В БД хранятся **строки сотрудников** на **конкретный год** и **отмеченные дни** с кодом вида отсутствия (1–5).  
- Идентификатор `id` у сотрудника в ответах — **внутренний** (из БД vacation), **не** `authUserId` из auth.

---

## 3. Виды отсутствия (`kind_code` → `kind`)

Легенда совпадает с колонками легенды в Excel. Стабильные ключи для UI и фильтров:

| `kind_code` | `kind` (строка в JSON) | Смысл |
|-------------|------------------------|--------|
| 1 | `annual_vacation` | Ежегодный отпуск |
| 2 | `sick_leave` | Отсутствие по болезни |
| 3 | `day_off` | Day off (нерабочий) |
| 4 | `business_trip` | Командировка |
| 5 | `remote_work` | Дистанционный режим |

Справочник в API (можно кэшировать на фронте):

- **GET** `/api/v1/vacations/schedule/kind-codes`  
- Ответ: объект `{"1":"annual_vacation","2":"sick_leave",...}` (ключи — строки).

---

## 4. Эндпоинты

Путь после gateway: **`/api/v1/vacations/`** + путь микросервиса без лишнего префикса.

### 4.1. Список сотрудников в графике за год

**GET** `/api/v1/vacations/schedule/employees?year=2026`

**Query**

| Параметр | Обязательный | Описание |
|----------|--------------|----------|
| `year` | да | Год графика, 2000–2100 |

**Ответ:** массив объектов (поля в **snake_case**):

```json
[
  {
    "id": 1,
    "year": 2026,
    "excel_row_no": 1,
    "full_name": "Иванов Иван",
    "planned_period_note": "10–20 июля"
  }
]
```

| Поле | Описание |
|------|-----------|
| `id` | ID записи в сервисе vacation (использовать в `employee_id` ниже) |
| `year` | Год |
| `excel_row_no` | Номер строки из Excel (`№`), может быть `null` |
| `full_name` | ФИО |
| `planned_period_note` | Текст из колонки «период» в файле, может быть `null` |

Сортировка на бэкенде: сначала по `excel_row_no`, затем по `id`.

---

### 4.2. Один сотрудник и все его дни отсутствий

**GET** `/api/v1/vacations/schedule/employees/{employee_id}`

**Query**

| Параметр | Обязательный | Описание |
|----------|--------------|----------|
| `year` | нет | Если передан и не совпадает с годом записи — **404** |

**Ответ:**

```json
{
  "id": 1,
  "year": 2026,
  "excel_row_no": 1,
  "full_name": "Иванов Иван",
  "planned_period_note": "10–20 июля",
  "absence_days": [
    {
      "absence_on": "2026-07-10",
      "kind_code": 1,
      "kind": "annual_vacation"
    }
  ]
}
```

Дни отсортированы по дате. Дата в формате **ISO `YYYY-MM-DD`**.

**404** — нет сотрудника с таким `id` (или несовпадение `year`, если query задан).

---

### 4.3. Плоский список дней (удобно для календаря / heatmap)

**GET** `/api/v1/vacations/schedule/absence-days?year=2026`

**Query**

| Параметр | Обязательный | Описание |
|----------|--------------|----------|
| `year` | да | Год |
| `employee_id` | нет | Фильтр по `id` из списка сотрудников |
| `date_from` | нет | Нижняя граница даты, `YYYY-MM-DD` |
| `date_to` | нет | Верхняя граница даты, `YYYY-MM-DD` |

**Ответ:** массив:

```json
[
  {
    "employee_id": 1,
    "full_name": "Иванов Иван",
    "absence_on": "2026-07-10",
    "kind_code": 1,
    "kind": "annual_vacation"
  }
]
```

Сортировка: по `absence_on`, затем `employee_id`.

---

### 4.4. Загрузка Excel (импорт за год)

**POST** `/api/v1/vacations/schedule/import`  

**Content-Type:** `multipart/form-data`

| Поле формы | Обязательное | Описание |
|------------|----------------|----------|
| `file` | да | Файл `.xlsx` или `.xlsm` (макс. 20 МБ) |
| `year` | да | Год графика (2000–2100), должен совпадать с годом дат в колонках Excel |
| `sheet` | нет | Имя листа; если не передано — берётся первый лист |

Пример через `fetch`:

```javascript
const form = new FormData();
form.append("file", fileInput.files[0]);
form.append("year", "2026");
// form.append("sheet", "График отсутствия в офисе");

await fetch(`${API_BASE}/api/v1/vacations/schedule/import`, {
  method: "POST",
  headers: { Authorization: `Bearer ${token}` },
  body: form,
});
```

Не задавайте вручную `Content-Type` для `fetch` с `FormData` — браузер добавит boundary.

**Ответ 200** (JSON):

```json
{
  "year": 2026,
  "employees_imported": 42,
  "absence_days_imported": 380
}
```

**400** — неверный формат, несовпадение года с датами в файле, слишком большой файл, битый Excel. Текст в `detail` (строка или объект — как вернул FastAPI).

**403** — нет прав на загрузку (см. раздел 1).

---

## 5. Типовые сценарии UI

1. **Общий календарь отдела на год**  
   **GET** `schedule/absence-days?year=2026` (при необходимости `date_from` / `date_to` для видимого диапазона).  
   Группировать по `absence_on` или строить матрицу «сотрудник × день» вместе с **GET** `schedule/employees?year=2026`.

2. **Карточка сотрудника**  
   **GET** `schedule/employees/{id}?year=2026` — одним запросом ФИО, примечание и все дни.

3. **Легенда цветов**  
   Один раз **GET** `schedule/kind-codes` или захардкодить соответствие по таблице из раздела 3.

4. **Загрузка нового графика за год**  
   Форма с выбором года и файла → **POST** `schedule/import` → показать `employees_imported` / `absence_days_imported` или сообщение об ошибке из `detail`.

---

## 6. Ошибки и пустые данные

| Код | Когда |
|-----|--------|
| 401 | Нет или невалидный Bearer |
| 403 | Роль не из списка в разделе 1 |
| 404 | Неверный `employee_id` (и опционально `year`) |
| 400 | Импорт: неверный файл, год ≠ датам в Excel, превышен размер |
| 503 | Сервис vacation не поднят или не настроен `VACATION_SERVICE_URL` на gateway |

Пустой массив `[]` — для выбранного года ещё не делали импорт Excel или нет подходящих записей.

---

## 7. Локальная разработка

- Gateway по умолчанию: `http://localhost:1234` (см. `GATEWAY_PORT` в `.env`).  
- Пример: `GET http://localhost:1234/api/v1/vacations/schedule/employees?year=2026` с тем же токеном, что и для остального приложения.

### Наполнение БД (импорт Excel) — для бэкенда / DevOps

Данные в API появляются только после импорта файла графика.

1. Запустите **Docker Desktop**.
2. Из корня репозитория `tickets-back` выполните (путь к `.xlsx` — ваш):

```powershell
.\vacation\scripts\import_via_docker.ps1 -ExcelPath "C:\Users\...\График_отпусков_работников_на_2026г.xlsx" -Year 2026
```

Скрипт поднимает `vacation_db`, собирает образ `vacation` и запускает `scripts/import_excel.py` внутри контейнера. Импорт **перезаписывает только строки выбранного года** (`-Year`); остальные годы в БД не трогаются.

Вручную (если Postgres уже доступен по `DATABASE_URL`):

```bash
cd vacation
pip install -r requirements.txt
set DATABASE_URL=postgresql://vacation:123456@HOST:5432/kosta_vacation
python scripts/import_excel.py "C:\path\to\file.xlsx" --year 2026
```

После импорта поднимите сервисы: `docker compose up -d vacation gateway`.
