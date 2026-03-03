from contextlib import asynccontextmanager
from sqlalchemy import text
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from infrastructure.database import engine, Base
from presentation.routes import auth_routes, user_routes, health


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
app.include_router(health.router)
