"""Модели БД (SQLAlchemy)."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infrastructure.database import Base


class OutlookCalendarTokenModel(Base):
    """Токены OAuth календаря Outlook (access + refresh) по user_id."""

    __tablename__ = "outlook_calendar_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TodoBoardModel(Base):
    """Личная Kanban-доска пользователя (одна на user_id)."""

    __tablename__ = "todo_boards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True, index=True)
    background_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    columns: Mapped[list["TodoColumnModel"]] = relationship(
        "TodoColumnModel",
        back_populates="board",
        cascade="all, delete-orphan",
    )


class TodoColumnModel(Base):
    """Колонка доски (порядок по полю position)."""

    __tablename__ = "todo_board_columns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    board_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("todo_boards.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    color: Mapped[str] = mapped_column(String(32), nullable=False, default="#6b7280")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    board: Mapped["TodoBoardModel"] = relationship("TodoBoardModel", back_populates="columns")
    cards: Mapped[list["TodoCardModel"]] = relationship(
        "TodoCardModel",
        back_populates="column",
        cascade="all, delete-orphan",
    )


class TodoCardModel(Base):
    """Карточка в колонке."""

    __tablename__ = "todo_board_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    column_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("todo_board_columns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    column: Mapped["TodoColumnModel"] = relationship("TodoColumnModel", back_populates="cards")
