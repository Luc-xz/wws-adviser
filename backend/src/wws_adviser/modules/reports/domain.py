"""Reports 领域：报告类型/状态机、版本常量、markdown 渲染。纯领域，禁框架 import。"""

from enum import StrEnum
from typing import Any

SCHEMA_VERSION = "1"
RISK_RULESET_VERSION = "v1"
PORTFOLIO_VERSION = "MWAC_v1"
SIGNALS_VERSION = "phase2_pending"
CALENDAR_VERSION = "v1"
PROMPT_VERSION = "wave6_pending"


class ReportType(StrEnum):
    PRE_MARKET = "pre_market"
    POST_MARKET = "post_market"


class ReportStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    RENDERED = "RENDERED"


# 合法状态转换（6_MODEL §6）：COMPLETED → RENDERED（渲染成功）；渲染失败不回滚。
_TRANSITIONS: dict[ReportStatus, frozenset[ReportStatus]] = {
    ReportStatus.PENDING: frozenset({ReportStatus.RUNNING, ReportStatus.FAILED}),
    ReportStatus.RUNNING: frozenset(
        {ReportStatus.COMPLETED, ReportStatus.PARTIAL, ReportStatus.FAILED}
    ),
    ReportStatus.COMPLETED: frozenset({ReportStatus.RENDERED}),
    ReportStatus.PARTIAL: frozenset({ReportStatus.RENDERED, ReportStatus.FAILED}),
}


def can_transition(src: ReportStatus, dst: ReportStatus) -> bool:
    return dst in _TRANSITIONS.get(src, frozenset())


def render_markdown(report: dict[str, Any]) -> str:
    """report.json → report.md（确定性纯渲染，无模板引擎）。"""
    head = report.get("header", {})
    lines: list[str] = []
    rt = str(head.get("report_type", ""))
    title = "开市前报告" if rt == "pre_market" else "收市后复盘"
    lines.append(f"# {title} {head.get('business_date', '')}")
    lines.append("")
    lines.append("## 版本与引用")
    lines.append(f"- schema_version: {head.get('schema_version')}")
    lines.append(f"- portfolio_version: {head.get('portfolio_version')}")
    lines.append(f"- risk_ruleset_version: {head.get('risk_ruleset_version')}")
    lines.append(f"- trade_cutoff_at: {head.get('trade_cutoff_at') or '-'}")
    lines.append(f"- frozen_at: {head.get('frozen_at')}")
    flags = head.get("degradation_flags") or []
    if flags:
        lines.append("")
        lines.append(f"> ⚠ 降级标记: {', '.join(flags)}（本报告标记为不完整 PARTIAL）")

    summary = report.get("summary", {})
    lines.append("")
    lines.append("## 组合摘要")
    lines.append(f"- 总资产: {summary.get('total_assets')}")
    lines.append(f"- 现金比例: {summary.get('cash_ratio')}")
    lines.append(f"- 累计盈亏: {summary.get('pnl_total')}")
    if summary.get("note"):
        lines.append(f"- 备注: {summary.get('note')}")

    positions = report.get("positions", [])
    if positions:
        lines.append("")
        lines.append("## 持仓")
        lines.append("| 代码 | 名称 | 数量 | 均价 | 市值 | 权重 | 新鲜度 |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- |")
        for p in positions:
            lines.append(
                f"| {p.get('code')} | {p.get('name')} | {p.get('quantity')} "
                f"| {p.get('avg_cost')} | {p.get('market_value') or '-'} "
                f"| {p.get('weight') or '-'} | {p.get('freshness')} |"
            )

    risk = report.get("risk", [])
    lines.append("")
    lines.append("## 风险")
    if risk:
        for b in risk:
            code_suffix = f"（{b['code']}）" if b.get("code") else ""
            lines.append(
                f"- [{b.get('level')}] {b.get('rule')}: 实际 {b.get('actual')} "
                f"上限 {b.get('limit')}{code_suffix}"
            )
    else:
        lines.append("- 未触发风险限制")

    attr = report.get("attribution", {})
    by_industry = attr.get("by_industry", [])
    if by_industry:
        lines.append("")
        lines.append("## 行业贡献")
        for row in by_industry:
            lines.append(
                f"- {row.get('industry')}: 市值 {row.get('market_value')}，"
                f"未实现盈亏 {row.get('unrealized_pnl')}"
            )
    return "\n".join(lines) + "\n"
