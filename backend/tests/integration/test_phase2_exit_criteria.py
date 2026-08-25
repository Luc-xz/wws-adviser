"""Phase 2 退出条件验收测试（PRD §17 阶段 2 / TECH §验收清单）。

退出条件：凯利输入通过样本外校准；硬风险限制和数据降级场景全部通过自动测试。
配套结构性检查：p 字段的写路径只能在校准服务（模型 Gateway 无权写入）。
"""

import inspect
import tempfile
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from wws_adviser.core.config import Settings
from wws_adviser.modules.analytics import calibration_service
from wws_adviser.modules.analytics.calibration import CalibrationState
from wws_adviser.modules.analytics.kelly import CalibrationState as KState
from wws_adviser.modules.analytics.kelly import KellyInput, compute_kelly
from wws_adviser.modules.analytics.models import SignalCalibration
from wws_adviser.modules.identity.models import User
from wws_adviser.modules.instruments import service as instruments_service
from wws_adviser.modules.portfolio import service as portfolio_service


def _settings() -> Settings:
    return Settings(env="test", data_dir=Path(tempfile.mkdtemp()))


# —— 退出条件 1：凯利输入只能来自样本外校准通过且未过期的信号 ——


def _kelly_input(state: KState, **overrides) -> KellyInput:
    base = dict(
        signal_id="s", p_low=Decimal("0.55"), p_mid=Decimal("0.6"), p_high=Decimal("0.65"),
        b=Decimal("1.25"), n_eff=200, n_eff_oos=120,
        calibration_state=state, calibration_expires_on="2099-12-31", as_of_date="2026-08-24",
        reliability_passed=True,
    )
    base.update(overrides)
    return KellyInput(**base)


def test_exit1_only_oos_calibrated_signal_qualifies() -> None:
    """UNCALIBRATED/CALIBRATING/STALE/DECAYED/过期/reliability 未过 → 全部拒绝。"""
    rejected_states = [
        (KState.UNCALIBRATED, "calibration_uncalibrated"),
        (KState.CALIBRATING, "calibration_uncalibrated"),
        (KState.STALE, "calibration_stale"),
        (KState.DECAYED, "calibration_stale"),
    ]
    for state, reason in rejected_states:
        out = compute_kelly(_kelly_input(state))
        assert not out.accepted and out.reject_reason == reason, state
        assert out.f_min is None and out.f_max is None  # 拒绝不携带区间
    # 已过期（状态对但超出有效期）→ 拒绝
    out = compute_kelly(_kelly_input(KState.CALIBRATED_OOS, calibration_expires_on="2026-08-01"))
    assert not out.accepted and out.reject_reason == "calibration_expired"
    # reliability 未通过 → 拒绝
    out = compute_kelly(_kelly_input(KState.CALIBRATED_OOS, reliability_passed=False))
    assert not out.accepted and out.reject_reason == "calibration_failed"
    # 样本外样本不足 → 拒绝（不得拿样本内凑）
    out = compute_kelly(_kelly_input(KState.CALIBRATED_OOS, n_eff_oos=29, n_eff=500))
    assert not out.accepted and out.reject_reason == "insufficient_samples"
    # 唯一放行形态：CALIBRATED_OOS + 未过期 + reliability 通过 + n_eff_oos 达标
    ok = compute_kelly(_kelly_input(KState.CALIBRATED_OOS))
    assert ok.accepted and ok.f_max is not None


def test_exit1_p_writes_only_in_calibration_service() -> None:
    """结构性检查：p 写路径只在回测/校准服务；模型 Gateway 无权写入（FR-ANL-003）。"""
    from wws_adviser.infrastructure.models import openai_model
    from wws_adviser.modules.analytics import signals
    from wws_adviser.modules.model_gateway import service as gateway_service

    for mod in (openai_model, gateway_service):
        src = inspect.getsource(mod)
        assert "signal_calibrations" not in src, "模型 Gateway 不得触碰校准记录"
        assert "SignalCalibration" not in src
    # p 的统计来源唯一：signals.wilson_interval 经 summarize（回测口径）
    src = inspect.getsource(signals)
    assert "wilson_interval" in src
    calib_src = inspect.getsource(calibration_service)
    assert "SignalCalibration" in calib_src  # 落库只在校准服务


# —— 退出条件 2：任一硬性风险限制均能截断理论凯利仓位 ——


