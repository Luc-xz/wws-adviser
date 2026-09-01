"""Portfolio HTTP 流程测试：账户、交易录入、CSV 导入预览/确认、幂等去重、错误行拒绝、
软删（migrated_client，覆盖 AC-01）。"""

import pytest

from wws_adviser.modules.identity import service as identity_service
from wws_adviser.modules.portfolio import service as portfolio_service


def _login(client) -> None:
    identity_service.reset_login_rate_limit()
    r = client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "pw12345"},
        headers={"Idempotency-Key": "login"},
    )
    assert r.status_code == 200


def _csrf(client) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("csrf_token", "")}


def _csv_bytes(body: str) -> bytes:
    return body.encode("utf-8")


def _create_account(client, key: str = "acct") -> None:
    """登录后建账户（幂等）。"""
    client.post(
        "/api/v1/accounts",
        json={"name": "main"},
        headers={**_csrf(client), "Idempotency-Key": key},
    )


def _import_preview(client, csv_body: str, key: str):
    """发起一次 CSV 导入预览，返回响应 JSON。"""
    r = client.post(
        "/api/v1/transactions/import",
        files={"file": ("trades.csv", _csv_bytes(csv_body), "text/csv")},
        headers={**_csrf(client), "Idempotency-Key": key},
    )
    assert r.status_code == 200, r.text
    return r.json()


def _import_confirm(client, batch_id: str, fingerprints: list[str], key: str):
    """按 batch_id 确认导入，返回响应 JSON。"""
    r = client.post(
        "/api/v1/transactions/import/confirm",
        json={"batch_id": batch_id, "fingerprints": fingerprints},
        headers={**_csrf(client), "Idempotency-Key": key},
    )
    assert r.status_code == 200, r.text
    return r.json()


CSV_HEADER = "成交日期,证券代码,证券名称,买卖方向,成交数量,成交价格,手续费,印花税\n"


@pytest.fixture(autouse=True)
def _clean_staging() -> None:
    portfolio_service.reset_import_staging()


def test_create_account_requires_idempotency_key(migrated_client) -> None:
    _login(migrated_client)
    r = migrated_client.post(
        "/api/v1/accounts", json={"name": "main"}, headers=_csrf(migrated_client)
    )
    assert r.status_code == 400  # 缺 Idempotency-Key


def test_create_account_idempotent(migrated_client) -> None:
    _login(migrated_client)
    h = {**_csrf(migrated_client), "Idempotency-Key": "k1"}
    r1 = migrated_client.post(
        "/api/v1/accounts",
        json={"name": "main", "initial_cash": "100000"},
        headers=h,
    )
    assert r1.status_code == 200
    assert r1.json()["name"] == "main"
    assert r1.json()["initial_cash"] == "100000.00"
    r2 = migrated_client.post(
        "/api/v1/accounts",
        json={"name": "main", "initial_cash": "100000"},
        headers=h,
    )
    assert r2.status_code == 200
    assert r2.json()["id"] == r1.json()["id"]  # 幂等：同账户

    listing = migrated_client.get("/api/v1/accounts")
    assert listing.status_code == 200
    assert len(listing.json()) == 1


def test_csv_import_preview_confirm_and_dedup(migrated_client) -> None:
    _login(migrated_client)
    csrf = _csrf(migrated_client)
    migrated_client.post(
        "/api/v1/accounts",
        json={"name": "main"},
        headers={**csrf, "Idempotency-Key": "acct"},
    )

    csv_body = CSV_HEADER + "2026-08-13,600519,贵州茅台,买入,100,1800.50,5.00,1.80\n"

    # 预览（不落库）
    body = _import_preview(migrated_client, csv_body, key="preview1")
    assert len(body["preview"]) == 1
    assert body["errors"] == []
    assert body["duplicates"] == []
    fp = body["preview"][0]["fingerprint"]

    # 确认 → 落库 1 行
    confirm = _import_confirm(migrated_client, body["batch_id"], [fp], key="confirm1")
    assert confirm == {"created": 1, "skipped": 0}

    txns = migrated_client.get("/api/v1/transactions").json()
    assert len(txns["items"]) == 1
    assert txns["items"][0]["kind"] == "BUY"
    assert txns["items"][0]["fee"] == "5.00"

    # AC-01：重复导入同一行 → 预览判定为 duplicate
    body2 = _import_preview(migrated_client, csv_body, key="preview2")
    assert len(body2["preview"]) == 0
    assert len(body2["duplicates"]) == 1

    # 重复确认 → 0 created（不产生重复流水）
    confirm2 = _import_confirm(
        migrated_client, body2["batch_id"], [body2["duplicates"][0]["fingerprint"]], key="confirm2"
    )
    assert confirm2 == {"created": 0, "skipped": 1}
    assert len(migrated_client.get("/api/v1/transactions").json()["items"]) == 1


