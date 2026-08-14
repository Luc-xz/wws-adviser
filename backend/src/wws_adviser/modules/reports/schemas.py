"""Reports DTO。"""

from typing import Any

from pydantic import BaseModel


class ReportOut(BaseModel):
    id: str
    report_type: str
    business_date: str
    status: str
    version: int
    sources_count: int
    schema_version: str
    risk_ruleset_version: str
    generated_at: str
    analysis_snapshot_id: str
    manifest_path: str | None = None
    content_json_path: str | None = None
    content_md_path: str | None = None


class ReportDetail(ReportOut):
    content: dict[str, Any] | None = None
    degradation_flags: list[str] = []


class ReportListResponse(BaseModel):
    items: list[ReportOut]


class GenerateRequest(BaseModel):
    report_type: str  # pre_market | post_market
    business_date: str | None = None  # 缺省=当日（Asia/Shanghai）


class GenerateResponse(BaseModel):
    job_run_id: str
    report: ReportDetail | None = None
    skipped: bool = False
    skip_reason: str | None = None


class JobOut(BaseModel):
    id: str
    job_type: str
    business_date: str
    status: str
    attempt: int
    progress: int | None = None
    error_code: str | None = None
    result_ref: str | None = None
