"""Market env 服务：指数快照/指数日K/板块资金流采集流水线 + 查询聚合入口。

依赖注入接收端口（IndexQuoteProvider/IndexBarProvider/SectorFlowProvider），不 import
具体适配器。事务边界在此；观测写入沿 5_DATA §12.2（RunContext + 失败先 rollback）。
市场环境是研究上下文：质量状态不触发 PAUSE_ADVICE（ADR-0014 决策 5）。
"""

import time
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from wws_adviser.core.config import Settings
from wws_adviser.core.ids import new_id
from wws_adviser.core.time import now_utc_iso
from wws_adviser.modules.audit import service as audit_service
from wws_adviser.modules.collections import service as collections_service
from wws_adviser.modules.market_env import repository
from wws_adviser.modules.market_env.domain import (
    INDEX_BY_CODE,
    INDEX_REGISTRY,
    TURNOVER_INDEX_CODES,
    IndexQuoteParseError,
    QualityStatus,
    SectorFlowParseError,
    parse_index_quote,
    parse_sector_flow,
)
from wws_adviser.modules.market_env.models import (
    IndexBar,
    IndexQuote,
    SectorBoard,
    SectorFlowSnapshot,
)
from wws_adviser.ports.market_env import (
    IndexBarProvider,
    IndexQuoteProvider,
    IndexRef,
    SectorFlowProvider,
    SectorKind,
)


@dataclass(frozen=True)
class IngestResult:
    ingested: int
    quality: str
    failed: int = 0


# —— 指数快照 ——


async def ingest_index_quotes(
    db: DBSession,
    *,
    provider: IndexQuoteProvider,
    refs: tuple[IndexRef, ...] = INDEX_REGISTRY,
    run_id: str | None = None,
    request_id: str | None = None,
) -> IngestResult:
    """指数快照采集：播种注册表 → fetch → 逐条标准化（坏条目计失败不中断）→ upsert。"""
    repository.ensure_registry(db)
    display = f"指数快照 {len(refs)} 项"
    target = "index:batch"
    data_ref = f"index-quotes:{now_utc_iso()[:10]}"
    t0 = time.perf_counter()
    try:
        raw_list = await provider.fetch_index_quotes(list(refs))
    except Exception as exc:  # noqa: BLE001 — 源失败先落观测再上抛
        collections_service.record_failure(
            db, category="index_quote", run_id=run_id, target_ref=target,
            display_name=display, error_code=type(exc).__name__, error_message=str(exc),
            duration_ms=int((time.perf_counter() - t0) * 1000),
        )
        raise
    if not raw_list:
        collections_service.record_failure(
            db, category="index_quote", run_id=run_id, target_ref=target,
            display_name=display, error_code="NO_DATA", error_message="源未返回任何指数快照",
            duration_ms=int((time.perf_counter() - t0) * 1000),
        )
        return IngestResult(ingested=0, quality=QualityStatus.MISSING.value)

    now = now_utc_iso()
    written = 0
    parse_failed = 0
    for raw in raw_list:
        try:
            nq = parse_index_quote(raw)
        except IndexQuoteParseError:
            parse_failed += 1
            continue
        repository.upsert_index_quote(
            db,
            IndexQuote(
                id=new_id(),
                index_code=nq.code,
                market_time=nq.market_time,
                price=format(nq.price, "f"),
                change_pct=format(nq.change_pct, "f"),
                volume=format(nq.volume, "f"),
                amount=format(nq.amount, "f"),
                pre_market_price=(format(nq.pre_market_price, "f")
                                  if nq.pre_market_price is not None else None),
                pre_market_change_pct=(format(nq.pre_market_change_pct, "f")
                                       if nq.pre_market_change_pct is not None else None),
                post_market_price=(format(nq.post_market_price, "f")
                                   if nq.post_market_price is not None else None),
                post_market_change_pct=(format(nq.post_market_change_pct, "f")
                                        if nq.post_market_change_pct is not None else None),
                source=raw.source,
                source_url=raw.source_url,
                fetched_at=raw.fetched_at,
                received_at=raw.received_at,
                source_delay_class=raw.source_delay_class,
                quality_status=QualityStatus.OK.value,
                created_at=now,
            ),
        )
        written += 1

    if written == 0:  # 全部条目解析失败 → 批次 PARSE_FAILED
        collections_service.record_failure(
            db, category="index_quote", run_id=run_id, target_ref=target,
            display_name=display, error_code="PARSE_FAILED",
            error_message=f"{parse_failed} 条快照全部解析失败",
            duration_ms=int((time.perf_counter() - t0) * 1000),
        )
        return IngestResult(ingested=0, quality=QualityStatus.PARSE_FAILED.value,
                            failed=parse_failed)

    collections_service.record_source_success(db, "index_quote")
    collections_service.record_item(
        db, category="index_quote", run_id=run_id, target_ref=target, display_name=display,
        action="ingested",
        status="PARTIAL" if parse_failed else "OK",
        rows_written=written, source=raw_list[0].source if raw_list else None,
        duration_ms=int((time.perf_counter() - t0) * 1000), data_ref=data_ref,
    )
    audit_service.append_event(
        db, action="market_env_quotes_ingested", target_type="market_env",
        target_id="index_quotes",
        after={"n": written, "parse_failed": parse_failed,
               "source": raw_list[0].source if raw_list else None},
        request_id=request_id,
    )
    db.commit()
    return IngestResult(
        ingested=written,
        quality=QualityStatus.OK.value if not parse_failed else QualityStatus.PARSE_FAILED.value,
        failed=parse_failed,
    )


