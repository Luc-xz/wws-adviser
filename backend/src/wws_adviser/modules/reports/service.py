"""Reports 服务：开市前/收市后报告流水线（波5，6_MODEL §6）。

流程：freeze（输入引用冻结，不可变）→ 确定性计算（波4 analytics）→ 降级判定 →
原子写文件（report.json/md/manifest）→ 落 reports + 来源清单 → commit → 渲染 → RENDERED。
状态以 SQLite 为准；PARTIAL 补算出新版本、旧版保留。
"""

import json
import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from sqlalchemy.orm import Session as DBSession

from wws_adviser.core.config import Settings
from wws_adviser.core.errors import DomainError
from wws_adviser.core.ids import new_id
from wws_adviser.core.time import now_utc_iso
from wws_adviser.modules.analytics import service as analytics_service
from wws_adviser.modules.audit import service as audit_service
from wws_adviser.modules.documents import service as documents_service
from wws_adviser.modules.market_data import repository as md_repository
from wws_adviser.modules.portfolio import service as portfolio_service
from wws_adviser.modules.reports import repository
from wws_adviser.modules.reports.domain import (
    CALENDAR_VERSION,
    PORTFOLIO_VERSION,
    PROMPT_VERSION,
    RISK_RULESET_VERSION,
    SCHEMA_VERSION,
    SIGNALS_VERSION,
    ReportStatus,
    ReportType,
    render_markdown,
)
from wws_adviser.modules.reports.models import AnalysisSnapshot, Report, ReportEvidence


class NotTradingDayError(DomainError):
    code = "CONFLICT"
    status = 409
    title = "非交易日"


@dataclass(frozen=True)
class GenerateResult:
    report: Report
    degradation_flags: list[str]


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def _dec(v: Decimal | None) -> str | None:
    return format(v, "f") if v is not None else None


def freeze_snapshot(
    db: DBSession,
    *,
    account_id: str,
    report_type: ReportType,
    business_date: str,
) -> AnalysisSnapshot:
    """冻结报告输入引用：交易截止、行情 refs、新鲜度、证据截止、各版本。幂等不可变。"""
    existing = repository.get_snapshot(db, account_id, business_date, report_type.value)
    if existing is not None:
        return existing

    txns = portfolio_service.list_transactions(
        db, user_id=_account_user_id(db, account_id), limit=100000
    )
    trade_cutoff = max((t.trade_at for t in txns.rows), default=None)

    # 行情 refs + 新鲜度：各持仓标的的最新日线/净值记录 id 与 business_date
    record_refs: list[dict[str, str]] = []
    freshness: dict[str, str] = {}
    state = portfolio_service.get_position_state(db, account_id)
    for inst_id in state.positions:
        rec = md_repository.latest_market_record_any_source(db, inst_id)
        if rec is not None:
            record_refs.append(
                {"instrument_id": inst_id, "business_date": rec.business_date, "source": rec.source}
            )
            freshness[inst_id] = rec.business_date
        else:
            freshness[inst_id] = "missing"

    now = now_utc_iso()
    snap = AnalysisSnapshot(
        id=new_id(),
        account_id=account_id,
        business_date=business_date,
        snapshot_purpose=report_type.value,
        frozen_at=now,
        portfolio_version=PORTFOLIO_VERSION,
        trade_cutoff_at=trade_cutoff,
        market_record_refs_json=json.dumps(record_refs, ensure_ascii=False),
        freshness_refs_json=json.dumps(freshness, ensure_ascii=False),
        evidence_cutoff_at=business_date,
        risk_ruleset_version=RISK_RULESET_VERSION,
        signals_version=SIGNALS_VERSION,
        calendar_version=CALENDAR_VERSION,
        anomalies_json=None,
        degradation_flags_json=None,
        created_at=now,
        updated_at=now,
        version=1,
    )
    return repository.freeze_snapshot(db, snap)


def _account_user_id(db: DBSession, account_id: str) -> str:
    account = portfolio_service.get_account_by_id(db, account_id)
    if account is None:
        raise DomainError("账户不存在")
    return account.user_id


