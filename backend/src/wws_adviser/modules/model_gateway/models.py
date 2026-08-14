"""Model gateway ORM：model_profiles、model_calls（波6，2_DATA §6.7）。

key_ref 只存 env 变量名；model_calls 为调用审计（无 key、无完整敏感 prompt）。
"""

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from wws_adviser.core.db import Base


class ModelProfile(Base):
    __tablename__ = "model_profiles"
    __table_args__ = (sa.UniqueConstraint("name", name="uq_model_profiles_name"),)

    id: Mapped[str] = mapped_column(sa.String(26), primary_key=True)
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    base_url: Mapped[str] = mapped_column(sa.Text, nullable=False)
    model_name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    key_ref: Mapped[str] = mapped_column(sa.Text, nullable=False)
    temperature: Mapped[float | None] = mapped_column(sa.Float)
    max_tokens: Mapped[int | None] = mapped_column(sa.Integer)
    timeout: Mapped[float | None] = mapped_column(sa.Float)
    retry: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)
    task_routes_json: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
    version: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)


class ModelCall(Base):
    __tablename__ = "model_calls"
    __table_args__ = (
        sa.Index("ix_model_calls_job_run", "job_run_id"),
        sa.Index("ix_model_calls_profile_started", "model_profile_id", "started_at"),
    )

    id: Mapped[str] = mapped_column(sa.String(26), primary_key=True)
    job_run_id: Mapped[str | None] = mapped_column(sa.String(26), sa.ForeignKey("job_runs.id"))
    model_profile_id: Mapped[str] = mapped_column(
        sa.String(26), sa.ForeignKey("model_profiles.id"), nullable=False
    )
    task_type: Mapped[str] = mapped_column(sa.Text, nullable=False)
    prompt_template: Mapped[str] = mapped_column(sa.Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(sa.Text, nullable=False)
    prompt_hash: Mapped[str] = mapped_column(sa.Text, nullable=False)
    input_evidence_ids_json: Mapped[str | None] = mapped_column(sa.Text)
    started_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
    ended_at: Mapped[str | None] = mapped_column(sa.Text)
    prompt_tokens: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)
    estimated_cost: Mapped[float] = mapped_column(sa.Float, nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(sa.Text, nullable=False)
    error_code: Mapped[str | None] = mapped_column(sa.Text)
    created_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
