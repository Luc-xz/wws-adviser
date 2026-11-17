"""Market env 领域：指数注册表 + 标准化/校验。纯领域，禁框架 import（对齐 market_data）。

指数注册表的 symbol 均经 2026-11-16 线上实录验证；质量状态沿用 market_data 六态
（quality_status 是跨数据域统一契约，5_DATA §7/§13.3）。
"""

from dataclasses import dataclass
from decimal import Decimal

from wws_adviser.core.errors import DomainError
from wws_adviser.modules.market_data.domain import QualityStatus
from wws_adviser.ports.market_env import IndexRef, RawIndexQuote, RawSectorFlow

# 指数注册表（ADR-0014；market_group 分组驱动 overview 聚合，3_API §3.18）。
# symbol_map：tencent = qt.gtimg.cn 代码；sina = hq.sinajs.cn 代码（仅外围，A股以
# 腾讯为主源无新浪兜底）；eastmoney = push2his secid（指数日 K，v1 仅 CN 指数）。
INDEX_REGISTRY: tuple[IndexRef, ...] = (
    # —— A 股宽基（cn_sh000001 + cn_sz399106 的 amount 汇总 = 两市成交额，2_DATA §6.8） ——
    IndexRef("cn_sh000001", "上证指数", "cn_broad",
             {"tencent": "sh000001", "eastmoney": "1.000001"}),
    IndexRef("cn_sz399001", "深证成指", "cn_broad",
             {"tencent": "sz399001", "eastmoney": "0.399001"}),
    IndexRef("cn_sz399106", "深证综指", "cn_broad",
             {"tencent": "sz399106", "eastmoney": "0.399106"}),
    IndexRef("cn_sh000300", "沪深300", "cn_broad",
             {"tencent": "sh000300", "eastmoney": "1.000300"}),
    IndexRef("cn_sh000905", "中证500", "cn_broad",
             {"tencent": "sh000905", "eastmoney": "1.000905"}),
    IndexRef("cn_sh000852", "中证1000", "cn_broad",
             {"tencent": "sh000852", "eastmoney": "1.000852"}),
    IndexRef("cn_sz399006", "创业板指", "cn_broad",
             {"tencent": "sz399006", "eastmoney": "0.399006"}),
    IndexRef("cn_sh000688", "科创50", "cn_broad",
             {"tencent": "sh000688", "eastmoney": "1.000688"}),
    # —— A 股风格 ——
    IndexRef("cn_sh000016", "上证50", "cn_style",
             {"tencent": "sh000016", "eastmoney": "1.000016"}),
    IndexRef("cn_sh000922", "中证红利", "cn_style",
             {"tencent": "sh000922", "eastmoney": "1.000922"}),
    # —— 外围：美股（盘前/盘后字段口径待 cassette 实测确认，5_DATA §13.6） ——
    IndexRef("us_dji", "道琼斯", "overseas_us",
             {"tencent": "usDJI", "sina": "gb_dji"}, has_pre_post=True),
    IndexRef("us_ixic", "纳斯达克", "overseas_us",
             {"tencent": "usIXIC", "sina": "gb_ixic"}, has_pre_post=True),
    IndexRef("us_inx", "标普500", "overseas_us",
             {"tencent": "usINX", "sina": "gb_inx"}, has_pre_post=True),
    # —— 外围：亚太（int_nikkei 仅 4 字段无时间戳，market_time 以 fetched_at 兜底） ——
    IndexRef("hk_hsi", "恒生指数", "overseas_ap", {"tencent": "hkHSI", "sina": "rt_hkHSI"}),
    IndexRef("hk_hstech", "恒生科技", "overseas_ap",
             {"tencent": "hkHSTECH", "sina": "rt_hkHSTECH"}),
    IndexRef("jp_n225", "日经225", "overseas_ap", {"sina": "int_nikkei"}),
    IndexRef("kr_kospi", "韩国KOSPI", "overseas_ap", {"sina": "b_KOSPI"}),
    # —— 美股指数期货（盘前参考，5_DATA §13.6 双轨；hf_ 族实测 2026-11-16） ——
    IndexRef("fut_es", "标普500期货", "futures_us", {"sina": "hf_ES"}),
    IndexRef("fut_nq", "纳斯达克期货", "futures_us", {"sina": "hf_NQ"}),
    IndexRef("fut_ym", "道琼斯期货", "futures_us", {"sina": "hf_YM"}),
)

