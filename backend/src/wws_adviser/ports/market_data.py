"""行情数据端口（QuoteProvider/BarProvider/NAVProvider）与原始 DTO。

端口返回原始对象（RawQuote 等，6 wrapper + 数值字段）；标准化（单位/scale）由内部
流水线统一执行；**不**携带已判定的 quality_status（5_DATA_INGESTION_AND_QUALITY.md §2）。
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Protocol


class SourceDelayClass(StrEnum):
    """行情延迟等级（实时/延时/日终）。"""

    REALTIME = "realtime"
    DELAYED = "delayed"
    END_OF_DAY = "end_of_day"


@dataclass(frozen=True)
class InstrumentRef:
    """标的引用（轻量标识；A 股 + 场内 ETF）。"""

    code: str
    market: str
    kind: str  # stock / etf


@dataclass(frozen=True)
class RawQuote:
    source: str
    source_url: str
    market_time: str
    fetched_at: str
    received_at: str
    source_delay_class: SourceDelayClass
    price: Decimal
    change_pct: Decimal
    volume: Decimal
    amount: Decimal
    bid_ask: dict[str, str] | None = None


@dataclass(frozen=True)
class BarRow:
    date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


@dataclass(frozen=True)
class RawDataset:
    source: str
    source_url: str
    market_time: str
    fetched_at: str
    received_at: str
    source_delay_class: SourceDelayClass
    bars: list[BarRow] = field(default_factory=list)


@dataclass(frozen=True)
class RawNAV:
    source: str
    source_url: str
    market_time: str
    fetched_at: str
    received_at: str
    source_delay_class: SourceDelayClass
    nav: Decimal
    published_at: str


class QuoteProvider(Protocol):
    async def fetch_quotes(self, instruments: list[InstrumentRef]) -> list[RawQuote]: ...


class BarProvider(Protocol):
    async def fetch_daily_bars(
        self, instrument: InstrumentRef, start: date, end: date
    ) -> RawDataset: ...


class NAVProvider(Protocol):
    async def fetch_nav(self, instrument: InstrumentRef, as_of: date) -> RawNAV: ...
