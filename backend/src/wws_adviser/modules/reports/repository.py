"""Reports 仓储：冻结快照（幂等不可变）、报告行、来源清单。"""

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from wws_adviser.modules.reports.models import AnalysisSnapshot, Report, ReportEvidence


def freeze_snapshot(db: DBSession, snapshot: AnalysisSnapshot) -> AnalysisSnapshot:
    """冻结快照：同 (account, business_date, purpose) 已存在 → 返回既有行（不可变，不覆盖）。

    重复生成报告（含 PARTIAL → 新版本）复用同一冻结，保证同日同目的可复现。
    """
    existing = db.scalar(
        select(AnalysisSnapshot).where(
            AnalysisSnapshot.account_id == snapshot.account_id,
            AnalysisSnapshot.business_date == snapshot.business_date,
            AnalysisSnapshot.snapshot_purpose == snapshot.snapshot_purpose,
        )
    )
    if existing is not None:
        return existing
    db.add(snapshot)
    db.flush()
    return snapshot


def get_snapshot(
    db: DBSession, account_id: str, business_date: str, purpose: str
) -> AnalysisSnapshot | None:
    return db.scalar(
        select(AnalysisSnapshot).where(
            AnalysisSnapshot.account_id == account_id,
            AnalysisSnapshot.business_date == business_date,
            AnalysisSnapshot.snapshot_purpose == purpose,
        )
    )


def insert_report(db: DBSession, report: Report) -> Report:
    db.add(report)
    db.flush()
    return report


def get_report(db: DBSession, report_id: str) -> Report | None:
    return db.get(Report, report_id)


def list_reports(
    db: DBSession,
    *,
    report_type: str | None = None,
    business_date: str | None = None,
    limit: int = 50,
) -> list[Report]:
    stmt = select(Report)
    if report_type is not None:
        stmt = stmt.where(Report.report_type == report_type)
    if business_date is not None:
        stmt = stmt.where(Report.business_date == business_date)
    stmt = stmt.order_by(Report.business_date.desc(), Report.version.desc()).limit(limit)
    return list(db.scalars(stmt))


def get_latest_version(db: DBSession, report_type: str, business_date: str) -> int:
    """该 (type, date) 已有的最大报告版本；无则 0（下一版从 1 起）。"""
    v = db.scalar(
        select(Report.version)
        .where(Report.report_type == report_type, Report.business_date == business_date)
        .order_by(Report.version.desc())
        .limit(1)
    )
    return int(v or 0)


def add_report_evidence(db: DBSession, ev: ReportEvidence) -> None:
    db.add(ev)
    db.flush()


def list_report_evidence(db: DBSession, report_id: str) -> list[ReportEvidence]:
    return list(
        db.scalars(select(ReportEvidence).where(ReportEvidence.report_id == report_id))
    )
