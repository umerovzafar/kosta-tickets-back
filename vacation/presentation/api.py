from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend_common.sql_injection_guard import SqlInjectionGuardMiddleware
from infrastructure.database import Base, engine
from infrastructure import models  # noqa: F401 — регистрация таблиц в metadata
from presentation.routes.health import router as health_router
from presentation.routes.schedule import router as schedule_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    if engine is not None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(
    title="Kosta Vacation / absence schedule",
    version="0.1.0",
    description="График отсутствий (импорт из Excel).",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SqlInjectionGuardMiddleware)
app.include_router(health_router)
app.include_router(schedule_router)
