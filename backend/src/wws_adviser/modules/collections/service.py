"""Collections 服务：采集可观测性（5_DATA §12）——源健康/条目记录 + 查询聚合。

写入点约定：record_* 由 market_data/documents 服务层调用（不进 infrastructure 适配器，
四层依赖方向）；record_failure 先 rollback 丢弃半程未审计数据，再单独提交观测行——
失败路径绝不能把半程数据连带提交。
"""

from sqlalchemy.orm import Session as DBSession

from wws_adviser.core.config import Settings
from wws_adviser.core.ids import new_id
from wws_adviser.core.time import now_utc_iso
from wws_adviser.modules.collections import repository
from wws_adviser.modules.collections.domain import Category, HealthStatus, encode_cursor
from wws_adviser.modules.collections.models import IngestItem

# FR-DATA-005 新闻仅 stub 实现（无真实 provider）——面板如实暴露缺口（5_DATA §12.3）
_UNCONFIGURED_CATEGORIES = frozenset({Category.NEWS.value})


# —— 写入（service 层调用） ——


def record_source_success(db: DBSession, category: str) -> None:
    """源健康成功（连败清零）。随调用方事务提交。"""
    repository.upsert_health_success(db, category)


def record_source_failure(
    db: DBSession, category: str, *, error_code: str, error_message: str | None = None
) -> None:
    """源健康失败（连败 +1）。随调用方事务提交；采集失败组合场景用 record_failure。"""
    repository.upsert_health_failure(
        db, category, error_code=error_code, error_message=error_message
    )


def record_item(
    db: DBSession,
    *,
    category: str,
    target_ref: str,
    display_name: str,
    action: str,
    status: str,
    run_id: str | None = None,
    rows_written: int | None = None,
    source: str | None = None,
    duration_ms: int | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    data_ref: str | None = None,
) -> None:
    """记一条采集条目。随调用方事务提交。"""
    repository.add_item(
        db,
        IngestItem(
            id=new_id(),
            run_id=run_id,
            category=category,
            action=action,
            status=status,
            target_ref=target_ref,
            display_name=display_name,
            rows_written=rows_written,
            source=source,
            duration_ms=duration_ms,
            error_code=error_code,
            error_message=(error_message[:200] if error_message else None),
            data_ref=data_ref,
            created_at=now_utc_iso(),
        ),
    )


def record_failure(
    db: DBSession,
    *,
    category: str,
    target_ref: str,
    display_name: str,
    error_code: str,
    error_message: str | None = None,
    run_id: str | None = None,
    duration_ms: int | None = None,
    source: str | None = None,
) -> None:
    """采集失败落观测：rollback 丢弃半程未审计数据 → 写 source_health + FAILED 条目并提交。"""
    db.rollback()
    repository.upsert_health_failure(
        db, category, error_code=error_code, error_message=error_message
    )
    record_item(
        db,
        category=category,
        run_id=run_id,
        target_ref=target_ref,
        display_name=display_name,
        action="failed",
        status="FAILED",
        error_code=error_code,
        error_message=error_message,
        duration_ms=duration_ms,
        source=source,
    )
    db.commit()


# —— 查询（API 层调用） ——


def health_overview(db: DBSession, settings: Settings) -> dict[str, object]:
    """六类别源健康 + 数据集覆盖（GET /collections/health）。

    派生状态：连败 ≥ unavailable_after → unavailable；≥ degraded_after → degraded；
    否则 ok；无行 → no_data（never collected）。
    """
    rows = repository.get_all_health(db)
    coverage = repository.dataset_coverage(db)
    sources: list[dict[str, object]] = []
    for cat in Category:
        row = rows.get(cat.value)
        entry: dict[str, object] = {
            "category": cat.value,
            "configured": cat.value not in _UNCONFIGURED_CATEGORIES,
            "last_success_at": None,
            "last_failure_at": None,
            "consecutive_failures": 0,
            "last_error_code": None,
            "last_error_message": None,
        }
        if row is None:
            entry["status"] = HealthStatus.NO_DATA.value
        else:
            cf = row.consecutive_failures or 0
            if cf >= settings.source_health_unavailable_after:
                entry["status"] = HealthStatus.UNAVAILABLE.value
            elif cf >= settings.source_health_degraded_after:
                entry["status"] = HealthStatus.DEGRADED.value
            else:
                entry["status"] = HealthStatus.OK.value
            entry.update(
                {
                    "last_success_at": row.last_success_at,
                    "last_failure_at": row.last_failure_at,
                    "consecutive_failures": cf,
                    "last_error_code": row.last_error_code,
                    "last_error_message": row.last_error_message,
                }
            )
        entry["latest_data"] = coverage.get(cat.value)
        sources.append(entry)
    return {"generated_at": now_utc_iso(), "sources": sources}


def list_items_page(
    db: DBSession,
    *,
    run_id: str | None = None,
    category: str | None = None,
    status: str | None = None,
    q: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> tuple[list[IngestItem], str | None]:
    """条目分页查询（run 下钻与跨批次检索共用；cursor 见 domain.decode_cursor）。"""
    from wws_adviser.modules.collections.domain import decode_cursor

    cursor_created_at: str | None = None
    cursor_id: str | None = None
    if cursor:
        cursor_created_at, cursor_id = decode_cursor(cursor)
    items, has_more = repository.list_items(
        db,
        run_id=run_id,
        category=category,
        status=status,
        q=q,
        date_from=date_from,
        date_to=date_to,
        cursor_created_at=cursor_created_at,
        cursor_id=cursor_id,
        limit=limit,
    )
    next_cursor = (
        encode_cursor(created_at=items[-1].created_at, item_id=items[-1].id)
        if has_more and items
        else None
    )
    return items, next_cursor


def prune_ingest_items(db: DBSession, settings: Settings) -> int:
    """按保留期清理条目（data_maintenance 收尾调用，5_DATA §11.1）。"""
    if settings.ingest_item_retention_days <= 0:
        return 0
    before = _iso_minus_days(now_utc_iso(), settings.ingest_item_retention_days)
    n = repository.prune_items(db, before_created_at=before)
    db.commit()
    return n


def _iso_minus_days(iso_ts: str, days: int) -> str:
    from datetime import datetime, timedelta

    try:
        return (datetime.fromisoformat(iso_ts) - timedelta(days=days)).isoformat()
    except ValueError:
        return iso_ts


__all__ = [
    "health_overview",
    "list_items_page",
    "prune_ingest_items",
    "record_failure",
    "record_item",
    "record_source_failure",
    "record_source_success",
]
