"""东财板块资金流适配器（SectorFlowProvider）：push2delay clist 板榜，升降序各一页。

字段（niuone 生产验证钉住；本机网络对 clist 连接层重置，线上验证留 VPS——
5_DATA §13.6 开放点）：f12 板块代码(BKxxxx) f14 名称 f3 涨跌幅 f6 成交额(元)
f62 主力净流入额(元) f128 领涨股名称 f136 领涨股涨跌幅 f124 更新时间戳(unix 秒)；
fltt=2 时缺失值为 "-"。fid=f62 按主力净额排序，po=1/0 取双向榜单（净流入/净流出）。
多域名轮换（push2delay→push2→82.push2，https→http）吸收东财风控（ADR-0014）。
"""

import asyncio
from datetime import datetime
from typing import Any

from wws_adviser.core.time import SHANGHAI, now_utc_iso
from wws_adviser.ports.market_data import SourceDelayClass
from wws_adviser.ports.market_env import RawSectorFlow, SectorKind

from ._parsing import MarketEnvParseError, dec_or_zero

_FIELDS = "f12,f14,f3,f6,f62,f128,f136,f124"
_FS = {SectorKind.INDUSTRY: "m:90+t:2", SectorKind.CONCEPT: "m:90+t:3"}
_HOST_ROTATION = (
    "https://push2delay.eastmoney.com",
    "https://push2.eastmoney.com",
    "https://82.push2.eastmoney.com",
    "http://push2delay.eastmoney.com",
    "http://82.push2.eastmoney.com",
)


def parse_eastmoney_clist_payload(
    payload: dict[str, Any], *, kind: SectorKind, source_url: str
) -> list[RawSectorFlow]:
    """clist JSON → RawSectorFlow 列表；diff 缺失/类型突变抛 MarketEnvParseError。"""
    data = (payload or {}).get("data")
    if not isinstance(data, dict) or "diff" not in data:
        raise MarketEnvParseError("eastmoney clist 响应缺 data.diff（schema 突变）")
    diff = data["diff"]
    if not isinstance(diff, list):
        raise MarketEnvParseError("eastmoney clist data.diff 非 list（schema 突变）")
    now = now_utc_iso()
    out: list[RawSectorFlow] = []
    for row in diff:
        if not isinstance(row, dict):
            raise MarketEnvParseError(f"clist 行非对象：{row!r}")
        code = str(row.get("f12") or "").strip()
        name = str(row.get("f14") or "").strip()
        if not code or not name:
            raise MarketEnvParseError(f"clist 行缺板块代码/名称：{row!r}")
        leader = str(row.get("f128") or "").strip()
        out.append(
            RawSectorFlow(
                kind=kind,
                board_code=code,
                board_name=name,
                change_pct=dec_or_zero(row.get("f3")),
                turnover=dec_or_zero(row.get("f6")),
                net_main_inflow=dec_or_zero(row.get("f62")),
                source="eastmoney",
                source_url=source_url,
                market_time=_ts_to_market_time(row.get("f124")) or now,
                fetched_at=now,
                received_at=now,
                source_delay_class=SourceDelayClass.DELAYED.value,
                leader_name=leader if leader not in ("", "-") else None,
                leader_code=None,
            )
        )
    return out


def _ts_to_market_time(v: object) -> str | None:
    """f124 unix 秒 → 上海时区 "YYYY-MM-DD HH:MM:SS"；缺失/非法 → None。"""
    try:
        n = int(str(v).split(".")[0])
        if n <= 0:
            return None
        return datetime.fromtimestamp(n, tz=SHANGHAI).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OSError, OverflowError):
        return None


def _fetch_page_sync(kind: SectorKind, *, po: int) -> dict[str, Any]:
    import httpx

    params = {
        "pn": "1",
        "pz": "100",
        "po": str(po),
        "np": "1",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": "2",
        "invt": "2",
        "fid": "f62",
        "fs": _FS[kind],
        "fields": _FIELDS,
    }
    last_exc: Exception | None = None
    for base in _HOST_ROTATION:
        try:
            resp = httpx.get(
                f"{base}/api/qt/clist/get", params=params, timeout=10.0,
                headers={"Referer": "https://quote.eastmoney.com/"},
            )
            resp.raise_for_status()
            return dict(resp.json())
        except Exception as exc:  # noqa: BLE001 — 域名轮换：下一域
            last_exc = exc
    raise last_exc if last_exc else MarketEnvParseError("clist 全域名轮换失败")


class EastmoneySectorFlowProvider:
    """板块资金流：行业/概念各取主力净额升降序两页（~200 板/类，双向榜单全覆盖）。"""

    def __init__(self, *, env: str = "dev") -> None:
        self._env = env

    async def fetch_sector_flows(self, kind: SectorKind) -> list[RawSectorFlow]:
        url = f"eastmoney://sector-flows/{kind.value}"
        by_code: dict[str, RawSectorFlow] = {}
        for po in (1, 0):  # 降序（净流入榜）+ 升序（净流出榜）
            payload = await asyncio.to_thread(_fetch_page_sync, kind, po=po)
            for flow in parse_eastmoney_clist_payload(payload, kind=kind, source_url=url):
                by_code.setdefault(flow.board_code, flow)
        return list(by_code.values())
