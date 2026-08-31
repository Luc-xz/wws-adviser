"""校准服务集成测试：扫描落库、有效期、执行器任务（波6）。"""

import asyncio
import tempfile
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from wws_adviser.core.config import Settings
from wws_adviser.modules.analytics import calibration_service
from wws_adviser.modules.analytics.calibration import CalibrationState
from wws_adviser.modules.analytics.models import SignalCalibration
from wws_adviser.modules.jobs import service as jobs_service
from wws_adviser.modules.jobs.domain import JobType
from wws_adviser.modules.jobs.models import JobRun
from wws_adviser.modules.market_data.domain import NormalizedBar
from wws_adviser.modules.reports import executor as reports_executor


def _test_settings() -> Settings:
    return Settings(env="test", data_dir=Path(tempfile.mkdtemp()))


def _bar(d: date, close: str, volume: str = "1000") -> NormalizedBar:
    c = Decimal(close)
    return NormalizedBar(business_date=d, open=c, high=c, low=c, close=c, volume=Decimal(volume))


def _synthetic_bars(n_instruments: int = 8, n_days: int = 120) -> dict[str, list[NormalizedBar]]:
    """构造多标的阶梯行情：每 10 日一次放量突破（保证样本量与横截面独立性）。"""
    d0 = date(2026, 1, 1)
    bars: dict[str, list[NormalizedBar]] = {}
    for k in range(n_instruments):
        rows = []
        price = Decimal("10")
        for i in range(n_days):
            vol = "5000" if i % 10 == 9 else "1000"
            rows.append(_bar(
                d0 + timedelta(days=i), str(price), volume=vol
            ))
            price += Decimal("0.3")
        bars[f"60{k:04d}"] = rows
    return bars


def test_calibration_scan_persists_record(db_session) -> None:
    result = calibration_service.run_calibration_scan(
        db_session, _test_settings(), bars_by_code=_synthetic_bars()
    )
    assert result["instruments"] == 8
    row = db_session.scalar(select(SignalCalibration))
    assert row is not None
    assert row.signal_id == "breakout-20"
    assert Decimal(row.p_low) <= Decimal(row.p_mid) <= Decimal(row.p_high)
    assert row.n_eff > 0
    assert row.expires_on > row.calibrated_on


def test_latest_valid_calibration_roundtrip_and_expiry(db_session) -> None:
    calibration_service.run_calibration_scan(
        db_session, _test_settings(), bars_by_code=_synthetic_bars()
    )
    rec = calibration_service.latest_valid_calibration(
        db_session, "breakout-20", as_of="2026-12-31"
    )
    assert rec is not None
    assert rec.signal_id == "breakout-20"
    # 远超有效期（fallback 88 天）→ 视同 STALE
    stale = calibration_service.latest_valid_calibration(
        db_session, "breakout-20", as_of="2027-12-31"
    )
    assert stale is not None
    assert stale.state is CalibrationState.STALE


def test_calibration_scan_without_bars_marks_uncalibrated(db_session) -> None:
    calibration_service.run_calibration_scan(db_session, _test_settings(), bars_by_code={})
    row = db_session.scalar(select(SignalCalibration))
    assert row is not None
    assert row.state == CalibrationState.UNCALIBRATED.value


def test_executor_runs_calibration_scan_job(db_session) -> None:
    settings = _test_settings()
    jobs_service.enqueue(
        db_session, settings,
        job_type=JobType.CALIBRATION_SCAN, business_date="2026-08-24", scope_key="default",
    )
    db_session.commit()
    asyncio.run(reports_executor.run_due_jobs(
        db_session, settings, settings.data_dir, model_port=None, notifier=None,
    ))
    job = db_session.scalar(
        select(JobRun).where(JobRun.job_type == JobType.CALIBRATION_SCAN.value)
    )
    assert job is not None
    assert job.status == "COMPLETED"
    assert job.result_ref and job.result_ref.startswith("calibration://")
