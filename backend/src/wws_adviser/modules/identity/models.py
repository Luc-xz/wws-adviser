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


class PasskeyCredential(Base):
    """Passkey 凭据（Phase 3.5 P1）：credential_id/attested_data 为 b64url 文本。

    不影响主键/权限——同一 user 的密码登录与 Passkey 登录完全等权（3_API §3.1）。
    """

    __tablename__ = "passkey_credentials"
    __table_args__ = (
        sa.UniqueConstraint("credential_id", name="uq_passkey_credentials_credential_id"),
        sa.Index("ix_passkey_credentials_user", "user_id"),
    )

    id: Mapped[str] = mapped_column(sa.String(26), primary_key=True)
    user_id: Mapped[str] = mapped_column(sa.String(26), sa.ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    credential_id: Mapped[str] = mapped_column(sa.Text, nullable=False)
    attested_data: Mapped[str] = mapped_column(sa.Text, nullable=False)
    sign_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    transports_json: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
    last_used_at: Mapped[str | None] = mapped_column(sa.Text)
    updated_at: Mapped[str] = mapped_column(sa.Text, nullable=False)


class PasskeyChallenge(Base):
    """一次性 ceremony challenge（120 秒过期；校验即删——防重放）。"""

    __tablename__ = "passkey_challenges"

    id: Mapped[str] = mapped_column(sa.String(26), primary_key=True)
    challenge: Mapped[str] = mapped_column(sa.Text, nullable=False, unique=True)
    user_id: Mapped[str | None] = mapped_column(sa.String(26))
    purpose: Mapped[str] = mapped_column(sa.Text, nullable=False)  # register | login
    expires_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
    created_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
