import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from infrastructure.database import Base, async_session_factory, engine
from infrastructure import models  # noqa: F401
from infrastructure.repositories import seed_reference_data
from presentation.routes import expenses, health, reference

_log = logging.getLogger("expenses.startup")

# В Docker Swarm / Portainer depends_on не гарантирует порядок старта — ждём БД
_STARTUP_RETRIES = 30
_STARTUP_DELAY_SEC = 2.0


@asynccontextmanager
async def lifespan(app: FastAPI):
    last_exc: Exception | None = None
    for attempt in range(1, _STARTUP_RETRIES + 1):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            async with async_session_factory() as session:
                await seed_reference_data(session)
                await session.commit()
            break
        except Exception as e:
            last_exc = e
            _log.warning(
                "БД недоступна для инициализации (попытка %s/%s): %s",
                attempt,
                _STARTUP_RETRIES,
                e,
            )
            await asyncio.sleep(_STARTUP_DELAY_SEC)
    else:
        _log.error("Не удалось подключиться к БД после %s попыток", _STARTUP_RETRIES)
        assert last_exc is not None
        raise last_exc
    yield


app = FastAPI(title="Kosta Expenses", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health.router)
app.include_router(expenses.router)
app.include_router(reference.router)
