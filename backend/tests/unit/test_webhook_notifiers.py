"""企微机器人 / Server酱 通知适配器测试（MockTransport，无真实网络）。

覆盖：消息构造纯函数、成功路径（断言请求 URL/报文形态）、业务错误码、
渠道不匹配与凭据缺失的快速失败。
"""

import json

import httpx

from wws_adviser.infrastructure.notifications.serverchan_notifier import (
    ServerChanNotifierPort,
    build_form,
)
from wws_adviser.infrastructure.notifications.wechat_work_notifier import (
    WeChatWorkNotifierPort,
    build_request_body,
)
from wws_adviser.ports.notifier import NotificationChannel


def test_wechat_work_request_body() -> None:
    body = build_request_body("report.completed", {"报告": "pre", "降级": "无"})
    assert body["msgtype"] == "text"
    content = body["text"]["content"]
    assert content.startswith("[WWS Adviser] report.completed")
    assert "报告: pre" in content and "降级: 无" in content


def test_serverchan_form() -> None:
    form = build_form("report.completed", {"pnl": "+1.2%"})
    assert form["title"] == "[WWS Adviser] report.completed"
    assert "- **pnl**: +1.2%" in form["desp"]


async def test_wechat_work_success_and_request_shape(monkeypatch) -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["json"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"errcode": 0, "errmsg": "ok"})

    monkeypatch.setenv("WWSE_WECHAT_WORK_WEBHOOK", "https://qyapi.example/cgi?k=SEC")
    port = WeChatWorkNotifierPort(
        webhook_ref="WWSE_WECHAT_WORK_WEBHOOK",
        env="test",
        transport=httpx.MockTransport(handler),
    )
    result = await port.notify(
        NotificationChannel.WECHAT_WORK, "report.completed", {"n": 1}
    )
    assert result.sent and result.error_code is None
    assert captured["url"].startswith("https://qyapi.example/cgi?")
    assert "k=SEC" not in repr(port)  # key 不进适配器状态，只进请求 URL
    assert captured["json"]["msgtype"] == "text"


async def test_wechat_work_errcode_nonzero_fails(monkeypatch) -> None:
    monkeypatch.setenv("WWSE_WECHAT_WORK_WEBHOOK", "https://qyapi.example/x")
    port = WeChatWorkNotifierPort(
        webhook_ref="WWSE_WECHAT_WORK_WEBHOOK",
        env="test",
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"errcode": 93000})),
    )
    result = await port.notify(NotificationChannel.WECHAT_WORK, "e", {})
    assert not result.sent
    assert result.error_code == "wechat_work_errcode_93000"


async def test_wechat_work_missing_env_fails_fast(monkeypatch) -> None:
    monkeypatch.delenv("WWSE_WECHAT_WORK_WEBHOOK", raising=False)
    port = WeChatWorkNotifierPort(webhook_ref="WWSE_WECHAT_WORK_WEBHOOK", env="test")
    result = await port.notify(NotificationChannel.WECHAT_WORK, "e", {})
    assert not result.sent and result.error_code == "missing_webhook_env"


async def test_wechat_work_channel_mismatch() -> None:
    port = WeChatWorkNotifierPort(webhook_ref="X", env="test")
    result = await port.notify(NotificationChannel.EMAIL, "e", {})
    assert not result.sent and result.error_code == "channel_mismatch"


async def test_serverchan_success_and_form_request(monkeypatch) -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = request.content.decode("utf-8")
        return httpx.Response(200, json={"code": 0})

    monkeypatch.setenv("WWSE_SERVERCHAN_KEY", "SCT123456")
    port = ServerChanNotifierPort(
        sendkey_ref="WWSE_SERVERCHAN_KEY",
        api_base="https://sct.test",
        env="test",
        transport=httpx.MockTransport(handler),
    )
    result = await port.notify(NotificationChannel.SERVER_CHAN, "job.failed", {"a": 1})
    assert result.sent
    assert captured["url"] == "https://sct.test/SCT123456.send"
    assert "title=" in captured["body"] and "desp=" in captured["body"]


async def test_serverchan_code_nonzero_fails(monkeypatch) -> None:
    monkeypatch.setenv("WWSE_SERVERCHAN_KEY", "K")
    port = ServerChanNotifierPort(
        sendkey_ref="WWSE_SERVERCHAN_KEY",
        api_base="https://sct.test",
        env="test",
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"code": 40001})),
    )
    result = await port.notify(NotificationChannel.SERVER_CHAN, "e", {})
    assert not result.sent and result.error_code == "serverchan_code_40001"


def test_env_refs_defaults() -> None:
    from wws_adviser.core.config import Settings

    s = Settings(env="test")
    assert s.wechat_work_webhook_ref == "WWSE_WECHAT_WORK_WEBHOOK"
    assert s.server_chan_sendkey_ref == "WWSE_SERVERCHAN_KEY"
