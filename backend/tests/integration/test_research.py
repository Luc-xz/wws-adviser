"""Research 模块测试：状态机、引用校验、任务 CRUD（Phase 3 波1）。"""

from fastapi.testclient import TestClient

# —— 状态机 ——


def test_research_task_state_machine() -> None:
    import pytest

    from wws_adviser.modules.research.domain import (
        ResearchStatus,
        transition,
    )

    s = ResearchStatus.PENDING
    s = transition(s, ResearchStatus.RUNNING)
    assert s is ResearchStatus.RUNNING
    s = transition(s, ResearchStatus.COMPLETED)
    assert s is ResearchStatus.COMPLETED

    # PENDING 可取消
    assert transition(ResearchStatus.PENDING, ResearchStatus.CANCELLED) is ResearchStatus.CANCELLED
    # RUNNING 不可取消（等完成）
    with pytest.raises(ValueError):
        transition(ResearchStatus.RUNNING, ResearchStatus.CANCELLED)
    # COMPLETED 是终态
    with pytest.raises(ValueError):
        transition(ResearchStatus.COMPLETED, ResearchStatus.RUNNING)


# —— 引用校验 ——


def test_validate_citations() -> None:
    from wws_adviser.modules.research.domain import (
        Citation,
        ResearchSection,
        SectionType,
        validate_citations,
    )

    # 事实段落无引用 → 违规
    fact_no_cite = ResearchSection(
        section_type=SectionType.OVERVIEW, title="概览",
        content="公司概览...", epistemic_type="fact",
    )
    assert len(validate_citations([fact_no_cite])) == 1

    # 推断段落无引用 → 不违规（inference 可以无引用）
    inference = ResearchSection(
        section_type=SectionType.RISKS, title="风险",
        content="可能面临...", epistemic_type="inference",
    )
    assert len(validate_citations([inference])) == 0

    # 有引用但未验证且无说明 → 违规
    unverified = ResearchSection(
        section_type=SectionType.FINANCIAL, title="财务",
        content="收入增长...", epistemic_type="fact",
        citations=(Citation(
            evidence_id="ev-1", section=SectionType.FINANCIAL,
            locator="p.12", content_hash="abc",
        ),),
    )
    assert len(validate_citations([unverified])) == 1

    # 有引用且已验证 → 通过
    verified = ResearchSection(
        section_type=SectionType.FINANCIAL, title="财务",
        content="收入增长...", epistemic_type="fact",
        citations=(Citation(
            evidence_id="ev-1", section=SectionType.FINANCIAL,
            locator="p.12", content_hash="abc", verified=True,
        ),),
    )
    assert len(validate_citations([verified])) == 0


# —— API ——


def _login(client: TestClient) -> dict[str, str]:
    r = client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "pw12345"},
        headers={"Idempotency-Key": "login-res-1"},
    )
    assert r.status_code == 200
    return {
        "x-csrf-token": r.cookies["csrf_token"],
        "Idempotency-Key": "res-1",
    }


def test_create_and_get_research_task(migrated_client: TestClient) -> None:
    headers = _login(migrated_client)
    r = migrated_client.post(
        "/api/v1/research/tasks",
        json={"task_type": "company", "subject": "600519", "depth": "standard"},
        headers=headers,
    )
    assert r.status_code == 200
    task = r.json()
    assert task["status"] == "PENDING"
    assert task["task_type"] == "company"

    # 幂等：同参数返回同任务
    r2 = migrated_client.post(
        "/api/v1/research/tasks",
        json={"task_type": "company", "subject": "600519", "depth": "standard"},
        headers={**headers, "Idempotency-Key": "res-2"},
    )
    assert r2.json()["id"] == task["id"]

    # 查询
    r3 = migrated_client.get(f"/api/v1/research/tasks/{task['id']}", headers=headers)
    assert r3.status_code == 200


def test_cancel_pending_task(migrated_client: TestClient) -> None:
    headers = _login(migrated_client)
    r = migrated_client.post(
        "/api/v1/research/tasks",
        json={"task_type": "industry", "subject": "半导体"},
        headers={**headers, "Idempotency-Key": "res-cancel-1"},
    )
    task_id = r.json()["id"]
    r2 = migrated_client.post(
        f"/api/v1/research/tasks/{task_id}/cancel", headers=headers,
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "CANCELLED"


def test_invalid_task_type_rejected(migrated_client: TestClient) -> None:
    headers = _login(migrated_client)
    r = migrated_client.post(
        "/api/v1/research/tasks",
        json={"task_type": "invalid", "subject": "x"},
        headers={**headers, "Idempotency-Key": "res-bad-1"},
    )
    assert r.status_code in (400, 422, 500)  # DomainError 或校验拒绝
