from datetime import datetime
from sqlalchemy import String, Integer, DateTime, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from infrastructure.database import Base


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    azure_oid: Mapped[str] = mapped_column(String(256), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    picture: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    role: Mapped[str] = mapped_column(String(64), nullable=False, default="Сотрудник")
    is_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
