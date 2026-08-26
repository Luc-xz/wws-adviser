"""Market data 服务：行情取数 + 日线/净值采集流水线 + 查询。

依赖注入接收端口（QuoteProvider/BarProvider/NAVProvider），不 import 具体适配器。
事务边界在此；采集 = fetch→parse→validate→dedup→assign quality→原子发布（Parquet + SQLite 索引）。
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from wws_adviser.core.ids import new_id
from wws_adviser.core.time import now_utc_iso
from wws_adviser.infrastructure.storage import parquet_store
from wws_adviser.modules.audit import service as audit_service
from wws_adviser.modules.instruments import service as instruments_service
from wws_adviser.modules.market_data import repository
from wws_adviser.modules.market_data.domain import (
    NormalizedBar,
    NormalizedQuote,
    QualityStatus,
    QuoteUnavailableError,
    parse_bars,
    parse_nav,
    parse_quote,
)
from wws_adviser.modules.market_data.models import MarketRecord, NavRecord
from wws_adviser.ports.market_data import (
    BarProvider,
    InstrumentRef,
    NAVProvider,
    QuoteProvider,
)


async def get_quote(instrument: InstrumentRef, provider: QuoteProvider) -> NormalizedQuote:
    quotes = await provider.fetch_quotes([instrument])
    if not quotes:
        raise QuoteUnavailableError(f"无行情：{instrument.code}")
    return parse_quote(quotes[0], instrument.code)


@dataclass(frozen=True)
class IngestResult:
    ingested: int
    quality: str
    content_hash: str | None = None


def _ref_of(code: str, market: str, kind: str) -> InstrumentRef:
    return InstrumentRef(code=code, market=market, kind=kind.lower())


def _bar_row(b: NormalizedBar) -> dict[str, str]:
    return {
        "business_date": b.business_date.isoformat(),
        "open": format(b.open, "f"),
        "high": format(b.high, "f"),
        "low": format(b.low, "f"),
        "close": format(b.close, "f"),
        "volume": format(b.volume, "f"),
        "amount": "",
    }


async def ingest_daily_bars(
    db: DBSession,
    *,
    data_dir: Path,
    instrument_id: str,
    provider: BarProvider,
    start: date,
    end: date,
    adjustment_type: str = "none",
    request_id: str | None = None,
) -> IngestResult:
    """日线采集流水线：fetch→parse→Parquet 写 + SQLite 索引 upsert（UNIQUE 去重）。"""
    instrument = instruments_service.get_instrument(db, instrument_id)
    if instrument is None:
        raise instruments_service.InstrumentNotFoundError(instrument_id)
    ref = _ref_of(instrument.code, instrument.market, instrument.kind)
    raw = await provider.fetch_daily_bars(ref, start, end)
    bars = parse_bars(raw, price_scale=instrument.price_scale, qty_scale=instrument.qty_scale)
    if not bars:
        return IngestResult(ingested=0, quality=QualityStatus.MISSING.value)

    by_year: dict[int, list[NormalizedBar]] = {}
    for b in bars:
        by_year.setdefault(b.business_date.year, []).append(b)
    content_hash = ""
    for year, ys in by_year.items():
        content_hash = parquet_store.write_bars(
            data_dir,
            market=instrument.market,
            instrument_id=instrument.id,
            year=year,
            rows=[_bar_row(b) for b in ys],
            adjustment_type=adjustment_type,
        )

    now = now_utc_iso()
    for b in bars:
        repository.upsert_market_record(
            db,
            MarketRecord(
                id=new_id(),
                instrument_id=instrument.id,
                business_date=b.business_date.isoformat(),
                open=format(b.open, "f"),
                high=format(b.high, "f"),
                low=format(b.low, "f"),
                close=format(b.close, "f"),
                volume=format(b.volume, "f"),
                amount=None,
                source=raw.source,
                source_url=raw.source_url,
                market_time=raw.market_time,
                fetched_at=raw.fetched_at,
                received_at=raw.received_at,
                source_delay_class=raw.source_delay_class.value,
                quality_status=QualityStatus.OK.value,
                content_hash=content_hash,
                adjustment_type=adjustment_type,
                created_at=now,
                updated_at=now,
                version=1,
            ),
        )
    audit_service.append_event(
        db,
        action="market_bars_ingested",
        target_type="instrument",
        target_id=instrument.id,
        after={"n": len(bars), "source": raw.source, "adjustment_type": adjustment_type},
        request_id=request_id,
    )
    db.commit()
    return IngestResult(
        ingested=len(bars), quality=QualityStatus.OK.value, content_hash=content_hash
    )


async def ingest_nav(
    db: DBSession,
    *,
    data_dir: Path,
    instrument_id: str,
    provider: NAVProvider,
    as_of: date,
    request_id: str | None = None,
) -> IngestResult:
    """净值采集：fetch→parse→Parquet 写 + SQLite 索引 upsert。"""
    instrument = instruments_service.get_instrument(db, instrument_id)
    if instrument is None:
        raise instruments_service.InstrumentNotFoundError(instrument_id)
    ref = _ref_of(instrument.code, instrument.market, instrument.kind)
    raw = await provider.fetch_nav(ref, as_of)
    nav = parse_nav(raw)
    nav_str = format(nav.nav, "f")
    content_hash = parquet_store.write_nav(
        data_dir,
        instrument_id=instrument.id,
        year=as_of.year,
        rows=[{"nav_date": as_of.isoformat(), "nav": nav_str, "published_at": nav.published_at}],
    )
    now = now_utc_iso()
    repository.upsert_nav_record(
        db,
        NavRecord(
            id=new_id(),
            instrument_id=instrument.id,
            nav_date=as_of.isoformat(),
            nav=nav_str,
            published_at=nav.published_at,
            source=raw.source,
            source_url=raw.source_url,
            market_time=raw.market_time,
            fetched_at=raw.fetched_at,
            received_at=raw.received_at,
            source_delay_class=raw.source_delay_class.value,
            quality_status=QualityStatus.OK.value,
            content_hash=content_hash,
            created_at=now,
            updated_at=now,
            version=1,
        ),
    )
    audit_service.append_event(
        db,
        action="market_nav_ingested",
        target_type="instrument",
        target_id=instrument.id,
        after={"nav_date": as_of.isoformat(), "source": raw.source},
        request_id=request_id,
    )
    db.commit()
    return IngestResult(ingested=1, quality=QualityStatus.OK.value, content_hash=content_hash)


def query_bars(
    data_dir: Path,
    *,
    instrument_id: str,
    start: str | None = None,
    end: str | None = None,
) -> list[dict[str, str]]:
    """日线查询：读 Parquet 主存（完整历史），按日期过滤。"""
    return parquet_store.read_bars(data_dir, instrument_id=instrument_id, start=start, end=end)


def query_nav(
    data_dir: Path,
    *,
    instrument_id: str,
    start: str | None = None,
    end: str | None = None,
) -> list[dict[str, str]]:
    return parquet_store.read_nav(data_dir, instrument_id=instrument_id, start=start, end=end)


@dataclass(frozen=True)
class LatestPrice:
    """最新估值价（日线 close 或基金 nav，跨 source 取最新）。"""

    price: Decimal
    business_date: str
    source: str


def latest_price(db: DBSession, instrument_id: str) -> LatestPrice | None:
    """取最新 close（跨 source）；无日线则取最新 nav。供 analytics 估值用。"""
    rec = repository.latest_market_record_any_source(db, instrument_id)
    if rec is not None and rec.close:
        return LatestPrice(
            price=Decimal(rec.close), business_date=rec.business_date, source=rec.source
        )
    nav = repository.latest_nav_record_any_source(db, instrument_id)
    if nav is not None:
        return LatestPrice(
            price=Decimal(nav.nav), business_date=nav.nav_date, source=nav.source
        )
    return None


def market_quality(
    db: DBSession, *, instrument_id: str | None = None
) -> list[dict[str, str]]:
    """各标的最新日线/净值质量状态（读 SQLite 元数据索引）。"""
    bar_stmt = select(MarketRecord)
    if instrument_id is not None:
        bar_stmt = bar_stmt.where(MarketRecord.instrument_id == instrument_id)
    latest_bar: dict[str, MarketRecord] = {}
    for r in db.scalars(bar_stmt.order_by(MarketRecord.business_date.desc())):
        latest_bar.setdefault(r.instrument_id, r)
    nav_stmt = select(NavRecord)
    if instrument_id is not None:
        nav_stmt = nav_stmt.where(NavRecord.instrument_id == instrument_id)
    latest_nav: dict[str, NavRecord] = {}
    for nr in db.scalars(nav_stmt.order_by(NavRecord.nav_date.desc())):
        latest_nav.setdefault(nr.instrument_id, nr)
    out: list[dict[str, str]] = []
    for inst_id, rec in latest_bar.items():
        out.append(
            {
                "instrument_id": inst_id,
                "series": "bar",
                "business_date": rec.business_date,
                "quality_status": rec.quality_status,
                "fetched_at": rec.fetched_at or "",
                "source": rec.source,
            }
        )
    for nav_inst_id, nav_rec in latest_nav.items():
        out.append(
            {
                "instrument_id": nav_inst_id,
                "series": "nav",
                "nav_date": nav_rec.nav_date,
                "quality_status": nav_rec.quality_status,
                "fetched_at": nav_rec.fetched_at or "",
                "source": nav_rec.source,
            }
        )
    return out


async def ingest_bars_for_holdings(
    db: DBSession,
    *,
    data_dir: Path,
    provider: BarProvider,
    lookback_days: int = 30,
    request_id: str | None = None,
) -> dict[str, str]:
    """为全部持仓标的批量采集日线（幂等：内容哈希去重，重采安全）。

    DATA_MAINTENANCE 每日任务用：15:20 采集赶在 16:00 收市后报告前拿到当日收盘。
    返回 {code: quality_status}（失败标的记异常类型名，不中断其余标的）。
    """
    import logging
    from datetime import timedelta

    from wws_adviser.modules.portfolio import service as portfolio_service
    from wws_adviser.modules.portfolio.models import Account

    logger = logging.getLogger(__name__)
    end = date.today()
    start = end - timedelta(days=lookback_days)
    results: dict[str, str] = {}
    seen: set[str] = set()
    for account in db.scalars(select(Account)).all():
        state = portfolio_service.get_position_state(db, account.id)
        for inst_id, st in state.positions.items():
            if st.qty <= 0 or inst_id in seen:
                continue
            seen.add(inst_id)
            inst = instruments_service.get_instrument(db, inst_id)
            if inst is None:
                continue
            try:
                r = await ingest_daily_bars(
                    db, data_dir=data_dir, instrument_id=inst_id, provider=provider,
                    start=start, end=end, request_id=request_id,
                )
                results[inst.code] = r.quality
            except Exception as exc:  # noqa: BLE001 — 单标的失败不中断批次
                logger.warning("日线采集失败 %s: %s", inst.code, exc)
                results[inst.code] = type(exc).__name__
    db.commit()
    return results
