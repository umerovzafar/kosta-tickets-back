from datetime import datetime, timezone

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from application.ports import HealthRepositoryPort
from infrastructure.models import (
    OutlookCalendarTokenModel,
    TodoBoardModel,
    TodoCardModel,
    TodoColumnModel,
)


class HealthRepository(HealthRepositoryPort):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def check(self) -> bool:
        try:
            await self._session.execute(text("SELECT 1"))
            return True
        except Exception:
            return False


class OutlookCalendarTokenRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_user_id(self, user_id: int) -> OutlookCalendarTokenModel | None:
        r = await self._session.execute(
            select(OutlookCalendarTokenModel).where(
                OutlookCalendarTokenModel.user_id == user_id
            )
        )
        return r.scalars().one_or_none()

    async def upsert(
        self,
        *,
        user_id: int,
        access_token: str,
        refresh_token: str,
        expires_at: datetime | None,
    ) -> None:
        row = await self.get_by_user_id(user_id)
        if row:
            row.access_token = access_token
            row.refresh_token = refresh_token
            row.expires_at = expires_at
            self._session.add(row)
        else:
            self._session.add(
                OutlookCalendarTokenModel(
                    user_id=user_id,
                    access_token=access_token,
                    refresh_token=refresh_token,
                    expires_at=expires_at,
                )
            )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# Колонки по умолчанию как на макете (заголовок + цвет точки / акцента)
_DEFAULT_KANBAN_COLUMNS: tuple[tuple[str, str], ...] = (
    ("Сегодня", "#7c3aed"),
    ("На этой неделе", "#2563eb"),
    ("Позже", "#ea580c"),
)


