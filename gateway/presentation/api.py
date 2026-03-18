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
)

app = FastAPI(title="Gateway", version="1.0.0")

# Конкретный origin (не "*") — иначе при credentials: 'include' браузер блокирует CORS
def _cors_origins() -> list[str]:
    settings = get_settings()
    origins: list[str] = []
    for url in (settings.frontend_url or "").strip(), (settings.admin_frontend_url or "").strip():
        if url and url != "*":
            origins.extend(u.strip() for u in url.split(",") if u.strip() and u.strip() != "*")
    if not origins:
        # по умолчанию — основной фронт и типичный origin админки (открытой с файлов или другого порта)
        origins = ["http://localhost:5173", "http://localhost:8080", "http://127.0.0.1:8080", "null"]
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
