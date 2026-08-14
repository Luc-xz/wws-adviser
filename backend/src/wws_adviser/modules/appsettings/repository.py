"""App settings 仓储：非敏感可调项 key-value 读写。"""

import json
from typing import Any

from sqlalchemy.orm import Session as DBSession

from wws_adviser.core.time import now_utc_iso
from wws_adviser.modules.appsettings.models import AppSetting


def get_value(db: DBSession, key: str) -> Any | None:
    row = db.get(AppSetting, key)
    if row is None:
        return None
    return json.loads(row.value_json)


def set_value(db: DBSession, key: str, value: Any) -> None:
    now = now_utc_iso()
    row = db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value_json=json.dumps(value), created_at=now, updated_at=now))
    else:
        row.value_json = json.dumps(value)
        row.updated_at = now
    db.flush()


def all_settings(db: DBSession) -> dict[str, Any]:
    return {row.key: json.loads(row.value_json) for row in db.query(AppSetting).all()}
