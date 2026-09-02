"""SSE /api/v1/events 集成测试（doc7 §11）：认证、事件形态、任务过滤字段齐备。"""

import json

from wws_adviser.modules.identity import service as identity_service
from wws_adviser.modules.jobs import service as jobs_service
from wws_adviser.modules.jobs.domain import JobStatus, JobType


def _login(client) -> None:
    identity_service.reset_login_rate_limit()
    r = client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "pw12345"},
        headers={"Idempotency-Key": "login-sse"},
    )
    assert r.status_code == 200


def test_events_requires_auth(client) -> None:
    r = client.get("/api/v1/events")
    assert r.status_code in (401, 403)


def test_events_stream_emits_job_status(migrated_client, tmp_path) -> None:
    _login(migrated_client)
    app = migrated_client.app
    with app.state.session_factory() as db:
        from wws_adviser.core.config import Settings

        s = Settings(env="test", data_dir=tmp_path)
        job = jobs_service.enqueue(
            db, s, job_type=JobType.PRE_MARKET, business_date="2026-09-02", scope_key="sse-test"
        )
        claimed = jobs_service.claim_next(db, s)
        assert claimed is not None and claimed.id == job.id
        jobs_service.complete(db, job.id, result_ref="report://x")
        jid = job.id

    got = None
    with migrated_client.stream("GET", "/api/v1/events") as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        for line in resp.iter_lines():
            if line.startswith("data: "):
                payload = json.loads(line[len("data: "):])
                assert set(payload) >= {"event", "job_id", "status", "progress", "ts"}
                assert payload["event"] == "job_status"
                if payload["job_id"] == jid:
                    got = payload
                    break  # 收到目标任务事件即关流
    assert got is not None
    assert got["status"] == JobStatus.COMPLETED.value
