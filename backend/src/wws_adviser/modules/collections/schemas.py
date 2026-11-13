"""Collections Pydantic schema（GET /collections/*，3_API §3.17）。"""

from typing import cast

from pydantic import BaseModel

from wws_adviser.modules.collections.models import IngestItem


class SourceHealthOut(BaseModel):
    category: str
    status: str  # ok / degraded / unavailable / no_data
    configured: bool  # False = 无真实 provider（news 仅 stub，FR-DATA-005）
    last_success_at: str | None
    last_failure_at: str | None
    consecutive_failures: int
    last_error_code: str | None
    last_error_message: str | None
    latest_data: dict[str, object] | None  # 数据集覆盖：最新业务日期/近 7 天行数


class CollectionsHealthResponse(BaseModel):
    generated_at: str
    sources: list[SourceHealthOut]


class IngestItemOut(BaseModel):
    id: str
    run_id: str | None
    category: str
    action: str  # ingested / updated / skipped / synced / no_data / failed
    status: str  # OK / PARTIAL / SKIPPED / FAILED
    target_ref: str
    display_name: str
    rows_written: int | None
    source: str | None
    duration_ms: int | None
    error_code: str | None
    error_message: str | None
    data_ref: str | None
    created_at: str


class IngestItemListResponse(BaseModel):
    items: list[IngestItemOut]
    next_cursor: str | None


def item_to_out(item: IngestItem) -> IngestItemOut:
    return IngestItemOut(
        id=item.id,
        run_id=item.run_id,
        category=item.category,
        action=item.action,
        status=item.status,
        target_ref=item.target_ref,
        display_name=item.display_name,
        rows_written=item.rows_written,
        source=item.source,
        duration_ms=item.duration_ms,
        error_code=item.error_code,
        error_message=item.error_message,
        data_ref=item.data_ref,
        created_at=item.created_at,
    )


def source_health_to_out(s: dict[str, object]) -> SourceHealthOut:
    """service.health_overview 的 sources 条目 → 响应模型（显式字段，免 **dict 类型漂移）。"""
    return SourceHealthOut(
        category=str(s["category"]),
        status=str(s["status"]),
        configured=bool(s["configured"]),
        last_success_at=cast("str | None", s.get("last_success_at")),
        last_failure_at=cast("str | None", s.get("last_failure_at")),
        consecutive_failures=cast(int, s.get("consecutive_failures", 0)),
        last_error_code=cast("str | None", s.get("last_error_code")),
        last_error_message=cast("str | None", s.get("last_error_message")),
        latest_data=cast("dict[str, object] | None", s.get("latest_data")),
    )
