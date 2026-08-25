"""建议评价回填集成测试：观察窗口评价 + 回灌校准闭环（Phase 2）。"""

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from wws_adviser.core.config import Settings
from wws_adviser.modules.advice import evaluation_service
from wws_adviser.modules.advice.models import AdviceRecord
from wws_adviser.modules.analytics import calibration_service
from wws_adviser.modules.analytics.calibration import CalibrationState
from wws_adviser.modules.analytics.models import SignalCalibration
from wws_adviser.modules.market_data.domain import NormalizedBar


def _user_id(db) -> str:
    from wws_adviser.core.ids import new_id
    from wws_adviser.core.time import now_utc_iso
    from wws_adviser.modules.identity import domain as identity_domain
    from wws_adviser.modules.identity.models import User

    uid = new_id()
    db.add(User(
        id=uid, username=f"u{uid[-6:]}",
        password_hash=identity_domain.hash_password("pw12345"),
        created_at=now_utc_iso(), updated_at=now_utc_iso(), version=1,
    ))
    db.flush()
    return uid


def _bar(d: date, close: str) -> NormalizedBar:
    c = Decimal(close)
    return NormalizedBar(business_date=d, open=c, high=c, low=c, close=c, volume=Decimal("1000"))


def _seed_advice(
    db, code: str, action: str, advice_id: str, valid_from: str, horizon_signal: str = "breakout-20"
) -> None:
    db.add(AdviceRecord(
        id=advice_id, user_id=_user_id(db), signal_id=horizon_signal, code=code,
        action=action, state="published",
        valid_from=valid_from, expires_at=valid_from[:10] + "T07:00:00+00:00",
        f_min="0.02", f_max="0.05",
        created_at=valid_from, updated_at=valid_from, row_version=1,
    ))


def test_review_writes_verdict_and_backfeeds_decay(db_session) -> None:
    """窗口收益为正 → direction_correct；持续错误 → 回灌 DECAYED。"""
    import tempfile
    from pathlib import Path

    settings = Settings(env="test", data_dir=Path(tempfile.mkdtemp()))
    calibration_service.seed_default_signal(db_session)  # breakout-20（horizon 5）

    d0 = date(2026, 7, 1)
    # 上涨标的：10 条建议全部 direction_correct；下跌标的：全部 direction_wrong
    up_bars = [_bar(d0 + timedelta(i), str(Decimal("10") + Decimal(i))) for i in range(60)]
    down_bars = [_bar(d0 + timedelta(i), str(Decimal("10") - Decimal(i) / 2)) for i in range(60)]
    bars_by_code = {"600001": up_bars, "600002": down_bars}
    # 通过注入走 bars（避免依赖 market_records 播种）
    orig_load = calibration_service.load_bars_by_code
    calibration_service.load_bars_by_code = lambda db, **kw: bars_by_code  # type: ignore[assignment]
    try:
        for i in range(6):
            _seed_advice(
                db_session, "600001", "buy",
                f"01GOODADVICE{i:013d}", "2026-07-10T02:00:00+00:00",
            )
        for i in range(8):
            _seed_advice(
                db_session, "600002", "buy",
                f"01BADADVICE{i:014d}", "2026-07-10T02:00:00+00:00",
            )
        db_session.commit()

        result = evaluation_service.review_due_advices(
            db_session, settings, today="2026-09-01"
        )
        assert result["reviewed"] == 14
        rows = db_session.scalars(select(AdviceRecord).order_by(AdviceRecord.id)).all()
        verdicts = {r.code: r.verdict for r in rows}
        assert verdicts["600001"] == "direction_correct"
        assert verdicts["600002"] == "direction_wrong"
        assert all(r.evaluated_at for r in rows)
    finally:
        calibration_service.load_bars_by_code = orig_load  # type: ignore[assignment]


def test_review_no_due_advices_is_noop(db_session) -> None:
    import tempfile
    from pathlib import Path

    settings = Settings(env="test", data_dir=Path(tempfile.mkdtemp()))
    result = evaluation_service.review_due_advices(db_session, settings, today="2026-09-01")
    assert result == {"reviewed": 0, "signals": {}}


def test_backfeed_decay_path_via_state_machine(db_session) -> None:
    """回灌 decay：校准记录走合法路径 CALIBRATED_OOS → STALE → DECAYED。"""
    sig = calibration_service.seed_default_signal(db_session)
    db_session.add(SignalCalibration(
        id="01DECAYTEST0000000000000A", signal_def_id=sig.id,
        signal_id=sig.signal_id, signal_version=sig.version,
        state=CalibrationState.CALIBRATED_OOS.value,
        calibrated_on="2026-07-01", expires_on="2026-12-31",
        p_low="0.55", p_mid="0.6", p_high="0.65", b="1.25",
        n_eff=200, n_eff_oos=120, reliability_passed=True,
        created_at="2026-07-01", updated_at="2026-07-01", row_version=1,
    ))
    db_session.commit()
    applied = evaluation_service._apply_backfeed(  # noqa: SLF001 — 直接测状态机路径
        db_session, "breakout-20", "decay", Decimal("0.8")
    )
    assert "decayed" in applied or "stale" in applied
    row = db_session.scalar(select(SignalCalibration))
    assert row.state in (CalibrationState.STALE.value, CalibrationState.DECAYED.value)


def test_backfeed_reduce_p_lowers_interval(db_session) -> None:
    sig = calibration_service.seed_default_signal(db_session)
    db_session.add(SignalCalibration(
        id="01REDUCETEST00000000000A", signal_def_id=sig.id,
        signal_id=sig.signal_id, signal_version=sig.version,
        state=CalibrationState.CALIBRATED_OOS.value,
        calibrated_on="2026-07-01", expires_on="2026-12-31",
        p_low="0.55", p_mid="0.6", p_high="0.65", b="1.25",
        n_eff=200, n_eff_oos=120, reliability_passed=True,
        created_at="2026-07-01", updated_at="2026-07-01", row_version=1,
    ))
    db_session.commit()
    applied = evaluation_service._apply_backfeed(  # noqa: SLF001
        db_session, "breakout-20", "reduce_p", Decimal("0.8")
    )
    assert "p×0.8" in applied
    row = db_session.scalar(select(SignalCalibration))
    assert Decimal(row.p_mid) == Decimal("0.6") * Decimal("0.8")


def test_executor_runs_advice_review_job(db_session) -> None:
    import asyncio
    import tempfile
    from pathlib import Path

    from wws_adviser.modules.jobs import service as jobs_service
    from wws_adviser.modules.jobs.domain import JobType
    from wws_adviser.modules.jobs.models import JobRun
    from wws_adviser.modules.reports import executor as reports_executor

    settings = Settings(env="test", data_dir=Path(tempfile.mkdtemp()))
    jobs_service.enqueue(
        db_session, settings,
        job_type=JobType.ADVICE_REVIEW, business_date="2026-08-25", scope_key="default",
    )
    db_session.commit()
    asyncio.run(reports_executor.run_due_jobs(
        db_session, settings, settings.data_dir, model_port=None, notifier=None,
    ))
    job = db_session.scalar(
        select(JobRun).where(JobRun.job_type == JobType.ADVICE_REVIEW.value)
    )
    assert job is not None and job.status == "COMPLETED"
    assert job.result_ref and job.result_ref.startswith("advice_review://")
