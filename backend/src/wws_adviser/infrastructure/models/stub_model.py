"""StubModelPort：返回预设结构化输出 + 审计（source="stub"），禁生产。"""

from wws_adviser.core.time import now_utc_iso
from wws_adviser.infrastructure import assert_not_prod
from wws_adviser.ports.model import ModelAudit, ModelRequest, ModelResponse


class StubModelPort:
    def __init__(self, *, env: str = "dev") -> None:
        assert_not_prod(env)

    async def call(self, request: ModelRequest) -> ModelResponse:
        now = now_utc_iso()
        audit = ModelAudit(
            task_type=request.task_type,
            model_profile_id=request.model_profile_id,
            prompt_template_name=request.prompt_template_name,
            prompt_template_version=request.prompt_template_version,
            prompt_hash="stub:" + request.prompt_template_name,
            input_evidence_ids=list(request.evidence_ids),
            started_at=now,
            ended_at=now,
            status="ok",
        )
        content = _stub_content(request)
        return ModelResponse(content=content, audit=audit)


def _stub_content(request: ModelRequest) -> dict:
    """研究类任务返回 sections 结构（引用输入白名单前两条）；其余返回 summary。"""
    if request.task_type.value.startswith("research_"):
        plan = request.structured_context.get("section_plan", [])
        ev = [e["evidence_id"] for e in request.structured_context.get("evidence", [])]
        return {
            "sections": [
                {
                    "section_type": p.get("section_type"),
                    "title": p.get("title", p.get("section_type")),
                    "content": f"（stub）{p.get('title')}：基于证据的段落内容。",
                    "evidence_ids": ev[:2] if p.get("require_citations") else [],
                }
                for p in plan
            ]
        }
    return {"summary": "stub model output"}
