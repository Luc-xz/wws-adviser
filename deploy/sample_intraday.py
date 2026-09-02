#!/usr/bin/env python
"""Phase 2 五日验证采样器：对 6 只持仓（沪 3 + 深 3）各发一次盘中问询，结果追加日志。

用法（容器内）：python sample_intraday.py >> /data/phase2-samples.log 2>&1
日志行：ISO 日期 | phase | code | action/state | reasons | data_stale(bool)
"""
import sys

sys.path.insert(0, "/app/src")

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path

from wws_adviser.core.config import Settings
from wws_adviser.core.db import create_app_engine, make_session_factory

SAMPLE_SH = ["510300", "515880", "510500"]
SAMPLE_SZ = ["159949", "159941", "512880"]


async def main() -> None:
    settings = Settings(env="dev", data_dir=Path("/data"))
    factory = make_session_factory(create_app_engine(settings))

    import urllib.request

    state = json.load(urllib.request.urlopen("http://127.0.0.1:8000/api/v1/market/state"))
    now = datetime.now().isoformat(timespec="seconds")
    print(f"=== {now} phase={state['phase']} is_trading_day={state['is_trading_day']} ===")
    if not state["is_trading_day"]:
        print("非交易日，跳过采样")
        return

    db = factory()
    try:
        from wws_adviser.core.time import now_utc_iso
        from wws_adviser.infrastructure.data_sources.akshare_quote import AKShareQuoteProvider
        from wws_adviser.modules.advice import service as advice_service
        from wws_adviser.modules.identity.models import User

        user = db.query(User).first()

        class _S:
            pass

        class _A:
            state = _S()

        class _R:
            app = _A()

        _R.app.state.quote_provider = AKShareQuoteProvider(env="dev")

        for code in SAMPLE_SH + SAMPLE_SZ:
            try:
                a = await advice_service.intraday_advice(
                    db, settings, _R(), user_id=user.id, code=code
                )
                stale = "data_stale" in a.reasons
                print(
                    f"{now_utc_iso()[:19]} | {state['phase']} | {code} | "
                    f"{a.action}/{a.state} | {','.join(a.reasons) or '-'} | "
                    f"stale={int(stale)}"
                )
            except Exception as exc:  # noqa: BLE001 — 单标的失败记录后继续
                print(f"{code} | ERROR | {type(exc).__name__}: {exc}")
    finally:
        db.close()


asyncio.run(main())
