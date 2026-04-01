from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from infrastructure.database import Base, async_session_factory, engine
from infrastructure import models  # noqa: F401
from infrastructure.repositories import seed_reference_data
from presentation.routes import expenses, health, reference


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_session_factory() as session:
        await seed_reference_data(session)
        await session.commit()
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
