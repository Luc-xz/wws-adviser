"""市场环境 stub 适配器：合成数据（source="stub"），禁生产（Phase 0/1 联调用）。

market_time/snapshot_at 与真实适配器同契约：上海本地时间 "YYYY-MM-DD HH:MM:SS"
（腾讯/新浪解析器的归一格式）——stub 满足统一 schema 不止字段齐，还包括格式。
"""

from datetime import date, datetime, timedelta
from decimal import Decimal

from wws_adviser.core.time import SHANGHAI, now_utc_iso
from wws_adviser.infrastructure import assert_not_prod
from wws_adviser.modules.market_env.domain import INDEX_REGISTRY, TURNOVER_INDEX_CODES
from wws_adviser.ports.market_data import BarRow, RawDataset, SourceDelayClass
from wws_adviser.ports.market_env import (
    IndexRef,
    RawIndexQuote,
    RawSectorFlow,
    SectorKind,
)

_STUB_SOURCE = "stub"


def _now_sh() -> str:
    """上海本地时间字符串（与真实适配器 market_time 契约一致）。"""
    return datetime.now(SHANGHAI).strftime("%Y-%m-%d %H:%M:%S")
# 两市成交额合成值（元）：读取侧汇总口径可被测试断言
_STUB_TURNOVER: dict[str, Decimal] = {
    "cn_sh000001": Decimal("500000000000"),
    "cn_sz399106": Decimal("400000000000"),
}
_STUB_BOARDS: dict[SectorKind, tuple[tuple[str, str], ...]] = {
    SectorKind.INDUSTRY: (
        ("BK0001", "银行"), ("BK0002", "证券"), ("BK0003", "半导体"), ("BK0004", "白酒"),
    ),
    SectorKind.CONCEPT: (
        ("BK1001", "人工智能"), ("BK1002", "机器人"), ("BK1003", "低空经济"),
    ),
}


class StubIndexQuoteProvider:
    """占位指数快照：注册表每项一条合成行情（含两市成交额口径）。"""

    def __init__(self, *, env: str = "dev") -> None:
        assert_not_prod(env)

    async def fetch_index_quotes(self, refs: list[IndexRef]) -> list[RawIndexQuote]:
        now = now_utc_iso()
        mt = _now_sh()
        out: list[RawIndexQuote] = []
        for i, ref in enumerate(refs):
            out.append(
                RawIndexQuote(
                    code=ref.code,
                    source=_STUB_SOURCE,
                    source_url=f"stub://index/{ref.code}",
                    market_time=mt,
                    fetched_at=now,
                    received_at=now,
                    source_delay_class=SourceDelayClass.REALTIME.value,
                    price=Decimal(1000 + i * 10),
                    change_pct=Decimal("0.5") if i % 2 == 0 else Decimal("-0.25"),
                    volume=Decimal("1000000"),
                    amount=_STUB_TURNOVER.get(ref.code, Decimal("0")),
                )
            )
        return out


class StubIndexBarProvider:
    """占位指数日 K：每指数 30 个合成交易日（跳过周末）。"""

    def __init__(self, *, env: str = "dev") -> None:
        assert_not_prod(env)

    async def fetch_index_bars(self, ref: IndexRef, start: date, end: date) -> RawDataset:
        now = now_utc_iso()
        bars: list[BarRow] = []
        d = end
        n = 0
        while d >= start and len(bars) < 30:
            if d.weekday() < 5:
                close = Decimal(1000 + n)
                bars.append(
                    BarRow(
                        date=d,
                        open=close - Decimal("5"),
                        high=close + Decimal("5"),
                        low=close - Decimal("8"),
                        close=close,
                        volume=Decimal("1000000"),
                    )
                )
                n += 1
            d -= timedelta(days=1)
        bars.reverse()
        return RawDataset(
            source=_STUB_SOURCE,
            source_url=f"stub://index-bars/{ref.code}",
            market_time=now,
            fetched_at=now,
            received_at=now,
            source_delay_class=SourceDelayClass.END_OF_DAY,
            bars=bars,
        )


class StubSectorFlowProvider:
    """占位板块资金流：固定板块 + 双向净额（含净流出板，供榜单双向断言）。"""

    def __init__(self, *, env: str = "dev") -> None:
        assert_not_prod(env)

    async def fetch_sector_flows(self, kind: SectorKind) -> list[RawSectorFlow]:
        now = now_utc_iso()
        mt = _now_sh()
        return [
            RawSectorFlow(
                kind=kind,
                board_code=code,
                board_name=name,
                change_pct=Decimal("1.5") if i % 2 == 0 else Decimal("-0.8"),
                turnover=Decimal(10_000_000_000) + Decimal(i) * Decimal("1000000000"),
                net_main_inflow=(Decimal("1200000000") - Decimal(i) * Decimal("1500000000")),
                source=_STUB_SOURCE,
                source_url=f"stub://sector-flows/{kind.value}",
                market_time=mt,
                fetched_at=now,
                received_at=now,
                source_delay_class=SourceDelayClass.DELAYED.value,
                leader_name=f"领涨股{i}",
                leader_code=None,
            )
            for i, (code, name) in enumerate(_STUB_BOARDS[kind])
        ]


def stub_turnover_total() -> Decimal:
    """两市合成成交额合计（测试断言用）。"""
    return sum((_STUB_TURNOVER[c] for c in TURNOVER_INDEX_CODES), Decimal("0"))


__all__ = [
    "StubIndexBarProvider",
    "StubIndexQuoteProvider",
    "StubSectorFlowProvider",
    "stub_turnover_total",
]


def _registry_guard() -> None:  # pragma: no cover - 导入即校验，防注册表漂移
    assert all(c in {r.code for r in INDEX_REGISTRY} for c in _STUB_TURNOVER)
