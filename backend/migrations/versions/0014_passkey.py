"""passkey_credentials + passkey_challenges（Phase 3.5 P1，3_API §3.1 / 8_SECURITY §3）。

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-08
"""
import sqlalchemy as sa
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "passkey_credentials",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("user_id", sa.String(length=26), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        # credential_id / attested_data：WebAuthn 二进制的 b64url 文本（不可变，注册即定）
        sa.Column("credential_id", sa.Text(), nullable=False),
        sa.Column("attested_data", sa.Text(), nullable=False),
        sa.Column("sign_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("transports_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("last_used_at", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint("credential_id", name="uq_passkey_credentials_credential_id"),
    )
    op.create_table(
        "passkey_challenges",
        sa.Column("id", sa.String(length=26), nullable=False),
        # 一次性 challenge（b64url）；register 归属用户，login 可为空（发现式凭据）
        sa.Column("challenge", sa.Text(), nullable=False),
        sa.Column("user_id", sa.String(length=26), nullable=True),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("challenge", name="uq_passkey_challenges_challenge"),
    )


def downgrade() -> None:
    op.drop_table("passkey_challenges")
    op.drop_table("passkey_credentials")
