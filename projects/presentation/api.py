"""
Сервис проектов (общий справочник для нескольких микросервисов).
Сейчас — заглушка: без БД и бизнес-API; дальше — модели и маршруты.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from presentation.routes.health import router as health_router

app = FastAPI(
    title="Kosta Projects",
    version="0.1.0",
    description="Справочник проектов. Пока только health; логику и БД добавим позже.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router)