# —— 指数日 K ——


async def ingest_index_bars(
    db: DBSession,
    *,
    provider: IndexBarProvider,
    code: str,
    start: date,
    end: date,
    run_id: str | None = None,
    request_id: str | None = None,
) -> IngestResult:
    """单指数日 K 采集（v1 仅 CN；东财主源 + 腾讯兜底在适配器内）。"""
    repository.ensure_registry(db)
    ref = INDEX_BY_CODE.get(code)
    if ref is None:
        raise ValueError(f"未注册指数：{code}")
    display = f"{ref.name}({code}) 日K {start.isoformat()}~{end.isoformat()}"
    target = f"index:{code}"
    data_ref = f"index-bars:{code}:{start.isoformat()}-{end.isoformat()}"
    t0 = time.perf_counter()
    try:
        ds = await provider.fetch_index_bars(ref, start, end)
        if not ds.bars:
            collections_service.record_failure(
                db, category="index_bar", run_id=run_id, target_ref=target,
                display_name=display, error_code="NO_DATA",
                error_message="源返回空日K（主备源均未命中）",
                duration_ms=int((time.perf_counter() - t0) * 1000),
            )
            return IngestResult(ingested=0, quality=QualityStatus.MISSING.value)
        now = now_utc_iso()
        for b in ds.bars:
            if b.low > b.high or min(b.open, b.close) < b.low or max(b.open, b.close) > b.high:
                collections_service.record_failure(
                    db, category="index_bar", run_id=run_id, target_ref=target,
                    display_name=display, error_code="PARSE_FAILED",
                    error_message=f"{b.date.isoformat()} OHLC 越界",
                    duration_ms=int((time.perf_counter() - t0) * 1000),
                )
                return IngestResult(ingested=0, quality=QualityStatus.PARSE_FAILED.value)
            repository.upsert_index_bar(
                db,
                IndexBar(
                    id=new_id(),
                    index_code=code,
                    business_date=b.date.isoformat(),
                    open=format(b.open, "f"),
                    high=format(b.high, "f"),
                    low=format(b.low, "f"),
                    close=format(b.close, "f"),
                    volume=format(b.volume, "f"),
                    amount=None,
                    source=ds.source,
                    source_url=ds.source_url,
                    fetched_at=ds.fetched_at,
                    quality_status=QualityStatus.OK.value,
                    created_at=now,
                    updated_at=now,
                ),
            )
        collections_service.record_source_success(db, "index_bar")
        collections_service.record_item(
            db, category="index_bar", run_id=run_id, target_ref=target, display_name=display,
            action="ingested", status="OK", rows_written=len(ds.bars), source=ds.source,
            duration_ms=int((time.perf_counter() - t0) * 1000), data_ref=data_ref,
        )
        audit_service.append_event(
            db, action="market_env_bars_ingested", target_type="market_env",
            target_id=code, after={"n": len(ds.bars), "source": ds.source},
            request_id=request_id,
        )
        db.commit()
        return IngestResult(ingested=len(ds.bars), quality=QualityStatus.OK.value)
    except Exception as exc:  # noqa: BLE001 — 源失败先落观测再上抛
        collections_service.record_failure(
            db, category="index_bar", run_id=run_id, target_ref=target, display_name=display,
            error_code=type(exc).__name__, error_message=str(exc),
            duration_ms=int((time.perf_counter() - t0) * 1000),
        )
        raise


# —— 板块资金流 ——


