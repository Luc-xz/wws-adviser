"""时间辅助。所有业务时间以 Asia/Shanghai 为基准（见术语表 business_date）。"""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

SHANGHAI = ZoneInfo("Asia/Shanghai")


def now_shanghai() -> datetime:
    return datetime.now(SHANGHAI)


def now_utc_iso() -> str:
    """UTC ISO 8601 字符串（所有表 created_at/occurred_at 等时间列的存储格式）。"""
    return datetime.now(UTC).isoformat()


def business_date(now: datetime | None = None) -> date:
    """当前交易日日期（Asia/Shanghai 下的 YYYY-MM-DD）。"""
    return (now or now_shanghai()).date()