def test_csv_import_rejects_error_rows(migrated_client) -> None:
    _login(migrated_client)
    _create_account(migrated_client)

    csv_body = (
        CSV_HEADER
        + "2026-08-13,600519,贵州茅台,买入,100,1800.50,5.00,1.80\n"  # 有效
        + "2026-08-13,600519,贵州茅台,换股,100,1800.50,5.00,1.80\n"  # 未知方向 → error
    )
    body = _import_preview(migrated_client, csv_body, key="preview-err")
    assert len(body["preview"]) == 1
    assert len(body["errors"]) == 1
    assert "换股" in body["errors"][0]["message"]


def test_manual_transaction_idempotent_and_cross_path_dedup(migrated_client) -> None:
    _login(migrated_client)
    csrf = _csrf(migrated_client)
    _create_account(migrated_client)

    # 先经导入建一笔（并建标的 600519）
    csv_body = CSV_HEADER + "2026-08-13,600519,贵州茅台,买入,100,1800.50,5.00,1.80\n"
    pv = _import_preview(migrated_client, csv_body, key="pv")
    _import_confirm(migrated_client, pv["batch_id"], [pv["preview"][0]["fingerprint"]], key="cf")
    instrument_id = migrated_client.get("/api/v1/transactions").json()["items"][0]["instrument_id"]

    # 手工录入不同日期 → 新行（不同指纹）
    h = {**csrf, "Idempotency-Key": "m1"}
    r1 = migrated_client.post(
        "/api/v1/transactions",
        json={
            "instrument_id": instrument_id, "kind": "BUY",
            "quantity": "100", "price": "1800.50", "fee": "5.00",
            "trade_at": "2026-08-14",
        },
        headers=h,
    )
    assert r1.status_code == 200
    first_id = r1.json()["id"]

    # 同体重复手工录入 → 返回已存在，不建第二行（fingerprint 幂等）
    r2 = migrated_client.post(
        "/api/v1/transactions",
        json={
            "instrument_id": instrument_id, "kind": "BUY",
            "quantity": "100", "price": "1800.50", "fee": "5.00",
            "trade_at": "2026-08-14",
        },
        headers={**csrf, "Idempotency-Key": "m2"},
    )
    assert r2.status_code == 200
    assert r2.json()["id"] == first_id

    # 跨路径：手工录入与导入同指纹 → 返回已存在
    r3 = migrated_client.post(
        "/api/v1/transactions",
        json={
            "instrument_id": instrument_id, "kind": "BUY",
            "quantity": "100", "price": "1800.50", "fee": "5.00",
            "trade_at": "2026-08-13",
        },
        headers={**csrf, "Idempotency-Key": "m3"},
    )
    assert r3.status_code == 200
    # 该指纹对应的是导入那行，id 应不同于手工新行
    assert r3.json()["id"] != first_id

    items = migrated_client.get("/api/v1/transactions").json()["items"]
    assert len(items) == 2  # 导入 1 + 手工新 1


