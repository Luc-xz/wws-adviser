"""研究任务执行器：领取 PENDING 任务并运行对应流水线（Phase 3 波4）。

由 main.py 常驻执行器线程在报告任务之后调用（同一轮询循环）。
单任务失败 → fail_task（error_code 保留原因），不影响后续任务。
"""

import logging
from pathlib import Path

from sqlalchemy.orm import Session as DBSession

from wws_adviser.core.config import Settings
from wws_adviser.modules.research import generation, service
from wws_adviser.modules.research.domain import ResearchTaskType
from wws_adviser.ports.model import ModelPort

_logger = logging.getLogger(__name__)

# 已实现流水线的任务类型（行业研究在波5接入）
_SUPPORTED_TYPES = {ResearchTaskType.COMPANY.value}


async def run_pending(
    db: DBSession,
    settings: Settings,
    data_dir: Path,
    *,
    model_port: ModelPort | None,
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
        try:
            await generation.run_company_research(
                db, settings, model_port, task=task, data_dir=data_dir,
            )
            ran += 1
        except Exception as exc:  # noqa: BLE001 — 执行器边界：单任务失败不阻断
            code = str(exc).split("：", 1)[0][:120] or type(exc).__name__
            service.fail_task(db, task, code)
            _logger.warning("研究任务 %s 失败：%s", task.id, exc)
    return ran
