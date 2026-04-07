# Сервис todos

Микросервис Kanban-доски и Outlook-календаря. Точка входа: `main.py` → `presentation.api:app` (Uvicorn, порт **1240**).

## Документация

| Файл | Описание |
|------|----------|
| [docs/TODOS.md](../docs/TODOS.md) | Инструкция по сервису: env, Docker, БД, gateway, медиа |
| [docs/FRONTEND_TODOS.md](../docs/FRONTEND_TODOS.md) | API и контракт для фронтенда |

## Быстрый старт (локально)

```bash
cd todos
pip install -r requirements.txt
# задать DATABASE_URL / TODOS_DATABASE_URL и AUTH_SERVICE_URL
uvicorn main:app --host 0.0.0.0 --port 1240
```

В Docker см. сервис `todos` в корневом `docker-compose.yml`.

Быстрый старт с пробросом порта **1240**: из корня **`tickets-back`** выполните **`.\scripts\todos_dev_up.ps1`** (нужен Docker Desktop; см. **`docs/TODOS.md`**).
