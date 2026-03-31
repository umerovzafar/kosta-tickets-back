from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from infrastructure.config import get_settings
from presentation.routes import (
    health,
    auth_azure,
    auth_admin,
    users,
    tickets,
    notifications,
    notifications_rest,
    inventory_routes,
    roles,
    todos_routes,
    media,
    attendance_routes,
    time_tracking_routes,
    expenses_routes,
)

app = FastAPI(title="Gateway", version="1.0.0")

# Конкретный origin (не "*") — иначе при credentials: 'include' браузер блокирует CORS
def _cors_origins() -> list[str]:
    settings = get_settings()
    origins: list[str] = []
    for url in (settings.frontend_url or "").strip(), (settings.admin_frontend_url or "").strip():
        if url and url != "*":
            origins.extend(u.strip() for u in url.split(",") if u.strip() and u.strip() != "*")
    # Всегда добавляем localhost для локальной разработки (frontend на 5173, admin на 8080)
    defaults = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ]
    for o in defaults:
        if o not in origins:
            origins.append(o)
    if not origins:
        origins = defaults + ["null"]
    return list(dict.fromkeys(origins))  # без дубликатов


origins = _cors_origins()

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health.router)
app.include_router(auth_azure.router)
app.include_router(auth_admin.router)
app.include_router(users.router)
app.include_router(tickets.router)
app.include_router(notifications.router)
app.include_router(notifications_rest.router)
app.include_router(inventory_routes.router)
app.include_router(roles.router)
app.include_router(todos_routes.router)
app.include_router(media.router)
app.include_router(attendance_routes.router_compat)  # /hikvision/attendance — до attendance
app.include_router(attendance_routes.router)
app.include_router(time_tracking_routes.router)
app.include_router(expenses_routes.router)
