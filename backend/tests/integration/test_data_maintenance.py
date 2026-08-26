"""数据维护任务测试：持仓日线批量采集（15:20 调度，波8 报告质量依赖）。"""

import asyncio
import tempfile
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from wws_adviser.core.config import Settings
from wws_adviser.core.ids import new_id
from wws_adviser.core.time import now_utc_iso
from wws_adviser.modules.identity import domain as identity_domain
from wws_adviser.modules.identity.models import User
from wws_adviser.modules.jobs import service as jobs_service
from wws_adviser.modules.jobs.domain import JobType
from wws_adviser.modules.jobs.models import JobRun
from wws_adviser.modules.market_data import service as market_service
from wws_adviser.modules.market_data.domain import BarRow
from wws_adviser.modules.portfolio import service as portfolio_service
from wws_adviser.modules.portfolio.domain import TransactionKind
from wws_adviser.modules.reports import executor as reports_executor
from wws_adviser.ports.market_data import InstrumentRef, RawDataset


class FakeBarProvider:
    """返回固定两日行情的假 provider（无网络）。"""

    async def fetch_daily_bars(
        self, instrument: InstrumentRef, start: date, end: date
    ) -> RawDataset:
        from wws_adviser.core.time import now_utc_iso
        from wws_adviser.ports.market_data import SourceDelayClass

        d0 = date.today() - timedelta(days=1)
        bars = [
            BarRow(date=d0, open=Decimal("1.0"), high=Decimal("1.1"),
                   low=Decimal("0.9"), close=Decimal("1.0"), volume=Decimal(100)),
            BarRow(date=date.today(), open=Decimal("1.0"), high=Decimal("1.2"),
                   low=Decimal("0.9"), close=Decimal("1.1"), volume=Decimal(200)),
        ]
        now = now_utc_iso()
        return RawDataset(
            source="fake", source_url="fake://bars", market_time=now,
            fetched_at=now, received_at=now,
            source_delay_class=SourceDelayClass.END_OF_DAY, bars=bars,
        )


class FailingProvider:
    async def fetch_daily_bars(
        self, instrument: InstrumentRef, start: date, end: date
    ) -> RawDataset:
        raise ConnectionError("source down")


def _seed_user_with_position(db) -> str:
    uid = new_id()
    db.add(User(
        id=uid, username=f"dm{uid[-6:]}",
        password_hash=identity_domain.hash_password("pw12345"),
        created_at=now_utc_iso(), updated_at=now_utc_iso(), version=1,
    ))
    db.flush()
    portfolio_service.create_account(db, user_id=uid, name="main",
                                     initial_cash=Decimal("10000"))
    from wws_adviser.modules.instruments import service as instruments_service

    inst = instruments_service.get_or_create_instrument(db, code="510500", name="500ETF")
    db.flush()
    portfolio_service.record_transaction(
        db, user_id=uid, instrument_id=inst.id, kind=TransactionKind.BUY,
        quantity=Decimal("100"), price=Decimal("1.0"), trade_at="2026-08-01",
    )
    db.commit()
    return uid


def test_ingest_bars_for_holdings(db_session, tmp_path) -> None:
    _seed_user_with_position(db_session)
    results = asyncio.run(market_service.ingest_bars_for_holdings(
        db_session, data_dir=tmp_path, provider=FakeBarProvider(),
    ))
    assert results == {"510500": "OK"}
    # 幂等：重采同样成功（内容哈希去重）
    results2 = asyncio.run(market_service.ingest_bars_for_holdings(
        db_session, data_dir=tmp_path, provider=FakeBarProvider(),
    ))
    assert results2 == {"510500": "OK"}


def test_ingest_bars_failure_recorded_not_fatal(db_session, tmp_path) -> None:
    _seed_user_with_position(db_session)
    results = asyncio.run(market_service.ingest_bars_for_holdings(
        db_session, data_dir=tmp_path, provider=FailingProvider(),
    ))
    assert results == {"510500": "ConnectionError"}


def test_executor_runs_data_maintenance_job(db_session) -> None:
    settings = Settings(env="test", data_dir=Path(tempfile.mkdtemp()))
    _seed_user_with_position(db_session)
    jobs_service.enqueue(
        db_session, settings,
        job_type=JobType.DATA_MAINTENANCE, business_date="2026-08-26", scope_key="default",
    )
    db_session.commit()
    # market_data_source 默认 stub → 维护任务直接完成（0/0）
    asyncio.run(reports_executor.run_due_jobs(
        db_session, settings, settings.data_dir, model_port=None, notifier=None,
    ))
    job = db_session.scalar(
        select(JobRun).where(JobRun.job_type == JobType.DATA_MAINTENANCE.value)
    )
    assert job is not None and job.status == "COMPLETED"
    assert job.result_ref and job.result_ref.startswith("bars://")
