"""Model Gateway 服务：路由 + key 解析 + 调用 + 一次受控修复 + 后置校验 + 审计。

绝不把模型异常抛给调用方：任何失败 → ModelCallResult(ok=False, error_code)（MODEL_UNAVAILABLE
降级，AC-06）。key 经 env 引用解析，绝不落日志/审计/报告。事务边界：调用方须保证调用时
无打开写事务（6_MODEL §3.2）；审计行由本服务在自己的事务里提交。
"""

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session as DBSession

from wws_adviser.core.config import Settings
from wws_adviser.core.ids import new_id
from wws_adviser.core.time import now_utc_iso
from wws_adviser.modules.model_gateway import repository
from wws_adviser.modules.model_gateway.domain import (
    PROMPTS,
    PromptTemplate,
    ValidationVerdict,
    build_masked_context,
    context_to_prompt_text,
    repair_prompt_errors,
    validate_model_output,
)
from wws_adviser.modules.model_gateway.models import ModelCall
from wws_adviser.ports.model import ModelPort, ModelRequest, ModelTaskType


@dataclass(frozen=True)
class ModelCallResult:
    ok: bool
    content: dict[str, Any] | None
    error_code: str | None
    prompt_version: str
    attempt: int


class ModelGatewayError(Exception):
    """内部错误载体（不外抛到报告层）。"""


def _resolve_key(key_ref: str) -> str:
    """env 引用 → 真实 key。缺失返回空串（调用将失败并降级，不阻断）。"""
    return os.environ.get(key_ref, "")


async def call_model(
    db: DBSession,
    settings: Settings,
    port: ModelPort,
    *,
    task_type: ModelTaskType,
    job_run_id: str | None,
    context: dict[str, Any],
    deterministic_summary: dict[str, str | None],
    evidence_whitelist: list[str] | None = None,
) -> ModelCallResult:
    """模型调用全流程。成功 → content（已过后置校验/数值覆盖）；失败 → ok=False + error_code。"""
    template: PromptTemplate = PROMPTS.get(task_type.value, PROMPTS["pre_market"])
    whitelist = evidence_whitelist or []
    profile = repository.upsert_default_profile(db, settings)
    db.commit()  # profile 播种独立提交；此后模型调用期间无打开写事务

    request = ModelRequest(
        task_type=task_type,
        model_profile_id=profile.id,
        prompt_template_name=template.name,
        prompt_template_version=template.version,
        structured_context=context,
        evidence_ids=whitelist,
        timeout=profile.timeout or settings.model_timeout,
        max_tokens=profile.max_tokens or settings.model_max_tokens,
    )
    _ = _resolve_key(profile.key_ref)  # 真实适配器自行解析；gateway 不持有 key

    attempt = 0
    started = now_utc_iso()
    try:
        # 传输层重试：代理/上游间歇性停摆（实测同一请求前后结果不同），
        # 退避重试可落在健康账号上。retry=1 表示首试+1 次重试。
        last_exc: Exception | None = None
        for backoff in (0, 15, 45)[: 1 + max(0, profile.retry or settings.model_retry)]:
            if backoff:
                await asyncio.sleep(backoff)
            try:
                response = await port.call(request)
                last_exc = None
                break
            except Exception as exc:  # noqa: BLE001 — 传输失败重试；耗尽后降级
                last_exc = exc
        if last_exc is not None:
            raise last_exc
        attempt = 1
        result = validate_model_output(
            response.content,
            deterministic_summary=deterministic_summary,
            evidence_whitelist=whitelist,
            task_type=task_type.value,
        )
        if result.verdict is ValidationVerdict.BLOCKED:
            _save_audit(
                db, profile_id=profile.id, job_run_id=job_run_id, task_type=task_type,
                template=template, evidence=whitelist, started=started,
                status="blocked", error_code="output_invalid", attempt=attempt,
            )
            return ModelCallResult(
                ok=False, content=None, error_code="output_invalid",
                prompt_version=template.version, attempt=attempt,
            )
        if result.verdict is ValidationVerdict.REPAIR:
            # 一次受控修复：校验错误回传重调一次
            repair_ctx = dict(context)
            repair_ctx["repair_instructions"] = repair_prompt_errors(result.errors)
            response = await port.call(
                ModelRequest(
                    task_type=task_type,
                    model_profile_id=profile.id,
                    prompt_template_name=template.name,
                    prompt_template_version=template.version,
                    structured_context=repair_ctx,
                    evidence_ids=whitelist,
                    timeout=profile.timeout or settings.model_timeout,
                    max_tokens=profile.max_tokens or settings.model_max_tokens,
                )
            )
            attempt = 2
            result2 = validate_model_output(
                response.content,
                deterministic_summary=deterministic_summary,
                evidence_whitelist=whitelist,
                task_type=task_type.value,
            )
            if result2.verdict is not ValidationVerdict.PASS:
                _save_audit(
                    db, profile_id=profile.id, job_run_id=job_run_id, task_type=task_type,
                    template=template, evidence=whitelist, started=started,
                    status="degraded", error_code="output_invalid_after_repair", attempt=attempt,
                )
                return ModelCallResult(
                    ok=False, content=None, error_code="output_invalid_after_repair",
                    prompt_version=template.version, attempt=attempt,
                )
            content = result2.content
        else:
            content = result.content
        _save_audit(
            db, profile_id=profile.id, job_run_id=job_run_id, task_type=task_type,
            template=template, evidence=whitelist, started=started,
            status="ok", error_code=None, attempt=attempt,
        )
        return ModelCallResult(
            ok=True, content=content, error_code=None,
            prompt_version=template.version, attempt=attempt,
        )
    except Exception as exc:  # noqa: BLE001 — 网关边界：模型异常一律降级，不外抛
        _save_audit(
            db, profile_id=profile.id, job_run_id=job_run_id, task_type=task_type,
            template=template, evidence=whitelist, started=started,
            status="error", error_code=type(exc).__name__, attempt=max(attempt, 1),
        )
        return ModelCallResult(
            ok=False, content=None, error_code="MODEL_UNAVAILABLE",
            prompt_version=template.version, attempt=max(attempt, 1),
        )


def _save_audit(
    db: DBSession,
    *,
    profile_id: str,
    job_run_id: str | None,
    task_type: ModelTaskType,
    template: PromptTemplate,
    evidence: list[str],
    started: str,
    status: str,
    error_code: str | None,
    attempt: int,
) -> None:
    now = now_utc_iso()
    db.add(
        ModelCall(
            id=new_id(),
            job_run_id=job_run_id,
            model_profile_id=profile_id,
            task_type=task_type.value,
            prompt_template=template.name,
            prompt_version=template.version,
            prompt_hash=template.prompt_hash,
            input_evidence_ids_json=json.dumps(evidence, ensure_ascii=False),
            started_at=started,
            ended_at=now,
            prompt_tokens=0,
            completion_tokens=0,
            estimated_cost=0.0,
            status=status,
            error_code=error_code,
            created_at=now,
            updated_at=now,
        )
    )
    db.commit()


__all__ = ["ModelCallResult", "call_model", "build_masked_context", "context_to_prompt_text"]
