from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from infrastructure.database import Base, engine
from infrastructure import models  # noqa: F401 — регистрация таблиц в Base.metadata
from infrastructure import models_reports  # noqa: F401 — таблицы отчётов
from infrastructure import models_invoices  # noqa: F401 — счета
from infrastructure.schema_patches import (
    apply_client_expense_categories_schema_patch,
    apply_client_projects_schema_patch,
    apply_client_tasks_schema_patch,
    apply_team_workload_schema_patch,
    apply_client_extra_contacts_schema_patch,
    apply_time_manager_clients_schema_patch,
    apply_user_project_access_patch,
    apply_time_entries_task_id_schema_patch,
    apply_time_entries_hours_precision_patch,
    apply_reports_schema_patch,
    apply_invoices_schema_patch,
)
from presentation.routes import (
    invoices,
    client_contacts,
    client_expense_categories,
    client_projects,
    client_tasks,
    clients,
    health,
    hourly_rates,
    project_access,
    reports,
    team_workload,
    time_entries,
    users,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await apply_team_workload_schema_patch(conn)
        await apply_time_manager_clients_schema_patch(conn)
        await apply_client_extra_contacts_schema_patch(conn)
        await apply_client_tasks_schema_patch(conn)
        await apply_client_expense_categories_schema_patch(conn)
        await apply_client_projects_schema_patch(conn)
        await apply_user_project_access_patch(conn)
        await apply_time_entries_task_id_schema_patch(conn)
        await apply_time_entries_hours_precision_patch(conn)
        await apply_reports_schema_patch(conn)
        await apply_invoices_schema_patch(conn)
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
app.include_router(client_expense_categories.router)
app.include_router(client_projects.router)
app.include_router(client_contacts.router)
app.include_router(clients.router)
app.include_router(team_workload.router)
app.include_router(hourly_rates.router)
app.include_router(time_entries.router)
app.include_router(project_access.router)
app.include_router(users.router)
app.include_router(reports.router)
app.include_router(invoices.router)
app.include_router(client_projects._global_projects_router)
