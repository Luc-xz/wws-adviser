"""Market env 仓储：注册表播种 + 指数快照/日K/板块资金流 upsert 与查询。

upsert 走「预查 → 更新/插入」（单 worker 安全，同 market_data 惯例）。
"""

import json

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from wws_adviser.core.time import now_utc_iso
from wws_adviser.modules.market_env.domain import INDEX_REGISTRY
from wws_adviser.modules.market_env.models import (
    IndexBar,
    IndexQuote,
    MarketEnvIndex,
    SectorBoard,
    SectorFlowSnapshot,
)

# —— market_env_indices（注册表播种） ——


def ensure_registry(db: DBSession) -> int:
    """领域注册表 → 注册表行 upsert（采集入口调用，幂等）。返回播种总数。"""
    now = now_utc_iso()
    n = 0
    for ref in INDEX_REGISTRY:
        row = db.get(MarketEnvIndex, ref.code)
        if row is None:
            db.add(
                MarketEnvIndex(
                    code=ref.code,
                    name=ref.name,
                    market_group=ref.market_group,
                    symbol_map_json=json.dumps(ref.symbol_map, ensure_ascii=False),
                    has_pre_post=ref.has_pre_post,
                    created_at=now,
                    updated_at=now,
                )
            )
        else:
            row.name = ref.name
            row.market_group = ref.market_group
            row.symbol_map_json = json.dumps(ref.symbol_map, ensure_ascii=False)
            row.has_pre_post = ref.has_pre_post
            row.updated_at = now
        n += 1
    db.flush()
    return n


# —— index_quotes ——


def upsert_index_quote(db: DBSession, quote: IndexQuote) -> None:
    existing = db.scalar(
        select(IndexQuote).where(
            IndexQuote.index_code == quote.index_code,
            IndexQuote.market_time == quote.market_time,
            IndexQuote.source == quote.source,
        )
    )
    if existing is not None:
        existing.price = quote.price
        existing.change_pct = quote.change_pct
        existing.volume = quote.volume
        existing.amount = quote.amount
        existing.pre_market_price = quote.pre_market_price
        existing.pre_market_change_pct = quote.pre_market_change_pct
        existing.post_market_price = quote.post_market_price
        existing.post_market_change_pct = quote.post_market_change_pct
        existing.fetched_at = quote.fetched_at
        existing.quality_status = quote.quality_status
        return
    db.add(quote)
    db.flush()


def latest_index_quotes(db: DBSession, *, group: str | None = None) -> list[IndexQuote]:
    """各指数最新快照（读取侧聚合，overview/查询面用）。"""
    rows: dict[str, IndexQuote] = {}
    stmt = select(IndexQuote).order_by(IndexQuote.market_time.desc())
    for row in db.scalars(stmt):
        rows.setdefault(row.index_code, row)
    if group is None:
        return list(rows.values())
    codes = {r.code for r in INDEX_REGISTRY if r.market_group == group}
    return [r for r in rows.values() if r.index_code in codes]


# —— index_bars ——


def upsert_index_bar(db: DBSession, bar: IndexBar) -> None:
    existing = db.scalar(
        select(IndexBar).where(
            IndexBar.index_code == bar.index_code,
            IndexBar.business_date == bar.business_date,
            IndexBar.source == bar.source,
        )
    )
    if existing is not None:
        existing.open = bar.open
        existing.high = bar.high
        existing.low = bar.low
        existing.close = bar.close
        existing.volume = bar.volume
        existing.amount = bar.amount
        existing.quality_status = bar.quality_status
        existing.updated_at = bar.updated_at
        return
    db.add(bar)
    db.flush()


def list_index_bars(
    db: DBSession, index_code: str, *, start: str | None = None, end: str | None = None
) -> list[IndexBar]:
    stmt = select(IndexBar).where(IndexBar.index_code == index_code)
    if start is not None:
        stmt = stmt.where(IndexBar.business_date >= start)
    if end is not None:
        stmt = stmt.where(IndexBar.business_date <= end)
    stmt = stmt.order_by(IndexBar.business_date)
    return list(db.scalars(stmt))


# —— sector_boards / sector_flow_snapshots ——


def upsert_sector_board(db: DBSession, board: SectorBoard) -> None:
    existing = db.get(SectorBoard, board.board_code)
    if existing is not None:
        existing.name = board.name
        existing.kind = board.kind
        existing.updated_at = board.updated_at
        return
    db.add(board)
    db.flush()


def upsert_sector_flow(db: DBSession, snap: SectorFlowSnapshot) -> None:
    existing = db.scalar(
        select(SectorFlowSnapshot).where(
            SectorFlowSnapshot.board_code == snap.board_code,
            SectorFlowSnapshot.snapshot_at == snap.snapshot_at,
            SectorFlowSnapshot.kind == snap.kind,
        )
    )
    if existing is not None:
        existing.change_pct = snap.change_pct
        existing.turnover = snap.turnover
        existing.net_main_inflow = snap.net_main_inflow
        existing.leader_code = snap.leader_code
        existing.leader_name = snap.leader_name
        existing.quality_status = snap.quality_status
        return
    db.add(snap)
    db.flush()


def latest_sector_flows(
    db: DBSession, *, kind: str, limit: int | None = None
) -> list[SectorFlowSnapshot]:
    """某类别最新一轮快照（按 snapshot_at 对齐取同一轮，读取侧聚合用）。"""
    latest_at = db.scalar(
        select(SectorFlowSnapshot.snapshot_at)
        .where(SectorFlowSnapshot.kind == kind)
        .order_by(SectorFlowSnapshot.snapshot_at.desc())
        .limit(1)
    )
    if latest_at is None:
        return []
    stmt = (
        select(SectorFlowSnapshot)
        .where(SectorFlowSnapshot.kind == kind, SectorFlowSnapshot.snapshot_at == latest_at)
        .order_by(SectorFlowSnapshot.net_main_inflow.desc())
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(db.scalars(stmt))


__all__ = [
    "ensure_registry",
    "latest_index_quotes",
    "latest_sector_flows",
    "list_index_bars",
    "upsert_index_bar",
    "upsert_index_quote",
    "upsert_sector_board",
    "upsert_sector_flow",
]
