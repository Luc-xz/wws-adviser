"""/api/v1/market-env 端点（3_API §3.18，需登录）——市场环境查询面。

研究上下文数据（ADR-0014 决策 5）：缺失/陈旧如实体现在 freshness 与空集合，
不产生 PAUSE_ADVICE / 降级错误语义。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session as DBSession

from wws_adviser.api.dependencies import get_current_user, get_session, get_settings
from wws_adviser.core.config import Settings
from wws_adviser.modules.identity.models import User
from wws_adviser.modules.market_env import repository, schemas, service
from wws_adviser.modules.market_env.domain import INDEX_BY_CODE

router = APIRouter(prefix="/api/v1/market-env", tags=["market-env"])

DBDep = Annotated[DBSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
UserDep = Annotated[User, Depends(get_current_user)]


@router.get("/overview", response_model=schemas.MarketEnvOverview)
async def get_overview(
    db: DBDep, settings: SettingsDep, _user: UserDep
) -> schemas.MarketEnvOverview:
    data = service.overview(db, settings)
    return schemas.MarketEnvOverview(**data)  # type: ignore[arg-type]


@router.get("/indices", response_model=list[schemas.IndexQuoteOut])
async def list_indices(
    db: DBDep,
    _user: UserDep,
    group: Annotated[str | None, Query()] = None,
) -> list[schemas.IndexQuoteOut]:
    rows = repository.latest_index_quotes(db, group=group)
    out: list[schemas.IndexQuoteOut] = []
    for row in rows:
        ref = INDEX_BY_CODE.get(row.index_code)
        if group is not None and (ref is None or ref.market_group != group):
            continue
        out.append(
            schemas.IndexQuoteOut(
                code=row.index_code,
                name=ref.name if ref else row.index_code,
                group=ref.market_group if ref else "unknown",
                price=row.price,
                change_pct=row.change_pct,
                volume=row.volume,
                amount=row.amount,
                market_time=row.market_time,
            )
        )
    return out


@router.get("/indices/{code}/bars", response_model=schemas.IndexBarsResponse)
async def get_index_bars(
    code: str,
    db: DBDep,
    _user: UserDep,
    start: Annotated[str | None, Query()] = None,
    end: Annotated[str | None, Query()] = None,
) -> schemas.IndexBarsResponse:
    if code not in INDEX_BY_CODE:
        raise HTTPException(status_code=404, detail=f"未注册指数：{code}")
    rows = repository.list_index_bars(db, code, start=start, end=end)
    return schemas.IndexBarsResponse(
        code=code,
        source=rows[-1].source if rows else None,
        items=[
            schemas.IndexBarOut(
                business_date=r.business_date,
                open=r.open,
                high=r.high,
                low=r.low,
                close=r.close,
                volume=r.volume,
                amount=r.amount,
            )
            for r in rows
        ],
    )


@router.get("/sectors/flows", response_model=list[schemas.SectorFlowOut])
async def get_sector_flows(
    db: DBDep,
    _user: UserDep,
    kind: Annotated[str, Query()] = "industry",
    top: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[schemas.SectorFlowOut]:
    if kind not in ("industry", "concept"):
        raise HTTPException(status_code=422, detail="kind 须为 industry|concept")
    rows = repository.latest_sector_flows(db, kind=kind, limit=top)
    out: list[schemas.SectorFlowOut] = []
    for r in rows:
        e = service.sector_entry(db, r)
        out.append(
            schemas.SectorFlowOut(
                board_code=str(e["board_code"]),
                kind=str(e["kind"]),
                board_name=str(e["board_name"]),
                change_pct=e["change_pct"],
                turnover=e["turnover"],
                net_main_inflow=e["net_main_inflow"],
                leader_name=e["leader_name"],
                snapshot_at=str(e["snapshot_at"]),
            )
        )
    return out
