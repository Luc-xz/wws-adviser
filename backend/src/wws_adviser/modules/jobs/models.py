"""JobRun ORM（job_runs 表）。"""

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from wws_adviser.core.db import Base


class JobRun(Base):
    __tablename__ = "job_runs"
    __table_args__ = (
        sa.UniqueConstraint(
            "job_type", "business_date", "scope_key", "config_version", name="uq_job_runs_idem"
        ),
        sa.Index("ix_job_runs_status_lease", "status", "lease_until"),
        sa.Index("ix_job_runs_idempotency_key", "idempotency_key"),
    )

    id: Mapped[str] = mapped_column(sa.String(26), primary_key=True)
    job_type: Mapped[str] = mapped_column(sa.Text, nullable=False)
    business_date: Mapped[str] = mapped_column(sa.Text, nullable=False)
    scope_key: Mapped[str] = mapped_column(sa.Text, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(sa.Text)
    config_version: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(sa.Text, nullable=False)
    attempt: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    lease_until: Mapped[str | None] = mapped_column(sa.Text)
    progress: Mapped[int | None] = mapped_column(sa.Integer)
    error_code: Mapped[str | None] = mapped_column(sa.Text)
    next_retry_at: Mapped[str | None] = mapped_column(sa.Text)
    started_at: Mapped[str | None] = mapped_column(sa.Text)
    completed_at: Mapped[str | None] = mapped_column(sa.Text)
    result_ref: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
