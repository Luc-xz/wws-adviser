"""User / Session ORM。"""

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from wws_adviser.core.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(sa.String(26), primary_key=True)
    username: Mapped[str] = mapped_column(sa.Text, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(sa.Text, nullable=False)
    created_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
    version: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)


class Session(Base):
    __tablename__ = "sessions"
    __table_args__ = (sa.Index("ix_sessions_user_id", "user_id"),)

    id: Mapped[str] = mapped_column(sa.String(26), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        sa.String(26), sa.ForeignKey("users.id"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(sa.Text, nullable=False, unique=True)
    issued_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
    expires_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
    revoked_at: Mapped[str | None] = mapped_column(sa.Text)
    user_agent_hash: Mapped[str | None] = mapped_column(sa.Text)
