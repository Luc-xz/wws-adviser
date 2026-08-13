"""Market data 服务：行情取数 + 日线/净值采集流水线 + 查询。

依赖注入接收端口（QuoteProvider/BarProvider/NAVProvider），不 import 具体适配器。
事务边界在此；采集 = fetch→parse→validate→dedup→assign quality→原子发布（Parquet + SQLite 索引）。
"""

from dataclasses import dataclass
from datetime import date
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
