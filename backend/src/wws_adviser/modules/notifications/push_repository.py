"""Push 订阅仓储（Phase 3.5 P1）：登记（endpoint 幂等）/ 列活跃 / 撤销。"""

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from wws_adviser.core.ids import new_id
from wws_adviser.core.time import now_utc_iso
from wws_adviser.modules.notifications.models import PushSubscription


def upsert(
    db: DBSession,
    *,
    user_id: str,
    endpoint: str,
    p256dh: str,
    auth: str,
) -> tuple[PushSubscription, bool]:
    """按 endpoint 幂等登记；换 key（权限重置后重新订阅）则更新。返回 (行, 是否新建)。"""
    row = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == endpoint))
    if row is not None:
        if row.p256dh != p256dh or row.auth != auth or row.revoked_at is not None:
            row.p256dh, row.auth = p256dh, auth
            row.revoked_at = None
            row.user_id = user_id
            row.updated_at = now_utc_iso()
            db.commit()
        return row, False
    now = now_utc_iso()
    created = PushSubscription(
        id=new_id(), user_id=user_id, endpoint=endpoint,
        p256dh=p256dh, auth=auth, created_at=now, updated_at=now,
    )
    db.add(created)
    db.commit()
    return created, True


def list_active(db: DBSession, *, user_id: str | None = None) -> list[PushSubscription]:
    stmt = select(PushSubscription).where(PushSubscription.revoked_at.is_(None))
    if user_id is not None:
        stmt = stmt.where(PushSubscription.user_id == user_id)
    return list(db.scalars(stmt).all())


def get_by_endpoint(db: DBSession, endpoint: str) -> PushSubscription | None:
    return db.scalar(select(PushSubscription).where(PushSubscription.endpoint == endpoint))


def revoke(db: DBSession, sub_id: str) -> None:
    """推送服务返回 404/410（订阅失效）时软撤销。"""
    row = db.get(PushSubscription, sub_id)
    if row is None or row.revoked_at is not None:
        return
    row.revoked_at = now_utc_iso()
    row.updated_at = now_utc_iso()
    db.commit()


def delete(db: DBSession, sub_id: str, user_id: str) -> bool:
    """用户主动解绑（前端 unsubscribe 后调用）。"""
    row = db.get(PushSubscription, sub_id)
    if row is None or row.user_id != user_id:
        return False
    db.delete(row)
    db.commit()
    return True
