"""信号生成、回测引擎与 n_eff 衰减测试（FR-ANL-003 概率来源原则）。"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from wws_adviser.modules.analytics.kelly import wilson_interval
from wws_adviser.modules.analytics.signals import (
    SignalClass,
    SignalDefinition,
    SignalInstance,
    backtest,
    breakout_signals,
    cluster_decay,
    split_chronological,
    summarize,
)
from wws_adviser.modules.market_data.domain import NormalizedBar

DEF = SignalDefinition(
    signal_id="sig-break-20", name="20日新高+量能", signal_class=SignalClass.L1_RULE,
    version="v1", lookback_days=3, horizon_days=2, cost_bps=Decimal("10"),
)


def _bar(d: date, close: str, open_: str | None = None, volume: str = "1000",
         high: str | None = None) -> NormalizedBar:
    o = open_ if open_ is not None else close
    h = high if high is not None else str(max(Decimal(o), Decimal(close)))
    return NormalizedBar(business_date=d, open=Decimal(o), high=Decimal(h),
                         low=Decimal(str(min(Decimal(o), Decimal(close)))), close=Decimal(close),
                         volume=Decimal(volume))


# —— 信号分层 ——


def test_signal_class_l4_never_eligible() -> None:
    assert SignalClass.L4_MODEL_LANGUAGE.kelly_eligible is False
    for c in (SignalClass.L1_RULE, SignalClass.L2_FACTOR, SignalClass.L3_EVENT):
        assert c.kelly_eligible is True


# —— L1 生成器 ——


def test_breakout_triggers_on_new_high_with_volume() -> None:
    d0 = date(2026, 8, 1)
    bars = [
        _bar(d0, "10", volume="1000"), _bar(d0 + timedelta(1), "10.5", volume="1000"),
        _bar(d0 + timedelta(2), "10.2", volume="1000"),
        # 收盘 11 > 前3日高 10.5，量 2000 > 均 1000×1.2 → 触发
        _bar(d0 + timedelta(3), "11", volume="2000"),
        _bar(d0 + timedelta(4), "10.8", volume="500"),  # 新高但量能不足 → 不触发
    ]
    signals = breakout_signals(DEF, {"600519": bars})
    assert len(signals) == 1
    assert signals[0].code == "600519"
    assert signals[0].trigger_date == d0 + timedelta(3)


def test_breakout_consecutive_highs_need_volume_too() -> None:
    """连续新高但量能不足不触发；量能脉冲日才触发（生成器保持机械，重叠在统计层衰减）。"""
    d0 = date(2026, 8, 1)
    closes = ["10", "11", "12", "13", "14", "15"]
    vols = ["1000", "1000", "1000", "2000", "1000", "2000"]
    bars = [_bar(d0 + timedelta(i), closes[i], volume=vols[i]) for i in range(6)]
    signals = breakout_signals(DEF, {"600519": bars})
    # 第4天（close 13>12 且 2000>1200）与第6天（close 15>14 且 2000>1600）触发；
    # 第5天量能 1000 < avg(1000,2000,1000)×1.2=1600 不触发
    assert [s.trigger_date for s in signals] == [d0 + timedelta(3), d0 + timedelta(5)]


def test_breakout_insufficient_history() -> None:
    bars = [_bar(date(2026, 8, 1), "10")]
    assert breakout_signals(DEF, {"600519": bars}) == []


# —— 回测引擎 ——


def _rising_bars(n: int, start: date, start_price: str = "10") -> list[NormalizedBar]:
    return [_bar(start + timedelta(i), str(Decimal(start_price) + Decimal(i))) for i in range(n)]


def test_backtest_entry_next_open_exit_horizon_close() -> None:
    d0 = date(2026, 8, 1)
    bars = [
        _bar(d0, "10"), _bar(d0 + timedelta(1), "11"),
        _bar(d0 + timedelta(2), "12"), _bar(d0 + timedelta(3), "13"),
        _bar(d0 + timedelta(4), "14"),
    ]
    inst = SignalInstance(signal_id=DEF.signal_id, code="600519", trigger_date=d0 + timedelta(1))
    outcomes = backtest(DEF, [inst], {"600519": bars})
    assert len(outcomes) == 1
    o = outcomes[0]
    # 入场 = 触发次日开盘 12（idx+1）；自入场持有 2 个交易日 → 第5根收盘 14（idx+1+horizon）
    assert o.entry_price == Decimal("12") and o.exit_price == Decimal("14")
    assert o.entry_date == d0 + timedelta(2) and o.exit_date == d0 + timedelta(4)
    cost = Decimal("10") / Decimal("10000") * 2
    assert o.net_return == pytest.approx(Decimal(2) / Decimal(12) - cost, abs=Decimal("1e-12"))
    assert o.win is True


def test_backtest_skips_insufficient_forward_window() -> None:
    d0 = date(2026, 8, 1)
    bars = [_bar(d0, "10"), _bar(d0 + timedelta(1), "11")]  # 触发后不足 horizon
    inst = SignalInstance(signal_id=DEF.signal_id, code="600519", trigger_date=d0)
    assert backtest(DEF, [inst], {"600519": bars}) == []


def test_backtest_cost_makes_marginal_win_a_loss() -> None:
    d0 = date(2026, 8, 1)
    # 入场 100（次日开），持有 2 日出场 100.1 → 毛收益 +0.1% < 双边成本 0.2% → 净亏损
    bars = [
        _bar(d0, "100"), _bar(d0 + timedelta(1), "100"),
        _bar(d0 + timedelta(2), "100"), _bar(d0 + timedelta(3), "100.1"),
    ]
    inst = SignalInstance(signal_id=DEF.signal_id, code="600519", trigger_date=d0)
    outcomes = backtest(DEF, [inst], {"600519": bars})
    assert outcomes[0].gross_return == pytest.approx(Decimal("0.001"), abs=Decimal("1e-12"))
    assert outcomes[0].win is False


# —— 统计汇总 ——


def test_summarize_wilson_and_payoff_ratio() -> None:
    d0 = date(2026, 8, 1)
    bars_win = [_bar(d0 + timedelta(i), str(10 + i)) for i in range(5)]
    bars_lose = [ _bar(d0 + timedelta(i), str(10 - i)) for i in range(5)]
    def inst(i):
        return SignalInstance(signal_id=DEF.signal_id, code=f"C{i}", trigger_date=d0)
    outcomes = (
        backtest(DEF, [inst(1)], {"C1": bars_win})      # 赢
        + backtest(DEF, [inst(2)], {"C2": bars_lose})   # 输
    )
    stats = summarize(outcomes, DEF.signal_id)
    assert stats.n_total == 2 and stats.n_win == 1 and stats.n_loss == 1
    low, mid, high = wilson_interval(1, 2)
    assert stats.p_low == low and stats.p_mid == mid and stats.p_high == high
    assert stats.b > 0
    assert stats.avg_cost == pytest.approx(Decimal("0.002"), abs=Decimal("1e-12"))


def test_summarize_empty_raises() -> None:
    with pytest.raises(ValueError):
        summarize([], "sig-x")


# —— n_eff 聚类衰减 ——


def test_cluster_decay_overlapping_instances_collapse() -> None:
    d0 = date(2026, 8, 1)
    # 同标的三连日触发（间隔 1 天 < horizon 2）→ 1 簇；隔 5 天再触发 → 另 1 簇
    insts = [
        SignalInstance("s", "600519", d0),
        SignalInstance("s", "600519", d0 + timedelta(1)),
        SignalInstance("s", "600519", d0 + timedelta(2)),
        SignalInstance("s", "600519", d0 + timedelta(10)),
    ]
    n_eff, details = cluster_decay(insts, horizon_days=2)
    assert n_eff == 2
    assert details[0].n_instances == 4 and details[0].n_clusters == 2
    assert details[0].cluster_sizes == (3, 1)


def test_cluster_decay_cross_sectional_full_count() -> None:
    d0 = date(2026, 8, 1)
    insts = [SignalInstance("s", f"C{i:03d}", d0) for i in range(50)]  # 50 标的同日
    n_eff, _ = cluster_decay(insts, horizon_days=2)
    assert n_eff == 50  # 横截面样本独立，不衰减


def test_cluster_decay_gap_exactly_horizon_splits() -> None:
    d0 = date(2026, 8, 1)
    insts = [SignalInstance("s", "C1", d0), SignalInstance("s", "C1", d0 + timedelta(2))]
    n_eff, _ = cluster_decay(insts, horizon_days=2)  # 间隔==horizon 不算重叠
    assert n_eff == 2


# —— 样本内外切分 ——


def test_split_chronological_by_exit_date() -> None:
    d0 = date(2026, 8, 1)
    bars = _rising_bars(8, d0)
    insts = [SignalInstance("s", "C1", d0 + timedelta(i)) for i in range(5)]
    outcomes = backtest(SignalDefinition(
        signal_id="s", name="x", signal_class=SignalClass.L1_RULE, version="v1",
        lookback_days=1, horizon_days=1, cost_bps=Decimal("0"),
    ), insts, {"C1": bars})
    cutoff = d0 + timedelta(4)
    split = split_chronological(outcomes, cutoff)
    assert len(split.in_sample) + len(split.out_of_sample) == len(outcomes)
    assert all(o.exit_date < cutoff for o in split.in_sample)
    assert all(o.exit_date >= cutoff for o in split.out_of_sample)
    assert len(split.out_of_sample) > 0
    # 顺序性保证：样本内最大出场日 < 样本外最小出场日
    if split.in_sample:
        max_is = max(o.exit_date for o in split.in_sample)
        min_oos = min(o.exit_date for o in split.out_of_sample)
        assert max_is < min_oos


# —— 端到端小闭环：生成 → 回测 → 衰减 → 切分 ——


def test_full_pipeline_small_dataset() -> None:
    d0 = date(2026, 7, 1)
    bars: dict[str, list[NormalizedBar]] = {}
    # 两只标的、阶梯上行 + 量能脉冲，构造若干触发
    for code, drift in (("600519", 1), ("000001", 2)):
        rows = []
        price = Decimal("10")
        for i in range(30):
            vol = "3000" if i % 7 == 3 else "1000"
            rows.append(_bar(d0 + timedelta(i), str(price), volume=vol))
            price += Decimal(drift) / 2
        bars[code] = rows
    signals = breakout_signals(DEF, bars)
    assert len(signals) > 0
    outcomes = backtest(DEF, signals, bars)
    assert len(outcomes) == len(signals)
    stats = summarize(outcomes, DEF.signal_id)
    assert stats.n_total == len(outcomes)
    n_eff, details = cluster_decay(signals, DEF.horizon_days)
    assert n_eff <= len(signals)
    assert all(d.n_clusters <= d.n_instances for d in details)
