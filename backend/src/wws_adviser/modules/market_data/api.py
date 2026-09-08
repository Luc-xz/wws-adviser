"""/api/v1/market-data（Phase-0 demo）与 /api/v1/market（§3.6 契约：bars/nav/quality/state）端点。

GET 行情为公开读（与 Phase-0 demo 一致）；refresh 采集为写操作，需登录(CSRF) + Idempotency-Key。
"""

from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from wws_adviser.api.dependencies import (
    get_bar_provider,
    get_nav_provider,
    get_quote_provider,
    get_session,
    get_settings,
)
from wws_adviser.core.config import Settings
from wws_adviser.core.errors import MissingIdempotencyKeyError
from wws_adviser.modules.market_data import schemas, service
from wws_adviser.modules.market_data.models import DataConflict, TradingCalendar
from wws_adviser.modules.market_data.schemas import (
    BarOut,
    BarSeriesResponse,
    IngestResponse,
    MarketStateOut,
    NavOut,
    NavSeriesResponse,
    QualityEntry,
    QualityResponse,
    QuoteOut,
)
from wws_adviser.ports.market_data import BarProvider, InstrumentRef, NAVProvider, QuoteProvider

# —— Phase-0 demo：单标的快照（前端 HomeOverview 在用，保留）——
router = APIRouter(prefix="/api/v1/market-data", tags=["market-data"])


@router.get("/quotes/{code}", response_model=QuoteOut)
async def get_quote(
    code: str, provider: Annotated[QuoteProvider, Depends(get_quote_provider)]
) -> QuoteOut:
    instrument = InstrumentRef(code=code, market="SSE", kind="stock")
    q = await service.get_quote(instrument, provider)
    return QuoteOut(
        code=q.code,
        source=q.source,
        price=str(q.price),
        change_pct=str(q.change_pct),
        market_time=q.market_time,
    )


# —— §3.6 契约：日线/净值/质量/状态 ——
market_router = APIRouter(prefix="/api/v1/market", tags=["market"])

