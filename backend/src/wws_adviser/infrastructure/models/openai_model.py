"""OpenAI-compatible 模型适配器（ModelPort）。

httpx（已有依赖）调 `/v1/chat/completions`；纯 JSON 解析（含 <think> 剥离）与请求体
构造为纯函数可单测。原生 structured-output：带 response_schema 时发 json_schema 模式，
供应商 4xx 不支持 → 剥离 response_format 重试一次（文本抽取兜底）。真实联调留待国内
VPS + 凭据；stub 为默认。
"""

import json
import os
import re
from typing import TYPE_CHECKING, Any

from wws_adviser.core.time import now_utc_iso
from wws_adviser.ports.model import (
    ModelAudit,
    ModelRequest,
    ModelResponse,
)

if TYPE_CHECKING:
    import httpx

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)

_SYSTEM_PROMPT = "你是严谨的投资报告解读助手，只输出 JSON。"


def strip_reasoning(text: str) -> str:
    """推理模型的 <think> 段必须在结构化解析前剥离（6_MODEL §12.2 R1）。"""
    return _THINK_RE.sub("", text).strip()


def parse_content(raw: str) -> dict[str, Any]:
    """模型文本 → dict：剥 <think> → ```json 代码块或首个 JSON 对象。失败抛 ValueError。"""
    text = strip_reasoning(raw)
    m = _JSON_BLOCK_RE.search(text)
    if m:
        text = m.group(1)
    else:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"模型输出非 JSON: {exc}") from exc
    if not isinstance(obj, dict):
        raise ValueError("模型输出不是 JSON 对象")
    return obj


def build_chat_body(
    request: ModelRequest, *, model: str, temperature: float, max_tokens: int
) -> dict[str, Any]:
    """ModelRequest → chat/completions 请求体（纯函数可单测）。

    带 response_schema 时启用原生 structured-output（json_schema/strict）。
    """
    body: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    request.structured_context, ensure_ascii=False, sort_keys=True
                ),
            },
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if request.response_schema:
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": f"{request.task_type.value}_structured",
                "schema": request.response_schema,
                "strict": True,
            },
        }
    return body


def strip_response_format(body: dict[str, Any]) -> dict[str, Any]:
    """剥离原生模式——供应商不支持时的文本抽取兜底形态（纯函数可单测）。"""
    return {k: v for k, v in body.items() if k != "response_format"}


class OpenAICompatibleModelPort:
    """通用 OpenAI-compatible（base_url + api_key(env 引用) + model，不锁定厂商）。"""

    def __init__(self, *, base_url: str, model_name: str, key_ref: str, timeout: float = 30.0,
                 temperature: float = 0.2, env: str = "dev",
                 transport: "httpx.AsyncBaseTransport | None" = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model_name
        self._key_ref = key_ref
        self._timeout = timeout
        self._temperature = temperature
        self._env = env
        self._transport = transport  # 测试注 MockTransport；生产走真实连接池

    def _headers(self) -> dict[str, str]:
        key = os.environ.get(self._key_ref, "")
        return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    async def call(self, request: ModelRequest) -> ModelResponse:
        import httpx

        started = now_utc_iso()
        body = build_chat_body(
            request, model=self._model, temperature=self._temperature,
            max_tokens=request.max_tokens,
        )
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            try:
                resp = await client.post(
                    f"{self._base_url}/chat/completions", json=body, headers=self._headers()
                )
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                # 4xx + 原生模式 → 多为供应商不支持 json_schema：剥离后重试一次
                if exc.response.status_code < 500 and "response_format" in body:
                    resp = await client.post(
                        f"{self._base_url}/chat/completions",
                        json=strip_response_format(body),
                        headers=self._headers(),
                    )
                    resp.raise_for_status()
                else:
                    raise
            data = resp.json()
        choice = data["choices"][0]["message"]["content"]
        content = parse_content(choice)
        usage = data.get("usage", {})
        return ModelResponse(
            content=content,
            audit=ModelAudit(
                task_type=request.task_type,
                model_profile_id=request.model_profile_id,
                prompt_template_name=request.prompt_template_name,
                prompt_template_version=request.prompt_template_version,
                prompt_hash=f"{self._model}:{request.prompt_template_name}",
                input_evidence_ids=list(request.evidence_ids),
                started_at=started,
                ended_at=now_utc_iso(),
                prompt_tokens=int(usage.get("prompt_tokens", 0)),
                completion_tokens=int(usage.get("completion_tokens", 0)),
                status="ok",
            ),
        )
