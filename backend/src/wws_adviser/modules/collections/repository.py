"""Collections 仓储：source_health upsert + ingest_items 写入/查询/清理。

数据集覆盖查询跨模块只读聚合 market_data/documents 表（5_DATA §12.3）——
模块边界上属读取侧聚合（同 audit/api 直查 AuditEvent 的先例），不引入写耦合。
"""

from datetime import date, timedelta
from typing import Any, cast

from sqlalchemy import ColumnElement, delete, func, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session as DBSession

from wws_adviser.core.time import now_utc_iso
from wws_adviser.modules.collections.models import IngestItem, SourceHealth
from wws_adviser.modules.documents.models import Document
from wws_adviser.modules.market_data.models import MarketRecord, NavRecord, TradingCalendar
from wws_adviser.modules.market_env.models import IndexBar, IndexQuote, SectorFlowSnapshot

_ERROR_MESSAGE_MAX = 200


def _trunc(message: str | None) -> str | None:
    if message is None:
        return None
    return message[:_ERROR_MESSAGE_MAX]


# —— source_health（类别级 upsert） ——


def upsert_health_success(db: DBSession, category: str) -> None:
    row = db.get(SourceHealth, category)
    now = now_utc_iso()
    if row is None:
        db.add(
            SourceHealth(
                category=category,
                last_success_at=now,
                consecutive_failures=0,
                updated_at=now,
            )
        )
        return
    row.last_success_at = now
    row.consecutive_failures = 0
    row.updated_at = now


def upsert_health_failure(
    db: DBSession, category: str, *, error_code: str, error_message: str | None
) -> None:
    row = db.get(SourceHealth, category)
    now = now_utc_iso()
    if row is None:
        db.add(
            SourceHealth(
                category=category,
                last_failure_at=now,
                consecutive_failures=1,
                last_error_code=error_code,
                last_error_message=_trunc(error_message),
                updated_at=now,
            )
        )
        return
    row.last_failure_at = now
    row.consecutive_failures = (row.consecutive_failures or 0) + 1
    row.last_error_code = error_code
    row.last_error_message = _trunc(error_message)
    row.updated_at = now


def get_all_health(db: DBSession) -> dict[str, SourceHealth]:
    return {row.category: row for row in db.scalars(select(SourceHealth)).all()}


# —— ingest_items（append-only 明细） ——


def add_item(db: DBSession, item: IngestItem) -> None:
    db.add(item)


def list_items(
    db: DBSession,
    *,
    run_id: str | None = None,
    category: str | None = None,
    status: str | None = None,
    q: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    cursor_created_at: str | None = None,
    cursor_id: str | None = None,
    limit: int = 50,
) -> tuple[list[IngestItem], bool]:
    """游标分页查询（created_at DESC, id DESC，3_API §4）。返回 (items, has_more)。"""
    stmt = select(IngestItem)
    filters: list[ColumnElement[bool]] = []
    if run_id is not None:
        filters.append(IngestItem.run_id == run_id)
    if category is not None:
        filters.append(IngestItem.category == category)
    if status is not None:
        filters.append(IngestItem.status == status)
    if q:
        filters.append(IngestItem.display_name.contains(q))
    if date_from is not None:
        filters.append(IngestItem.created_at >= date_from)
    if date_to is not None:
        filters.append(IngestItem.created_at < date_to)
    if cursor_created_at is not None and cursor_id is not None:
        filters.append(
            (IngestItem.created_at < cursor_created_at)
            | ((IngestItem.created_at == cursor_created_at) & (IngestItem.id < cursor_id))
        )
    if filters:
        stmt = stmt.where(*filters)
    rows = list(
        db.scalars(
            stmt.order_by(IngestItem.created_at.desc(), IngestItem.id.desc()).limit(limit + 1)
        ).all()
    )
    has_more = len(rows) > limit
    return (rows[:limit], has_more)