def generate_report(
    db: DBSession,
    *,
    settings: Settings,
    data_dir: Path,
    user_id: str,
    report_type: ReportType,
    business_date: str,
    job_run_id: str | None = None,
    manual: bool = False,
) -> GenerateResult:
    """生成一份报告（同 type+date 幂等：已有同版报告则直接返回）。"""
    account = portfolio_service.get_user_account(db, user_id)

    # 交易日校验：非交易日自动生成拒绝（手动触发放行，FR-REP-003）
    if not manual:
        cal = md_repository.get_calendar(db, business_date)
        if cal is not None and not cal.is_trading_day:
            raise NotTradingDayError(f"{business_date} 非交易日，跳过自动生成")

    # 幂等：最新版本报告若已为终态（RENDERED/COMPLETED/PARTIAL）→ 生成新版本（PARTIAL 补算）；
    # 若数据齐备且最新版已是 RENDERED → 直接返回既有报告（不重复生成）
    latest = _latest_final_report(db, report_type, business_date)
    if latest is not None and latest.status == ReportStatus.RENDERED.value:
        return GenerateResult(report=latest, degradation_flags=[])

    snap = freeze_snapshot(
        db, account_id=account.id, report_type=report_type, business_date=business_date
    )

    # —— 确定性计算（波4 analytics；引用已冻结，可复现）——
    valuation = analytics_service.valuate(db, user_id)
    summary = analytics_service.summary(db, user_id)
    risk = analytics_service.risk(db, user_id, settings)
    attribution = analytics_service.attribution(db, user_id)

    # —— 降级判定（AC-02/AC-04）——
    flags: list[str] = []
    held = [p for p in valuation.positions if p.quantity > 0]
    if any(p.freshness == "missing" for p in held):
        flags.append("market_data_missing")
    held_ids = [p.instrument_id for p in held]
    docs_for_holdings = (
        [
            d
            for d in documents_service.list_documents(db, limit=200)
            if _doc_linked_to_any(db, d.id, held_ids)
        ]
        if held_ids
        else []
    )
    if not docs_for_holdings:
        flags.append("documents_unavailable")

    status = ReportStatus.PARTIAL if flags else ReportStatus.COMPLETED

    # —— 组装 report.json ——
    report_id = new_id()
    version = repository.get_latest_version(db, report_type.value, business_date) + 1
    report_json = {
        "header": {
            "report_id": report_id,
            "report_type": report_type.value,
            "business_date": business_date,
            "schema_version": SCHEMA_VERSION,
            "prompt_version": PROMPT_VERSION,
            "portfolio_version": PORTFOLIO_VERSION,
            "risk_ruleset_version": RISK_RULESET_VERSION,
            "signals_version": SIGNALS_VERSION,
            "calendar_version": CALENDAR_VERSION,
            "frozen_at": snap.frozen_at,
            "trade_cutoff_at": snap.trade_cutoff_at,
            "evidence_cutoff_at": snap.evidence_cutoff_at,
            "degradation_flags": flags,
        },
        "summary": {
            "total_assets": _dec(summary.total_assets),
            "cash": _dec(summary.cash),
            "cash_ratio": _dec(summary.cash_ratio),
            "pnl_total": _dec(summary.pnl_total),
            "concentration": _dec(summary.concentration),
            "note": summary.note,
        },
        "positions": [
            {
                "instrument_id": p.instrument_id,
                "code": p.code,
                "name": p.name,
                "quantity": _dec(p.quantity),
                "avg_cost": _dec(p.avg_cost),
                "market_value": _dec(p.market_value),
                "unrealized_pnl": _dec(p.unrealized_pnl),
                "realized_pnl": _dec(p.realized_pnl),
                "weight": _dec(p.weight),
                "freshness": p.freshness,
            }
            for p in held
        ],
        "risk": [
            {
                "rule": b.rule,
                "level": b.level,
                "actual": _dec(b.actual),
                "limit": _dec(b.limit),
                "code": b.code,
                "industry": b.industry,
            }
            for b in risk
        ],
        "attribution": {
            "by_industry": [
                {
                    "industry": r.industry,
                    "market_value": _dec(r.market_value),
                    "unrealized_pnl": _dec(r.unrealized_pnl),
                }
                for r in attribution.by_industry
            ],
            "cash": _dec(attribution.cash),
        },
    }
    markdown = render_markdown(report_json)

    # —— 原子写文件（data/reports/<date>/<report_id>/）——
    rel_dir = os.path.join("reports", business_date, report_id)
    abs_dir = data_dir / rel_dir
    json_rel = os.path.join(rel_dir, "report.json")
    md_rel = os.path.join(rel_dir, "report.md")
    manifest_rel = os.path.join(rel_dir, "manifest.json")
    _atomic_write(abs_dir / "report.json", json.dumps(report_json, ensure_ascii=False, indent=2))
    _atomic_write(abs_dir / "report.md", markdown)
    manifest = {
        "report_id": report_id,
        "report_type": report_type.value,
        "business_date": business_date,
        "version": version,
        "status": status.value,
        "schema_version": SCHEMA_VERSION,
        "files": ["report.json", "report.md"],
    }
    _atomic_write(abs_dir / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    # —— 落库（report.json + 来源清单 commit 后才置终态）——
    # 文件（json+md）已同步写成功：完整 → RENDERED；降级 → PARTIAL（渲染产物由 *_path 存在性表明）
    stored_status = ReportStatus.PARTIAL.value if flags else ReportStatus.RENDERED.value
    now = now_utc_iso()
    report = Report(
        id=report_id,
        report_type=report_type.value,
        business_date=business_date,
        status=stored_status,
        version=version,
        manifest_path=manifest_rel,
        content_json_path=json_rel,
        content_md_path=md_rel,
        analysis_snapshot_id=snap.id,
        sources_count=len(docs_for_holdings),
        schema_version=SCHEMA_VERSION,
        prompt_version=PROMPT_VERSION,
        risk_ruleset_version=RISK_RULESET_VERSION,
        generated_at=now,
        created_at=now,
        updated_at=now,
    )
    repository.insert_report(db, report)
    for d in docs_for_holdings:
        repository.add_report_evidence(
            db,
            ReportEvidence(
                id=new_id(), report_id=report_id, evidence_id=None, citation_ref=d.source_url
            ),
        )
    if flags:
        snap.degradation_flags_json = json.dumps(flags, ensure_ascii=False)
        snap.updated_at = now
        snap.version += 1
    audit_service.append_event(
        db,
        action="report_generated",
        target_type="report",
        target_id=report_id,
        after={"report_type": report_type.value, "status": status.value, "version": version},
        job_id=job_run_id,
    )
    db.commit()
    return GenerateResult(report=report, degradation_flags=flags)


def _latest_final_report(
    db: DBSession, report_type: ReportType, business_date: str
) -> Report | None:
    reports = repository.list_reports(
        db, report_type=report_type.value, business_date=business_date, limit=1
    )
    return reports[0] if reports else None


def _doc_linked_to_any(db: DBSession, document_id: str, instrument_ids: list[str]) -> bool:
    """文档是否关联到任一持仓标的（按 document_links）。"""
    from sqlalchemy import select as sa_select

    from wws_adviser.modules.documents.models import DocumentLink

    row = db.scalar(
        sa_select(DocumentLink.document_id).where(
            DocumentLink.document_id == document_id,
            DocumentLink.instrument_id.in_(instrument_ids),
        )
    )
    return row is not None


def get_report_content(data_dir: Path, report: Report) -> dict[str, object] | None:
    """读 report.json 内容（文件为权威渲染产物；读失败返回 None）。"""
    if not report.content_json_path:
        return None
    p = data_dir / report.content_json_path
    if not p.exists():
        return None
    content: dict[str, object] = json.loads(p.read_text(encoding="utf-8"))
    return content


def read_render(data_dir: Path, report: Report, fmt: str) -> str | None:
    if fmt == "md" and report.content_md_path:
        p = data_dir / report.content_md_path
        return p.read_text(encoding="utf-8") if p.exists() else None
    if fmt == "json" and report.content_json_path:
        p = data_dir / report.content_json_path
        return p.read_text(encoding="utf-8") if p.exists() else None
    return None
