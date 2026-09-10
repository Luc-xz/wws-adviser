"""Advice 记录查询 API 集成测试（3_API §3.9：HOME-02 列表 / CHAT-02 详情 / 评价）。

数据准备走 service._persist 同构路径（直插 AdviceRecord），断言：
用户隔离、筛选、游标分页、降级记录不带区间、评价回读 404 语义。
"""

import json

from fastapi.testclient import TestClient

from wws_adviser.core.ids import new_id
from wws_adviser.core.time import now_utc_iso
from wws_adviser.modules.advice.models import AdviceRecord


def _login(client: TestClient) -> dict[str, str]:
    r = client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "pw12345"},
        headers={"Idempotency-Key": "login-advice-records-1"},
    )
    assert r.status_code == 200
    return {"x-csrf-token": r.cookies["csrf_token"]}


def _seed_record(db, *, user_id: str, **overrides: object) -> AdviceRecord:
    now = now_utc_iso()
    fields: dict[str, object] = dict(
        id=new_id(), user_id=user_id, signal_id="", code="600519",
        action="suspend", state="degraded",
        valid_from=now, expires_at=now,
        reasons_json=json.dumps(["no_calibrated_signal"]),
        trail_json="[]", evidence_json="[]",
        created_at=now, updated_at=now, row_version=1,
    )
    fields.update(overrides)
    row = AdviceRecord(**fields)  # type: ignore[arg-type]
    db.add(row)
    db.commit()
    return row


def _alice_id(client: TestClient) -> str:
    from sqlalchemy import select

    from wws_adviser.modules.identity.models import User

    with client.app.state.session_factory() as db:
        return db.scalar(select(User).where(User.username == "alice")).id


def test_list_requires_auth(client: TestClient) -> None:
    r = client.get("/api/v1/advice")
    assert r.status_code == 401


def test_list_returns_records_newest_first(migrated_client: TestClient) -> None:
    _login(migrated_client)
    uid = _alice_id(migrated_client)
    with migrated_client.app.state.session_factory() as db:
        older = _seed_record(db, user_id=uid)
        newer = _seed_record(db, user_id=uid, code="000001")

    r = migrated_client.get("/api/v1/advice")
    assert r.status_code == 200
    body = r.json()
    ids = [i["advice_id"] for i in body["items"]]
    assert ids.index(newer.id) < ids.index(older.id)
    # 字段齐备：降级形态 reasons 携带原因码、区间为 None
    item = next(i for i in body["items"] if i["advice_id"] == older.id)
    assert item["action"] == "suspend" and item["state"] == "degraded"
    assert item["reasons"] == ["no_calibrated_signal"]
    assert item["f_min"] is None and item["f_max"] is None
    assert item["actionable"] is False


def test_list_filters_by_code_and_action(migrated_client: TestClient) -> None:
    _login(migrated_client)
    uid = _alice_id(migrated_client)
    with migrated_client.app.state.session_factory() as db:
        _seed_record(db, user_id=uid, code="600519", action="suspend")
        _seed_record(db, user_id=uid, code="000001", action="hold", state="published")

    r = migrated_client.get("/api/v1/advice", params={"code": "000001"})
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1 and items[0]["code"] == "000001"

    r = migrated_client.get("/api/v1/advice", params={"action": "hold"})
    items = r.json()["items"]
    assert len(items) == 1 and items[0]["action"] == "hold"


def test_list_pagination_cursor(migrated_client: TestClient) -> None:
    _login(migrated_client)
    uid = _alice_id(migrated_client)
    with migrated_client.app.state.session_factory() as db:
        for i in range(3):
            _seed_record(
                db, user_id=uid, code=f"60051{i}",
                created_at=f"2026-09-10T10:00:0{i}+00:00",
                updated_at=f"2026-09-10T10:00:0{i}+00:00",
            )

    r1 = migrated_client.get("/api/v1/advice", params={"limit": 2})
    body1 = r1.json()
    assert len(body1["items"]) == 2 and body1["has_more"] is True

    r2 = migrated_client.get(
        "/api/v1/advice", params={"limit": 2, "cursor": body1["next_cursor"]}
    )
    body2 = r2.json()
    assert len(body2["items"]) == 1 and body2["has_more"] is False
    # 两页合并 = 全量且不重复
    ids1 = {i["advice_id"] for i in body1["items"]}
    ids2 = {i["advice_id"] for i in body2["items"]}
    assert ids1.isdisjoint(ids2) and len(ids1 | ids2) == 3


def test_detail_includes_published_fields_and_evaluation(
    migrated_client: TestClient,
) -> None:
    _login(migrated_client)
    uid = _alice_id(migrated_client)
    with migrated_client.app.state.session_factory() as db:
        row = _seed_record(
            db, user_id=uid, action="buy", state="published",
            f_min="0.025", f_max="0.030", suggested_lots=2,
            trail_json=json.dumps(
                [{"kind": "clip_single_cap", "note": "单标的上限",
                  "before": "0.05", "after": "0.03"}]
            ),
            verdict="direction_correct",
            evaluated_at="2026-09-10T08:30:00+00:00",
            evaluation_json=json.dumps(
                {"spec_version": "1", "reasons": ["窗口收益为正"],
                 "direction_return": "0.031", "horizon": 5}
            ),
        )

    r = migrated_client.get(f"/api/v1/advice/{row.id}")
    assert r.status_code == 200
    d = r.json()
    assert d["actionable"] is True
    assert d["f_min"] == "0.025" and d["f_max"] == "0.030"
    assert d["trail"][0]["kind"] == "clip_single_cap"
    assert d["verdict"] == "direction_correct"
    assert d["evaluation"]["horizon"] == 5

    ev = migrated_client.get(f"/api/v1/advice/{row.id}/evaluation").json()
    assert ev["verdict"] == "direction_correct"
    assert ev["direction_return"] == "0.031"
    assert ev["reasons"] == ["窗口收益为正"]


def test_detail_not_found_and_user_isolation(migrated_client: TestClient) -> None:
    _login(migrated_client)
    with migrated_client.app.state.session_factory() as db:
        from wws_adviser.core.ids import new_id as _new_id
        from wws_adviser.modules.identity import domain as identity_domain
        from wws_adviser.modules.identity import models as identity_models

        now = now_utc_iso()
        bob = identity_models.User(
            id=_new_id(), username="bob",
            password_hash=identity_domain.hash_password("pw12345"),
            created_at=now, updated_at=now, version=1,
        )
        db.add(bob)
        db.commit()
        other = _seed_record(db, user_id=bob.id)

    r = migrated_client.get(f"/api/v1/advice/{other.id}")
    assert r.status_code == 404
    assert r.json()["code"] == "NOT_FOUND"

    r = migrated_client.get("/api/v1/advice/nonexistent")
    assert r.status_code == 404

    r = migrated_client.get("/api/v1/advice/nonexistent/evaluation")
    assert r.status_code == 404