def item_counts_by_run(db: DBSession, run_ids: list[str]) -> dict[str, dict[str, int]]:
    """批次 → 条目状态计数（任务列表摘要用；空列表直接返回）。"""
    if not run_ids:
        return {}
    rows = db.execute(
        select(IngestItem.run_id, IngestItem.status, func.count())
        .where(IngestItem.run_id.in_(run_ids))
        .group_by(IngestItem.run_id, IngestItem.status)
    ).all()
    out: dict[str, dict[str, int]] = {}
    for run_id, status, n in rows:
        out.setdefault(run_id, {})[status] = int(n)
    return out


def prune_items(db: DBSession, *, before_created_at: str) -> int:
    result = db.execute(delete(IngestItem).where(IngestItem.created_at < before_created_at))
    return int(cast("CursorResult[Any]", result).rowcount or 0)


# —— 数据集覆盖（只读聚合，GET /collections/health） ——


def dataset_coverage(db: DBSession) -> dict[str, dict[str, object]]:
    """各数据集最新业务日期 + 近 7 天行数（无该类数据时值为 None）。"""
    week_ago_date = (date.today() - timedelta(days=7)).isoformat()
    week_ago_ts = _iso_minus_days(now_utc_iso(), 7)

    bar_latest = db.scalar(select(func.max(MarketRecord.business_date)))
    bar_7d = db.scalar(
        select(func.count()).select_from(MarketRecord).where(
            MarketRecord.business_date >= week_ago_date
        )
    )
    nav_latest = db.scalar(select(func.max(NavRecord.nav_date)))
    nav_7d = db.scalar(
        select(func.count()).select_from(NavRecord).where(NavRecord.nav_date >= week_ago_date)
    )
    cal_latest = db.scalar(select(func.max(TradingCalendar.date)))
    doc_total = db.scalar(select(func.count()).select_from(Document))
    doc_latest_published = db.scalar(select(func.max(Document.published_at)))
    doc_7d = db.scalar(
        select(func.count()).select_from(Document).where(Document.created_at >= week_ago_ts)
    )
    # 市场环境三类别（ADR-0014 / 5_DATA §12.3 同口径：最新业务时间 + 近 7 天行数）
    iq_latest = db.scalar(select(func.max(IndexQuote.market_time)))
    iq_7d = db.scalar(
        select(func.count()).select_from(IndexQuote).where(IndexQuote.market_time >= week_ago_ts)
    )
    ibar_latest = db.scalar(select(func.max(IndexBar.business_date)))
    ibar_7d = db.scalar(
        select(func.count()).select_from(IndexBar).where(IndexBar.business_date >= week_ago_date)
    )
    sf_latest = db.scalar(select(func.max(SectorFlowSnapshot.snapshot_at)))
    sf_7d = db.scalar(
        select(func.count())
        .select_from(SectorFlowSnapshot)
        .where(SectorFlowSnapshot.snapshot_at >= week_ago_ts)
    )
    return {
        "bar": {"latest_business_date": bar_latest, "rows_7d": int(bar_7d or 0)},
        "nav": {"latest_business_date": nav_latest, "rows_7d": int(nav_7d or 0)},
        "calendar": {"latest_business_date": cal_latest, "rows_7d": None},
        "document": {
            "total": int(doc_total or 0),
            "latest_published_at": doc_latest_published,
            "rows_7d": int(doc_7d or 0),
        },
        "index_quote": {"latest_business_date": iq_latest, "rows_7d": int(iq_7d or 0)},
        "index_bar": {"latest_business_date": ibar_latest, "rows_7d": int(ibar_7d or 0)},
        "sector_flow": {"latest_business_date": sf_latest, "rows_7d": int(sf_7d or 0)},
    }


def _iso_minus_days(iso_ts: str, days: int) -> str:
    """ISO 时间戳减天数（字符串运算足够：ISO 8601 字典序即时间序）。"""
    from datetime import datetime
    from datetime import timedelta as _td

    try:
        return (datetime.fromisoformat(iso_ts) - _td(days=days)).isoformat()
    except ValueError:
        return iso_ts
