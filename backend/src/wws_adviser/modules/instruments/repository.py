"""Instruments 仓储。"""

from sqlalchemy import or_, select
from sqlalchemy.orm import Session as DBSession

from wws_adviser.modules.instruments.models import Instrument


def get_by_id(db: DBSession, instrument_id: str) -> Instrument | None:
    return db.get(Instrument, instrument_id)


def get_by_market_code(db: DBSession, market: str, code: str) -> Instrument | None:
    return db.scalar(
        select(Instrument).where(Instrument.market == market, Instrument.code == code)
    )


def search(
    db: DBSession,
    *,
    q: str | None = None,
    market: str | None = None,
    kind: str | None = None,
    industry: str | None = None,
    limit: int = 50,
) -> list[Instrument]:
    stmt = select(Instrument)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Instrument.code.like(like), Instrument.name.like(like)))
    if market:
        stmt = stmt.where(Instrument.market == market)
    if kind:
        stmt = stmt.where(Instrument.kind == kind)
    if industry:
        stmt = stmt.where(Instrument.industry == industry)
    stmt = stmt.order_by(Instrument.code).limit(limit)
    return list(db.scalars(stmt))


def add(db: DBSession, instrument: Instrument) -> Instrument:
    db.add(instrument)
    db.flush()
    return instrument