DBDep = Annotated[DBSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
BarDep = Annotated[BarProvider, Depends(get_bar_provider)]
NavDep = Annotated[NAVProvider, Depends(get_nav_provider)]


def _require_idempotency_key(
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> str:
    if not idempotency_key:
        raise MissingIdempotencyKeyError()
    return idempotency_key


def _parse_date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d")


@market_router.get("/bars/{instrument_id}", response_model=BarSeriesResponse)
async def get_bars(
    instrument_id: str,
    settings: SettingsDep,
    start: Annotated[str | None, Query()] = None,
    end: Annotated[str | None, Query()] = None,
    adjustment: Annotated[str, Query()] = "none",
) -> BarSeriesResponse:
    bars = service.query_bars(
        settings.data_dir, instrument_id=instrument_id, start=start, end=end
    )
    return BarSeriesResponse(
        instrument_id=instrument_id,
        adjustment=adjustment,
        bars=[
            BarOut(
                business_date=b["business_date"],
                open=b["open"],
                high=b["high"],
                low=b["low"],
                close=b["close"],
                volume=b["volume"],
                amount=b.get("amount") or None,
            )
            for b in bars
        ],
    )


@market_router.post("/bars/{instrument_id}/refresh", response_model=IngestResponse)
async def refresh_bars(
    instrument_id: str,
    request: Request,
    db: DBDep,
    settings: SettingsDep,
    provider: BarDep,
    _key: Annotated[str, Depends(_require_idempotency_key)],
    start_date: Annotated[str, Query()],
    end_date: Annotated[str, Query()],
    adjustment: Annotated[str, Query()] = "none",
) -> IngestResponse:
    result = await service.ingest_daily_bars(
        db,
        data_dir=settings.data_dir,
        instrument_id=instrument_id,
        provider=provider,
        start=_parse_date(start_date).date(),
        end=_parse_date(end_date).date(),
        adjustment_type=adjustment,
        request_id=request.headers.get("x-request-id"),
    )
    return IngestResponse(
        ingested=result.ingested, quality=result.quality, content_hash=result.content_hash
    )


@market_router.get("/nav/{instrument_id}", response_model=NavSeriesResponse)
async def get_nav(
    instrument_id: str,
    settings: SettingsDep,
    start: Annotated[str | None, Query()] = None,
    end: Annotated[str | None, Query()] = None,
) -> NavSeriesResponse:
    navs = service.query_nav(settings.data_dir, instrument_id=instrument_id, start=start, end=end)
    return NavSeriesResponse(
        instrument_id=instrument_id,
        navs=[
            NavOut(
                nav_date=n["nav_date"],
                nav=n["nav"],
                published_at=n.get("published_at") or None,
            )
            for n in navs
        ],
    )


@market_router.post("/nav/{instrument_id}/refresh", response_model=IngestResponse)
async def refresh_nav(
    instrument_id: str,
    request: Request,
    db: DBDep,
    settings: SettingsDep,
    provider: NavDep,
    _key: Annotated[str, Depends(_require_idempotency_key)],
    as_of: Annotated[str, Query()],
) -> IngestResponse:
    result = await service.ingest_nav(
        db,
        data_dir=settings.data_dir,
        instrument_id=instrument_id,
        provider=provider,
        as_of=_parse_date(as_of).date(),
        request_id=request.headers.get("x-request-id"),
    )
    return IngestResponse(
        ingested=result.ingested, quality=result.quality, content_hash=result.content_hash
    )


@market_router.get("/quality", response_model=QualityResponse)
async def get_quality(
    db: DBDep,
    instrument_id: Annotated[str | None, Query()] = None,
) -> QualityResponse:
    items = service.market_quality(db, instrument_id=instrument_id)
    return QualityResponse(items=[QualityEntry(**item) for item in items])


@market_router.get("/state", response_model=MarketStateOut)
async def get_state(db: DBDep) -> MarketStateOut:
    """市场状态机（5_DATA §8）：交易日历判 is_trading_day（无记录走 weekday 兜底），
    时段表判 phase；closed/非交易日的 next_event_at 取日历下一交易日的集合竞价开始。"""
    from wws_adviser.core.time import now_shanghai
    from wws_adviser.modules.market_data import repository as md_repository
    from wws_adviser.modules.market_data.domain import market_phase, weekday_trading_fallback

    now = now_shanghai()
    today = now.date().isoformat()
    cal = md_repository.get_calendar(db, today)
    is_trading = (
        cal.is_trading_day if cal is not None else weekday_trading_fallback(now.date())
    )
    phase, next_t = market_phase(now, is_trading_day=is_trading)
    next_event_at: str | None = None
    if next_t is not None:
        nxt = now.replace(hour=next_t.hour, minute=next_t.minute, second=0, microsecond=0)
        next_event_at = nxt.isoformat()
    else:
        # 当日无更多边界：取日历下一交易日的 09:15（无日历退化为次日）
        row = db.scalar(
            select(TradingCalendar.date)
            .where(
                TradingCalendar.market == "CN",
                TradingCalendar.is_trading_day.is_(True),
                TradingCalendar.date > today,
            )
            .order_by(TradingCalendar.date)
            .limit(1)
        )
        next_day = row or (now.date() + timedelta(days=1)).isoformat()
        next_event_at = f"{next_day}T09:15:00+08:00"
    return MarketStateOut(
        phase=phase, is_trading_day=is_trading, next_event_at=next_event_at
    )


# —— 多源冲突（Phase 3.3，DATA-01 数据状态中心 / SET-02 消解） ——


@market_router.get("/conflicts", response_model=schemas.ConflictListResponse)
async def list_conflicts(
    db: DBDep,
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> schemas.ConflictListResponse:
    from wws_adviser.modules.market_data import repository as md_repository

    rows = md_repository.list_conflicts(db, status=status, limit=limit)
    return schemas.ConflictListResponse(items=[_conflict_out(r) for r in rows])


@market_router.post("/conflicts/{conflict_id}/resolve", response_model=schemas.ConflictOut)
async def resolve_conflict(
    conflict_id: str,
    body: schemas.ConflictResolveRequest,
    db: DBDep,
    _key: Annotated[str, Depends(_require_idempotency_key)],
) -> schemas.ConflictOut:
    """人工消解（SET-02）：选源 + 理由。幂等——已 RESOLVED 直接返回。"""
    from wws_adviser.core.errors import DomainError
    from wws_adviser.modules.market_data import repository as md_repository

    row = db.get(DataConflict, conflict_id)
    if row is None:
        raise DomainError("冲突记录不存在")
    if body.winner not in (row.source_a, row.source_b):
        raise DomainError(f"winner 须为 {row.source_a} 或 {row.source_b}")
    resolved = md_repository.resolve_conflict(
        db, conflict_id, resolved_by=body.note or "manual", winner=body.winner
    )
    db.commit()
    assert resolved is not None
    return _conflict_out(resolved)


def _conflict_out(row: DataConflict) -> schemas.ConflictOut:
    return schemas.ConflictOut(
        id=row.id, instrument_id=row.instrument_id, business_date=row.business_date,
        field=row.field, source_a=row.source_a, source_b=row.source_b,
        value_a=row.value_a, value_b=row.value_b, status=row.status,
        resolved_by=row.resolved_by, resolved_at=row.resolved_at, created_at=row.created_at,
    )
