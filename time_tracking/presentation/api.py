from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from infrastructure.database import Base, engine
from infrastructure import models  # noqa: F401 — регистрация таблиц в Base.metadata
from infrastructure.schema_patches import (
    apply_client_tasks_schema_patch,
    apply_team_workload_schema_patch,
    apply_time_manager_clients_schema_patch,
)
from presentation.routes import client_tasks, clients, health, hourly_rates, team_workload, time_entries, users


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await apply_team_workload_schema_patch(conn)
        await apply_time_manager_clients_schema_patch(conn)
        await apply_client_tasks_schema_patch(conn)
    yield


app = FastAPI(title="Time Tracking", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health.router)
app.include_router(client_tasks.router)
app.include_router(clients.router)
app.include_router(team_workload.router)
app.include_router(hourly_rates.router)
app.include_router(time_entries.router)
app.include_router(users.router)