def test_exit2_every_hard_limit_truncates_kelly() -> None:
    """强信号理论仓位 5.6%（f*=0.28 × 折扣 0.20，PRD 基线），每道硬限制单独作用都必须压低它。"""
    base = dict(
        signal_id="s", p_low=Decimal("0.55"), p_mid=Decimal("0.6"), p_high=Decimal("0.65"),
        b=Decimal("1.25"), n_eff=200, n_eff_oos=120,
        calibration_state=KState.CALIBRATED_OOS, reliability_passed=True,
        calibration_expires_on="2099-12-31", as_of_date="2026-08-24",
        kelly_discount=Decimal("0.20"),
        total_assets=Decimal("1000000"), available_cash=Decimal("1000000"),
        current_position_value=Decimal("0"),
    )
    unlimited = compute_kelly(KellyInput(**base))
    assert unlimited.f_max == Decimal("0.056")  # 0.28 × 0.20

    # 现金下限：可投现金 15000（保留 10 万×10%）→ 截断
    cash_capped = compute_kelly(KellyInput(**{**base, "available_cash": Decimal("115000")}))
    assert cash_capped.value_max == Decimal("15000")
    assert any(s.kind == "clip_cash_floor" for s in cash_capped.trail)

    # 单标的上限：已有持仓 28 万，上限 30%×100 万 → 新增 ≤ 2 万
    single_capped = compute_kelly(
        KellyInput(**{**base, "current_position_value": Decimal("280000")})
    )
    assert single_capped.value_max == Decimal("20000")

    # 行业上限剩余额度
    industry_capped = compute_kelly(
        KellyInput(**{**base, "industry_headroom_value": Decimal("10000")})
    )
    assert industry_capped.value_max == Decimal("10000")

    # 组合波动/回撤约束
    portfolio_capped = compute_kelly(
        KellyInput(**{**base, "portfolio_headroom_value": Decimal("5000")})
    )
    assert portfolio_capped.value_max == Decimal("5000")

    # 每道截断后的仓位都严格低于理论值对应金额（5.6 万）
    for capped in (cash_capped, single_capped, industry_capped, portfolio_capped):
        assert capped.value_max < Decimal("56000")
        assert capped.value_max < unlimited.value_max


# —— 退出条件 3：数据降级场景全部通过自动测试（盘中 API 200 + 明确降级原因）——


def _login_headers(client: TestClient) -> dict[str, str]:
    r = client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "pw12345"},
        headers={"Idempotency-Key": "login-exit-1"},
    )
    assert r.status_code == 200
    return {"x-csrf-token": r.cookies["csrf_token"], "Idempotency-Key": "intraday-exit-1"}


def test_exit3_degradation_scenarios_all_explicit(migrated_client: TestClient) -> None:
    """无校准/无账户/未触发：全部 200 + SUSPEND + 原因，绝不 5xx 或静默给建议。"""
    headers = _login_headers(migrated_client)
    r = migrated_client.post(
        "/api/v1/assistant/intraday", json={"code": "600519"}, headers=headers
    )
    assert r.status_code == 200
    advice = r.json()["advice"]
    assert advice["action"] == "suspend"
    assert advice["f_min"] is None and advice["f_max"] is None
    assert advice["reasons"]  # 降级必须给原因，不静默


def test_exit3_expired_calibration_never_yields_position(migrated_client: TestClient) -> None:
    """校准记录存在但已过期 → 建议不携带仓位区间（读时过期 → STALE → 凯利拒绝）。"""
    app = migrated_client.app
    headers = _login_headers(migrated_client)
    with app.state.session_factory() as db:
        uid = db.scalar(select(User.id))
        portfolio_service.create_account(
            db, user_id=uid, name="main", initial_cash=Decimal("100000")
        )
        instruments_service.get_or_create_instrument(db, code="600519", name="贵州茅台")
        db.commit()
        # 造一份「已过期」的校准记录（状态对但有效期已过）
        sig = calibration_service.seed_default_signal(db)
        db.add(SignalCalibration(
            id="01EXPIREDCALIBRATION000001", signal_def_id=sig.id,
            signal_id=sig.signal_id, signal_version=sig.version,
            state=CalibrationState.CALIBRATED_OOS.value,
            calibrated_on="2026-01-01", expires_on="2026-02-01",
            p_low="0.55", p_mid="0.6", p_high="0.65", b="1.25",
            n_eff=200, n_eff_oos=120, reliability_passed=True,
            created_at="2026-01-01T00:00:00", updated_at="2026-01-01T00:00:00",
            row_version=1,
        ))
        db.commit()
        rec = calibration_service.latest_valid_calibration(db, "breakout-20", as_of="2026-08-24")
        assert rec is not None and rec.state is CalibrationState.STALE  # 读时过期生效

    r = migrated_client.post(
        "/api/v1/assistant/intraday", json={"code": "600519"}, headers=headers
    )
    assert r.status_code == 200
    advice = r.json()["advice"]
    assert advice["f_min"] is None and advice["f_max"] is None  # 过期校准绝不产仓位
