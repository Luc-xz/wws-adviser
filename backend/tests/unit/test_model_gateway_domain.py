"""Model gateway 领域纯函数测试：校验规则/掩码/prompt hash + openai/smtp 解析（无 DB/网络）。"""

import pytest

from wws_adviser.modules.model_gateway.domain import (
    PROMPTS,
    ValidationVerdict,
    build_masked_context,
    context_to_prompt_text,
    repair_prompt_errors,
    validate_model_output,
)
from wws_adviser.modules.notifications.domain import compute_payload_hash, mask_payload

DET = {"pnl_total": "150.00", "cash_ratio": "0.4000"}


def test_validate_pass() -> None:
    r = validate_model_output(
        {"summary": "组合稳健", "evidence_ids": []},
        deterministic_summary=DET,
        evidence_whitelist=["doc1"],
    )
    assert r.verdict is ValidationVerdict.PASS
    assert r.errors == []


def test_validate_missing_field_needs_repair() -> None:
    r = validate_model_output(
        {"evidence_ids": []}, deterministic_summary=DET, evidence_whitelist=[]
    )
    assert r.verdict is ValidationVerdict.REPAIR
    assert any("summary" in e for e in r.errors)


def test_validate_numeric_mismatch_overridden() -> None:
    """模型复述数值与确定性不一致 → 覆盖为确定性值（永不显示模型冲突数值）。"""
    r = validate_model_output(
        {"summary": "x", "pnl_total": "999999", "evidence_ids": []},
        deterministic_summary=DET,
        evidence_whitelist=[],
    )
    assert r.verdict is ValidationVerdict.REPAIR  # 记录了错误（数值覆盖）
    assert r.content["pnl_total"] == "150.00"  # 已被确定性值覆盖


def test_validate_evidence_whitelist_blocked() -> None:
    r = validate_model_output(
        {"summary": "x", "evidence_ids": ["evil-doc"]},
        deterministic_summary=DET,
        evidence_whitelist=["doc1"],
    )
    assert r.verdict is ValidationVerdict.BLOCKED


def test_repair_prompt_mentions_errors() -> None:
    s = repair_prompt_errors(["缺少字段: ['summary']"])
    assert "缺少字段" in s
    assert "JSON" in s


def test_prompt_registry_hash_stable_and_versioned() -> None:
    t = PROMPTS["pre_market"]
    assert t.version == "v1"
    assert t.prompt_hash == PROMPTS["pre_market"].prompt_hash
    assert len(t.prompt_hash) == 32
    assert "不得给出具体交易数量" in t.text  # 模板禁令（不可重算/不给数量）


def test_masked_context_contains_no_cash_amount() -> None:
    """8_SECURITY §5：现金绝对金额不进模型明文。"""
    ctx = build_masked_context(
        report_type="pre_market",
        business_date="2026-08-14",
        summary={"cash_ratio": "0.40", "pnl_total": "150", "concentration": "0.5"},
        risk=[{"rule": "single_cap", "level": "hard", "actual": "0.5"}],
        positions=[{"code": "600519", "weight": "0.5", "freshness": "2026-08-13"}],
        snapshot_refs={"trade_cutoff_at": "2026-08-13", "frozen_at": "t"},
    )
    s = str(ctx)
    assert "cash_ratio" in s
    assert "cash" not in {k for k in ctx["portfolio"]}
    assert "600519" in s


def test_context_wrapped_in_untrusted_block() -> None:
    """上下文以 <untrusted_context> 数据块注入（防提示注入）。"""
    t = PROMPTS["post_market"]
    p = context_to_prompt_text(t, {"a": 1})
    assert "<untrusted_context>" in p and "</untrusted_context>" in p
    assert "数据块" in p


# —— openai 适配器纯函数 ——


def test_parse_content_strips_think_and_code_block() -> None:
    from wws_adviser.infrastructure.models.openai_model import parse_content

    raw = '<think>推理过程…</think>```json\n{"summary": "好"}\n```'
    assert parse_content(raw) == {"summary": "好"}
    assert parse_content('前置文本 {"summary": "纯"} 后置') == {"summary": "纯"}
    with pytest.raises(ValueError):
        parse_content("完全不是 JSON")


# —— smtp 适配器纯函数 ——


def test_smtp_build_message() -> None:
    from wws_adviser.infrastructure.notifications.smtp_notifier import build_message

    msg = build_message(subject="[WWS] 报告", body="内容", from_addr="a@x.com", to_addr="b@y.com")
    assert msg["Subject"] == "[WWS] 报告"
    assert msg["To"] == "b@y.com"


# —— 通知域 ——


def test_payload_hash_stable() -> None:
    assert compute_payload_hash({"a": 1, "b": 2}) == compute_payload_hash({"b": 2, "a": 1})


def test_mask_payload_privacy() -> None:
    """隐私模式：不含标的/金额/动作。"""
    masked = mask_payload(
        {
            "event_type": "report_completed",
            "code": "600519",
            "amount": "100000",
            "risk_breach_count": 2,
        }
    )
    s = str(masked)
    assert "600519" not in s and "100000" not in s
    assert masked["risk_breach_count"] == 2
