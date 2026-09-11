"""E2E 一体服务器（W4）：种子数据 + 进程内 uvicorn（Playwright webServer 用）。

用法：uv run python scripts/e2e_server.py [--port 8000]
- 临时数据目录（每次全新种子，幂等可重跑）
- 用户 alice/pw12345；账户 + 600519 两笔买入；600519 公告语料 2 条
- 完成态公司研究报告一份（stub 模型，含 evidence 引用）——E6 依据抽屉用
"""

import argparse
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND / "src"))

import asyncio  # noqa: E402
from datetime import UTC, datetime, timedelta  # noqa: E402

from wws_adviser.core.config import Settings  # noqa: E402
from wws_adviser.core.db import Base, create_app_engine, make_session_factory  # noqa: E402
from wws_adviser.core.ids import new_id  # noqa: E402
from wws_adviser.core.time import now_utc_iso  # noqa: E402


def seed(settings: Settings) -> str:
    """建库 + 种子数据。返回用户 id。"""
    # 显式导入全部模型模块（同 tests/conftest）——FK 目标表需注册进 metadata
    from wws_adviser.modules.advice import models as _m1  # noqa: F401
    from wws_adviser.modules.analytics import models as _m2  # noqa: F401
    from wws_adviser.modules.appsettings import models as _m3  # noqa: F401
    from wws_adviser.modules.audit import models as _m4  # noqa: F401
    from wws_adviser.modules.documents import models as _m5  # noqa: F401
    from wws_adviser.modules.instruments import models as _m6  # noqa: F401
    from wws_adviser.modules.jobs import models as _m7  # noqa: F401
    from wws_adviser.modules.market_data import models as _m8  # noqa: F401
    from wws_adviser.modules.model_gateway import models as _m9  # noqa: F401
    from wws_adviser.modules.notifications import models as _m10  # noqa: F401
    from wws_adviser.modules.portfolio import models as _m11  # noqa: F401
    from wws_adviser.modules.reports import models as _m12  # noqa: F401
    from wws_adviser.modules.research import models as _m13  # noqa: F401

    from wws_adviser.infrastructure.data_sources.stub_document import StubDocumentProvider
    from wws_adviser.infrastructure.models.stub_model import StubModelPort
    from wws_adviser.infrastructure.storage.local_object_store import LocalObjectStore
    from wws_adviser.modules.documents import service as doc_service
    from wws_adviser.modules.documents.repository import create_fts_if_missing
    from wws_adviser.modules.identity import domain as identity_domain
    from wws_adviser.modules.identity import models as identity_models
    from wws_adviser.modules.instruments import service as instruments_service
    from wws_adviser.modules.instruments.models import Instrument
    from wws_adviser.modules.portfolio.models import Account, Transaction
    from wws_adviser.modules.research import executor as research_executor
    from wws_adviser.modules.research import service as research_service
    from wws_adviser.ports.document_source import DocumentScope
    from wws_adviser.ports.market_data import InstrumentRef

    engine = create_app_engine(settings)
    Base.metadata.create_all(engine)
    create_fts_if_missing(engine)
    factory = make_session_factory(engine)

    with factory() as db:
        user = identity_models.User(
            id=new_id(),
            username="alice",
            password_hash=identity_domain.hash_password("pw12345"),
            created_at=now_utc_iso(),
            updated_at=now_utc_iso(),
            version=1,
        )
        db.add(user)
        db.flush()

        inst = instruments_service.get_or_create_instrument(
            db, code="600519", name="贵州茅台", market="SSE"
        )
        account = Account(
            id=new_id(), user_id=user.id, name="主账户", currency="CNY",
            initial_cash_minor=200_000_00, initial_cash_scale=2,
            current_cash_minor=200_000_00, current_cash_scale=2,
            reconciled=False, reconciled_at=None,
            created_at=now_utc_iso(), updated_at=now_utc_iso(),
        )
        db.add(account)
        db.flush()

        now = datetime.now(UTC)
        for i, (qty, price, days_ago) in enumerate(
            [(100, "1500.00", 30), (200, "1550.00", 20)]
        ):
            trade = (now - timedelta(days=days_ago)).isoformat()
            db.add(Transaction(
                id=new_id(), account_id=account.id, instrument_id=inst.id,
                kind="BUY", direction="IN", quantity=qty, price=price,
                fee_minor=50, fee_scale=2, tax_minor=0, tax_scale=2,
                trade_at=trade, external_ref=f"e2e-seed-{i}",
                fingerprint=f"e2e-seed-fp-{i}-{new_id()[:8]}",
                created_at=now_utc_iso(), updated_at=now_utc_iso(), version=1,
            ))
        db.commit()

        # 公告语料 2 条（stub provider，标题即正文——E2E 只验证链路不验证内容）
        store = LocalObjectStore(settings.data_dir)
        scope = DocumentScope(
            instrument=InstrumentRef(code="600519", market="SSE", kind="stock"),
            kinds=None,
        )
        asyncio.run(doc_service.ingest_documents(
            db, object_store=store, provider=StubDocumentProvider(env="dev"),
            scope=scope, since=datetime.min.replace(tzinfo=UTC),
            request_id="e2e-seed-docs",
        ))

        # 完成态公司研究报告（stub 模型同步执行）——E6 依据抽屉用
        task = research_service.create_task(
            db, user_id=user.id, task_type="company", subject="600519",
            depth="quick",
        )
        asyncio.run(research_executor.run_pending(
            db, settings, settings.data_dir,
            model_port=StubModelPort(env="dev"), notifier=None, limit=1,
        ))
        db.refresh(task)
        assert task.status == "COMPLETED", f"种子研究任务未完成: {task.status}/{task.error_code}"

        # 完成态盘前日报一份——E4 离线打开用（无行情 → 降级形态但 COMPLETED）
        from wws_adviser.modules.jobs.domain import JobType
        from wws_adviser.modules.reports.executor import (
            enqueue_report_job,
            run_due_jobs,
        )

        enqueue_report_job(db, settings, report_type=JobType.PRE_MARKET)
        executed = asyncio.run(run_due_jobs(
            db, settings, settings.data_dir,
            model_port=StubModelPort(env="dev"), notifier=None,
        ))
        assert executed >= 1, "种子日报未执行"
        print(f"E2E seed ok: user={user.id} instrument={inst.id} task={task.id}")
        return user.id


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    data_dir = Path(tempfile.mkdtemp(prefix="wws-e2e-"))
    settings = Settings(
        env="dev",
        data_dir=data_dir,
        session_secret="e2e-insecure-secret",
        passkey_rp_id="localhost",
        passkey_origin="http://localhost:5174",
    )
    seed(settings)
    print(f"E2E data dir: {data_dir}")

    import os

    os.environ["WWSE_DATA_DIR"] = str(data_dir)
    os.environ["WWSE_ENV"] = "dev"
    os.environ["WWSE_SESSION_SECRET"] = "e2e-insecure-secret"

    import uvicorn

    uvicorn.run(
        "wws_adviser.main:app",
        host="127.0.0.1",
        port=args.port,
        workers=1,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
