import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend_common.sql_injection_guard import SqlInjectionGuardMiddleware
from infrastructure.database import Base, engine
from infrastructure import models  # noqa: F401 — регистрация таблиц в metadata
from presentation.routes.health import router as health_router
from presentation.routes.schedule import router as schedule_router

_log = logging.getLogger("vacation.startup")
_STARTUP_RETRIES = 30
_STARTUP_DELAY_SEC = 2.0


@asynccontextmanager
async def lifespan(app: FastAPI):
    if engine is None:
        yield
        return
    last_exc: Exception | None = None
    for attempt in range(1, _STARTUP_RETRIES + 1):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            break
        except Exception as e:
            last_exc = e
            _log.warning(
                "БД недоступна для vacation (попытка %s/%s): %s",
                attempt,
                _STARTUP_RETRIES,
                e,
            )
            await asyncio.sleep(_STARTUP_DELAY_SEC)
    else:
        assert last_exc is not None
        _log.error("Не удалось подключиться к БД vacation после %s попыток", _STARTUP_RETRIES)
        raise last_exc
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
