"""Problem Details 错误模型测试（3_API_CONTRACT.md §错误码）。"""

import json

from wws_adviser.api.errors import ERROR_STATUS, problem
from wws_adviser.core.errors import DomainError


def test_problem_basic():
    resp = problem("DATA_STALE", "行情延迟", reasons=["age>180s"])
    assert resp.status_code == 409
    body = json.loads(resp.body)
    assert body["code"] == "DATA_STALE"
    assert body["status"] == 409
    assert body["detail"] == "行情延迟"
    assert body["reasons"] == ["age>180s"]
    assert body["type"].endswith("/data-stale")
    assert body["title"] == "数据过期"


def test_problem_unknown_code_defaults_500():
    resp = problem("SOMETHING_NEW", "x")
    assert resp.status_code == 500
    assert json.loads(resp.body)["code"] == "SOMETHING_NEW"


def test_all_error_codes_have_status():
    """错误码表完整性：每个 code 都有 HTTP 映射。"""
    expected = {
        "UNAUTHENTICATED", "REAUTH_REQUIRED", "FORBIDDEN", "VALIDATION_ERROR",
        "MISSING_IDEMPOTENCY_KEY", "IDEMPOTENCY_CONFLICT", "NOT_FOUND", "CONFLICT",
        "DATA_STALE", "DATA_MISSING", "DATA_CONFLICT", "LEDGER_UNRECONCILED",
        "MARKET_ABNORMAL", "CALIBRATION_REJECTED", "MODEL_UNAVAILABLE",
        "RATE_LIMITED", "DB_NOT_WRITABLE", "INTERNAL_ERROR",
    }
    assert set(ERROR_STATUS) == expected


def test_domain_subclass_carries_code():
    class StaleError(DomainError):
        code = "DATA_STALE"
        status = 409
        title = "数据过期"

    err = StaleError("行情延迟", reasons=["x"])
    assert err.code == "DATA_STALE"
    assert err.status == 409
    assert err.reasons == ["x"]
