"""模型端口（结构化调用 + 审计回调）。Model Gateway 对外只暴露 ModelPort。

call 方法名取自文档伪代码 `model_gateway.call(ModelRequest(...))`（6_MODEL §3）。
响应携带结构化输出 content 与 audit（对齐 model_calls 列，6_MODEL §3.1 步骤 6）。
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol


class ModelTaskType(StrEnum):
    INTRADAY = "intraday"
    PRE_MARKET = "pre_market"
    POST_MARKET = "post_market"
    RESEARCH_COMPANY = "research_company"
    RESEARCH_INDUSTRY = "research_industry"
    DOC_EXTRACT = "doc_extract"


@dataclass(frozen=True)
class ModelRequest:
    task_type: ModelTaskType
    model_profile_id: str
    prompt_template_name: str
    prompt_template_version: str
    structured_context: dict[str, Any]
    evidence_ids: list[str] = field(default_factory=list)
    response_schema: dict[str, Any] = field(default_factory=dict)
    timeout: float = 30.0
    max_tokens: int = 2048
    budget: float = 0.0


@dataclass(frozen=True)
class ModelAudit:
    task_type: ModelTaskType
    model_profile_id: str
    prompt_template_name: str
    prompt_template_version: str
    prompt_hash: str
    input_evidence_ids: list[str] = field(default_factory=list)
    started_at: str = ""
    ended_at: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    estimated_cost: float = 0.0
    status: str = "ok"
    error_code: str | None = None


@dataclass(frozen=True)
class ModelResponse:
    content: dict[str, Any]
    audit: ModelAudit


class ModelPort(Protocol):
    async def call(self, request: ModelRequest) -> ModelResponse: ...
