from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from infrastructure.models import (  # noqa: F401 — регистрация таблиц для create_all
    OutlookCalendarTokenModel,
    TodoBoardModel,
    TodoCardModel,
    TodoColumnModel,
)
from presentation.routes import board_routes, calendar_routes, health
from infrastructure.database import Base, engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Создание таблиц при старте (если нет миграций)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(title="Kosta Todos", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health.router)
app.include_router(calendar_routes.router, prefix="/api/v1/todos")
app.include_router(board_routes.router, prefix="/api/v1/todos")