def test_transaction_list_cursor_pagination(migrated_client) -> None:
    _login(migrated_client)
    csrf = _csrf(migrated_client)
    _create_account(migrated_client)

    # 建标的 + 录入 3 笔不同日期
    inst = migrated_client.post(
        "/api/v1/transactions",
        json={
            "instrument_id": "_", "kind": "BUY",
            "quantity": "100", "price": "10", "trade_at": "2026-08-10",
        },
        headers={**csrf, "Idempotency-Key": "x"},
    )
    assert inst.status_code == 404  # instrument_id 不存在 → 404
    # 改用导入建标的
    csv_body = CSV_HEADER + "2026-08-10,600519,贵州茅台,买入,100,10.00,0,0\n"
    pv = _import_preview(migrated_client, csv_body, key="pv0")
    _import_confirm(migrated_client, pv["batch_id"], [pv["preview"][0]["fingerprint"]], key="cf0")
    instrument_id = migrated_client.get("/api/v1/transactions").json()["items"][0]["instrument_id"]

    for i, d in enumerate(["2026-08-11", "2026-08-12", "2026-08-13"], start=1):
        migrated_client.post(
            "/api/v1/transactions",
            json={
                "instrument_id": instrument_id, "kind": "BUY",
                "quantity": "100", "price": "10", "trade_at": d,
            },
            headers={**csrf, "Idempotency-Key": f"pg{i}"},
        )

    page1 = migrated_client.get("/api/v1/transactions", params={"limit": 2}).json()
    assert page1["has_more"] is True
    assert len(page1["items"]) == 2
    assert page1["next_cursor"] is not None
    # 最新在前
    assert page1["items"][0]["trade_at"] == "2026-08-13"

    page2 = migrated_client.get(
        "/api/v1/transactions", params={"limit": 2, "cursor": page1["next_cursor"]}
    ).json()
    assert len(page2["items"]) == 2  # 共 4 笔，第 2 页 2 笔
    assert page2["has_more"] is False


def test_soft_delete_transaction(migrated_client) -> None:
    _login(migrated_client)
    csrf = _csrf(migrated_client)
    _create_account(migrated_client)

    csv_body = CSV_HEADER + "2026-08-13,600519,贵州茅台,买入,100,1800.50,5.00,1.80\n"
    pv = _import_preview(migrated_client, csv_body, key="pv")
    _import_confirm(migrated_client, pv["batch_id"], [pv["preview"][0]["fingerprint"]], key="cf")
    txn_id = migrated_client.get("/api/v1/transactions").json()["items"][0]["id"]

    deleted = migrated_client.delete(f"/api/v1/transactions/{txn_id}", headers=csrf)
    assert deleted.status_code == 200
    items = migrated_client.get("/api/v1/transactions").json()["items"]
    assert len(items) == 0  # 软删后列表不再可见


# —— 对账机制（Phase 2 收官：ledger_unreconciled 降级的解除项）——


def _account_id(client) -> str:
    r = client.get("/api/v1/accounts")
    assert r.status_code == 200
    return r.json()[0]["id"]


def test_reconcile_marks_and_new_transaction_resets(migrated_client) -> None:
    _login(migrated_client)
    _create_account(migrated_client, key="recon-acct")
    aid = _account_id(migrated_client)
    assert migrated_client.get("/api/v1/accounts").json()[0]["reconciled"] is False

    # 对账确认 → True + 时间戳
    r = migrated_client.post(
        f"/api/v1/accounts/{aid}/reconcile", headers=_csrf(migrated_client)
    )
    assert r.status_code == 200
    assert r.json()["reconciled"] is True and r.json()["reconciled_at"]

    # 新交易入账 → 自动复位（经导入路径建一笔新交易）
    csv_body = CSV_HEADER + "2026-09-01,600519,贵州茅台,买入,100,1800.50,5.00,1.80\n"
    pv = _import_preview(migrated_client, csv_body, key="recon-pv")
    assert len(pv["preview"]) == 1
    _import_confirm(
        migrated_client, pv["batch_id"], [pv["preview"][0]["fingerprint"]], key="recon-cf"
    )
    acct = migrated_client.get("/api/v1/accounts").json()[0]
    assert acct["reconciled"] is False and acct["reconciled_at"] is None


def test_reconcile_wrong_account_404_and_requires_auth(migrated_client, client) -> None:
    # 未登录：CSRF/认证中间件先行拦截（401 或 403 均证明不可匿名调用）
    assert client.post("/api/v1/accounts/x/reconcile").status_code in (401, 403)
    _login(migrated_client)
    _create_account(migrated_client, key="recon-acct2")
    r = migrated_client.post(
        "/api/v1/accounts/01WRONGACCOUNTID000000/reconcile",
        headers=_csrf(migrated_client),
    )
    assert r.status_code == 404
