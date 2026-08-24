"""信号定义、回测引擎与有效样本衰减（纯领域服务，FR-ANL-003/004）。

概率来源原则：`p` 的校准对象是信号规则在**适用的全市场标的集合**上的历史回测表现
（横截面与时间序列并集），不是用户个体持仓。本模块只产出统计原始材料（胜/负、
平均盈亏、Wilson 区间、n_eff），`p` 只能在回测/校准服务内写入（模型 Gateway 无权）。

信号分层（按可校准性）：
    L1 规则化/机械信号（默认有资格）  L2 基本面因子（需滚动校准）
    L3 事件驱动（条件性资格）          L4 模型语言判断（永远无资格）

零外部依赖；全部 Decimal。bars 输入复用 market_data 的 NormalizedBar。
"""

from dataclasses import dataclass, field
from datetime import date as Date
from decimal import Decimal
from enum import StrEnum
from typing import Mapping, Sequence

from wws_adviser.modules.analytics.kelly import wilson_interval
from wws_adviser.modules.market_data.domain import NormalizedBar


SCHEMA_VERSION = "1"


class SignalClass(StrEnum):
    """信号分层（FR-ANL-003）。L4（模型语言判断）永远不具凯利资格。"""

    L1_RULE = "L1"
    L2_FACTOR = "L2"
    L3_EVENT = "L3"
    L4_MODEL_LANGUAGE = "L4"

    @property
    def kelly_eligible(self) -> bool:
        return self is not SignalClass.L4_MODEL_LANGUAGE


@dataclass(frozen=True)
class SignalDefinition:
    """版本化信号定义：记录统计窗口、适用范围与成本假设（FR-ANL-003）。"""

    signal_id: str
    name: str
    signal_class: SignalClass
    version: str
    lookback_days: int                  # 规则回看窗口
    horizon_days: int                   # 持有期（前向收益窗口）
    cost_bps: Decimal = Decimal("10")   # 单边交易成本假设（基点）
    universe: str = "A_SHARE"           # 适用品种集合


@dataclass(frozen=True)
class SignalInstance:
    """一次具体信号触发（某标的某日）。"""

    signal_id: str
    code: str
    trigger_date: Date


@dataclass(frozen=True)
class SignalOutcome:
    """一次信号实例的前向收益评估（回测引擎输出）。"""

    instance: SignalInstance
    entry_date: Date
    exit_date: Date
    entry_price: Decimal
    exit_price: Decimal
    gross_return: Decimal               # (exit−entry)/entry
    cost: Decimal                       # 双边成本合计（比例）
    net_return: Decimal                 # gross − cost
    win: bool

    @property
    def holding_days(self) -> int:
        return (self.exit_date - self.entry_date).days


@dataclass(frozen=True)
class BacktestStats:
    """一组信号结果的总计统计——凯利/校准服务的原始输入。"""

    signal_id: str
    n_total: int
    n_win: int
    n_loss: int
    avg_win: Decimal                    # 平均盈利（比例，>0）
    avg_loss: Decimal                   # 平均亏损（比例，>0，绝对值）
    b: Decimal                          # 平均盈利/平均亏损
    # Wilson 区间（p 的唯一合法形态）
    p_low: Decimal
    p_mid: Decimal
    p_high: Decimal
    avg_cost: Decimal


@dataclass(frozen=True)
class ClusterDecay:
    """重叠信号聚类衰减明细（可审计）。"""

    code: str
    n_instances: int
    n_clusters: int
    cluster_sizes: tuple[int, ...] = field(default_factory=tuple)


# —— L1 信号生成器：N 日新高突破 + 量能放大（机械规则，示例基线）——


def breakout_signals(
    definition: SignalDefinition, bars_by_code: Mapping[str, Sequence[NormalizedBar]]
) -> list[SignalInstance]:
    """L1 规则：收盘价创 lookback 日新高且成交量 > 前 lookback 日均量×1.2。

    纯函数：bars 须按日期升序。触发日当天生成实例（入场在其后一交易日，见回测）。
    """
    out: list[SignalInstance] = []
    lookback = definition.lookback_days
    vol_mult = Decimal("1.2")
    for code, bars in bars_by_code.items():
        if len(bars) <= lookback:
            continue
        for i in range(lookback, len(bars)):
            window = bars[i - lookback : i]
            prior_high = max(b.high for b in window)
            prior_avg_vol = sum((b.volume for b in window), Decimal(0)) / Decimal(lookback)
            bar = bars[i]
            if bar.close > prior_high and bar.volume > prior_avg_vol * vol_mult:
                out.append(
                    SignalInstance(
                        signal_id=definition.signal_id, code=code, trigger_date=bar.business_date
                    )
                )
    return out


# —— 回测引擎：前向收益（次开入场、horizon 日收盘出场、双边成本）——


