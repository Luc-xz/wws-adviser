"""Problem Details（RFC 9457）错误模型与全局异常处理。

错误码与 HTTP 映射见 3_API_CONTRACT.md §错误码表。`code` 是前端分支的键。
service 抛 DomainError，本模块统一翻译为 Problem Details（见 1_REPO_STRUCTURE.md §4.2）。
"""

from collections.abc import Iterable

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from wws_adviser.core.errors import DomainError
from wws_adviser.core.logging import request_id_var

# code → HTTP status（3_API_CONTRACT.md:188-207）
ERROR_STATUS: dict[str, int] = {
    "UNAUTHENTICATED": 401,
    "REAUTH_REQUIRED": 401,
    "FORBIDDEN": 403,
    "VALIDATION_ERROR": 422,
    "MISSING_IDEMPOTENCY_KEY": 400,
    "IDEMPOTENCY_CONFLICT": 409,
    "NOT_FOUND": 404,
    "CONFLICT": 409,
    "DATA_STALE": 409,
    "DATA_MISSING": 409,
    "DATA_CONFLICT": 409,
    "LEDGER_UNRECONCILED": 409,
    "MARKET_ABNORMAL": 409,
    "CALIBRATION_REJECTED": 409,
    "MODEL_UNAVAILABLE": 503,
    "RATE_LIMITED": 429,
    "DB_NOT_WRITABLE": 503,
    "INTERNAL_ERROR": 500,
}

ERROR_TITLE: dict[str, str] = {
    "UNAUTHENTICATED": "未认证",
    "REAUTH_REQUIRED": "需要重新认证",
    "FORBIDDEN": "无权限",
    "VALIDATION_ERROR": "参数校验失败",
    "MISSING_IDEMPOTENCY_KEY": "缺少幂等键",
    "IDEMPOTENCY_CONFLICT": "幂等冲突",
    "NOT_FOUND": "资源不存在",
    "CONFLICT": "冲突",
    "DATA_STALE": "数据过期",
    "DATA_MISSING": "数据缺失",
    "DATA_CONFLICT": "数据冲突",
    "LEDGER_UNRECONCILED": "账本未对账",
    "MARKET_ABNORMAL": "市场异常",
    "CALIBRATION_REJECTED": "校准被拒",
    "MODEL_UNAVAILABLE": "模型不可用",
    "RATE_LIMITED": "请求过于频繁",
    "DB_NOT_WRITABLE": "数据库不可写",
    "INTERNAL_ERROR": "内部错误",
}


def _slug(code: str) -> str:
    return code.lower().replace("_", "-")


def problem(
    code: str,
    detail: str,
    *,
    status: int | None = None,
    reasons: Iterable[str] | None = None,
    instance: str | None = None,
) -> JSONResponse:
    """构造 Problem Details 响应。"""
    http_status = status or ERROR_STATUS.get(code, 500)
    rid = request_id_var.get("")
    body: dict[str, object] = {
        "type": f"https://wws-adviser/errors/{_slug(code)}",
        "title": ERROR_TITLE.get(code, "内部错误"),
        "status": http_status,
        "detail": detail,
        "code": code,
    }
    if instance:
        body["instance"] = instance
    if rid:
        body["request_id"] = rid
    reason_list = list(reasons) if reasons else []
    if reason_list:
        body["reasons"] = reason_list
    headers = {"X-Request-ID": rid} if rid else None
    return JSONResponse(status_code=http_status, content=body, headers=headers)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain_error(_: Request, exc: DomainError) -> JSONResponse:
        return problem(
            exc.code, exc.detail, status=exc.status, reasons=exc.reasons
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        reasons = [f"{e.get('loc')}: {e.get('msg')}" for e in exc.errors()]
        return problem("VALIDATION_ERROR", "请求参数校验失败", status=422, reasons=reasons)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        # 兜底：未识别异常统一为 INTERNAL_ERROR，关联 request_id 便于排查
        return problem("INTERNAL_ERROR", "内部错误", status=500, reasons=[type(exc).__name__])