class KanbanRepository:
    """Доска, колонки и карточки: одна доска на пользователя."""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_board_row(self, user_id: int) -> TodoBoardModel | None:
        r = await self._session.execute(
            select(TodoBoardModel).where(TodoBoardModel.user_id == user_id)
        )
        return r.scalars().one_or_none()

    async def ensure_board(self, user_id: int) -> TodoBoardModel:
        row = await self.get_board_row(user_id)
        if row:
            return row
        now = _utc_now()
        row = TodoBoardModel(
            user_id=user_id,
            background_url=None,
            created_at=now,
            updated_at=None,
        )
        self._session.add(row)
        await self._session.flush()
        for i, (title, color) in enumerate(_DEFAULT_KANBAN_COLUMNS):
            self._session.add(
                TodoColumnModel(
                    board_id=row.id,
                    title=title,
                    position=i,
                    color=color,
                    is_collapsed=False,
                    created_at=now,
                    updated_at=None,
                )
            )
        return row

    async def _columns_for_board(self, board_id: int) -> list[TodoColumnModel]:
        r = await self._session.execute(
            select(TodoColumnModel).where(TodoColumnModel.board_id == board_id)
        )
        cols = list(r.scalars().all())
        cols.sort(key=lambda c: (c.position, c.id))
        return cols

    async def _cards_for_column(self, column_id: int) -> list[TodoCardModel]:
        r = await self._session.execute(
            select(TodoCardModel).where(TodoCardModel.column_id == column_id)
        )
        cards = list(r.scalars().all())
        cards.sort(key=lambda x: (x.position, x.id))
        return cards

    async def get_column_if_owned(
        self,
        user_id: int,
        column_id: int,
    ) -> TodoColumnModel | None:
        r = await self._session.execute(
            select(TodoColumnModel)
            .join(TodoBoardModel, TodoColumnModel.board_id == TodoBoardModel.id)
            .where(
                TodoBoardModel.user_id == user_id,
                TodoColumnModel.id == column_id,
            )
        )
        return r.scalars().one_or_none()

    async def get_card_if_owned(self, user_id: int, card_id: int) -> TodoCardModel | None:
        r = await self._session.execute(
            select(TodoCardModel)
            .join(TodoColumnModel, TodoCardModel.column_id == TodoColumnModel.id)
            .join(TodoBoardModel, TodoColumnModel.board_id == TodoBoardModel.id)
            .where(
                TodoBoardModel.user_id == user_id,
                TodoCardModel.id == card_id,
            )
        )
        return r.scalars().one_or_none()

    async def patch_board(
        self,
        user_id: int,
        *,
        background_url: str | None,
    ) -> TodoBoardModel:
        row = await self.ensure_board(user_id)
        row.background_url = background_url
        row.updated_at = _utc_now()
        self._session.add(row)
        return row

    async def add_column(
        self,
        user_id: int,
        *,
        title: str,
        color: str,
        insert_at: int | None,
    ) -> TodoColumnModel:
        board = await self.ensure_board(user_id)
        cols = await self._columns_for_board(board.id)
        n = len(cols)
        pos = n if insert_at is None else max(0, min(int(insert_at), n))
        now = _utc_now()
        for c in cols:
            if c.position >= pos:
                c.position += 1
                c.updated_at = now
                self._session.add(c)
        col = TodoColumnModel(
            board_id=board.id,
            title=title.strip(),
            position=pos,
            color=(color or "#6b7280").strip()[:32],
            is_collapsed=bool(is_collapsed),
            created_at=now,
            updated_at=None,
        )
        self._session.add(col)
        await self._session.flush()
        return col

    async def update_column(
        self,
        user_id: int,
        column_id: int,
        *,
        title: str | None,
        color: str | None,
        is_collapsed: bool | None,
    ) -> TodoColumnModel | None:
        col = await self.get_column_if_owned(user_id, column_id)
        if not col:
            return None
        now = _utc_now()
        if title is not None:
            col.title = title.strip()
        if color is not None:
            col.color = color.strip()[:32]
        if is_collapsed is not None:
            col.is_collapsed = bool(is_collapsed)
        col.updated_at = now
        self._session.add(col)
        return col

    async def delete_column(self, user_id: int, column_id: int) -> bool:
        col = await self.get_column_if_owned(user_id, column_id)
        if not col:
            return False
        board_id = col.board_id
        await self._session.execute(delete(TodoColumnModel).where(TodoColumnModel.id == column_id))
        await self._session.flush()
        await self._compact_column_positions(board_id)
        return True

    async def _compact_column_positions(self, board_id: int) -> None:
        cols = await self._columns_for_board(board_id)
        now = _utc_now()
        for i, c in enumerate(cols):
            if c.position != i:
                c.position = i
                c.updated_at = now
                self._session.add(c)

    async def reorder_columns(self, user_id: int, ordered_column_ids: list[int]) -> bool:
        board = await self.get_board_row(user_id)
        if not board:
            return False
        cols = await self._columns_for_board(board.id)
        existing = {c.id for c in cols}
        if set(ordered_column_ids) != existing or len(ordered_column_ids) != len(existing):
            return False
        now = _utc_now()
        for i, cid in enumerate(ordered_column_ids):
            for c in cols:
                if c.id == cid and c.position != i:
                    c.position = i
                    c.updated_at = now
                    self._session.add(c)
        return True

    async def add_card(
        self,
        user_id: int,
        column_id: int,
        *,
        title: str,
        body: str | None,
        insert_at: int | None,
    ) -> TodoCardModel | None:
        col = await self.get_column_if_owned(user_id, column_id)
        if not col:
            return None
        cards = await self._cards_for_column(column_id)
        n = len(cards)
        pos = n if insert_at is None else max(0, min(int(insert_at), n))
        now = _utc_now()
        for c in cards:
            if c.position >= pos:
                c.position += 1
                c.updated_at = now
                self._session.add(c)
        card = TodoCardModel(
            column_id=column_id,
            title=title.strip(),
            body=body,
            position=pos,
            created_at=now,
            updated_at=None,
        )
        self._session.add(card)
        await self._session.flush()
        return card

    async def update_card(
        self,
        user_id: int,
        card_id: int,
        *,
        title: str | None,
        body: str | None,
        new_column_id: int | None,
        new_position: int | None,
    ) -> TodoCardModel | None:
        card = await self.get_card_if_owned(user_id, card_id)
        if not card:
            return None
        now = _utc_now()
        if title is not None:
            card.title = title.strip()
        if body is not None:
            card.body = body
        old_col = card.column_id
        if new_column_id is not None and new_column_id != old_col:
            tgt = await self.get_column_if_owned(user_id, new_column_id)
            if not tgt:
                return None
            old_pos = card.position
            for c in await self._cards_for_column(old_col):
                if c.id != card.id and c.position > old_pos:
                    c.position -= 1
                    c.updated_at = now
                    self._session.add(c)
            card.column_id = new_column_id
            await self._session.flush()
            others = [
                c
                for c in await self._cards_for_column(new_column_id)
                if c.id != card.id
            ]
            others.sort(key=lambda x: (x.position, x.id))
            np = (
                len(others)
                if new_position is None
                else max(0, min(int(new_position), len(others)))
            )
            for c in others:
                if c.position >= np:
                    c.position += 1
                    c.updated_at = now
                    self._session.add(c)
            card.position = np
        elif new_position is not None:
            col_id = card.column_id
            cards = await self._cards_for_column(col_id)
            ordered = sorted(cards, key=lambda x: (x.position, x.id))
            ordered_ids = [c.id for c in ordered]
            ordered_ids.remove(card.id)
            np = max(0, min(int(new_position), len(ordered_ids)))
            ordered_ids.insert(np, card.id)
            for i, cid in enumerate(ordered_ids):
                for c in cards:
                    if c.id == cid and c.position != i:
                        c.position = i
                        c.updated_at = now
                        self._session.add(c)
        card.updated_at = now
        self._session.add(card)
        return card

    async def delete_card(self, user_id: int, card_id: int) -> bool:
        card = await self.get_card_if_owned(user_id, card_id)
        if not card:
            return False
        col_id = card.column_id
        pos = card.position
        await self._session.execute(delete(TodoCardModel).where(TodoCardModel.id == card_id))
        await self._session.flush()
        cards = await self._cards_for_column(col_id)
        now = _utc_now()
        for c in cards:
            if c.position > pos:
                c.position -= 1
                c.updated_at = now
                self._session.add(c)
        return True

    async def reorder_cards_in_column(
        self,
        user_id: int,
        column_id: int,
        ordered_card_ids: list[int],
    ) -> bool:
        col = await self.get_column_if_owned(user_id, column_id)
        if not col:
            return False
        cards = await self._cards_for_column(column_id)
        existing = {c.id for c in cards}
        if set(ordered_card_ids) != existing or len(ordered_card_ids) != len(existing):
            return False
        now = _utc_now()
        for i, cid in enumerate(ordered_card_ids):
            for c in cards:
                if c.id == cid and c.position != i:
                    c.position = i
                    c.updated_at = now
                    self._session.add(c)
        return True
