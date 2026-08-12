"""单 worker 守卫。

WWS Adviser 依赖单 worker 保证 SQLite WAL 写入与单调度实例正确性。
生产环境多 worker 直接拒绝启动；非生产告警但继续（见 1_REPO_STRUCTURE.md §7）。
"""

import logging
import os

from wws_adviser.core.config import Settings

_logger = logging.getLogger(__name__)


class MultiWorkerError(RuntimeError):
    """生产环境检测到多 worker 配置。"""


def _parse_int(value: str | None) -> int | None:
    if value is None or value.strip() == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def detected_workers(settings: Settings) -> int:
    """当前推断的 worker 数：优先 WEB_CONCURRENCY 环境变量，否则配置值。"""
    return _parse_int(os.environ.get("WEB_CONCURRENCY")) or settings.expected_workers


def enforce_single_worker(settings: Settings) -> None:
    workers = detected_workers(settings)
    if workers <= 1:
        return
    if settings.is_prod:
        raise MultiWorkerError(
            f"生产环境禁止多 worker（检测到 {workers}）。"
            "WWS Adviser 依赖单 worker 保证 SQLite/调度正确性。"
        )
    _logger.warning(
        "检测到多 worker 配置（%s），非生产环境继续，但生产环境将拒绝启动", workers
    )
