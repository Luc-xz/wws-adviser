"""Research 服务：任务创建/查询/执行编排（Phase 3 波1，FR-RES-001）。

流程（TECH §10.4）：
    创建任务（PENDING）→ 执行器领取（RUNNING）→ 证据收集 → 确定性分析 →
    模型生成 → 输出校验 → 保存报告（COMPLETED）
"""

import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from wws_adviser.core.errors import DomainError
from wws_adviser.core.ids import new_id
from wws_adviser.core.time import now_utc_iso
from wws_adviser.modules.research.domain import (
    ResearchStatus,
    ResearchTaskType,
    transition,
)
from wws_adviser.modules.research.models import ResearchReport, ResearchTask

_logger = logging.getLogger(__name__)


def create_task(
    db: DBSession,
    *,
    user_id: str,
    task_type: str,
    subject: str,
    peer_codes: list[str] | None = None,
    time_span: str | None = None,
    depth: str = "standard",
) -> ResearchTask:
    """创建研究任务（幂等：同用户+类型+主题+深度不重复）。"""
    if task_type not in {t.value for t in ResearchTaskType}:
        raise DomainError(f"未知研究类型：{task_type}")
    if not subject.strip():
        raise DomainError("研究主题不能为空")
    existing = db.scalar(
        select(ResearchTask).where(
            ResearchTask.user_id == user_id,
            ResearchTask.task_type == task_type,
            ResearchTask.subject == subject,
            ResearchTask.depth == depth,
            ResearchTask.status.in_([ResearchStatus.PENDING.value, ResearchStatus.RUNNING.value]),
        )
    )
    if existing is not None:
        return existing
    now = now_utc_iso()
    task = ResearchTask(
        id=new_id(), user_id=user_id, task_type=task_type, subject=subject.strip(),
        peer_codes_json=json.dumps(peer_codes, ensure_ascii=False) if peer_codes else None,
        time_span=time_span, depth=depth,
        status=ResearchStatus.PENDING.value,
        created_at=now, updated_at=now,
    )
    db.add(task)
    db.commit()
    return task


def get_task(db: DBSession, task_id: str) -> ResearchTask | None:
    return db.scalar(select(ResearchTask).where(ResearchTask.id == task_id))


def get_report_task_checked(
    db: DBSession, task_id: str, user_id: str
) -> ResearchTask:
    """取任务并校验属主（不存在/越权统一报「任务不存在」）。"""
    task = get_task(db, task_id)
    if task is None or task.user_id != user_id:
        raise DomainError("任务不存在")
    return task


def list_tasks(
    db: DBSession, user_id: str, *, limit: int = 20
) -> list[ResearchTask]:
    return list(db.scalars(
        select(ResearchTask)
        .where(ResearchTask.user_id == user_id)
        .order_by(ResearchTask.created_at.desc())
        .limit(limit)
    ))


def claim_pending(
    db: DBSession, *, task_type: str | None = None
) -> ResearchTask | None:
    """领取一个待执行任务（PENDING → RUNNING）。

    task_type 过滤用于渐进上线：执行器只领取已实现流水线的类型，
    未实现类型的任务保持 PENDING。
    """
    stmt = (
        select(ResearchTask)
        .where(ResearchTask.status == ResearchStatus.PENDING.value)
        .order_by(ResearchTask.created_at)
        .limit(1)
    )
    if task_type is not None:
        stmt = stmt.where(ResearchTask.task_type == task_type)
    task = db.scalar(stmt)
    if task is None:
        return None
    task.status = transition(ResearchStatus(task.status), ResearchStatus.RUNNING).value
    task.started_at = now_utc_iso()
    task.progress = 5
    db.commit()
    return task


def update_progress(db: DBSession, task: ResearchTask, progress: int) -> None:
    task.progress = max(0, min(100, progress))
    task.updated_at = now_utc_iso()
    db.commit()


def complete_task(db: DBSession, task: ResearchTask, report_id: str) -> None:
    task.status = transition(ResearchStatus(task.status), ResearchStatus.COMPLETED).value
    task.report_id = report_id
    task.progress = 100
    task.completed_at = now_utc_iso()
    task.updated_at = now_utc_iso()
    db.commit()


def fail_task(db: DBSession, task: ResearchTask, error_code: str) -> None:
    task.status = transition(ResearchStatus(task.status), ResearchStatus.FAILED).value
    task.error_code = error_code
    task.updated_at = now_utc_iso()
    db.commit()


def cancel_task(db: DBSession, task_id: str, user_id: str) -> ResearchTask:
    """用户取消（仅 PENDING 态可取消）。"""
    task = get_task(db, task_id)
    if task is None or task.user_id != user_id:
        raise DomainError("任务不存在")
    task.status = transition(ResearchStatus(task.status), ResearchStatus.CANCELLED).value
    task.updated_at = now_utc_iso()
    db.commit()
    return task


def save_report(
    db: DBSession,
    task: ResearchTask,
    *,
    data_dir: Path,
    content_md: str,
    citations_json: list[dict[str, Any]],
    generation_config: dict[str, Any],
) -> ResearchReport:
    """保存研究报告（原子写文件 + 落库）。"""
    report_id = new_id()
    rel_dir = f"research/{task.id}"
    abs_dir = data_dir / rel_dir
    abs_dir.mkdir(parents=True, exist_ok=True)
    md_rel = f"{rel_dir}/report.md"
    (data_dir / md_rel).write_text(content_md, encoding="utf-8")

    now = now_utc_iso()
    report = ResearchReport(
        id=report_id, task_id=task.id,
        report_type=task.task_type, subject=task.subject,
        content_md_path=md_rel,
        citations_json=json.dumps(citations_json, ensure_ascii=False),
        generation_config_json=json.dumps(generation_config, ensure_ascii=False),
        created_at=now,
    )
    db.add(report)
    db.commit()
    return report


def get_report(db: DBSession, report_id: str) -> ResearchReport | None:
    return db.scalar(select(ResearchReport).where(ResearchReport.id == report_id))
