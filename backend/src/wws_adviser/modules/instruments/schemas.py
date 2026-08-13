"""Instruments DTO。"""

from pydantic import BaseModel


class InstrumentOut(BaseModel):
    id: str
    code: str
    market: str
    kind: str
    name: str
    industry: str | None = None
    sector: str | None = None
    lot_size: int
    price_scale: int
    qty_scale: int
    tradable: bool
    status: str


class InstrumentListResponse(BaseModel):
    items: list[InstrumentOut]
