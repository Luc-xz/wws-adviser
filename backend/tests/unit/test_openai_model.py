"""OpenAI-compatible 适配器测试：请求体构造 / 原生 structured-output 回退（MockTransport）。

无网络：httpx.MockTransport 断言请求形态与回退行为。
"""

import json
from typing import Any

import httpx
import pytest

from wws_adviser.infrastructure.models.openai_model import (
    OpenAICompatibleModelPort,
    build_chat_body,
    strip_response_format,
)
from wws_adviser.modules.model_gateway.domain import response_schema_for
from wws_adviser.ports.model import ModelRequest, ModelTaskType


def _request(**overrides: Any) -> ModelRequest:
    base: dict[str, Any] = dict(
        task_type=ModelTaskType.PRE_MARKET,
        model_profile_id="p1",
        prompt_template_name="pre_market",
        prompt_template_version="v1",
        structured_context={"a": 1},
        evidence_ids=[],
    )
    base.update(overrides)
    return ModelRequest(**base)


def _port(handler) -> OpenAICompatibleModelPort:
    return OpenAICompatibleModelPort(
        base_url="https://llm.test/v1",
        model_name="test-model",
        key_ref="WWSE_MODEL_API_KEY",
        timeout=5.0,
        env="test",
        transport=httpx.MockTransport(handler),
    )


def test_body_without_schema_has_no_response_format() -> None:
    body = build_chat_body(_request(), model="m", temperature=0.2, max_tokens=128)
    assert "response_format" not in body
    assert json.loads(body["messages"][1]["content"]) == {"a": 1}


def test_body_with_schema_uses_strict_json_schema() -> None:
    schema = response_schema_for("pre_market")
    body = build_chat_body(_request(response_schema=schema), model="m", temperature=0.2,
                           max_tokens=128)
    rf = body["response_format"]
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["strict"] is True
    assert rf["json_schema"]["schema"]["required"] == ["summary", "evidence_ids"]
    # 剥离即回退形态
    assert "response_format" not in strip_response_format(body)


def _completion(content_obj: dict[str, Any]) -> dict[str, Any]:
    return {
        "choices": [{"message": {"content": json.dumps(content_obj, ensure_ascii=False)}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }


async def test_call_native_success_sends_response_format(monkeypatch) -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json=_completion({"summary": "好", "evidence_ids": []}))

    monkeypatch.setenv("WWSE_MODEL_API_KEY", "k-test")
    resp = await _port(handler).call(_request(response_schema=response_schema_for("pre_market")))
    assert resp.content == {"summary": "好", "evidence_ids": []}
    assert "response_format" in seen["body"]
    assert resp.audit.status == "ok"


async def test_call_falls_back_on_4xx_unsupported_schema(monkeypatch) -> None:
    bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        bodies.append(body)
        if "response_format" in body:
            return httpx.Response(400, json={"error": "response_format unsupported"})
        return httpx.Response(200, json=_completion({"summary": "兜底", "evidence_ids": []}))

    monkeypatch.setenv("WWSE_MODEL_API_KEY", "k-test")
    resp = await _port(handler).call(_request(response_schema=response_schema_for("pre_market")))
    assert resp.content == {"summary": "兜底", "evidence_ids": []}
    assert len(bodies) == 2
    assert "response_format" in bodies[0] and "response_format" not in bodies[1]


async def test_call_5xx_raises_for_gateway_degrade(monkeypatch) -> None:
    monkeypatch.setenv("WWSE_MODEL_API_KEY", "k-test")
    port = _port(lambda req: httpx.Response(500, json={"error": "boom"}))
    with pytest.raises(httpx.HTTPStatusError):
        await port.call(_request(response_schema=response_schema_for("pre_market")))
