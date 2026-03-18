from contextlib import asynccontextmanager
from sqlalchemy import text
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from infrastructure.database import engine, Base
from presentation.routes import auth_routes, user_routes, role_routes, health
from domain.roles import Role


def _seed_default_roles(sync_conn):
    """Создать роли по умолчанию и права time_tracking / time_tracking_admin для ролей."""
    result = sync_conn.execute(text("SELECT id FROM roles LIMIT 1"))
    if result.fetchone() is None:
        for r in Role:
            sync_conn.execute(text("INSERT INTO roles (name, created_at) VALUES (:name, NOW())"), {"name": r.value})
    result = sync_conn.execute(text("SELECT id, name FROM roles"))
    rows = result.fetchall()
    role_ids = {name: id_ for (id_, name) in rows}
    if Role.MAIN_ADMIN.value not in role_ids:
        sync_conn.execute(text("INSERT INTO roles (name, created_at) VALUES (:name, NOW())"), {"name": Role.MAIN_ADMIN.value})
        result = sync_conn.execute(text("SELECT id FROM roles WHERE name = :name"), {"name": Role.MAIN_ADMIN.value})
        row = result.fetchone()
        if row:
            role_ids[Role.MAIN_ADMIN.value] = row[0]
    main_admin_id = role_ids.get(Role.MAIN_ADMIN.value)
    for role_name in (Role.MAIN_ADMIN.value, Role.ADMIN.value, Role.PARTNER.value, Role.OFFICE_MANAGER.value, Role.IT_DEPARTMENT.value):
        rid = role_ids.get(role_name)
        if rid is not None:
            sync_conn.execute(
                text(
                    "INSERT INTO role_permissions (role_id, permission_key, allowed) VALUES (:rid, 'time_tracking', TRUE) "
                    "ON CONFLICT (role_id, permission_key) DO NOTHING"
                ),
                {"rid": rid},
            )
    if main_admin_id is not None:
        sync_conn.execute(
            text(
                "INSERT INTO role_permissions (role_id, permission_key, allowed) VALUES (:rid, 'time_tracking_admin', TRUE) "
                "ON CONFLICT (role_id, permission_key) DO NOTHING"
            ),
            {"rid": main_admin_id},
        )
    # Локальный админ (admin-login) — всегда Главный администратор
    sync_conn.execute(
        text("UPDATE users SET role = :role WHERE azure_oid = 'local-admin'"),
        {"role": Role.MAIN_ADMIN.value},
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS picture VARCHAR(1024)"
        ))
        await conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(64) DEFAULT 'Сотрудник'"
        ))
        await conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_blocked BOOLEAN DEFAULT FALSE"
        ))
        await conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_archived BOOLEAN DEFAULT FALSE"
        ))
        await conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS time_tracking_role VARCHAR(32)"
        ))
        await conn.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS position VARCHAR(256)"
        ))
        await conn.run_sync(_seed_default_roles)
    yield


app = FastAPI(title="Auth", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_routes.router)
app.include_router(user_routes.router)
app.include_router(role_routes.router)
app.include_router(health.router)
