from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from application.client_expense_category_defaults import (
    seed_default_expense_categories_for_all_clients,
)
from application.client_task_defaults import seed_default_common_tasks_for_all_clients
from infrastructure.database import Base, async_session_factory, engine
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
    apply_time_entries_seconds_and_rounded_patch,
    apply_reports_schema_patch,
    apply_invoices_schema_patch,
    apply_project_currency_patch,
    apply_fx_cache_and_billable_columns_patch,
)
from application.billable_fx import backfill_billable_for_all_entries
from application.settings_sync import renormalize_time_entries_to_minute
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
        await apply_project_currency_patch(conn)
        await apply_time_entries_seconds_and_rounded_patch(conn)
        await apply_fx_cache_and_billable_columns_patch(conn)
    async with async_session_factory() as session:
        await seed_default_common_tasks_for_all_clients(session)
        await seed_default_expense_categories_for_all_clients(session)
        # Одноразовый идемпотентный бэкфилл: квантуем duration_seconds до минут, выравниваем hours/rounded_hours.
        await renormalize_time_entries_to_minute(session)
        await backfill_billable_for_all_entries(session)
        await session.commit()
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
