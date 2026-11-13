"""Jobs DTO（GET /api/v1/jobs*，3_API §3.13）。"""

from pydantic import BaseModel


class JobRunOut(BaseModel):
    id: str
    job_type: str
    business_date: str
    scope_key: str
    status: str
    attempt: int
    max_attempts: int
    progress: int | None = None
    error_code: str | None = None
    result_ref: str | None = None
    result_summary: dict[str, object] = {}  # result_ref 解析摘要（parse_result_ref）
    item_counts: dict[str, int] = {}  # 条目状态计数（ingest_items；历史批次为空）
    started_at: str | None = None
    completed_at: str | None = None
    created_at: str | None = None


class JobListResponse(BaseModel):
    items: list[JobRunOut]
    next_cursor: str | None


class JobStatsResponse(BaseModel):
    window_days: int
    total: int
    by_status: dict[str, int]
    success_rate: float | None  # (COMPLETED+PARTIAL)/已终态（FAILED 计分母，CANCELLED 不计）
    avg_duration_ms: int | None
    consecutive_failures: dict[str, int]  # job_type → 当前连续失败数（窗口内最新序列）
