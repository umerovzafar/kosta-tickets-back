"""
Сервис проектов (общий справочник для нескольких микросервисов).
БД: kosta_projects (см. PROJECTS_DATABASE_URL / PROJECTS_DB_NAME).
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from infrastructure.database import Base, engine
from infrastructure import models  # noqa: F401 — регистрация таблиц в Base.metadata
from presentation.routes.health import router as health_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    if engine is not None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(
    title="Kosta Projects",
    version="0.1.0",
    description="Справочник проектов. Подключение к БД; доменная модель — далее.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router)
