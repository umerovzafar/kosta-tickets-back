from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.config import get_settings
from infrastructure.database import get_session
from infrastructure.repositories import ExpenseRepository
from presentation.schemas import HealthResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=HealthResponse)
async def health(session: AsyncSession = Depends(get_session)):
    repo = ExpenseRepository(session)
    ok = await repo.health_check()
    return HealthResponse(
        status="healthy" if ok else "degraded",
        service=get_settings().service_name,
        timestamp=datetime.now(timezone.utc),
    )
