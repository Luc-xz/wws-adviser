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
        return ModelResponse(content={"summary": "stub model output"}, audit=audit)
