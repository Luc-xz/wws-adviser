"""Research ORM：研究任务与报告（Phase 3，FR-RES-001~004）。

- research_tasks：用户创建的公司/行业研究任务（异步执行，可离开页面）。
- research_reports：研究产出（含引用清单和生成配置，可复盘）。

Decimal 字符串存储（与 market_records 同约定）。
"""

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from wws_adviser.core.db import Base


class ResearchTask(Base):
    __tablename__ = "research_tasks"
    __table_args__ = (
        sa.Index("ix_research_tasks_user_created", "user_id", "created_at"),
        sa.Index("ix_research_tasks_status", "status"),
    )

    id: Mapped[str] = mapped_column(sa.String(26), primary_key=True)
    user_id: Mapped[str] = mapped_column(sa.String(26), sa.ForeignKey("users.id"), nullable=False)
    task_type: Mapped[str] = mapped_column(sa.Text, nullable=False)  # company | industry
    # 公司研究：证券代码；行业研究：行业名称/代码
    subject: Mapped[str] = mapped_column(sa.Text, nullable=False)
    # 可选参数
    peer_codes_json: Mapped[str | None] = mapped_column(sa.Text)    # 可比公司列表
    time_span: Mapped[str | None] = mapped_column(sa.Text)          # "3y" | "5y" | "max"
    # quick | standard | deep
    depth: Mapped[str] = mapped_column(sa.Text, nullable=False, default="standard")
    # 执行状态
    status: Mapped[str] = mapped_column(sa.Text, nullable=False, default="PENDING")
    progress: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=0)  # 0-100
    error_code: Mapped[str | None] = mapped_column(sa.Text)
    started_at: Mapped[str | None] = mapped_column(sa.Text)
    completed_at: Mapped[str | None] = mapped_column(sa.Text)
    # 关联产出
    report_id: Mapped[str | None] = mapped_column(sa.String(26))
    created_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(sa.Text, nullable=False)


class ResearchReport(Base):
    __tablename__ = "research_reports"
    __table_args__ = (
        sa.Index("ix_research_reports_task", "task_id"),
    )

    id: Mapped[str] = mapped_column(sa.String(26), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        sa.String(26), sa.ForeignKey("research_tasks.id"), nullable=False
    )
    report_type: Mapped[str] = mapped_column(sa.Text, nullable=False)  # company | industry
    subject: Mapped[str] = mapped_column(sa.Text, nullable=False)
    # 结构化内容 JSON（含 sections/evidence/version_refs）
    content_json_path: Mapped[str | None] = mapped_column(sa.Text)
    content_md_path: Mapped[str | None] = mapped_column(sa.Text)
    # 引用清单 JSON（evidence_id → 定位信息，可追溯）
    citations_json: Mapped[str | None] = mapped_column(sa.Text)
    # 生成配置快照（模板版本/模型/参数，可复盘）
    generation_config_json: Mapped[str | None] = mapped_column(sa.Text)
    version: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)
    created_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
