"""市场环境数据端口（IndexQuoteProvider/IndexBarProvider/SectorFlowProvider）与原始 DTO。

ADR-0014 / 5_DATA_INGESTION_AND_QUALITY.md §13：市场环境是研究上下文数据域（指数/
板块资金流/外围市场），独立于投资标的域。端口只返回原始对象，质量判定由内部流水线
统一执行（与 ports/market_data 同约定）；日 K 复用 BarRow/RawDataset。
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from wws_adviser.ports.market_data import RawDataset


class SectorKind(StrEnum):
    """板块类别（东财行业 / 概念）。"""

    INDUSTRY = "industry"
    CONCEPT = "concept"


@dataclass(frozen=True)
class IndexRef:
    """指数引用：code 为规范代码（cn_sh000001 / us_dji / jp_n225 / hk_hsi）。

    symbol_map 为各源 symbol 映射（{"tencent": "sh000001", "sina": "gb_dji",
    "eastmoney": "1.000001"}）——代码均经 2026-11-16 线上实录验证（5_DATA §13.2），
    仅 clist 板块源待 VPS 验证（§13.6）。
    """

    code: str
    name: str
    market_group: str  # cn_broad / cn_style / overseas_us / overseas_ap
    symbol_map: dict[str, str]
    has_pre_post: bool = False  # 美股指数专用（盘前/盘后字段口径见 5_DATA §13.6）


@dataclass(frozen=True)
class RawIndexQuote:
    """指数快照原始 DTO。盘前/盘后仅美股源填充，其余置 None。"""

    code: str
    source: str
    source_url: str
    market_time: str
    fetched_at: str
    received_at: str
    source_delay_class: str
    price: Decimal
    change_pct: Decimal
    volume: Decimal = Decimal("0")
    amount: Decimal = Decimal("0")
    pre_market_price: Decimal | None = None
    pre_market_change_pct: Decimal | None = None
    post_market_price: Decimal | None = None
    post_market_change_pct: Decimal | None = None


@dataclass(frozen=True)
class RawSectorFlow:
    """板块资金流快照原始 DTO：涨幅榜（活跃板块）与主力净流入/流出榜同源覆盖。"""

    kind: SectorKind
    board_code: str
    board_name: str
    change_pct: Decimal
    turnover: Decimal
    net_main_inflow: Decimal
    source: str
    source_url: str
    market_time: str
    fetched_at: str
    received_at: str
    source_delay_class: str
    leader_code: str | None = None
    leader_name: str | None = None


class IndexQuoteProvider(Protocol):
    async def fetch_index_quotes(self, refs: list[IndexRef]) -> list[RawIndexQuote]: ...


class IndexBarProvider(Protocol):
    async def fetch_index_bars(self, ref: IndexRef, start: date, end: date) -> RawDataset: ...


class SectorFlowProvider(Protocol):
    async def fetch_sector_flows(self, kind: SectorKind) -> list[RawSectorFlow]: ...
