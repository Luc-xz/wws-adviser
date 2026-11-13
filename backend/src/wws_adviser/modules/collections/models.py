"""Collections ORM：source_health + ingest_items（5_DATA §12 采集可观测性，迁移 0016）。"""

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from wws_adviser.core.db import Base


class SourceHealth(Base):
    """源健康（类别级 upsert，5_DATA §12.1）。

    派生状态（ok/degraded/unavailable）由读取侧按连续失败阈值计算，不落库。
    物理源级「最近成功」从 market_records/documents 的 source + fetched_at 推导。
    """

    __tablename__ = "source_health"

    category: Mapped[str] = mapped_column(sa.Text, primary_key=True)
    last_success_at: Mapped[str | None] = mapped_column(sa.Text)
    last_failure_at: Mapped[str | None] = mapped_column(sa.Text)
    consecutive_failures: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    last_error_code: Mapped[str | None] = mapped_column(sa.Text)
    last_error_message: Mapped[str | None] = mapped_column(sa.Text)
    updated_at: Mapped[str] = mapped_column(sa.Text, nullable=False)


class IngestItem(Base):
    """采集条目明细（append-only，5_DATA §12.1）。

    不复制 payload：K 线/公告正文永远单源在 market_records/documents；
    display_name 写入时去规范化，列表零 join 直出；保留策略见 ingest_item_retention_days。
    """

    __tablename__ = "ingest_items"
    __table_args__ = (
        sa.Index("ix_ingest_items_run_category", "run_id", "category"),
        sa.Index("ix_ingest_items_category_status", "category", "status"),
        sa.Index("ix_ingest_items_created", "created_at"),
        sa.Index("ix_ingest_items_target", "target_ref"),
    )

    id: Mapped[str] = mapped_column(sa.String(26), primary_key=True)
    run_id: Mapped[str | None] = mapped_column(
        sa.String(26), sa.ForeignKey("job_runs.id", ondelete="CASCADE")
    )
    category: Mapped[str] = mapped_column(sa.Text, nullable=False)
    action: Mapped[str] = mapped_column(sa.Text, nullable=False)
    status: Mapped[str] = mapped_column(sa.Text, nullable=False)
    target_ref: Mapped[str] = mapped_column(sa.Text, nullable=False)
    display_name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    rows_written: Mapped[int | None] = mapped_column(sa.Integer)
    source: Mapped[str | None] = mapped_column(sa.Text)
    duration_ms: Mapped[int | None] = mapped_column(sa.Integer)
    error_code: Mapped[str | None] = mapped_column(sa.Text)
    error_message: Mapped[str | None] = mapped_column(sa.Text)
    data_ref: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
