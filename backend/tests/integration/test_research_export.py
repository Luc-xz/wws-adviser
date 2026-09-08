"""研究报告导出测试（Phase 3 波6）：md 附件 / html 渲染 / 越权与格式校验。"""

import asyncio
import json

from fastapi.testclient import TestClient

from wws_adviser.modules.research import export as export_mod

# —— md_to_html 纯函数 ——


def test_md_to_html_renders_report_subset() -> None:
    md = (
        "# 公司研究报告：600519\n"
        "\n"
        "- 数据截止：2026-08-01\n"
        "\n"
        "## 财务与经营指标【事实】\n"
        "\n"
        "收入稳健增长。\n"
        "\n"
        "> 引用[1] 半年报#para:1（单源引用）\n"
        "\n"
        "| 指标 | 当前值 | 单位 |\n"
        "| --- | --- | --- |\n"
        "| 营业收入 | 100.5 | 亿元 |\n"
    )
    page = export_mod.md_to_html(md, title="测试报告")
    assert page.startswith("<!DOCTYPE html>")
    assert "<title>测试报告</title>" in page
    assert "<h1>公司研究报告：600519</h1>" in page
    assert "<h2>财务与经营指标【事实】</h2>" in page
    assert "<p>收入稳健增长。</p>" in page
    assert "<blockquote>" in page and "半年报#para:1" in page
    assert "<table>" in page and "<th>指标</th>" in page and "<td>100.5</td>" in page
    assert "<li>数据截止：2026-08-01</li>" in page
    assert "|" not in page.split("<body>")[1].replace("&#124;", "")  # 表格线不残留


def test_md_to_html_escapes_content() -> None:
    page = export_mod.md_to_html("段落 <script>alert(1)</script>")
    assert "<script>" not in page
    assert "&lt;script&gt;" in page


# —— API ——


def _login(client: TestClient, key: str) -> dict[str, str]:
    r = client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "pw12345"},
        headers={"Idempotency-Key": key},
    )
    assert r.status_code == 200
    return {"x-csrf-token": r.cookies["csrf_token"], "Idempotency-Key": key}


def _make_report(client: TestClient) -> str:
    """生成一份真实报告（stub 模型）并返回 report_id。"""
    import hashlib
    import pathlib
    import tempfile

    from wws_adviser.core.ids import new_id
    from wws_adviser.core.time import now_utc_iso
    from wws_adviser.modules.documents.models import Document, DocumentLink
    from wws_adviser.modules.documents.repository import index_document_fts
    from wws_adviser.modules.instruments import service as instruments_service
    from wws_adviser.modules.research import executor as research_executor

    app = client.app
    with app.state.session_factory() as db:
        doc = Document(
            id=new_id(), kind="announcement", title="600519贵州茅台2026年半年报",
            source="test", source_url=None,
            content_sha256=hashlib.sha256(b"t").hexdigest(),
            trust_level="official", quality_status="OK",
            published_at="2026-08-01", created_at=now_utc_iso(),
            updated_at=now_utc_iso(),
        )
        db.add(doc)
        db.flush()
        p = pathlib.Path(tempfile.mkdtemp()) / f"{doc.id}.txt"
        p.write_text("600519 贵州茅台营业收入增长15%。", encoding="utf-8")
        doc.text_path = str(p)
        inst = instruments_service.get_or_create_instrument(db, code="600519", name="贵州茅台")
        db.add(DocumentLink(document_id=doc.id, instrument_id=inst.id, link_type="about"))
        db.flush()
        index_document_fts(db, doc.id, doc.title, p.read_text(encoding="utf-8"))
        db.commit()

    headers = _login(client, "exp-login-1")
    r = client.post(
        "/api/v1/research/tasks",
        json={"task_type": "company", "subject": "600519", "depth": "quick"},
        headers={**headers, "Idempotency-Key": "exp-1"},
    )
    task_id = r.json()["id"]
    with app.state.session_factory() as db:
        asyncio.run(research_executor.run_pending(
            db, app.state.settings, app.state.settings.data_dir,
            model_port=app.state.model_port,
        ))
    r2 = client.get(f"/api/v1/research/tasks/{task_id}", headers=headers)
    return r2.json()["report_id"], headers


def test_export_md_and_html(migrated_client: TestClient) -> None:
    report_id, headers = _make_report(migrated_client)

    r = migrated_client.get(
        f"/api/v1/research/reports/{report_id}/export?format=md", headers=headers,
    )
    assert r.status_code == 200
    assert "text/markdown" in r.headers["content-type"]
    assert 'filename="research-' in r.headers["content-disposition"]
    assert "公司研究报告" in r.text

    r2 = migrated_client.get(
        f"/api/v1/research/reports/{report_id}/export?format=html", headers=headers,
    )
    assert r2.status_code == 200
    assert "text/html" in r2.headers["content-type"]
    assert r2.text.startswith("<!DOCTYPE html>")
    assert "<h1>" in r2.text and "引用" in r2.text


def test_export_rejects_unknown_format_and_missing_report(migrated_client: TestClient) -> None:
    headers = _login(migrated_client, "exp-login-2")
    r = migrated_client.get(
        "/api/v1/research/reports/01AAAAAAAAAAAAAAAAAAAAAAAAA/export?format=pdf",
        headers=headers,
    )
    assert r.status_code in (400, 404, 500)  # DomainError → 4xx/5xx 统一处理

    report_id, _ = _make_report(migrated_client)
    r2 = migrated_client.get(
        f"/api/v1/research/reports/{report_id}/export?format=pdf", headers=headers,
    )
    assert r2.status_code in (400, 422, 500)


def test_task_sse_streams_until_terminal(migrated_client: TestClient) -> None:
    """SSE：PENDING 阶段可订阅到事件流；越权任务拒绝。"""
    headers = _login(migrated_client, "exp-sse-1")
    r = migrated_client.post(
        "/api/v1/research/tasks",
        json={"task_type": "industry", "subject": "白酒行业", "depth": "quick"},
        headers={**headers, "Idempotency-Key": "sse-1"},
    )
    task_id = r.json()["id"]

    # max_seconds=1 → 流自行终止（无需客户端断开），普通 GET 即可读完
    r = migrated_client.get(
        f"/api/v1/research/tasks/{task_id}/events?max_seconds=1", headers=headers,
    )
    assert r.status_code == 200
    assert "text/event-stream" in r.headers["content-type"]
    data_lines = [ln for ln in r.text.splitlines() if ln.startswith("data:")]
    assert data_lines, "至少一条事件"
    payload = json.loads(data_lines[0][5:].strip())
    assert payload["task_id"] == task_id
    assert payload["status"] == "PENDING"
    assert payload["progress"] == 0

    # 不存在/越权 → DomainError
    r2 = migrated_client.get(
        "/api/v1/research/tasks/01AAAAAAAAAAAAAAAAAAAAAAAAA/events", headers=headers,
    )
    assert r2.status_code in (400, 404, 500)
