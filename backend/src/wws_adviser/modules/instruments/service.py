"""Instruments 服务：搜索、详情、按 market+code 取或建（导入时用）。"""

from sqlalchemy.orm import Session as DBSession

from wws_adviser.core.errors import DomainError
from wws_adviser.core.ids import new_id
from wws_adviser.core.time import now_utc_iso
from wws_adviser.modules.instruments import repository
from wws_adviser.modules.instruments.domain import infer_instrument_kind, infer_market
from wws_adviser.modules.instruments.models import Instrument


class InstrumentNotFoundError(DomainError):
    code = "NOT_FOUND"
    status = 404
    title = "标的不存在"


def search_instruments(
    db: DBSession,
    *,
    q: str | None = None,
    market: str | None = None,
    kind: str | None = None,
    industry: str | None = None,
    limit: int = 50,
) -> list[Instrument]:
    return repository.search(db, q=q, market=market, kind=kind, industry=industry, limit=limit)


def get_instrument(db: DBSession, instrument_id: str) -> Instrument | None:
    return repository.get_by_id(db, instrument_id)


def get_or_create_instrument(
    db: DBSession,
    *,
    code: str,
    name: str = "",
    kind: str | None = None,
    market: str | None = None,
) -> Instrument:
    """按 (market, code) 取；不存在则建。只 flush 不 commit（由调用方提交）。

    market/kind 缺省时按代码推断（导入与手工共用，保证指纹一致）。
    """
    resolved_market = market or infer_market(code).value
    existing = repository.get_by_market_code(db, resolved_market, code)
    if existing is not None:
        return existing
    instrument = Instrument(
        id=new_id(),
        code=code,
        market=resolved_market,
        kind=kind or infer_instrument_kind(code).value,
        name=name or code,
        lot_size=100,
        price_scale=2,
        qty_scale=2,
        tradable=True,
        status="active",
        created_at=now_utc_iso(),
        updated_at=now_utc_iso(),
        version=1,
    )
    return repository.add(db, instrument)
