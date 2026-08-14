"""Market data 仓储：日线/净值的元数据索引（SQLite）。完整序列另存 Parquet。

upsert 走「预查 → 更新/插入」（单 worker 安全；多 worker 需补 UNIQUE 冲突捕获）。
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from wws_adviser.modules.market_data.models import MarketRecord, NavRecord, TradingCalendar

# —— market_records ——


def upsert_market_record(db: DBSession, record: MarketRecord) -> None:
    existing = db.scalar(
        select(MarketRecord).where(
            MarketRecord.instrument_id == record.instrument_id,
            MarketRecord.business_date == record.business_date,
            MarketRecord.source == record.source,
            MarketRecord.adjustment_type == record.adjustment_type,
        )
    )
    if existing is not None:
        existing.open = record.open
        existing.high = record.high
        existing.low = record.low
        existing.close = record.close
        existing.volume = record.volume
        existing.amount = record.amount
        existing.market_time = record.market_time
        existing.fetched_at = record.fetched_at
        existing.received_at = record.received_at
        existing.source_delay_class = record.source_delay_class
        existing.quality_status = record.quality_status
        existing.content_hash = record.content_hash
        existing.updated_at = record.updated_at
        existing.version += 1
        return
    db.add(record)
    db.flush()


def get_latest_market_record(
    db: DBSession, instrument_id: str, *, source: str, adjustment_type: str = "none"
) -> MarketRecord | None:
    return db.scalar(
        select(MarketRecord)
        .where(
            MarketRecord.instrument_id == instrument_id,
            MarketRecord.source == source,
            MarketRecord.adjustment_type == adjustment_type,
        )
        .order_by(MarketRecord.business_date.desc())
        .limit(1)
    )


def list_market_records(
    db: DBSession,
    instrument_id: str,
    *,
    source: str | None = None,
    adjustment_type: str = "none",
    start: str | None = None,
    end: str | None = None,
) -> list[MarketRecord]:
    stmt = select(MarketRecord).where(
        MarketRecord.instrument_id == instrument_id,
        MarketRecord.adjustment_type == adjustment_type,
    )
    if source is not None:
        stmt = stmt.where(MarketRecord.source == source)
    if start is not None:
        stmt = stmt.where(MarketRecord.business_date >= start)
    if end is not None:
        stmt = stmt.where(MarketRecord.business_date <= end)
    stmt = stmt.order_by(MarketRecord.business_date)
    return list(db.scalars(stmt))


# —— nav_records ——


def upsert_nav_record(db: DBSession, record: NavRecord) -> None:
    existing = db.scalar(
        select(NavRecord).where(
            NavRecord.instrument_id == record.instrument_id,
            NavRecord.nav_date == record.nav_date,
            NavRecord.source == record.source,
        )
    )
    if existing is not None:
        existing.nav = record.nav
        existing.published_at = record.published_at
        existing.fetched_at = record.fetched_at
        existing.received_at = record.received_at
        existing.source_delay_class = record.source_delay_class
        existing.quality_status = record.quality_status
        existing.content_hash = record.content_hash
        existing.updated_at = record.updated_at
        existing.version += 1
        return
    db.add(record)
    db.flush()


def get_latest_nav_record(
    db: DBSession, instrument_id: str, *, source: str
) -> NavRecord | None:
    return db.scalar(
        select(NavRecord)
        .where(
            NavRecord.instrument_id == instrument_id,
            NavRecord.source == source,
        )
        .order_by(NavRecord.nav_date.desc())
        .limit(1)
    )


# —— trading_calendar ——


def upsert_calendar_row(db: DBSession, row: TradingCalendar) -> None:
    existing = db.get(TradingCalendar, row.date)
    if existing is not None:
        existing.is_trading_day = row.is_trading_day
        existing.session_schedule_json = row.session_schedule_json
        existing.calendar_version = row.calendar_version
        return
    db.add(row)
    db.flush()


def get_calendar(db: DBSession, day: date | str) -> TradingCalendar | None:
    return db.get(TradingCalendar, day if isinstance(day, str) else day.isoformat())


def latest_market_record_any_source(
    db: DBSession, instrument_id: str
) -> MarketRecord | None:
    """最新日线（跨 source，取 business_date 最大）——估值用。"""
    return db.scalar(
        select(MarketRecord)
        .where(MarketRecord.instrument_id == instrument_id)
        .order_by(MarketRecord.business_date.desc())
        .limit(1)
    )


def latest_nav_record_any_source(db: DBSession, instrument_id: str) -> NavRecord | None:
    return db.scalar(
        select(NavRecord)
        .where(NavRecord.instrument_id == instrument_id)
        .order_by(NavRecord.nav_date.desc())
        .limit(1)
    )
