"""行情 DTO（Decimal 以字符串传输，技术架构 §7.3）。"""

from pydantic import BaseModel


class QuoteOut(BaseModel):
    code: str
    source: str
    price: str
    change_pct: str
    market_time: str
