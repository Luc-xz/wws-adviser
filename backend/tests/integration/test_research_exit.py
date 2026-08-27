"""Phase 3 退出条件测试（波8）：

- 引用可追溯：报告每条 fact 引用 → Evidence 行 → 文档 + 内容哈希可复盘重算
- 异步体验稳定：离开页面仍完成 / 完成后订阅立即收终态 / 失败不卡死 /
  终态后可重建同任务 / 进度单调不减
"""

import asyncio
import hashlib
import pathlib
import tempfile

from fastapi.testclient import TestClient
from sqlalchemy import select

from wws_adviser.core.ids import new_id
from wws_adviser.core.time import now_utc_iso
from wws_adviser.modules.documents.models import Document, DocumentLink, Evidence
from wws_adviser.modules.instruments import service as instruments_service
from wws_adviser.modules.research import service as research_service
from wws_adviser.modules.research.evidence import slice_document


def _seed_doc(db, *, title: str, text: str, code: str = "600519") -> None:
    from wws_adviser.modules.documents.repository import index_document_fts

    doc = Document(
        id=new_id(), kind="announcement", title=title, source="test", source_url=None,
        content_sha256=hashlib.sha256(title.encode()).hexdigest(),
        trust_level="official", quality_status="OK",
        published_at="2026-08-01", created_at=now_utc_iso(), updated_at=now_utc_iso(),
    )
    db.add(doc)
    db.flush()
    p = pathlib.Path(tempfile.mkdtemp()) / f"{doc.id}.txt"
    p.write_text(text, encoding="utf-8")
    doc.text_path = str(p)
    inst = instruments_service.get_or_create_instrument(db, code=code, name=title[:6])
    db.add(DocumentLink(document_id=doc.id, instrument_id=inst.id, link_type="about"))
    db.flush()
    index_document_fts(db, doc.id, title, text)


def _login(client: TestClient, key: str) -> dict[str, str]:
    r = client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "pw12345"},
        headers={"Idempotency-Key": key},
    )
    assert r.status_code == 200
    return {"x-csrf-token": r.cookies["csrf_token"], "Idempotency-Key": key}


def _run_executor(app, model_port=None) -> None:
    from wws_adviser.modules.research import executor as research_executor

    with app.state.session_factory() as db:
        asyncio.run(research_executor.run_pending(
            db, app.state.settings, app.state.settings.data_dir,
            model_port=model_port or app.state.model_port,
        ))


def _make_task(client: TestClient, key: str, **body) -> str:
    headers = _login(client, key)
    r = client.post(
        "/api/v1/research/tasks",
        json={"task_type": "company", "subject": "600519", "depth": "standard", **body},
        headers={**headers, "Idempotency-Key": key},
    )
    assert r.status_code == 200
    return r.json()["id"], headers


# —— 退出条件 1：引用可追溯 ——


def test_exit_citation_traceability(migrated_client: TestClient) -> None:
    """报告引用 → Evidence 行 → 文档正文切片哈希可重算（抽样复盘闭环）。"""
    app = migrated_client.app
    doc_texts = {
        "600519贵州茅台2026年半年报": "600519 贵州茅台营业收入增长15%，净利润增长20%。",
        "600519贵州茅台利润分配公告": "600519 贵州茅台每10股派发现金红利。",
    }
    with app.state.session_factory() as db:
        for title, text in doc_texts.items():
            _seed_doc(db, title=title, text=text)
        db.commit()

    task_id, headers = _make_task(migrated_client, "exit-trace-1")
    _run_executor(app)

    with app.state.session_factory() as db:
        task = research_service.get_task(db, task_id)
        assert task is not None and task.status == "COMPLETED"
        report = research_service.get_report(db, task.report_id)
        assert report is not None

        import json as _json
        citations = _json.loads(report.citations_json)
        assert citations, "报告应含引用"

        # 每条引用：Evidence 行存在且哈希一致；文档正文里能重算出同哈希切片
        for c in citations:
            ev = db.scalar(
                select(Evidence).where(Evidence.id == c["evidence_id"])
            )
            assert ev is not None, f"引用 {c['evidence_id'][:8]}… 未持久化"
            assert ev.content_hash == c["content_hash"]

            doc = db.scalar(select(Document).where(Document.id == ev.document_id))
            assert doc is not None
            slices = slice_document(doc, "600519")
            hashes = {s.content_hash for s in slices}
            assert c["content_hash"] in hashes, (
                f"哈希无法从文档 {doc.title} 复算——复盘链断裂"
            )
            # 定位格式可解析（标题#para:N）
            assert doc.title in c["locator"] and "para:" in c["locator"]

        # fact 段全部带引用（防线结构成立）
        assert all(c["evidence_id"] for c in citations)


