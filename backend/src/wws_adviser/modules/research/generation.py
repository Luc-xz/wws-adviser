"""公司报告生成流水线（Phase 3 波4，FR-RES-002 / FR-RES-004）。

组装前三波的能力：
    证据检索（波2）→ 确定性分析（波3）→ 模型生成（model_gateway）→
    引用校验（波1 domain.validate_citations）→ 报告落盘（波1 service.save_report）

防线（FR-RES-004）：
    - fact 段落无引用 → 降级为 inference 并显式标注（不得写成确定事实）
    - 单源引用 → unverified_note 标注「未双源验证」
    - 模型 evidence_id 不在白名单 → 网关 BLOCKED → 任务失败（不产出报告）
"""

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session as DBSession

from wws_adviser.core.config import Settings
from wws_adviser.modules.model_gateway.service import ModelCallResult, call_model
from wws_adviser.modules.research import service as research_service
from wws_adviser.modules.research.analysis import (
    MetricRow,
    build_metric_table,
)
from wws_adviser.modules.research.domain import (
    Citation,
    ResearchSection,
    SectionType,
    validate_citations,
)
from wws_adviser.modules.research.evidence import EvidenceSlice, retrieve_evidence
from wws_adviser.modules.research.models import ResearchTask
from wws_adviser.ports.model import ModelPort, ModelTaskType

_logger = logging.getLogger(__name__)

# 模板版本（generation_config 快照的一部分，可复盘）
COMPANY_TEMPLATE_VERSION = "company-v1"


@dataclass(frozen=True)
class SectionSpec:
    """报告段落规格：类型 + 标题 + 认知层级 + 是否强制引用。"""

    section_type: SectionType
    title: str
    epistemic_type: str            # fact | inference | model_judgment
    require_citations: bool


# 公司报告段落计划（FR-RES-002 全集；quick 深度取子集）
COMPANY_SECTION_PLAN: tuple[SectionSpec, ...] = (
    SectionSpec(SectionType.OVERVIEW, "公司概览与商业模式", "fact", True),
    SectionSpec(SectionType.COMPETITIVE, "行业位置与竞争格局", "fact", True),
    SectionSpec(SectionType.FINANCIAL, "财务与经营指标", "fact", True),
    SectionSpec(SectionType.VALUATION, "估值分析", "inference", False),
    SectionSpec(SectionType.CATALYSTS, "催化剂", "inference", False),
    SectionSpec(SectionType.RISKS, "主要风险与反方观点", "inference", False),
    SectionSpec(SectionType.CONCLUSION, "结论与待验证假设", "model_judgment", False),
)

_QUICK_PLAN: tuple[SectionSpec, ...] = (
    COMPANY_SECTION_PLAN[0],   # overview
    COMPANY_SECTION_PLAN[3],   # valuation
    COMPANY_SECTION_PLAN[-1],  # conclusion
)


def plan_for_depth(depth: str) -> tuple[SectionSpec, ...]:
    """quick = 概览+估值+结论；standard/deep = 全量七段。"""
    if depth == "quick":
        return _QUICK_PLAN
    return COMPANY_SECTION_PLAN


@dataclass(frozen=True)
class DeterministicInputs:
    """确定性分析的可选输入（数据源接入前可为空，报告如实标注覆盖情况）。"""

    current_price: Decimal | None = None
    raw_metrics: dict[str, dict[str, str | None]] = field(default_factory=dict)


# —— 上下文组装 ——


def build_company_context(
    *,
    subject: str,
    plan: tuple[SectionSpec, ...],
    evidence: list[EvidenceSlice],
    metric_rows: list[MetricRow],
    current_price: Decimal | None,
    depth: str,
    time_span: str | None,
) -> dict[str, Any]:
    """证据 + 确定性数据 → 模型上下文（不包含用户持仓等私有数据）。"""
    return {
        "subject": subject,
        "depth": depth,
        "time_span": time_span,
        "section_plan": [
            {
                "section_type": s.section_type.value,
                "title": s.title,
                "epistemic_type": s.epistemic_type,
                "require_citations": s.require_citations,
            }
            for s in plan
        ],
        "evidence": [
            {
                "evidence_id": e.evidence_id,
                "title": e.title,
                "source": e.source,
                "trust_level": e.trust_level,
                "published_at": e.published_at,
                "slice_ref": e.slice_ref,
                "text": e.text,
            }
            for e in evidence
        ],
        "deterministic": {
            "current_price": str(current_price) if current_price is not None else None,
            "metrics": [
                {
                    "name": r.name, "value": str(r.value) if r.value is not None else None,
                    "unit": r.unit,
                    "prior_year": str(r.prior_year) if r.prior_year is not None else None,
                    "yoy_change": str(r.yoy_change) if r.yoy_change is not None else None,
                }
                for r in metric_rows
            ],
        },
    }