async def ingest_sector_flows(
    db: DBSession,
    *,
    provider: SectorFlowProvider,
    kind: SectorKind,
    run_id: str | None = None,
    request_id: str | None = None,
) -> IngestResult:
    """板块资金流采集：板块注册 upsert（漂移吸收）→ 快照 upsert（UNIQUE 去重重采安全）。"""
    display = f"板块资金流 {kind.value}"
    target = f"sector:{kind.value}"
    data_ref = f"sector-flows:{kind.value}:{now_utc_iso()[:10]}"
    t0 = time.perf_counter()
    try:
        raw_list = await provider.fetch_sector_flows(kind)
    except Exception as exc:  # noqa: BLE001 — 源失败先落观测再上抛
        collections_service.record_failure(
            db, category="sector_flow", run_id=run_id, target_ref=target,
            display_name=display, error_code=type(exc).__name__, error_message=str(exc),
            duration_ms=int((time.perf_counter() - t0) * 1000),
        )
        raise
    if not raw_list:
        collections_service.record_failure(
            db, category="sector_flow", run_id=run_id, target_ref=target,
            display_name=display, error_code="NO_DATA", error_message="源未返回板块数据",
            duration_ms=int((time.perf_counter() - t0) * 1000),
        )
        return IngestResult(ingested=0, quality=QualityStatus.MISSING.value)

    now = now_utc_iso()
    written = 0
    parse_failed = 0
    for raw in raw_list:
        try:
            nf = parse_sector_flow(raw)
        except SectorFlowParseError:
            parse_failed += 1
            continue
        repository.upsert_sector_board(
            db,
            SectorBoard(
                board_code=nf.board_code, name=nf.board_name, kind=nf.kind, updated_at=now
            ),
        )
        repository.upsert_sector_flow(
            db,
            SectorFlowSnapshot(
                id=new_id(),
                board_code=nf.board_code,
                kind=nf.kind,
                snapshot_at=nf.market_time,
                change_pct=format(nf.change_pct, "f"),
                turnover=format(nf.turnover, "f"),
                net_main_inflow=format(nf.net_main_inflow, "f"),
                leader_code=nf.leader_code,
                leader_name=nf.leader_name,
                source=raw.source,
                quality_status=QualityStatus.OK.value,
                created_at=now,
            ),
        )
        written += 1

    if written == 0:
        collections_service.record_failure(
            db, category="sector_flow", run_id=run_id, target_ref=target,
            display_name=display, error_code="PARSE_FAILED",
            error_message=f"{parse_failed} 条板块数据全部解析失败",
            duration_ms=int((time.perf_counter() - t0) * 1000),
        )
        return IngestResult(ingested=0, quality=QualityStatus.PARSE_FAILED.value,
                            failed=parse_failed)

    collections_service.record_source_success(db, "sector_flow")
    collections_service.record_item(
        db, category="sector_flow", run_id=run_id, target_ref=target, display_name=display,
        action="ingested",
        status="PARTIAL" if parse_failed else "OK",
        rows_written=written, source=raw_list[0].source if raw_list else None,
        duration_ms=int((time.perf_counter() - t0) * 1000), data_ref=data_ref,
    )
    audit_service.append_event(
        db, action="market_env_sector_flows_ingested", target_type="market_env",
        target_id=kind.value, after={"n": written, "parse_failed": parse_failed},
        request_id=request_id,
    )
    db.commit()
    return IngestResult(
        ingested=written,
        quality=QualityStatus.OK.value if not parse_failed else QualityStatus.PARSE_FAILED.value,
        failed=parse_failed,
    )


# —— 读取侧聚合（测试 + 批次 B overview 用） ——


def market_turnover(db: DBSession) -> Decimal | None:
    """两市成交额（元）：上证综指 + 深证综指最新快照 amount 汇总（2_DATA §6.8）。"""
    total = Decimal("0")
    found = 0
    for code in TURNOVER_INDEX_CODES:
        row = db.scalar(
            select(IndexQuote)
            .where(IndexQuote.index_code == code)
            .order_by(IndexQuote.market_time.desc())
            .limit(1)
        )
        if row is not None and row.amount:
            total += Decimal(row.amount)
            found += 1
    return total if found == len(TURNOVER_INDEX_CODES) else None


# —— 读取侧聚合：overview（3_API §3.18）/ 报告段 / 研究上下文（ADR-0014 决策 5：仅研究展示） ——

_CN_GROUPS = frozenset({"cn_broad", "cn_style"})
_OVERSEAS_GROUPS = frozenset({"overseas_us", "overseas_ap"})


def _age_seconds(market_time: str | None) -> int | None:
    """上海本地时间 market_time 距现在的秒数；不可解析 → None。"""
    from datetime import datetime

    from wws_adviser.core.time import SHANGHAI

    if not market_time:
        return None
    try:
        mt = datetime.strptime(market_time, "%Y-%m-%d %H:%M:%S").replace(tzinfo=SHANGHAI)
    except ValueError:
        return None
    return int((datetime.now(SHANGHAI) - mt).total_seconds())


