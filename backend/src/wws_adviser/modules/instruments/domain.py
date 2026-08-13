"""Instruments 领域：标的分类、市场/类型推断、精度校验。纯领域，禁框架 import。"""

from enum import StrEnum


class InstrumentKind(StrEnum):
    STOCK = "STOCK"
    ETF = "ETF"
    FUND = "FUND"
    BOND = "BOND"
    INDEX = "INDEX"


class Market(StrEnum):
    SSE = "SSE"  # 上海证券交易所
    SZSE = "SZSE"  # 深圳证券交易所
    BSE = "BSE"  # 北京证券交易所


def infer_market(code: str) -> Market:
    """按证券代码前缀推断市场（A 股 MVP 规则）。

    6/5 → 上交所(SSE)；0/3/1 → 深交所(SZSE)；其余默认 SSE。
    """
    c = code.strip()
    if not c:
        return Market.SSE
    head = c[0]
    if head in ("6", "5"):
        return Market.SSE
    if head in ("0", "3", "1"):
        return Market.SZSE
    return Market.SSE


def infer_instrument_kind(code: str) -> InstrumentKind:
    """按代码前缀粗分标的类型：5/1 开头多为 ETF/基金，其余按股票。"""
    head = code.strip()[:1]
    if head in ("5", "1"):
        return InstrumentKind.ETF
    return InstrumentKind.STOCK


def validate_scale(value: int, *, min_scale: int = 0, max_scale: int = 8) -> int:
    """价格/数量精度列校验。"""
    if not (min_scale <= value <= max_scale):
        raise ValueError(f"scale 越界：{value} 不在 [{min_scale}, {max_scale}]")
    return value
