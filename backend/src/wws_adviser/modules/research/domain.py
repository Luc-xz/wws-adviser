"""Research 领域：任务状态机 + 内容结构。纯函数，禁框架 import（TID251）。"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ResearchTaskType(StrEnum):
    COMPANY = "company"
    INDUSTRY = "industry"


class ResearchStatus(StrEnum):
    """研究任务状态机：PENDING → RUNNING → COMPLETED / FAILED / CANCELLED。

    - progress 0-100 由执行器更新（数据收集→确定性分析→模型生成→校验）
    - CANCELLED 仅在 RUNNING 前有效（开始后不可取消，等完成）
    """

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


_VALID_TRANSITIONS: dict[ResearchStatus, set[ResearchStatus]] = {
    ResearchStatus.PENDING: {ResearchStatus.RUNNING, ResearchStatus.CANCELLED},
    ResearchStatus.RUNNING: {ResearchStatus.COMPLETED, ResearchStatus.FAILED},
    ResearchStatus.COMPLETED: set(),
    ResearchStatus.FAILED: set(),
    ResearchStatus.CANCELLED: set(),
}


def transition(state: ResearchStatus, target: ResearchStatus) -> ResearchStatus:
    """非法转换抛 ValueError（状态机完整性）。"""
    if target not in _VALID_TRANSITIONS[state]:
        raise ValueError(f"非法研究任务状态转换：{state.value} → {target.value}")
    return target


class SectionType(StrEnum):
    """研究报告段落类型（事实/推断/模型判断显式区分，FR-RES-002）。"""

    OVERVIEW = "overview"              # 公司概览/行业定义
    COMPETITIVE = "competitive"        # 竞争格局
    FINANCIAL = "financial"            # 财务指标（确定性计算）
    VALUATION = "valuation"            # 估值（历史分位/可比/情景/DCF）
    CATALYSTS = "catalysts"            # 催化剂
    RISKS = "risks"                    # 风险与反方观点
    CONCLUSION = "conclusion"          # 结论与待验证假设


@dataclass(frozen=True)
class Citation:
    """引用条目（FR-RES-004：可定位到文档或网页，必要时含页码/章节）。"""

    evidence_id: str
    section: SectionType
    locator: str                       # "p.12 §3.2" / "公告标题#段落" / URL
    content_hash: str                  # 来源内容哈希（可复盘）
    verified: bool = False             # 双源验证标记
    unverified_note: str | None = None # 未证实信息说明


@dataclass(frozen=True)
class ResearchSection:
    """报告的一个段落。fact/inference/model_judgment 显式区分。"""

    section_type: SectionType
    title: str
    content: str                       # 模型生成的文本
    epistemic_type: str                # "fact" | "inference" | "model_judgment"
    citations: tuple[Citation, ...] = field(default_factory=tuple)
    deterministic_data: dict[str, Any] = field(default_factory=dict)  # 确定性计算结果


@dataclass(frozen=True)
class ResearchReportContent:
    """研究报告完整结构。"""

    subject: str
    report_type: str                    # company | industry
    sections: tuple[ResearchSection, ...]
    data_cutoff: str                    # 数据截止时间
    generation_config: dict[str, Any]   # 模板版本/模型/参数
    version_refs: dict[str, str]        # 各组件版本（组合算法/风险规则等）


def validate_citations(sections: list[ResearchSection]) -> list[str]:
    """校验引用完整性（FR-RES-004）。

    - fact 类型段落必须有至少一个引用
    - 未验证的引用须有 unverified_note
    - 返回违规项列表（空 = 全通过）。
    """
    violations: list[str] = []
    for s in sections:
        if s.epistemic_type == "fact" and not s.citations:
            violations.append(
                f"事实段落「{s.title}」缺少引用"
            )
        for c in s.citations:
            if not c.verified and not c.unverified_note:
                violations.append(
                    f"引用 {c.evidence_id[:12]}… 未双源验证且缺少 unverified_note"
                )
    return violations
