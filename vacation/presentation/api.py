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


async def _ensure_schema_with_retries() -> None:
    """Создание таблиц; ретраи не блокируют bind uvicorn (иначе healthcheck и балансировщик видят Connection refused)."""
    last_exc: Exception | None = None
    for attempt in range(1, _STARTUP_RETRIES + 1):
        try:
            if engine is None:
                return
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            _log.info("Схема БД vacation готова")
            return
        except Exception as e:
            last_exc = e
            _log.warning(
                "БД недоступна для vacation (попытка %s/%s): %s",
                attempt,
                _STARTUP_RETRIES,
                e,
            )
            await asyncio.sleep(_STARTUP_DELAY_SEC)
    assert last_exc is not None
    _log.error("Не удалось подключиться к БД vacation после %s попыток", _STARTUP_RETRIES)
    raise last_exc


def _schema_task_done(task: asyncio.Task[None]) -> None:
    try:
        task.result()
    except asyncio.CancelledError:
        pass
    except Exception as e:
        _log.error("Инициализация схемы vacation не удалась", exc_info=e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if engine is None:
        yield
        return
    # Фоновая инициализация: uvicorn сразу слушает порт — /health отвечает (503 пока БД недоступна), без Connection refused в healthcheck.
    task = asyncio.create_task(_ensure_schema_with_retries())
    task.add_done_callback(_schema_task_done)
    try:
        yield
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


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
