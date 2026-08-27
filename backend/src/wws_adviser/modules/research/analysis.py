"""确定性分析：财务指标表 + 可比公司 + 估值情景（Phase 3 波3，FR-RES-002）。

纯函数模块（禁框架 import），输入为市场数据/财务数据的原始值，
输出结构化指标表和情景计算结果。模型只做解读，不得覆盖这些数字。
"""

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

# —— 指标表 ——


@dataclass(frozen=True)
class MetricRow:
    """单个财务/经营指标行。"""

    name: str                          # 指标名（中文）
    value: Decimal | None              # 当前值（None = 数据不足）
    unit: str                          # "亿元" / "%" / "倍"
    prior_year: Decimal | None = None  # 上年同期
    yoy_change: Decimal | None = None  # 同比变化（自动计算或显式传入）
    source: str = "deterministic"      # 来源标记


def compute_yoy(current: Decimal | None, prior: Decimal | None) -> Decimal | None:
    """同比变化 = (current - prior) / |prior| × 100%。prior=0/None → None。量化 2 位。"""
    if current is None or prior is None or prior == 0:
        return None
    return ((current - prior) / abs(prior) * Decimal(100)).quantize(Decimal("0.01"))


def build_metric_table(
    raw_metrics: dict[str, dict[str, str | None]],
) -> list[MetricRow]:
    """原始指标字典 → 指标表（自动计算同比）。

    raw_metrics 格式：{"营业收入": {"value": "100.5", "prior": "85.2", "unit": "亿元"}, …}
    """
    rows: list[MetricRow] = []
    for name, m in raw_metrics.items():
        val = _to_dec(m.get("value"))
        prior = _to_dec(m.get("prior"))
        yoy = compute_yoy(val, prior)
        rows.append(MetricRow(
            name=name, value=val,
            unit=str(m.get("unit", "")),
            prior_year=prior, yoy_change=yoy,
        ))
    return rows


def _to_dec(v: Any) -> Decimal | None:
    if v is None or v == "":
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return None


# —— 可比公司表 ——


@dataclass(frozen=True)
class ComparableRow:
    """可比公司一行。"""

    code: str
    name: str
    metric_name: str
    subject_value: Decimal | None = None    # 研究标的值
    peer_values: dict[str, Decimal | None] = field(default_factory=dict)  # code → value
    median: Decimal | None = None           # 同业中位数
    percentile: Decimal | None = None       # 标的在同业的分位（0-100）


def build_comparable_table(
    metric_name: str,
    subject_code: str,
    subject_name: str,
    subject_value: Decimal | None,
    peers: list[tuple[str, str, Decimal | None]],  # (code, name, value)
) -> ComparableRow:
    """构建可比公司对比行（中位数 + 分位自动计算）。"""
    peer_dict = {c: v for c, n, v in peers}
    values = [v for v in peer_dict.values() if v is not None]
    median = _median(values) if values else None
    pct = _percentile(subject_value, values) if subject_value is not None and values else None
    return ComparableRow(
        code=subject_code, name=subject_name, metric_name=metric_name,
        subject_value=subject_value,
        peer_values=peer_dict,
        median=median, percentile=pct,
    )


def _median(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / Decimal(2)


def _percentile(value: Decimal, peers: list[Decimal]) -> Decimal | None:
    """value 在 peers 中的分位（0=最低，100=最高）。"""
    if not peers:
        return None
    below = sum(1 for p in peers if p < value)
    return (Decimal(below) / Decimal(len(peers)) * Decimal(100)).quantize(Decimal("0.01"))


# —— 估值情景 ——


@dataclass(frozen=True)
class ScenarioResult:
    """单个估值情景。"""

    name: str                          # "乐观" / "中性" / "悲观"
    assumption: str                     # 假设描述
    implied_value: Decimal | None      # 隐含估值（PE×E / PB×B 等）
    upside_pct: Decimal | None         # 相对当前价的上行/下行空间


@dataclass(frozen=True)
class ValuationScenarios:
    """估值情景分析结果集。"""

    current_price: Decimal | None
    method: str                        # "pe" | "pb" | "dcf_simplified"
    scenarios: list[ScenarioResult] = field(default_factory=list)


def build_valuation_scenarios(
    *,
    current_price: Decimal | None,
    method: str,
    base_metric: Decimal | None,       # 基准指标（如预测 EPS / BVPS）
    bull_multiple: Decimal | None,     # 乐观倍数
    base_multiple: Decimal | None,     # 中性倍数
    bear_multiple: Decimal | None,     # 悲观倍数
) -> ValuationScenarios:
    """构建三档估值情景（PE/PB 法简化版）。

    implied_value = multiple × base_metric
    upside_pct = (implied_value - current_price) / current_price × 100
    """
    mults = [
        ("乐观", "乐观情景假设", bull_multiple),
        ("中性", "中性情景假设", base_multiple),
        ("悲观", "悲观情景假设", bear_multiple),
    ]
    scenarios: list[ScenarioResult] = []
    for name, desc, mult in mults:
        implied = None
        upside = None
        if mult is not None and base_metric is not None:
            implied = mult * base_metric
            if current_price is not None and current_price > 0:
                upside = (implied - current_price) / current_price * Decimal(100)
        scenarios.append(ScenarioResult(
            name=name, assumption=desc,
            implied_value=implied, upside_pct=upside,
        ))
    return ValuationScenarios(
        current_price=current_price, method=method, scenarios=scenarios,
    )


# —— 历史分位 ——


def historical_percentile(
    current: Decimal | None,
    history: list[Decimal],
) -> Decimal | None:
    """当前值在历史序列中的分位（0=历史最低，100=最高）。"""
    if current is None or not history:
        return None
    below = sum(1 for h in history if h < current)
    return (Decimal(below) / Decimal(len(history)) * Decimal(100)).quantize(Decimal("0.01"))
