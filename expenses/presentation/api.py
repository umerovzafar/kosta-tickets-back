import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from infrastructure.database import Base, async_session_factory, engine
from infrastructure import models  # noqa: F401
from infrastructure.repositories import seed_reference_data
from presentation.routes import expenses, health, reference

_log = logging.getLogger("expenses.startup")

# В Docker Swarm / Portainer depends_on не гарантирует порядок старта — ждём БД
_STARTUP_RETRIES = 30
_STARTUP_DELAY_SEC = 2.0

_LEGACY_INT_PK = frozenset({"integer", "bigint", "smallint"})


async def _drop_legacy_integer_expense_tables(conn) -> None:
    """
    Старые БД могли создать expense_requests.id как INTEGER; текущая схема — VARCHAR(40) для KL-id.
    Тогда CREATE TABLE для дочерних таблиц падает с DatatypeMismatchError.
    Удаляем только таблицы модуля расходов (данные заявок теряются).
    """
    result = await conn.execute(
        text(
            """
            SELECT data_type FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'expense_requests'
              AND column_name = 'id'
            """
        )
    )
    row = result.first()
    if row is None:
        return
    dt = (row[0] or "").lower()
    if dt not in _LEGACY_INT_PK:
        return
    _log.warning(
        "Обнаружен legacy expense_requests.id (%s). Удаляем таблицы расходов для пересоздания под VARCHAR id "
        "(данные заявок будут удалены).",
        row[0],
    )
    for ddl in (
        "DROP TABLE IF EXISTS expense_attachments CASCADE",
        "DROP TABLE IF EXISTS expense_status_history CASCADE",
        "DROP TABLE IF EXISTS expense_audit_logs CASCADE",
        "DROP TABLE IF EXISTS expense_requests CASCADE",
        "DROP TABLE IF EXISTS expense_kl_sequence CASCADE",
    ):
        await conn.execute(text(ddl))


@asynccontextmanager
async def lifespan(app: FastAPI):
    last_exc: Exception | None = None
    for attempt in range(1, _STARTUP_RETRIES + 1):
        try:
            async with engine.begin() as conn:
                await _drop_legacy_integer_expense_tables(conn)
                await conn.run_sync(Base.metadata.create_all)
                try:
                    await conn.execute(
                        text(
                            "ALTER TABLE expense_attachments ADD COLUMN IF NOT EXISTS attachment_kind VARCHAR(64)"
                        )
                    )
                except Exception as ex:
                    _log.debug("attachment_kind column migration: %s", ex)
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