# —— 模型输出 → 报告段落 ——


def _locator_of(e: EvidenceSlice) -> str:
    """引用定位：标题#段落；有 URL 时附上（FR-RES-004 可定位）。"""
    loc = f"{e.title}#{e.slice_ref}"
    if e.source_url:
        loc += f"（{e.source_url}）"
    return loc


def sections_from_model(
    content: dict[str, Any],
    *,
    plan: tuple[SectionSpec, ...],
    evidence: list[EvidenceSlice],
) -> tuple[ResearchSection, ...]:
    """模型 JSON → ResearchSection 列表。

    - 按 section_type 对齐计划段落；计划段缺失 → ValueError（任务失败，不静默缺段）
    - fact 段无有效引用 → 降级 inference + 显式标注（不写成确定事实）
    - 同段引用 ≥2 个不同文档 → verified；单源 → unverified_note
    """
    by_type: dict[str, dict[str, Any]] = {}
    for sec in content.get("sections", []):
        if isinstance(sec, dict) and isinstance(sec.get("section_type"), str):
            by_type[sec["section_type"]] = sec

    ev_by_id = {e.evidence_id: e for e in evidence}
    sections: list[ResearchSection] = []
    for spec in plan:
        sec = by_type.get(spec.section_type.value)
        if sec is None:
            raise ValueError(f"模型输出缺少计划段落：{spec.section_type.value}")
        content_text = str(sec.get("content", "")).strip()
        if not content_text:
            raise ValueError(f"模型输出段落内容为空：{spec.section_type.value}")

        cited = [ev_by_id[i] for i in (sec.get("evidence_ids") or []) if i in ev_by_id]
        epistemic = spec.epistemic_type
        # 防线：事实段落无引用 → 降级为推断并显式标注
        if spec.epistemic_type == "fact" and not cited:
            epistemic = "inference"
            content_text += "\n\n（注：本段缺少引用支撑，已降级为推断，内容未经证实。）"

        distinct_docs = {c.document_id for c in cited}
        citations = tuple(
            Citation(
                evidence_id=c.evidence_id,
                section=spec.section_type,
                locator=_locator_of(c),
                content_hash=c.content_hash,
                verified=len(distinct_docs) >= 2,
                unverified_note=None if len(distinct_docs) >= 2 else "单源引用，未经双源验证",
            )
            for c in cited
        )
        det_data: dict[str, Any] = {}
        if spec.section_type is SectionType.FINANCIAL:
            det_data["metrics_provided"] = True  # 具体表由 assemble 阶段附加
        sections.append(ResearchSection(
            section_type=spec.section_type,
            title=str(sec.get("title") or spec.title),
            content=content_text,
            epistemic_type=epistemic,
            citations=citations,
            deterministic_data=det_data,
        ))
    return tuple(sections)


# —— Markdown 渲染 ——

_EPISTEMIC_LABEL = {"fact": "事实", "inference": "推断", "model_judgment": "模型判断"}


def _fmt(v: Decimal | None) -> str:
    return "—" if v is None else f"{v}"


def _metric_table_md(rows: list[MetricRow]) -> str:
    if not rows:
        return ""
    lines = ["| 指标 | 当前值 | 单位 | 上年同期 | 同比 |", "| --- | --- | --- | --- | --- |"]
    for r in rows:
        lines.append(
            f"| {r.name} | {_fmt(r.value)} | {r.unit} | {_fmt(r.prior_year)} | "
            f"{_fmt(r.yoy_change) if r.yoy_change is None else f'{r.yoy_change}%'} |"
        )
    return "\n".join(lines)


