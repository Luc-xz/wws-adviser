"""/api/v1/instruments 端点：搜索、详情。"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DBSession

from wws_adviser.api.dependencies import get_current_user, get_session
from wws_adviser.modules.identity.models import User
from wws_adviser.modules.instruments import service
from wws_adviser.modules.instruments.models import Instrument
from wws_adviser.modules.instruments.schemas import InstrumentListResponse, InstrumentOut

router = APIRouter(prefix="/api/v1/instruments", tags=["instruments"])

DBDep = Annotated[DBSession, Depends(get_session)]
UserDep = Annotated[User, Depends(get_current_user)]


def _to_out(inst: Instrument) -> InstrumentOut:
    return InstrumentOut(
        id=inst.id,
        code=inst.code,
        market=inst.market,
        kind=inst.kind,
        name=inst.name,
        industry=inst.industry,
        sector=inst.sector,
        lot_size=inst.lot_size,
        price_scale=inst.price_scale,
        qty_scale=inst.qty_scale,
        tradable=inst.tradable,
        status=inst.status,
    )


@router.get("", response_model=InstrumentListResponse)
async def search_instruments(
    db: DBDep,
    user: UserDep,
    q: str | None = None,
    market: str | None = None,
    kind: str | None = None,
    industry: str | None = None,
    limit: int = 50,
) -> InstrumentListResponse:
    items = service.search_instruments(
        db, q=q, market=market, kind=kind, industry=industry, limit=limit
    )
    return InstrumentListResponse(items=[_to_out(i) for i in items])


@router.get("/{instrument_id}", response_model=InstrumentOut)
async def get_instrument(instrument_id: str, db: DBDep, user: UserDep) -> InstrumentOut:
    inst = service.get_instrument(db, instrument_id)
    if inst is None:
        raise service.InstrumentNotFoundError(instrument_id)
    return _to_out(inst)