INDEX_BY_CODE: dict[str, IndexRef] = {r.code: r for r in INDEX_REGISTRY}

# 两市成交额汇总口径（2_DATA §6.8）：上证综指 + 深证综指的 amount（元）。
TURNOVER_INDEX_CODES = ("cn_sh000001", "cn_sz399106")


class IndexQuoteParseError(DomainError):
    """指数快照解析/校验失败（价格非正等）。上层据此记 quality_status=PARSE_FAILED。"""

    code = "DATA_MISSING"
    status = 409
    title = "指数快照解析失败"


class SectorFlowParseError(DomainError):
    """板块资金流解析/校验失败。"""

    code = "DATA_MISSING"
    status = 409
    title = "板块资金流解析失败"


@dataclass(frozen=True)
class NormalizedIndexQuote:
    code: str
    source: str
    price: Decimal
    change_pct: Decimal
    volume: Decimal
    amount: Decimal
    market_time: str
    pre_market_price: Decimal | None = None
    pre_market_change_pct: Decimal | None = None
    post_market_price: Decimal | None = None
    post_market_change_pct: Decimal | None = None


@dataclass(frozen=True)
class NormalizedSectorFlow:
    kind: str
    board_code: str
    board_name: str
    change_pct: Decimal
    turnover: Decimal
    net_main_inflow: Decimal
    leader_code: str | None
    leader_name: str | None
    market_time: str


def parse_index_quote(raw: RawIndexQuote, *, price_scale: int = 4) -> NormalizedIndexQuote:
    """原始指数快照 → 标准化。价格非正（停摆/坏数据）抛 IndexQuoteParseError。"""
    if raw.price <= 0:
        raise IndexQuoteParseError(f"指数 {raw.code} 价格非正：{raw.price}")
    q = Decimal(1).scaleb(-price_scale)
    return NormalizedIndexQuote(
        code=raw.code,
        source=raw.source,
        price=raw.price.quantize(q),
        change_pct=raw.change_pct.quantize(q),
        volume=raw.volume,
        amount=raw.amount,
        market_time=raw.market_time,
        pre_market_price=(raw.pre_market_price.quantize(q)
                          if raw.pre_market_price is not None else None),
        pre_market_change_pct=(raw.pre_market_change_pct.quantize(q)
                               if raw.pre_market_change_pct is not None else None),
        post_market_price=(raw.post_market_price.quantize(q)
                           if raw.post_market_price is not None else None),
        post_market_change_pct=(raw.post_market_change_pct.quantize(q)
                                if raw.post_market_change_pct is not None else None),
    )


def parse_sector_flow(raw: RawSectorFlow) -> NormalizedSectorFlow:
    """原始板块资金流 → 标准化。board_code 为空抛 SectorFlowParseError。"""
    if not raw.board_code:
        raise SectorFlowParseError("板块代码为空")
    return NormalizedSectorFlow(
        kind=raw.kind.value,
        board_code=raw.board_code,
        board_name=raw.board_name,
        change_pct=raw.change_pct,
        turnover=raw.turnover,
        net_main_inflow=raw.net_main_inflow,
        leader_code=raw.leader_code,
        leader_name=raw.leader_name,
        market_time=raw.market_time,
    )


__all__ = [
    "INDEX_BY_CODE",
    "INDEX_REGISTRY",
    "TURNOVER_INDEX_CODES",
    "IndexQuoteParseError",
    "NormalizedIndexQuote",
    "NormalizedSectorFlow",
    "QualityStatus",
    "SectorFlowParseError",
    "parse_index_quote",
    "parse_sector_flow",
]
