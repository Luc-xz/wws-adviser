"""腾讯指数快照解析（qt.gtimg.cn，GBK 文本）——纯函数，cassette 契约测试的落点。

线上格式（2026-11-16 实录钉住，5_DATA §13.2）：
`v_sh000001="1~上证指数~000001~现价[3]~昨收[4]~今开[5]~成交量(手)[6]~…"`
- **位序不可靠**：同一响应内 sh000001 行 86 字段（时间在 [28]）、深市行 88 字段
  （时间在 [30]）——时间与成交额按**模式定位**，不按固定位序；价格/昨收/量 [3][4][6]
  在全部实录行稳定。
- 时间三形态：A股 14 位紧凑 / 美股 "YYYY-MM-DD HH:MM:SS" / 港股 "YYYY/MM/DD HH:MM:SS"。
- 成交额：仅 A 股行存在 "价/量/额(元)" 斜杠三元组（口径无歧义）；美股对应位是币种
  "USD"、港股无斜杠形态——非斜杠一律 0，不发布语义不明的数。
- 涨跌幅由 现价/昨收 自算（不依赖位序）。
"""

import re
from decimal import Decimal

from wws_adviser.core.time import now_utc_iso
from wws_adviser.ports.market_data import SourceDelayClass
from wws_adviser.ports.market_env import IndexRef, RawIndexQuote

from ._parsing import dec_or_zero, normalize_market_time

_LINE_RE = re.compile(r'v_(\w+)="([^"]*)"')
_TS_RE = re.compile(r"^(\d{14}|\d{4}[-/]\d{2}[-/]\d{2}[ ,]\d{2}:\d{2}:\d{2})$")
_AMOUNT_RE = re.compile(r"^[\d.]+/[\d.]+/([\d.]+)$")


def parse_tencent_index_text(text: str, refs: list[IndexRef]) -> list[RawIndexQuote]:
    """腾讯批量行情响应文本 → RawIndexQuote 列表（sym → ref 经 symbol_map 反查）。"""
    sym_to_ref = {
        ref.symbol_map["tencent"]: ref for ref in refs if "tencent" in ref.symbol_map
    }
    out: list[RawIndexQuote] = []
    now = now_utc_iso()
    for sym, body in _LINE_RE.findall(text):
        ref = sym_to_ref.get(sym)
        if ref is None:
            continue
        parts = body.split("~")
        if len(parts) < 10:
            continue
        price = dec_or_zero(parts[3])
        prev = dec_or_zero(parts[4])
        if price <= 0 or prev <= 0:
            continue  # 停摆/坏行：跳过（快照缺失由 service 记 NO_DATA）
        change_pct = (price - prev) / prev * 100
        out.append(
            RawIndexQuote(
                code=ref.code,
                source="tencent",
                source_url=f"tencent://index/{sym}",
                market_time=_find_market_time(parts) or now,
                fetched_at=now,
                received_at=now,
                source_delay_class=SourceDelayClass.REALTIME.value,
                price=price,
                change_pct=change_pct,
                volume=dec_or_zero(parts[6]),
                amount=_find_amount(parts),
            )
        )
    return out


def _find_market_time(parts: list[str]) -> str | None:
    """首个时间戳形态字段（14 位紧凑 / 带分隔日期时间）→ 归一。"""
    for p in parts:
        if _TS_RE.match(p):
            normalized = normalize_market_time(p)
            if normalized:
                return normalized
    return None


def _find_amount(parts: list[str]) -> Decimal:
    """首个 "价/量/额(元)" 斜杠三元组 → 成交额（元）。无斜杠形态 → 0。"""
    for p in parts:
        m = _AMOUNT_RE.match(p)
        if m:
            v = dec_or_zero(m.group(1))
            if v > 0:
                return v
    return Decimal("0")