def _quote_entry(row: IndexQuote) -> dict[str, str | None]:
    ref = INDEX_BY_CODE.get(row.index_code)
    return {
        "code": row.index_code,
        "name": ref.name if ref else row.index_code,
        "group": ref.market_group if ref else "unknown",
        "price": row.price,
        "change_pct": row.change_pct,
        "volume": row.volume,
        "amount": row.amount,
        "market_time": row.market_time,
    }


def sector_entry(db: DBSession, row: SectorFlowSnapshot) -> dict[str, str | None]:
    board = db.get(SectorBoard, row.board_code)
    return {
        "board_code": row.board_code,
        "kind": row.kind,
        "board_name": board.name if board is not None else row.board_code,
        "change_pct": row.change_pct,
        "turnover": row.turnover,
        "net_main_inflow": row.net_main_inflow,
        "leader_name": row.leader_name,
        "snapshot_at": row.snapshot_at,
    }


def overview(db: DBSession, settings: Settings) -> dict[str, object]:
    """市场环境一次聚合（GET /market-env/overview）。缺失/陈旧只体现在 freshness 字段，
    不产生降级语义（ADR-0014 决策 5）。"""
    quotes = repository.latest_index_quotes(db)
    cn: list[dict[str, str | None]] = []
    overseas: list[dict[str, str | None]] = []
    futures: list[dict[str, str | None]] = []
    cn_ages: list[int] = []
    for row in quotes:
        ref = INDEX_BY_CODE.get(row.index_code)
        group = ref.market_group if ref else ""
        if group in _CN_GROUPS:
            cn.append(_quote_entry(row))
            age = _age_seconds(row.market_time)
            if age is not None:
                cn_ages.append(age)
        elif group in _OVERSEAS_GROUPS:
            overseas.append(_quote_entry(row))
        elif group == "futures_us":
            futures.append(_quote_entry(row))

    industry = repository.latest_sector_flows(db, kind="industry")
    active = sorted(industry, key=lambda r: Decimal(r.change_pct or "0"), reverse=True)[:5]
    inflow = sorted(industry, key=lambda r: Decimal(r.net_main_inflow or "0"), reverse=True)[:5]
    outflow = sorted(industry, key=lambda r: Decimal(r.net_main_inflow or "0"))[:5]
    turnover = market_turnover(db)
    sector_age = _age_seconds(industry[0].snapshot_at) if industry else None
    cn_age = min(cn_ages) if cn_ages else None
    return {
        "generated_at": now_utc_iso(),
        "cn_indices": cn,
        "market_turnover": format(turnover, "f") if turnover is not None else None,
        "active_sectors": [sector_entry(db, r) for r in active],
        "net_inflow_top": [sector_entry(db, r) for r in inflow],
        "net_outflow_top": [sector_entry(db, r) for r in outflow],
        "overseas": overseas,
        "futures": futures,
        "freshness": {
            "cn_quote_age_seconds": cn_age,
            "cn_quote_fresh": (
                cn_age <= settings.index_quote_freshness_threshold_seconds
                if cn_age is not None
                else None
            ),
            "sector_flow_age_seconds": sector_age,
            "sector_flow_fresh": (
                sector_age <= settings.sector_flow_freshness_threshold_seconds
                if sector_age is not None
                else None
            ),
        },
    }


def build_report_section(db: DBSession) -> dict[str, object] | None:
    """晨报「市场环境」段（report_json.market_env）；无任何指数快照时返回 None 不占段。"""
    quotes = repository.latest_index_quotes(db)
    if not quotes:
        return None
    cn: list[dict[str, str | None]] = []
    overseas: list[dict[str, str | None]] = []
    futures: list[dict[str, str | None]] = []
    for row in quotes:
        ref = INDEX_BY_CODE.get(row.index_code)
        group = ref.market_group if ref else ""
        if group in _CN_GROUPS:
            cn.append(_quote_entry(row))
        elif group in _OVERSEAS_GROUPS:
            overseas.append(_quote_entry(row))
        elif group == "futures_us":
            futures.append(_quote_entry(row))
    industry = repository.latest_sector_flows(db, kind="industry")
    active = sorted(industry, key=lambda r: Decimal(r.change_pct or "0"), reverse=True)[:3]
    inflow = sorted(industry, key=lambda r: Decimal(r.net_main_inflow or "0"), reverse=True)[:3]
    outflow = sorted(industry, key=lambda r: Decimal(r.net_main_inflow or "0"))[:3]
    turnover = market_turnover(db)
    return {
        "cn_indices": cn,
        "market_turnover": format(turnover, "f") if turnover is not None else None,
        "active_sectors": [sector_entry(db, r) for r in active],
        "net_inflow_top": [sector_entry(db, r) for r in inflow],
        "net_outflow_top": [sector_entry(db, r) for r in outflow],
        "overseas": overseas,
        "futures": futures,
    }
