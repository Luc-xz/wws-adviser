"""/api/v1/market-data 端点（stub→domain→API 闭环 demo）。"""

from typing import Annotated

from fastapi import APIRouter, Depends

from wws_adviser.api.dependencies import get_quote_provider
from wws_adviser.modules.market_data import service
from wws_adviser.modules.market_data.schemas import QuoteOut
from wws_adviser.ports.market_data import InstrumentRef, QuoteProvider

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