def backtest(
    definition: SignalDefinition,
    instances: Sequence[SignalInstance],
    bars_by_code: Mapping[str, Sequence[NormalizedBar]],
) -> list[SignalOutcome]:
    """对每个信号实例求前向净收益：触发次日开盘入场，自入场起持有 horizon 个交易日后收盘出场。"""
    horizon = definition.horizon_days
    cost = definition.cost_bps / Decimal("10000") * Decimal(2)  # 双边
    out: list[SignalOutcome] = []
    for inst in instances:
        bars = bars_by_code.get(inst.code, ())
        idx = next(
            (i for i, b in enumerate(bars) if b.business_date == inst.trigger_date), None
        )
        # 入场在触发次日（idx+1）、出场在 idx+1+horizon，均须存在
        if idx is None or idx + 1 + horizon >= len(bars):
            continue
        entry_i, exit_i = idx + 1, idx + 1 + horizon
        entry, exit_bar = bars[entry_i], bars[exit_i]
        if entry.open <= 0:
            continue
        gross = (exit_bar.close - entry.open) / entry.open
        net = gross - cost
        out.append(
            SignalOutcome(
                instance=inst, entry_date=entry.business_date, exit_date=exit_bar.business_date,
                entry_price=entry.open, exit_price=exit_bar.close,
                gross_return=gross, cost=cost, net_return=net, win=net > 0,
            )
        )
    return out


# —— 统计汇总（Wilson 区间在此产生，p 唯一合法来源）——


def summarize(outcomes: Sequence[SignalOutcome], signal_id: str) -> BacktestStats:
    """胜/负统计 + 平均盈亏 + Wilson 区间。无胜负样本时抛 ValueError（调用方保证口径）。"""
    if not outcomes:
        raise ValueError("summarize: 无样本")
    wins = [o.net_return for o in outcomes if o.win]
    losses = [-o.net_return for o in outcomes if not o.win]
    if not wins or not losses:
        # 全胜或全负：b 无法估计，交由上层标记（此处给退化值并保持结构完整）
        avg_win = wins[0] if wins else Decimal(0)
        avg_loss = losses[0] if losses else Decimal(0)
    else:
        avg_win = sum(wins, Decimal(0)) / Decimal(len(wins))
        avg_loss = sum(losses, Decimal(0)) / Decimal(len(losses))
    b = (avg_win / avg_loss) if avg_loss > 0 else Decimal(0)
    p_low, p_mid, p_high = wilson_interval(len(wins), len(outcomes))
    return BacktestStats(
        signal_id=signal_id,
        n_total=len(outcomes), n_win=len(wins), n_loss=len(losses),
        avg_win=avg_win, avg_loss=avg_loss, b=b,
        p_low=p_low, p_mid=p_mid, p_high=p_high,
        avg_cost=sum((o.cost for o in outcomes), Decimal(0)) / Decimal(len(outcomes)),
    )


# —— n_eff：重叠信号聚类衰减（TECH §9.3：相邻日期同一信号重复计入问题）——


def cluster_decay(
    instances: Sequence[SignalInstance], horizon_days: int
) -> tuple[int, list[ClusterDecay]]:
    """按标的把触发日间隔 < horizon 的实例聚为一簇，每簇计 1 个有效样本。

    返回 (n_eff, 每标的衰减明细)。跨标的样本天然独立（横截面并集），不做衰减。
    """
    by_code: dict[str, list[Date]] = {}
    for inst in instances:
        by_code.setdefault(inst.code, []).append(inst.trigger_date)
    n_eff = 0
    details: list[ClusterDecay] = []
    for code in sorted(by_code):
        dates = sorted(by_code[code])
        sizes: list[int] = []
        run = 1
        for prev, cur in zip(dates, dates[1:]):
            if (cur - prev).days < horizon_days:
                run += 1
            else:
                sizes.append(run)
                run = 1
        sizes.append(run)
        n_eff += len(sizes)
        details.append(
            ClusterDecay(code=code, n_instances=len(dates), n_clusters=len(sizes), cluster_sizes=tuple(sizes))
        )
    return n_eff, details


# —— 样本内/样本外切分（时间切分，禁止随机打乱）——


@dataclass(frozen=True)
class SplitResult:
    in_sample: tuple[SignalOutcome, ...]
    out_of_sample: tuple[SignalOutcome, ...]
    cutoff_date: Date

    @property
    def split_ratio_in(self) -> Decimal:
        n = len(self.in_sample) + len(self.out_of_sample)
        return Decimal(len(self.in_sample)) / Decimal(n) if n else Decimal(0)


def split_chronological(
    outcomes: Sequence[SignalOutcome], cutoff: Date
) -> SplitResult:
    """按出场时间切分：exit_date < cutoff 入样本内，否则样本外。

    以出场日（而非触发日）为准，保证样本外窗口的前向收益完整落在窗口内。
    """
    ins = tuple(o for o in outcomes if o.exit_date < cutoff)
    oos = tuple(o for o in outcomes if o.exit_date >= cutoff)
    return SplitResult(in_sample=ins, out_of_sample=oos, cutoff_date=cutoff)
