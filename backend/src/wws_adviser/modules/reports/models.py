"""Reports ORM：analysis_snapshots、reports、report_evidence（波5，2_DATA_MODEL §6.6/§6.7）。

reports 行不可变（新版本=新行），version 为报告版本（UNIQUE 组成部分），无乐观锁列。
"""

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from wws_adviser.core.db import Base


class AnalysisSnapshot(Base):
    __tablename__ = "analysis_snapshots"
    __table_args__ = (
        sa.UniqueConstraint(
            "account_id", "business_date", "snapshot_purpose", name="uq_analysis_snapshots_key"
        ),
    )

    id: Mapped[str] = mapped_column(sa.String(26), primary_key=True)
    account_id: Mapped[str] = mapped_column(
        sa.String(26), sa.ForeignKey("accounts.id"), nullable=False
    )
    business_date: Mapped[str] = mapped_column(sa.Text, nullable=False)
    snapshot_purpose: Mapped[str] = mapped_column(sa.Text, nullable=False)
    frozen_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
    portfolio_version: Mapped[str] = mapped_column(sa.Text, nullable=False)
    trade_cutoff_at: Mapped[str | None] = mapped_column(sa.Text)
    market_record_refs_json: Mapped[str | None] = mapped_column(sa.Text)
    freshness_refs_json: Mapped[str | None] = mapped_column(sa.Text)
    evidence_cutoff_at: Mapped[str | None] = mapped_column(sa.Text)
    risk_ruleset_version: Mapped[str] = mapped_column(sa.Text, nullable=False)
    signals_version: Mapped[str | None] = mapped_column(sa.Text)
    calendar_version: Mapped[str | None] = mapped_column(sa.Text)
    anomalies_json: Mapped[str | None] = mapped_column(sa.Text)
    degradation_flags_json: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
    version: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (
        sa.UniqueConstraint("report_type", "business_date", "version", name="uq_reports_key"),
        sa.Index("ix_reports_date", "business_date"),
    )

    id: Mapped[str] = mapped_column(sa.String(26), primary_key=True)
    report_type: Mapped[str] = mapped_column(sa.Text, nullable=False)
    business_date: Mapped[str] = mapped_column(sa.Text, nullable=False)
    status: Mapped[str] = mapped_column(sa.Text, nullable=False)
    version: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    manifest_path: Mapped[str | None] = mapped_column(sa.Text)
    content_json_path: Mapped[str | None] = mapped_column(sa.Text)
    content_md_path: Mapped[str | None] = mapped_column(sa.Text)
    analysis_snapshot_id: Mapped[str] = mapped_column(
        sa.String(26), sa.ForeignKey("analysis_snapshots.id"), nullable=False
    )
    sources_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    schema_version: Mapped[str] = mapped_column(sa.Text, nullable=False)
    prompt_version: Mapped[str | None] = mapped_column(sa.Text)
    risk_ruleset_version: Mapped[str] = mapped_column(sa.Text, nullable=False)
    generated_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
    created_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(sa.Text, nullable=False)


class ReportEvidence(Base):
    __tablename__ = "report_evidence"
    __table_args__ = (sa.Index("ix_report_evidence_report", "report_id"),)

    id: Mapped[str] = mapped_column(sa.String(26), primary_key=True)
    report_id: Mapped[str] = mapped_column(
        sa.String(26), sa.ForeignKey("reports.id"), nullable=False
    )
    evidence_id: Mapped[str | None] = mapped_column(sa.Text)
    citation_ref: Mapped[str | None] = mapped_column(sa.Text)
