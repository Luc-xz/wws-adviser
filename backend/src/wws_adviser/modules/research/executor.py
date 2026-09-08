"""研究任务执行器：领取 PENDING 任务并运行对应流水线（Phase 3 波4/波5）。

由 main.py 常驻执行器线程在报告任务之后调用（同一轮询循环）。
单任务失败 → fail_task（error_code 保留原因），不影响后续任务。
任务终态后发送通知（FR-NOTIFY-002「异步研究报告完成」）；
通知失败绝不失败研究任务（FR-NOTIFY-001）。payload 不含标的名称
（FR-NOTIFY-003 隐私默认开启：task_type + id 即可，登录后查看详情）。
"""

import logging
from pathlib import Path

from sqlalchemy.orm import Session as DBSession

from wws_adviser.core.config import Settings
from wws_adviser.modules.notifications import service as notifications_service
from wws_adviser.modules.notifications.domain import NotificationEvent
from wws_adviser.modules.research import generation, service
from wws_adviser.modules.research.domain import ResearchTaskType
from wws_adviser.ports.model import ModelPort
from wws_adviser.ports.notifier import NotifierPort

_logger = logging.getLogger(__name__)

# 已实现流水线的任务类型
_SUPPORTED_TYPES = {ResearchTaskType.COMPANY.value, ResearchTaskType.INDUSTRY.value}


async def _notify_research_event(
    db: DBSession,
    settings: Settings,
    notifier: NotifierPort | None,
    *,
    event_type: str,
    payload: dict[str, object],
) -> None:
    """发送研究任务通知；任何失败只记日志（FR-NOTIFY-001）。"""
    if notifier is None:
        return
    try:
        await notifications_service.notify(
            db, settings, notifier, event_type=event_type, payload=payload
        )
    except Exception as exc:  # noqa: BLE001 — 通知绝不影响研究任务
        _logger.warning("研究任务通知发送失败（不影响任务）: %s", exc)


async def run_pending(
    db: DBSession,
    settings: Settings,
    data_dir: Path,
    *,
    model_port: ModelPort | None,
    notifier: NotifierPort | None = None,
    limit: int = 1,
) -> int:
    """领取并执行待处理研究任务。返回本轮执行的任务数。"""
    if model_port is None:
        return 0  # 无模型端口（如测试环境未配置）时不领取，任务保持 PENDING

    ran = 0
    for _ in range(limit):
        task = service.claim_pending(db)
        if task is None:
            break
        if task.task_type not in _SUPPORTED_TYPES:
            # 未支持类型：回退 PENDING（claim_pending 不带过滤领取时的兜底）
            task.status = "PENDING"
            task.progress = 0
            db.commit()
            continue
        pipeline = (
            generation.run_industry_research
            if task.task_type == ResearchTaskType.INDUSTRY.value
            else generation.run_company_research
        )
        try:
            report_id = await pipeline(db, settings, model_port, task=task, data_dir=data_dir)
            ran += 1
            await _notify_research_event(
                db, settings, notifier,
                event_type=NotificationEvent.RESEARCH_COMPLETED.value,
                payload={
                    "task_type": task.task_type,
                    "task_id": task.id,
                    "report_id": report_id,
                },
            )
        except Exception as exc:  # noqa: BLE001 — 执行器边界：单任务失败不阻断
            code = str(exc).split("：", 1)[0][:120] or type(exc).__name__
            service.fail_task(db, task, code)
            _logger.warning("研究任务 %s 失败：%s", task.id, exc)
            await _notify_research_event(
                db, settings, notifier,
                event_type=NotificationEvent.RESEARCH_FAILED.value,
                payload={"task_type": task.task_type, "task_id": task.id, "error_code": code},
            )
    return ran
