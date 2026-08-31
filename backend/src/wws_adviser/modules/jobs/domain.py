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
