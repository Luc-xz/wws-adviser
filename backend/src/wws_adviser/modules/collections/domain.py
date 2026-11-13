"""Collections 领域：采集可观测性枚举、result_ref 解析、游标编解码。

纯领域，禁框架 import（对齐 jobs/documents domain 惯例，5_DATA §12）。
"""

import base64
from enum import StrEnum


class Category(StrEnum):
    """采集数据类别（source_health / ingest_items 共用；类别级，非物理源级）。"""

    QUOTE = "quote"
    BAR = "bar"
    NAV = "nav"
    CALENDAR = "calendar"
    DOCUMENT = "document"
    NEWS = "news"


class ItemStatus(StrEnum):
    """条目面板徽标态（区别于 quality_status 六态：条目是过程，记录是结果）。"""

    OK = "OK"
    PARTIAL = "PARTIAL"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


class ItemAction(StrEnum):
    INGESTED = "ingested"
    UPDATED = "updated"
    SKIPPED = "skipped"
    SYNCED = "synced"
    NO_DATA = "no_data"
    FAILED = "failed"


class HealthStatus(StrEnum):
    """源健康派生态（读取侧按连续失败阈值计算，不落库，5_DATA §12.1）。"""

    OK = "ok"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    NO_DATA = "no_data"


def parse_result_ref(ref: str | None) -> dict[str, object]:
    """job_runs.result_ref 兼容摘要解析（bars://3/1 等）；未知格式原样返回。

    明细以 ingest_items 为准（5_DATA §12.3）；本函数只服务批次列表的摘要列。
    """
    if not ref:
        return {}
    kind, sep, rest = ref.partition("://")
    if not sep or not rest:
        return {"raw": ref}
    if kind == "bars":
        ok_s, _, fail_s = rest.partition("/")
        return {"kind": "bars", "ok": _to_int(ok_s), "failed": _to_int(fail_s)}
    if kind == "docs":
        ing_s, _, tail = rest.partition("/")
        upd_s, _, skp_s = tail.partition("/")
        return {
            "kind": "docs",
            "ingested": _to_int(ing_s),
            "updated": _to_int(upd_s),
            "skipped": _to_int(skp_s),
        }
    if rest.isdigit():
        return {"kind": kind, "n": int(rest)}
    return {"kind": kind, "ref": rest}


def _to_int(s: str) -> int:
    try:
        return int(s)
    except ValueError:
        return 0


def encode_cursor(*, created_at: str, item_id: str) -> str:
    """排序键 → 不透明游标（base64url）。客户端原样回传，无需理解内容。"""
    raw = f"{created_at}|{item_id}".encode()
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_cursor(cursor: str) -> tuple[str, str]:
    """游标 → (created_at, id)。格式非法抛 ValueError（API 层转 400）。"""
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
    except Exception as exc:
        raise ValueError(f"游标不是合法 base64url: {exc}") from exc
    if "|" not in raw:
        raise ValueError("游标缺少分隔符")
    created_at, item_id = raw.split("|", 1)
    if not created_at or not item_id:
        raise ValueError("游标字段为空")
    return created_at, item_id
