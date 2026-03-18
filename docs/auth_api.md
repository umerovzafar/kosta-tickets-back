# Инструкция по запросам Auth API

Все запросы выполняются через **Gateway**. Базовый URL: `http://localhost:1234` (или ваш адрес Gateway).

---

## 1. GET /api/v1/auth/azure/login — Azure Login

**Назначение:** инициация входа через Microsoft (Azure AD). Возвращает редирект на страницу входа Microsoft.

**Метод:** `GET`  
**Путь:** `/api/v1/auth/azure/login`

**Query-параметры:**

| Параметр | Тип    | Обязательный | Описание |
|----------|--------|--------------|----------|
| `state`  | string | нет          | Если передать `state=admin`, после входа редирект будет на админ-панель. Без параметра — на основной фронт. |

**Пример запроса в браузере:**
```
http://localhost:1234/api/v1/auth/azure/login
```
С редиректом в админку:
```
http://localhost:1234/api/v1/auth/azure/login?state=admin
```

**Ответ:** редирект (302/307) на URL входа Microsoft. После успешного входа пользователь попадает на callback (см. Azure Callback).

**Ошибки:** 502 — сервис auth недоступен (проверьте, что контейнер auth запущен).

---

## 2. GET /api/v1/auth/azure/logout — Logout

**Назначение:** выход из учётной записи Microsoft. Редирект на страницу выхода провайдера.

**Метод:** `GET`  
**Путь:** `/api/v1/auth/azure/logout`

**Параметры:** нет.

**Пример запроса в браузере:**
```
http://localhost:1234/api/v1/auth/azure/logout
```

**Ответ:** редирект (302/307) на URL выхода Microsoft.

**Ошибки:** 502 — сервис auth недоступен.

---

## 3. GET /api/v1/auth/azure/callback — Azure Callback

**Назначение:** обработка ответа от Microsoft после входа. Вызывается автоматически после редиректа с Azure (передаётся `code`). Обменивает код на токен и редиректит на фронт с `access_token` в URL.

**Метод:** `GET`  
**Путь:** `/api/v1/auth/azure/callback`

**Query-параметры:**

| Параметр | Тип    | Обязательный | Описание |
|----------|--------|--------------|----------|
| `code`   | string | да           | Код авторизации, полученный от Microsoft. |
| `state`  | string | нет          | Если `state=admin` — редирект на админ-панель с токеном; иначе — на основной фронт. |

**Пример (типичный редирект от Microsoft):**
```
http://localhost:1234/api/v1/auth/azure/callback?code=...&state=admin
```

**Ответ:** редирект (302) на фронт с токеном в query, например:
- основной фронт: `{frontend_url}/auth/callback?access_token={token}`
- админка: `{admin_frontend_url}/auth/callback.html?access_token={token}`

При ошибке обмена кода — редирект на страницу ошибки (например `/login?error=auth_failed` или `/index.html?error=auth_failed` для админки).

**Примечание:** этот URL вызывается браузером/провайдером после входа; с фронта обычно не вызывается вручную, кроме тестов.

---

## 4. POST /api/v1/auth/admin/login — Admin Login

**Назначение:** вход в админ-панель по логину и паролю (без Microsoft). Возвращает JWT-токен для последующих запросов.

**Метод:** `POST`  
**Путь:** `/api/v1/auth/admin/login`

**Заголовки:**
- `Content-Type: application/json`

**Тело запроса (JSON):**

| Поле      | Тип    | Обязательное | Описание   |
|-----------|--------|--------------|------------|
| `username` | string | да           | Логин администратора. |
| `password` | string | да           | Пароль.    |

**Пример тела:**
```json
{
  "username": "admin",
  "password": "admin123"
}
```

**Пример cURL:**
```bash
curl -X POST "http://localhost:1234/api/v1/auth/admin/login" \
  -H "Content-Type: application/json" \
  -d "{\"username\": \"admin\", \"password\": \"admin123\"}"
```

**Успешный ответ (200):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

Токен из `access_token` передаётся в заголовке для запросов к API:  
`Authorization: Bearer <access_token>`.

**Ошибки:**
- **401** — неверный логин или пароль.
- **502** — сервис auth недоступен или не поддерживает admin login (перезапустите/пересоберите контейнер auth).

---

## Общее

- Все запросы к auth идут через Gateway; прямой вызов сервиса auth с фронта не используется.
- Логин и пароль админа задаются в конфигурации сервиса auth (`ADMIN_USERNAME`, `ADMIN_PASSWORD` / переменные окружения).
- Swagger: `http://localhost:1234/docs` (группа **auth**).
