"""Личная Kanban-доска пользователя (колонки, карточки, фон)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.database import get_session
from infrastructure.repositories import KanbanRepository
from presentation.dependencies import get_current_user_id

router = APIRouter(prefix="/board", tags=["board"])


class CardOut(BaseModel):
    id: int
    title: str
    body: str | None
    position: int


class ColumnOut(BaseModel):
    id: int
    title: str
    position: int
    color: str
    is_collapsed: bool = False
    task_count: int
    cards: list[CardOut]


class BoardOut(BaseModel):
    id: int
    user_id: int
    background_url: str | None
    columns: list[ColumnOut]


class PatchBoardBody(BaseModel):
    background_url: str | None = None


class CreateColumnBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str = Field(..., min_length=1, max_length=200)
    color: str = Field(default="#6b7280", max_length=32)
    insert_at: int | None = Field(
        None,
        description="Индекс вставки (0 — начало); по умолчанию в конец",
    )
    is_collapsed: bool = Field(False, alias="isCollapsed")


class PatchColumnBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str | None = Field(None, min_length=1, max_length=200)
    color: str | None = Field(None, max_length=32)
    is_collapsed: bool | None = Field(None, alias="isCollapsed")


class ReorderColumnsBody(BaseModel):
    ordered_column_ids: list[int] = Field(..., min_length=1)


class CreateCardBody(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    body: str | None = None
    insert_at: int | None = Field(
        None,
        description="Индекс в колонке; по умолчанию в конец",
    )


class PatchCardBody(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=500)
    body: str | None = None
    column_id: int | None = None
    position: int | None = Field(
        None,
        description="Позиция в колонке (после смены column_id — в целевой колонке)",
    )


class ReorderCardsBody(BaseModel):
    ordered_card_ids: list[int] = Field(..., min_length=1)


async def _build_board_out(
    session: AsyncSession,
    user_id: int,
) -> BoardOut:
    repo = KanbanRepository(session)
    board = await repo.ensure_board(user_id)
    cols = await repo._columns_for_board(board.id)
    out_cols: list[ColumnOut] = []
    for col in cols:
        cards = await repo._cards_for_column(col.id)
        out_cols.append(
            ColumnOut(
                id=col.id,
                title=col.title,
                position=col.position,
                color=col.color,
                is_collapsed=col.is_collapsed,
                task_count=len(cards),
                cards=[
                    CardOut(
                        id=c.id,
                        title=c.title,
                        body=c.body,
                        position=c.position,
                    )
                    for c in cards
                ],
            )
        )
    return BoardOut(
        id=board.id,
        user_id=board.user_id,
        background_url=board.background_url,
        columns=out_cols,
    )


@router.get("", response_model=BoardOut)
async def get_board(
    user_id: Annotated[int, Depends(get_current_user_id)],
    session: AsyncSession = Depends(get_session),
):
    """Возвращает доску; при первом обращении создаёт доску с колонками по умолчанию (как на макете)."""
    repo = KanbanRepository(session)
    await repo.ensure_board(user_id)
    await session.commit()
    return await _build_board_out(session, user_id)


@router.patch("", response_model=BoardOut)
async def patch_board(
    body: PatchBoardBody,
    user_id: Annotated[int, Depends(get_current_user_id)],
    session: AsyncSession = Depends(get_session),
):
    data = body.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")
    repo = KanbanRepository(session)
    await repo.patch_board(
        user_id,
        background_url=data.get("background_url"),
    )
    await session.commit()
    return await _build_board_out(session, user_id)


@router.post("/columns", response_model=BoardOut)
async def create_column(
    body: CreateColumnBody,
    user_id: Annotated[int, Depends(get_current_user_id)],
    session: AsyncSession = Depends(get_session),
):
    repo = KanbanRepository(session)
    await repo.add_column(
        user_id,
        title=body.title,
        color=body.color,
        insert_at=body.insert_at,
        is_collapsed=body.is_collapsed,
    )
    await session.commit()
    return await _build_board_out(session, user_id)


@router.patch("/columns/{column_id}", response_model=BoardOut)
async def patch_column(
    column_id: int,
    body: PatchColumnBody,
    user_id: Annotated[int, Depends(get_current_user_id)],
    session: AsyncSession = Depends(get_session),
):
    patch = body.model_dump(exclude_unset=True, by_alias=False)
    if not patch:
        raise HTTPException(status_code=400, detail="No fields to update")
    repo = KanbanRepository(session)
    col = await repo.update_column(
        user_id,
        column_id,
        title=patch.get("title"),
        color=patch.get("color"),
        is_collapsed=patch.get("is_collapsed"),
    )
    if not col:
        raise HTTPException(status_code=404, detail="Column not found")
    await session.commit()
    return await _build_board_out(session, user_id)


@router.delete("/columns/{column_id}", response_model=BoardOut)
async def delete_column(
    column_id: int,
    user_id: Annotated[int, Depends(get_current_user_id)],
    session: AsyncSession = Depends(get_session),
):
    repo = KanbanRepository(session)
    ok = await repo.delete_column(user_id, column_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Column not found")
    await session.commit()
    return await _build_board_out(session, user_id)


@router.put("/columns/reorder", response_model=BoardOut)
async def reorder_columns(
    body: ReorderColumnsBody,
    user_id: Annotated[int, Depends(get_current_user_id)],
    session: AsyncSession = Depends(get_session),
):
    repo = KanbanRepository(session)
    ok = await repo.reorder_columns(user_id, body.ordered_column_ids)
    if not ok:
        raise HTTPException(
            status_code=400,
            detail="Invalid column id list (must match all columns on the board)",
        )
    await session.commit()
    return await _build_board_out(session, user_id)


@router.post("/columns/{column_id}/cards", response_model=BoardOut)
async def create_card(
    column_id: int,
    body: CreateCardBody,
    user_id: Annotated[int, Depends(get_current_user_id)],
    session: AsyncSession = Depends(get_session),
):
    repo = KanbanRepository(session)
    card = await repo.add_card(
        user_id,
        column_id,
        title=body.title,
        body=body.body,
        insert_at=body.insert_at,
    )
    if not card:
        raise HTTPException(status_code=404, detail="Column not found")
    await session.commit()
    return await _build_board_out(session, user_id)


@router.patch("/cards/{card_id}", response_model=BoardOut)
async def patch_card(
    card_id: int,
    body: PatchCardBody,
    user_id: Annotated[int, Depends(get_current_user_id)],
    session: AsyncSession = Depends(get_session),
):
    patch = body.model_dump(exclude_unset=True)
    if not patch:
        raise HTTPException(status_code=400, detail="No fields to update")
    repo = KanbanRepository(session)
    card = await repo.update_card(
        user_id,
        card_id,
        title=patch.get("title"),
        body=patch.get("body"),
        new_column_id=patch.get("column_id"),
        new_position=patch.get("position"),
    )
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    await session.commit()
    return await _build_board_out(session, user_id)


@router.delete("/cards/{card_id}", response_model=BoardOut)
async def delete_card(
    card_id: int,
    user_id: Annotated[int, Depends(get_current_user_id)],
    session: AsyncSession = Depends(get_session),
):
    repo = KanbanRepository(session)
    ok = await repo.delete_card(user_id, card_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Card not found")
    await session.commit()
    return await _build_board_out(session, user_id)


@router.put("/columns/{column_id}/cards/reorder", response_model=BoardOut)
async def reorder_cards(
    column_id: int,
    body: ReorderCardsBody,
    user_id: Annotated[int, Depends(get_current_user_id)],
    session: AsyncSession = Depends(get_session),
):
    repo = KanbanRepository(session)
    ok = await repo.reorder_cards_in_column(user_id, column_id, body.ordered_card_ids)
    if not ok:
        raise HTTPException(
            status_code=400,
            detail="Invalid card id list (must match all cards in the column)",
        )
    await session.commit()
    return await _build_board_out(session, user_id)
