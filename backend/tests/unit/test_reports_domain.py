"""Reports 领域纯函数测试：状态机 + render_markdown（无 DB）。"""

import pytest

from wws_adviser.modules.reports.domain import (
    ReportStatus,
    ReportType,
    can_transition,
    render_markdown,
)


@pytest.mark.parametrize(
    "src,dst,expected",
    [
        (ReportStatus.PENDING, ReportStatus.RUNNING, True),
        (ReportStatus.RUNNING, ReportStatus.COMPLETED, True),
        (ReportStatus.RUNNING, ReportStatus.PARTIAL, True),
        (ReportStatus.RUNNING, ReportStatus.FAILED, True),
        (ReportStatus.COMPLETED, ReportStatus.RENDERED, True),
        (ReportStatus.PENDING, ReportStatus.COMPLETED, False),  # 未跑不能直接完成
        (ReportStatus.RENDERED, ReportStatus.RUNNING, False),  # 终态不可逆
        (ReportStatus.FAILED, ReportStatus.RENDERED, False),
    ],
)
def test_report_status_transitions(src, dst, expected) -> None:
    assert can_transition(src, dst) is expected


def test_report_type_values() -> None:
    assert ReportType.PRE_MARKET.value == "pre_market"
    assert ReportType.POST_MARKET.value == "post_market"


def test_render_markdown_complete_report() -> None:
    md = render_markdown(
        {
            "header": {
                "report_type": "pre_market",
                "business_date": "2026-08-14",
                "schema_version": "1",
                "portfolio_version": "MWAC_v1",
                "risk_ruleset_version": "v1",
                "trade_cutoff_at": "2026-08-13",
                "frozen_at": "2026-08-14T00:30:00+00:00",
                "degradation_flags": [],
            },
            "summary": {"total_assets": "100000", "cash_ratio": "0.4", "pnl_total": "150"},
            "positions": [
                {
                    "code": "600519",
                    "name": "贵州茅台",
                    "quantity": "100",
                    "avg_cost": "1000",
                    "market_value": "1200",
                    "weight": "0.012",
                    "freshness": "2026-08-13",
                }
            ],
            "risk": [
                {
                    "rule": "single_cap",
                    "level": "hard",
                    "actual": "0.5",
                    "limit": "0.3",
                    "code": "600519",
                }
            ],
            "attribution": {
                "by_industry": [
                    {"industry": "白酒", "market_value": "1200", "unrealized_pnl": "200"}
                ]
            },
        }
    )
    assert "# 开市前报告 2026-08-14" in md
    assert "schema_version: 1" in md
    assert "600519" in md
    assert "single_cap" in md
    assert "白酒" in md
    assert "降级" not in md


def test_render_markdown_degraded_report_shows_flags() -> None:
    md = render_markdown(
        {
            "header": {
                "report_type": "post_market",
                "business_date": "2026-08-14",
                "schema_version": "1",
                "portfolio_version": "MWAC_v1",
                "risk_ruleset_version": "v1",
                "frozen_at": "t",
                "degradation_flags": ["market_data_missing", "documents_unavailable"],
            },
            "summary": {"total_assets": "0", "cash_ratio": "1", "pnl_total": "0"},
            "positions": [],
            "risk": [],
            "attribution": {"by_industry": []},
        }
    )
    assert "收市后复盘" in md
    assert "market_data_missing" in md
    assert "documents_unavailable" in md
    assert "PARTIAL" in md
