"""Model gateway 仓储：默认 profile 播种 + 调用审计插入。"""

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from wws_adviser.core.config import Settings
from wws_adviser.core.ids import new_id
from wws_adviser.core.time import now_utc_iso
from wws_adviser.modules.model_gateway.models import ModelCall, ModelProfile


def upsert_default_profile(db: DBSession, settings: Settings) -> ModelProfile:
    """按当前配置播种/更新默认 profile（name='default'）。key_ref 只存 env 变量名。"""
    import json

    existing = db.scalar(select(ModelProfile).where(ModelProfile.name == "default"))
    now = now_utc_iso()
    if existing is not None:
        existing.base_url = settings.model_base_url
        existing.model_name = settings.model_name
        existing.key_ref = settings.model_api_key_ref
        existing.temperature = settings.model_temperature
        existing.max_tokens = settings.model_max_tokens
        existing.timeout = settings.model_timeout
        existing.retry = settings.model_retry
        existing.task_routes_json = json.dumps({"default": settings.model_name})
        existing.updated_at = now
        existing.version += 1
        db.flush()
        return existing
    profile = ModelProfile(
        id=new_id(),
        name="default",
        base_url=settings.model_base_url,
        model_name=settings.model_name,
        key_ref=settings.model_api_key_ref,
        temperature=settings.model_temperature,
        max_tokens=settings.model_max_tokens,
        timeout=settings.model_timeout,
        retry=settings.model_retry,
        task_routes_json=json.dumps({"default": settings.model_name}),
        created_at=now,
        updated_at=now,
        version=1,
    )
    db.add(profile)
    db.flush()
    return profile


def insert_call(db: DBSession, call: ModelCall) -> ModelCall:
    db.add(call)
    db.flush()
    return call
