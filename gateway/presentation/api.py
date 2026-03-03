from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from presentation.routes import (
    health,
    auth_azure,
    auth_admin,
    users,
    tickets,
    notifications,
    notifications_rest,
    inventory_routes,
    media,
)

app = FastAPI(title="Gateway", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
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
app.include_router(media.router)
