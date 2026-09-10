"""Advice 记录查询 schemas（3_API §3.9：GET /advice 列表/详情/评价）。

与 `service.advice_to_payload`（盘中实时形态）字段同义；记录形态额外携带
评价回填（FR-REV-003）与 created_at。历史记录不携带触发/失效条件文本
（未持久化列，避免伪造——失效语义由 expires_at 表达）。
"""

from pydantic import BaseModel, Field


class AdviceTrailStepOut(BaseModel):
    kind: str
    note: str
    before: str | None = None
    after: str | None = None


class AdviceEvaluationOut(BaseModel):
    """评价回填（评价前 verdict=None；口径见 evaluation.py spec_version）。"""

    verdict: str | None = None
    evaluated_at: str | None = None
    spec_version: str | None = None
    reasons: list[str] = Field(default_factory=list)
    direction_return: str | None = None
    horizon: int | None = None


class AdviceRecordOut(BaseModel):
    advice_id: str
    signal_id: str
    code: str
    action: str
    state: str
    valid_from: str
    expires_at: str
    actionable: bool
    invalidated: bool = False
    f_min: str | None = None
    f_max: str | None = None
    value_min: str | None = None
    value_max: str | None = None
    suggested_lots: int | None = None
    reasons: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    trail: list[AdviceTrailStepOut] = Field(default_factory=list)
    model_explanation: str | None = None
    verdict: str | None = None
    evaluated_at: str | None = None
    evaluation: AdviceEvaluationOut | None = None
    created_at: str


class AdviceRecordListResponse(BaseModel):
    items: list[AdviceRecordOut]
    next_cursor: str | None = None
    has_more: bool = False
