"""reports: analysis_snapshots, reports, report_evidence

建报告流水线 3 表（波5 / 工作项 1.5）。analysis_snapshots 冻结全部输入引用（可复现，
技术架构 §9.2）；reports 状态以 SQLite 为准、文件产物在 data/reports/<date>/<id>/；
PARTIAL 补算出新版本、旧版保留（UNIQUE(report_type, business_date, version)）。
job_runs 已在 0002 建；model_calls/notifications 随波6。

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-14
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # —— analysis_snapshots（冻结快照，UNIQUE(account,business_date,purpose)）——
    op.create_table(
        "analysis_snapshots",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("account_id", sa.String(length=26), nullable=False),
        sa.Column("business_date", sa.Text(), nullable=False),
        sa.Column("snapshot_purpose", sa.Text(), nullable=False),
        sa.Column("frozen_at", sa.Text(), nullable=False),
        sa.Column("portfolio_version", sa.Text(), nullable=False),
        sa.Column("trade_cutoff_at", sa.Text(), nullable=True),
        sa.Column("market_record_refs_json", sa.Text(), nullable=True),
        sa.Column("freshness_refs_json", sa.Text(), nullable=True),
        sa.Column("evidence_cutoff_at", sa.Text(), nullable=True),
        sa.Column("risk_ruleset_version", sa.Text(), nullable=False),
        sa.Column("signals_version", sa.Text(), nullable=True),
        sa.Column("calendar_version", sa.Text(), nullable=True),
        sa.Column("anomalies_json", sa.Text(), nullable=True),
        sa.Column("degradation_flags_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.id"], name="fk_analysis_snapshots_account_id"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "account_id", "business_date", "snapshot_purpose", name="uq_analysis_snapshots_key"
        ),
    )

    # —— reports ——
    op.create_table(
        "reports",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("report_type", sa.Text(), nullable=False),
        sa.Column("business_date", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("manifest_path", sa.Text(), nullable=True),
        sa.Column("content_json_path", sa.Text(), nullable=True),
        sa.Column("content_md_path", sa.Text(), nullable=True),
        sa.Column("analysis_snapshot_id", sa.String(length=26), nullable=False),
        sa.Column("sources_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("schema_version", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=True),
        sa.Column("risk_ruleset_version", sa.Text(), nullable=False),
        sa.Column("generated_at", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["analysis_snapshot_id"],
            ["analysis_snapshots.id"],
            name="fk_reports_analysis_snapshot_id",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("report_type", "business_date", "version", name="uq_reports_key"),
    )
    op.create_index("ix_reports_date", "reports", ["business_date"])

    # —— report_evidence（报告来源清单）——
    op.create_table(
        "report_evidence",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("report_id", sa.String(length=26), nullable=False),
        sa.Column("evidence_id", sa.String(length=26), nullable=True),
        sa.Column("citation_ref", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["report_id"], ["reports.id"], name="fk_report_evidence_report_id"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_report_evidence_report", "report_evidence", ["report_id"])


def downgrade() -> None:
    op.drop_index("ix_report_evidence_report", table_name="report_evidence")
    op.drop_table("report_evidence")
    op.drop_index("ix_reports_date", table_name="reports")
    op.drop_table("reports")
    op.drop_table("analysis_snapshots")