def assemble_report_md(
    *,
    subject: str,
    sections: tuple[ResearchSection, ...],
    metric_rows: list[MetricRow],
    current_price: Decimal | None,
    data_cutoff: str,
    generation_config: dict[str, Any],
) -> str:
    """段落 + 确定性表 → 完整 Markdown 报告。"""
    lines: list[str] = [f"# 公司研究报告：{subject}", ""]
    if current_price is not None:
        lines.append(f"- 当前价（确定性）：{current_price}")
    lines.append(f"- 数据截止：{data_cutoff}")
    lines.append(f"- 生成配置：depth={generation_config.get('depth')}，"
                 f"模板={generation_config.get('template_version')}")
    lines.append("")

    for s in sections:
        label = _EPISTEMIC_LABEL.get(s.epistemic_type, s.epistemic_type)
        lines.append(f"## {s.title}【{label}】")
        lines.append("")
        lines.append(s.content)
        lines.append("")
        if s.citations:
            for i, c in enumerate(s.citations, 1):
                mark = "已验证" if c.verified else (c.unverified_note or "未验证")
                lines.append(f"> 引用[{i}] {c.locator}（{mark}，hash={c.content_hash[:12]}…）")
            lines.append("")
        if s.section_type is SectionType.FINANCIAL:
            table = _metric_table_md(metric_rows)
            if table:
                lines.append("确定性指标表（模型不得修改）：")
                lines.append("")
                lines.append(table)
            else:
                lines.append("> 确定性财务数据未接入，本段数值未经确定性计算核验。")
            lines.append("")
    return "\n".join(lines)


# —— 流水线 ——


async def run_company_research(
    db: DBSession,
    settings: Settings,
    port: ModelPort,
    *,
    task: ResearchTask,
    data_dir,
    det_inputs: DeterministicInputs | None = None,
) -> str:
    """执行公司研究任务全流程。成功 → report_id；失败 → 抛异常（调用方 fail_task）。"""
    inputs = det_inputs or DeterministicInputs()
    plan = plan_for_depth(task.depth)
    subject_name = task.subject

    # 1) 证据检索（波2）
    result = retrieve_evidence(
        db, query=subject_name, instrument_code=task.subject, max_results=12,
    )
    research_service.update_progress(db, task, 20)
    if not result.slices:
        raise ValueError("insufficient_evidence：未检索到任何证据切片")
    evidence = result.slices
    evidence_ids = [e.evidence_id for e in evidence]

    # 2) 确定性分析（波3；数据源未接入时为空表，报告如实标注）
    metric_rows = build_metric_table(inputs.raw_metrics)
    research_service.update_progress(db, task, 40)

    # 3) 模型生成（model_gateway：白名单校验 + 受控修复 + 审计）
    context = build_company_context(
        subject=subject_name, plan=plan, evidence=evidence,
        metric_rows=metric_rows, current_price=inputs.current_price,
        depth=task.depth, time_span=task.time_span,
    )
    research_service.update_progress(db, task, 60)
    call: ModelCallResult = await call_model(
        db, settings, port,
        task_type=ModelTaskType.RESEARCH_COMPANY,
        job_run_id=None,
        context=context,
        deterministic_summary={},
        evidence_whitelist=evidence_ids,
    )
    research_service.update_progress(db, task, 80)
    if not call.ok or call.content is None:
        raise ValueError(f"model_failed:{call.error_code}")

    # 4) 引用校验（波1 domain：fact 段必引用 + 未验证须有说明）
    sections = sections_from_model(call.content, plan=plan, evidence=evidence)
    violations = validate_citations(list(sections))
    if violations:
        raise ValueError(f"citation_violation:{violations}")
    research_service.update_progress(db, task, 90)

    # 5) 渲染 + 保存（波1 service：原子写 + 落库）
    data_cutoff = evidence[0].published_at or "unknown"
    generation_config = {
        "template_version": COMPANY_TEMPLATE_VERSION,
        "prompt_version": call.prompt_version,
        "depth": task.depth,
        "time_span": task.time_span,
        "sections": [s.section_type.value for s in sections],
    }
    content_md = assemble_report_md(
        subject=subject_name, sections=sections, metric_rows=metric_rows,
        current_price=inputs.current_price,
        data_cutoff=data_cutoff, generation_config=generation_config,
    )
    citations_json = [
        {
            "evidence_id": c.evidence_id,
            "section": c.section.value,
            "locator": c.locator,
            "content_hash": c.content_hash,
            "verified": c.verified,
            "unverified_note": c.unverified_note,
        }
        for s in sections for c in s.citations
    ]
    report = research_service.save_report(
        db, task,
        data_dir=data_dir,
        content_md=content_md,
        citations_json=citations_json,
        generation_config=generation_config,
    )
    research_service.complete_task(db, task, report.id)
    return report.id
