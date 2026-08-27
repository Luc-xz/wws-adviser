"""OpenAI-compatible 模型适配器（ModelPort）。

httpx（已有依赖）调 `/v1/chat/completions`；纯 JSON 解析（含 <think> 剥离）为纯函数可单测。
真实联调留待国内 VPS + 凭据；stub 为默认。
"""

import json
import os
import re
from typing import Any

from wws_adviser.core.time import now_utc_iso
from wws_adviser.ports.model import (
    ModelAudit,
    ModelRequest,
    ModelResponse,
)

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


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


class OpenAICompatibleModelPort:
    """通用 OpenAI-compatible（base_url + api_key(env 引用) + model，不锁定厂商）。"""

    def __init__(self, *, base_url: str, model_name: str, key_ref: str, timeout: float = 30.0,
                 temperature: float = 0.2, env: str = "dev") -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model_name
        self._key_ref = key_ref
        self._timeout = timeout
        self._temperature = temperature
        self._env = env

    def _headers(self) -> dict[str, str]:
        key = os.environ.get(self._key_ref, "")
        return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    async def call(self, request: ModelRequest) -> ModelResponse:
        import httpx

        user_content = json.dumps(
            request.structured_context, ensure_ascii=False, sort_keys=True
        )
        started = now_utc_iso()
        body = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": "你是严谨的投资报告解读助手，只输出 JSON。"},
                {"role": "user", "content": user_content},
            ],
            "temperature": self._temperature,
            "max_tokens": request.max_tokens,
            # 流式：推理型模型（deepseek-r/flash 系）思考数分钟才产出正文，
            # 非流式在思考期间零字节——单一读超时会被整体掐断；流式增量
            # 持续到达（含 reasoning 增量），连接保持活跃直至完成。
            "stream": True,
        }
        # 流式下 httpx 的 read timeout 是"相邻两次读之间"的超时，而非整体
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream(
                "POST", f"{self._base_url}/chat/completions",
                json=body, headers=self._headers(),
            ) as resp:
                resp.raise_for_status()
                chunks: list[str] = []
                usage: dict[str, Any] = {}
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[len("data: "):]
                    if payload.strip() == "[DONE]":
                        break
                    content, chunk_usage = parse_sse_chunk(payload)
                    if content:
                        chunks.append(content)
                    if chunk_usage:
                        usage = chunk_usage
                choice = "".join(chunks)
        content = parse_content(choice)
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


def parse_sse_chunk(payload: str) -> tuple[str, dict[str, Any]]:
    """SSE data 载荷（JSON 字符串）→ (content 增量, usage)。

    只累积 delta.content（推理增量 delta.reasoning_content 剥离——
    与非流式路径 strip_reasoning 口径一致）；usage 出现在末块（若供应商支持）。
    纯函数可单测；非法 JSON 返回空（流中偶发心跳/空行）。
    """
    try:
        obj = json.loads(payload)
    except json.JSONDecodeError:
        return "", {}
    delta = (obj.get("choices") or [{}])[0].get("delta") or {}
    content = delta.get("content") or ""
    usage = obj.get("usage") or {}
    return str(content), dict(usage) if usage else {}
