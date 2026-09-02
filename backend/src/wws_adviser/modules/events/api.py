"""/api/v1/events：SSE 任务状态流（doc7 §11 / 6_MODEL §9 / 3_API §3.13）。

事件载荷仅 {event, job_id, status, progress, ts}——不含持仓/敏感数值。
EventSource 同源带 cookie 认证；轮询 job_runs 变化推送，注释行保活；
客户端断开或流上限（10 分钟）自动收流。每轮短会话查询，不长期持有读连接。
"""

import asyncio
import json
import time
from collections.abc import AsyncIterator, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from wws_adviser.api.dependencies import get_current_user, get_session
from wws_adviser.core.time import now_utc_iso
from wws_adviser.modules.identity.models import User
from wws_adviser.modules.jobs.models import JobRun

router = APIRouter(prefix="/api/v1", tags=["events"])

DBDep = Annotated[DBSession, Depends(get_session)]
UserDep = Annotated[User, Depends(get_current_user)]

# 单流时长上限（秒）：EventSource 断线自动重连，无需服务端无限续
_STREAM_MAX_SECONDS = 600
_POLL_INTERVAL = 1.0
_KEEPALIVE_EVERY = 15.0

_TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}


async def _event_stream(
    request: Request, session_factory: Callable[[], DBSession]
) -> AsyncIterator[str]:
    last: dict[str, tuple[str, int | None]] = {}
    started = time.monotonic()
    last_beat = 0.0
    while time.monotonic() - started < _STREAM_MAX_SECONDS:
        if await request.is_disconnected():
            return
        with session_factory() as db:
            rows = db.execute(
                select(JobRun.id, JobRun.status, JobRun.progress)
                .order_by(JobRun.created_at.desc())
                .limit(20)
            ).all()
        emitted = False
        all_terminal = True
        for jid, status, progress in rows:
            key = (status, progress)
            if last.get(jid) != key:
                last[jid] = key
                payload = json.dumps(
                    {
                        "event": "job_status",
                        "job_id": jid,
                        "status": status,
                        "progress": progress,
                        "ts": now_utc_iso(),
                    },
                    ensure_ascii=False,
                )
                yield f"data: {payload}\n\n"
                emitted = True
            if status not in _TERMINAL:
                all_terminal = False
        if emitted:
            # 本轮有事件且任务已全部终态：推完即收流（客户端也自会关闭）
            if all_terminal and last:
                return
            await asyncio.sleep(_POLL_INTERVAL)
            continue
        now = time.monotonic()
        if now - last_beat >= _KEEPALIVE_EVERY:
            last_beat = now
            yield ": keepalive\n\n"
        await asyncio.sleep(_POLL_INTERVAL)


@router.get("/events")
async def events(request: Request, db: DBDep, user: UserDep) -> StreamingResponse:
    # 流期间不复用请求级会话（会随请求关闭）；改用工厂开短会话逐轮查询
    session_factory = request.app.state.session_factory
    return StreamingResponse(
        _event_stream(request, session_factory),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
