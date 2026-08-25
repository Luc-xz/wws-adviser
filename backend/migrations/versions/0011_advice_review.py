"""advice_records 评价回填列（Phase 2 / FR-REV-003 观察窗口评价）。

model_explanation（盘中模型解释段）与 verdict/evaluated_at/evaluation_json
（评价回填写回）。

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-25
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("advice_records", sa.Column("model_explanation", sa.Text(), nullable=True))
    op.add_column("advice_records", sa.Column("verdict", sa.Text(), nullable=True))
    op.add_column("advice_records", sa.Column("evaluated_at", sa.Text(), nullable=True))
    op.add_column("advice_records", sa.Column("evaluation_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("advice_records", "evaluation_json")
    op.drop_column("advice_records", "evaluated_at")
    op.drop_column("advice_records", "verdict")
    op.drop_column("advice_records", "model_explanation")
