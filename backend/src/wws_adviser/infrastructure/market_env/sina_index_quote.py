"""新浪全球指数解析（hq.sinajs.cn，GBK 文本，需固定 Referer）——纯函数。

线上格式按 symbol 前缀分族（2026-11-16 实录钉住，5_DATA §13.2）：
- rt_hk*：`代码,名称,开,昨收,高,低,最新[6],涨跌额[7],涨跌幅%[8],…,日期[17],时间[18]`
- b_*：`名称[0],最新[1],涨跌额[2],涨跌幅%[3],…,日期[6],时间[7]`（b_N225 为空——日经
  用 int_ 族；空载荷直接跳过）
- int_*：`名称[0],最新[1],涨跌额[2],涨跌幅%[3]`（仅 4 字段，无时间戳）
- gb_*：`名称[0],最新[1],涨跌幅%[2],时间[3],涨跌额[4]`
- hf_*（美股指数期货，盘前参考，5_DATA §13.6 双轨）：
  `最新[0],,买[2],卖[3],高[4],低[5],时间[6],昨结[7],昨开[8],…,日期[12],名称[13]`
  ——涨跌幅以 最新/昨结 自算（hf_ES/hf_NQ/hf_YM 实测一致）
"""

import re
from decimal import Decimal

from wws_adviser.core.time import now_utc_iso
from wws_adviser.ports.market_data import SourceDelayClass
from wws_adviser.ports.market_env import IndexRef, RawIndexQuote

from ._parsing import dec_or_zero, normalize_market_time

_LINE_RE = re.compile(r'hq_str_(\w+)="([^"]*)"')


def parse_sina_global_text(text: str, refs: list[IndexRef]) -> list[RawIndexQuote]:
    """新浪全球指数响应文本 → RawIndexQuote 列表（空载荷/未注册行跳过）。"""
    sym_to_ref = {ref.symbol_map["sina"]: ref for ref in refs if "sina" in ref.symbol_map}
    out: list[RawIndexQuote] = []
    now = now_utc_iso()
    for sym, body in _LINE_RE.findall(text):
        ref = sym_to_ref.get(sym)
        if ref is None or not body:
            continue
        parsed = _parse_by_family(sym, body.split(","))
        if parsed is None:
            continue
        price, change_pct, market_time = parsed
        if price <= 0:
            continue
        out.append(
            RawIndexQuote(
                code=ref.code,
                source="sina",
                source_url=f"sina://index/{sym}",
                market_time=market_time or now,  # int_ 族无时间戳 → fetched_at 兜底
                fetched_at=now,
                received_at=now,
                source_delay_class=SourceDelayClass.REALTIME.value
                if sym.startswith("hf_")
                else SourceDelayClass.DELAYED.value,
                price=price,
                change_pct=change_pct,
            )
        )
    return out


def _parse_by_family(
    sym: str, f: list[str]
) -> tuple[Decimal, Decimal, str | None] | None:
    """按 symbol 前缀族解析 → (price, change_pct, market_time|None)。结构不符 → None。"""
    try:
        if sym.startswith("rt_hk"):
            if len(f) < 19:
                return None
            return (
                dec_or_zero(f[6]),
                dec_or_zero(f[8]),
                normalize_market_time(f"{f[17]} {f[18]}"),
            )
        if sym.startswith("b_"):
            if len(f) < 8:
                return None
            return dec_or_zero(f[1]), dec_or_zero(f[3]), normalize_market_time(f"{f[6]} {f[7]}")
        if sym.startswith("int_"):
            if len(f) < 4:
                return None
            return dec_or_zero(f[1]), dec_or_zero(f[3]), None
        if sym.startswith("gb_"):
            if len(f) < 5:
                return None
            return dec_or_zero(f[1]), dec_or_zero(f[2]), normalize_market_time(f[3])
        if sym.startswith("hf_"):
            if len(f) < 14:
                return None
            last = dec_or_zero(f[0])
            settle = dec_or_zero(f[7])  # 昨结算（涨跌幅基准）
            pct = (last - settle) / settle * 100 if settle > 0 else Decimal("0")
            return last, pct, normalize_market_time(f"{f[12]} {f[6]}")
        return None
    except (IndexError, ValueError):
        return None
