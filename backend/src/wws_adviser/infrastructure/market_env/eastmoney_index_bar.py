"""东财指数日 K 适配器（IndexBarProvider）：push2his 主源 + 腾讯日 K 兜底（v1 仅 CN）。

线上格式（2026-11-16 实录钉住）：data.klines 行 "日期,开,收,高,低,量,额(元)"
——注意 开/收 在 高/低 之前（fields2 f51-f57 顺序），解析须按位映射不可想当然。
"""

import asyncio
from datetime import date
from decimal import Decimal
from typing import Any

from wws_adviser.core.time import now_utc_iso
from wws_adviser.ports.market_data import BarRow, RawDataset, SourceDelayClass
from wws_adviser.ports.market_env import IndexRef

from ._parsing import MarketEnvParseError, dec_or_zero

_EM_KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
_TENCENT_KLINE_URL = "https://ifzq.gtimg.cn/appstock/app/fqkline/get"


def parse_eastmoney_kline_payload(
    payload: dict[str, Any], *, source_url: str
) -> RawDataset:
    """push2his kline JSON → RawDataset（按行结构校验，坏行抛 MarketEnvParseError）。"""
    data = (payload or {}).get("data") or {}
    klines = data.get("klines")
    if not isinstance(klines, list):
        raise MarketEnvParseError("eastmoney kline 响应缺 data.klines（schema 突变）")
    now = now_utc_iso()
    bars: list[BarRow] = []
    for row in klines:
        parts = str(row).split(",")
        if len(parts) < 6:
            raise MarketEnvParseError(f"kline 行字段不足：{row!r}")
        try:
            bars.append(
                BarRow(
                    date=date.fromisoformat(parts[0][:10]),
                    open=dec_or_zero(parts[1]),
                    close=dec_or_zero(parts[2]),
                    high=dec_or_zero(parts[3]),
                    low=dec_or_zero(parts[4]),
                    volume=dec_or_zero(parts[5]),
                )
            )
        except ValueError as exc:
            raise MarketEnvParseError(f"kline 行无法解析：{row!r}") from exc
    return RawDataset(
        source="eastmoney",
        source_url=source_url,
        market_time=now,
        fetched_at=now,
        received_at=now,
        source_delay_class=SourceDelayClass.END_OF_DAY,
        bars=bars,
    )


def _parse_tencent_kline_payload(
    payload: dict[str, Any], *, symbol: str, source_url: str
) -> RawDataset:
    """腾讯日 K 兜底：data.<sym>.day 行 [日期,开,收,高,低,量(手)]。"""
    days = ((payload or {}).get("data") or {}).get(symbol) or {}
    rows = days.get("day") or []
    now = now_utc_iso()
    bars: list[BarRow] = []
    for d in rows:
        if len(d) < 6:
            raise MarketEnvParseError(f"tencent kline 行字段不足：{d!r}")
        try:
            bars.append(
                BarRow(
                    date=date.fromisoformat(str(d[0])[:10]),
                    open=Decimal(str(d[1])),
                    close=Decimal(str(d[2])),
                    high=Decimal(str(d[3])),
                    low=Decimal(str(d[4])),
                    volume=Decimal(str(d[5])),
                )
            )
        except (ValueError, ArithmeticError) as exc:
            raise MarketEnvParseError(f"tencent kline 行无法解析：{d!r}") from exc
    return RawDataset(
        source="tencent",
        source_url=source_url,
        market_time=now,
        fetched_at=now,
        received_at=now,
        source_delay_class=SourceDelayClass.END_OF_DAY,
        bars=bars,
    )


def _fetch_em_sync(secid: str, start: date, end: date) -> dict[str, Any]:
    import httpx

    params = {
        "secid": secid,
        "klt": "101",
        "fqt": "0",
        "lmt": "100000",  # 全量由 start/end 过滤（dktotal ~8800，2026-11 实录）
        "end": "20500101",
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57",
    }
    resp = httpx.get(
        _EM_KLINE_URL, params=params, timeout=15.0,
        headers={"Referer": "https://quote.eastmoney.com/"},
    )
    resp.raise_for_status()
    return dict(resp.json())


def _fetch_tencent_sync(symbol: str, start: date, end: date) -> dict[str, Any]:
    import httpx

    params = {"param": f"{symbol},day,{start.isoformat()},{end.isoformat()},640,"}
    resp = httpx.get(
        _TENCENT_KLINE_URL, params=params, timeout=15.0,
        headers={"Referer": "https://gu.qq.com/"},
    )
    resp.raise_for_status()
    return dict(resp.json())


class EastmoneyIndexBarProvider:
    """指数日 K：东财 push2his 主源，腾讯日 K 兜底。v1 仅 CN 指数（无 secid 即拒绝）。"""

    def __init__(self, *, env: str = "dev") -> None:
        self._env = env

    async def fetch_index_bars(self, ref: IndexRef, start: date, end: date) -> RawDataset:
        secid = ref.symbol_map.get("eastmoney")
        if not secid:
            raise MarketEnvParseError(f"指数 {ref.code} 无 eastmoney secid（v1 日 K 仅 CN）")
        url = f"eastmoney://index-bars/{ref.code}"
        try:
            payload = await asyncio.to_thread(_fetch_em_sync, secid, start, end)
            ds = parse_eastmoney_kline_payload(payload, source_url=url)
        except MarketEnvParseError:
            raise  # schema 突变不是传输故障，不吞
        except Exception:  # noqa: BLE001 — 传输失败走腾讯兜底
            ds = RawDataset(source="eastmoney", source_url=url, market_time="",
                            fetched_at="", received_at="",
                            source_delay_class=SourceDelayClass.END_OF_DAY, bars=[])
        if ds.bars:
            return self._range(ds, start, end)
        # 空结果（封锁形态之一：200+空）→ 腾讯兜底
        tencent_sym = ref.symbol_map.get("tencent")
        if not tencent_sym:
            raise MarketEnvParseError(f"指数 {ref.code} 日 K 主源空且无腾讯兜底")
        payload = await asyncio.to_thread(_fetch_tencent_sync, tencent_sym, start, end)
        ds = _parse_tencent_kline_payload(
            payload, symbol=tencent_sym, source_url=f"tencent://index-bars/{ref.code}"
        )
        return self._range(ds, start, end)

    @staticmethod
    def _range(ds: RawDataset, start: date, end: date) -> RawDataset:
        bars = [b for b in ds.bars if start <= b.date <= end]
        return RawDataset(
            source=ds.source, source_url=ds.source_url, market_time=ds.market_time,
            fetched_at=ds.fetched_at, received_at=ds.received_at,
            source_delay_class=ds.source_delay_class, bars=bars,
        )
