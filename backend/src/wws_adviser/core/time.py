"""时间辅助。所有业务时间以 Asia/Shanghai 为基准（见术语表 business_date）。"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

SHANGHAI = ZoneInfo("Asia/Shanghai")


def now_shanghai() -> datetime:
    return datetime.now(SHANGHAI)


def business_date(now: datetime | None = None) -> date:
    """当前交易日日期（Asia/Shanghai 下的 YYYY-MM-DD）。"""
    return (now or now_shanghai()).date()
