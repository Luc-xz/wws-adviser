"""AKShare 日线适配器（BarProvider）——脚手架。

akshare 为 optional extra（重依赖：pandas/numpy/JS 引擎），**懒加载**：未安装时本模块仍可
导入，仅当 settings.market_data_source=="akshare" 且可导入时由 main.py 构造。
真实 akshare 调用 + DF 获取留待国内 VPS 实录验证；`rows_to_dataset` 为纯函数，可单测（无 pandas）。
"""

import asyncio
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from wws_adviser.core.time import now_utc_iso
from wws_adviser.ports.market_data import BarRow, InstrumentRef, RawDataset, SourceDelayClass

_TENCENT_KLINE_URL = "https://ifzq.gtimg.cn/appstock/app/fqkline/get"


def _dec(v: object) -> Decimal:
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _parse_date(s: object) -> date:
    return date.fromisoformat(str(s)[:10])


def rows_to_dataset(
    rows: list[dict[str, Any]], *, source: str, source_url: str
) -> RawDataset:
    """akshare DF 记录（中文列名）→ RawDataset。纯函数，可单测。"""
    now = now_utc_iso()
    bars = [
        BarRow(
            date=_parse_date(r.get("日期", r.get("date", ""))),
            open=_dec(r.get("开盘", 0)),
            high=_dec(r.get("最高", 0)),
            low=_dec(r.get("最低", 0)),
            close=_dec(r.get("收盘", 0)),
            volume=_dec(r.get("成交量", 0)),
        )
        for r in rows
    ]
    return RawDataset(
        source=source,
        source_url=source_url,
        market_time=now,
        fetched_at=now,
        received_at=now,
        source_delay_class=SourceDelayClass.END_OF_DAY,
        bars=bars,
    )


class AKShareBarProvider:
    """股票用 stock_zh_a_hist，ETF 用 fund_etf_hist_em。"""

    def __init__(self, *, env: str = "dev", adjust: str = "") -> None:
        self._env = env
        self._adjust = adjust  # "" | "qfq" | "hfq"

    def _fetch_df(
        self, ak: Any, instrument: InstrumentRef, start: date, end: date
    ) -> Any:
        start_s, end_s = start.strftime("%Y%m%d"), end.strftime("%Y%m%d")
        if instrument.kind.lower() == "etf":
            return ak.fund_etf_hist_em(
                symbol=instrument.code, period="daily",
                start_date=start_s, end_date=end_s, adjust=self._adjust,
            )
        return ak.stock_zh_a_hist(
            symbol=instrument.code, period="daily",
            start_date=start_s, end_date=end_s, adjust=self._adjust,
        )

    def _fetch_tencent_bars(
        self, instrument: InstrumentRef, start: date, end: date
    ) -> RawDataset:
        """腾讯日线（qfq 优先，day 兜底）。东财封锁期 fallback。"""
        import httpx

        from wws_adviser.infrastructure.data_sources.akshare_quote import tencent_symbol

        sym = tencent_symbol(instrument.market, instrument.code)
        params = {"param": f"{sym},day,{start.isoformat()},{end.isoformat()},640,qfq"}
        resp = httpx.get(_TENCENT_KLINE_URL, params=params, timeout=15.0)
        resp.raise_for_status()
        payload = (resp.json().get("data") or {}).get(sym) or {}
        days = payload.get("qfqday") or payload.get("day") or []
        # 腾讯行结构：[日期, 开, 收, 高, 低, 成交量(手)] → rows_to_dataset 中文列
        rows = [
            {"日期": d[0], "开盘": d[1], "收盘": d[2], "最高": d[3], "最低": d[4],
             "成交量": d[5] if len(d) > 5 else 0}
            for d in days
        ]
        return rows_to_dataset(
            rows, source="tencent", source_url=f"tencent://bars/{instrument.code}"
        )

    async def fetch_daily_bars(
        self, instrument: InstrumentRef, start: date, end: date
    ) -> RawDataset:
        import akshare as ak  # type: ignore[import-not-found]

        # 东财滚动风控重试；全败 → 腾讯日线 fallback（2026-08 实测东财封锁可持续数日）
        last_exc: Exception | None = None
        df: Any = None
        for delay in (0, 2, 5):
            if delay:
                await asyncio.sleep(delay)
            try:
                df = await asyncio.to_thread(self._fetch_df, ak, instrument, start, end)
                break
            except Exception as exc:  # noqa: BLE001 — 传输层抖动重试
                last_exc = exc
        if df is None or getattr(df, "empty", False):
            # 空 DF 也是封锁形态（200 + 空结果）——走腾讯备源
            try:
                return await asyncio.to_thread(
                    self._fetch_tencent_bars, instrument, start, end
                )
            except Exception as fallback_exc:  # noqa: BLE001 — 备源失败上抛主源异常
                raise last_exc from fallback_exc
        rows: list[dict[str, Any]] = list(df.to_dict("records"))
        return rows_to_dataset(
            rows, source="akshare", source_url=f"akshare://bars/{instrument.code}"
        )
