"""市场环境适配器共享解析助手（纯函数 + 结构化解析错误，可单测）。"""

from decimal import Decimal, InvalidOperation
from typing import Any


class MarketEnvParseError(ValueError):
    """源响应结构突变（schema 不匹配）。契约测试 step 3 据此断言不抛不透明异常。"""



def dec_or_zero(v: Any) -> Decimal:
    """宽松转 Decimal：非法/"-"（东财缺失占位）→ 0。"""
    try:
        s = str(v).strip()
        if not s or s == "-":
            return Decimal("0")
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return Decimal("0")


def dec_or_none(v: Any) -> Decimal | None:
    """宽松转 Decimal：非法/"-" → None（可选字段）。"""
    try:
        s = str(v).strip()
        if not s or s == "-":
            return None
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def normalize_market_time(s: Any) -> str | None:
    """源时间字符串 → "YYYY-MM-DD HH:MM:SS"；无法解析 → None（调用方以 fetched_at 兜底）。

    已知线上形态（2026-11-16 实录，5_DATA §13.2）：
    - 腾讯 A 股 "20261116155127"（14 位紧凑）
    - 腾讯美股 "2026-11-13 16:43:26"
    - 腾讯港股 / 新浪 rt_hk "2026/11/16 15:36:28"
    - 新浪 b_*    "2026-11-16,14:32:50"（日期/时间分列，调用方拼接后传入）
    - 新浪 gb_*   "2026-11-14 05:43:43"
    """
    t = str(s).strip()
    if not t:
        return None
    compact = t.replace("/", "-").replace(",", " ")
    parts = compact.split()
    if len(parts) == 2:
        day, tm = parts[0], parts[1]
        if len(day) == 8 and day.isdigit():  # 20261116 → 2026-11-16
            day = f"{day[:4]}-{day[4:6]}-{day[6:]}"
        return f"{day} {tm}"
    if len(compact) == 14 and compact.isdigit():  # 20261116155127
        return (
            f"{compact[:4]}-{compact[4:6]}-{compact[6:8]} "
            f"{compact[8:10]}:{compact[10:12]}:{compact[12:]}"
        )
    return None
