"""Jobs 领域：任务类型与状态机。纯领域，禁框架 import。"""

from enum import StrEnum


class JobStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    RETRY_WAIT = "RETRY_WAIT"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class JobType(StrEnum):
    PRE_MARKET = "pre_market"
    POST_MARKET = "post_market"
    BACKUP = "backup"
    DATA_MAINTENANCE = "data_maintenance"
    CALIBRATION_SCAN = "calibration_scan"
    ADVICE_REVIEW = "advice_review"
    INGEST_MANUAL = "ingest_manual"  # 手动补采批次（refresh 端点同步执行，5_DATA §12.2）
    # 市场环境数据域（ADR-0014 / 5_DATA §13.5）
    MARKET_ENV_INTRADAY = "market_env_intraday"  # 交易日 09:00-15:00 每 5 分钟（scope_key=HH:MM）
    MARKET_ENV_EOD = "market_env_eod"  # 15:25 指数日K + 板块终态
    OVERSEAS_MORNING = "overseas_morning"  # 08:10 隔夜外围 + 美股期货（盘前参考）
    STUB = "stub"


# 合法状态转换（from -> {to}），见 6_MODEL_AND_REPORT_PIPELINE.md §8.2
_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.PENDING: frozenset({JobStatus.RUNNING, JobStatus.CANCELLED}),
    JobStatus.RUNNING: frozenset(
        {
            JobStatus.COMPLETED,
            JobStatus.RETRY_WAIT,
            JobStatus.PARTIAL,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        }
    ),
    JobStatus.RETRY_WAIT: frozenset({JobStatus.RUNNING}),
}


def can_transition(src: JobStatus, dst: JobStatus) -> bool:
    return dst in _TRANSITIONS.get(src, frozenset())