# —— 退出条件 2：异步体验稳定 ——


def test_exit_task_completes_without_subscription(migrated_client: TestClient) -> None:
    """用户离开页面（无 SSE 订阅）任务照常完成；回来查询即得终态与报告。"""
    app = migrated_client.app
    with app.state.session_factory() as db:
        _seed_doc(db, title="600519贵州茅台2026年半年报",
                  text="600519 贵州茅台营业收入增长15%。")
        db.commit()

    task_id, headers = _make_task(migrated_client, "exit-async-1")
    # 不订阅任何事件流，直接执行
    _run_executor(app)

    r = migrated_client.get(f"/api/v1/research/tasks/{task_id}", headers=headers)
    t = r.json()
    assert t["status"] == "COMPLETED"
    assert t["progress"] == 100
    assert t["report_id"]

    # 完成后再订阅：首个事件即终态，流立即关闭（max_seconds 自限）
    r2 = migrated_client.get(
        f"/api/v1/research/tasks/{task_id}/events?max_seconds=1", headers=headers,
    )
    assert r2.status_code == 200
    first = next(ln for ln in r2.text.splitlines() if ln.startswith("data:"))
    assert '"COMPLETED"' in first


def test_exit_failure_not_stuck_and_retryable(migrated_client: TestClient) -> None:
    """模型失败 → FAILED（带原因）不卡 RUNNING；终态后同任务可重建再跑。"""
    app = migrated_client.app
    with app.state.session_factory() as db:
        _seed_doc(db, title="600519贵州茅台2026年半年报",
                  text="600519 贵州茅台营业收入增长15%。")
        db.commit()

    class _FailingPort:
        async def call(self, request):  # type: ignore[no-untyped-def]
            raise ConnectionError("down")

    task_id, headers = _make_task(migrated_client, "exit-fail-1")
    _run_executor(app, model_port=_FailingPort())

    r = migrated_client.get(f"/api/v1/research/tasks/{task_id}", headers=headers)
    t = r.json()
    assert t["status"] == "FAILED"
    assert t["error_code"] and "model_failed" in t["error_code"]
    assert t["report_id"] is None

    # 终态不阻塞重建（幂等仅覆盖 PENDING/RUNNING）→ 换好模型重跑成功
    r2 = migrated_client.post(
        "/api/v1/research/tasks",
        json={"task_type": "company", "subject": "600519", "depth": "standard"},
        headers={**headers, "Idempotency-Key": "exit-fail-2"},
    )
    assert r2.json()["id"] != task_id, "失败任务后应能新建同参任务"
    _run_executor(app)  # 恢复 stub 模型
    r3 = migrated_client.get(f"/api/v1/research/tasks/{r2.json()['id']}", headers=headers)
    assert r3.json()["status"] == "COMPLETED"


def test_exit_progress_monotonic(migrated_client: TestClient) -> None:
    """进度只增不减（执行器 update_progress 钳制 + 流水线顺序递增）。"""
    app = migrated_client.app
    with app.state.session_factory() as db:
        _seed_doc(db, title="600519贵州茅台2026年半年报",
                  text="600519 贵州茅台营业收入增长15%。")
        db.commit()

    task_id, headers = _make_task(migrated_client, "exit-prog-1")

    progress_values: list[int] = []
    from wws_adviser.modules.research import generation, service

    orig_update = service.update_progress

    def spy(db, task, progress):  # type: ignore[no-untyped-def]
        progress_values.append(progress)
        orig_update(db, task, progress)

    service.update_progress = spy  # type: ignore[assignment]
    generation.research_service.update_progress = spy  # type: ignore[assignment]
    try:
        _run_executor(app)
    finally:
        service.update_progress = orig_update  # type: ignore[assignment]
        generation.research_service.update_progress = orig_update  # type: ignore[assignment]

    assert progress_values == sorted(progress_values), f"进度回退：{progress_values}"
    # 终值 100 由 complete_task 直写（不走 update_progress），经任务状态验证
    r = migrated_client.get(f"/api/v1/research/tasks/{task_id}", headers=headers)
    assert r.json()["progress"] == 100
