"""公司报告生成流水线测试：模板、引用防线、执行器闭环（Phase 3 波4）。"""

import asyncio
import hashlib
import pathlib
import tempfile

import pytest
from fastapi.testclient import TestClient

from wws_adviser.core.ids import new_id
from wws_adviser.core.time import now_utc_iso
from wws_adviser.modules.documents.models import Document, DocumentLink
from wws_adviser.modules.instruments import service as instruments_service
from wws_adviser.modules.research import generation
from wws_adviser.modules.research import service as research_service
from wws_adviser.ports.model import ModelAudit, ModelRequest, ModelResponse

# —— 纯函数：段落计划 / 引用防线 ——


def test_plan_for_depth() -> None:
    full = generation.plan_for_depth("standard")
    quick = generation.plan_for_depth("quick")
    assert len(full) == 7
    assert [s.section_type.value for s in quick] == ["overview", "valuation", "conclusion"]
    # fact 段强制引用，judgment 段不强制
    assert all(s.require_citations for s in full if s.epistemic_type == "fact")
    assert not full[-1].require_citations


def _mk_slice(evidence_id: str, doc_id: str, text: str = "内容"):
    from wws_adviser.modules.research.evidence import EvidenceSlice
    return EvidenceSlice(
        evidence_id=evidence_id, document_id=doc_id, title="测试文档", source="test",
        source_url=None, published_at="2026-08-01", trust_level="official",
        slice_ref="para:1", text=text,
        content_hash=hashlib.sha256(text.encode()).hexdigest()[:32], score=1.0,
    )


def test_sections_from_model_fact_demoted_without_citation() -> None:
    """fact 段无引用 → 降级 inference + 显式标注（不得写成确定事实）。"""
    plan = generation.plan_for_depth("quick")
    evidence = [_mk_slice("ev-1", "doc-1"), _mk_slice("ev-2", "doc-2")]
    model_out = {
        "sections": [
            {"section_type": "overview", "title": "概览", "content": "公司主营…",
             "evidence_ids": []},  # 事实段无引用
            {"section_type": "valuation", "title": "估值", "content": "估值偏高…",
             "evidence_ids": []},
            {"section_type": "conclusion", "title": "结论", "content": "待验证…",
             "evidence_ids": []},
        ]
    }
    sections = generation.sections_from_model(model_out, plan=plan, evidence=evidence)
    overview = sections[0]
    assert overview.epistemic_type == "inference"          # 降级
    assert "已降级为推断" in overview.content               # 显式标注
    assert not overview.citations


def test_sections_from_model_double_source_verified() -> None:
    """同段引用 ≥2 个不同文档 → verified；单源 → unverified_note。"""
    plan = (generation.plan_for_depth("quick")[0],)  # 仅 overview
    evidence = [_mk_slice("ev-1", "doc-1"), _mk_slice("ev-2", "doc-2"), _mk_slice("ev-3", "doc-1")]
    model_out = {
        "sections": [
            {"section_type": "overview", "title": "概览", "content": "公司主营…",
             "evidence_ids": ["ev-1", "ev-2"]},  # 双文档
        ]
    }
    sections = generation.sections_from_model(model_out, plan=plan, evidence=evidence)
    assert all(c.verified for c in sections[0].citations)

    model_out_single = {
        "sections": [
            {"section_type": "overview", "title": "概览", "content": "公司主营…",
             "evidence_ids": ["ev-1", "ev-3"]},  # 同一文档两片
        ]
    }
    sections2 = generation.sections_from_model(model_out_single, plan=plan, evidence=evidence)
    assert not any(c.verified for c in sections2[0].citations)
    assert all(c.unverified_note for c in sections2[0].citations)


def test_sections_from_model_missing_plan_section_raises() -> None:
    plan = (generation.plan_for_depth("quick")[0],)
    with pytest.raises(ValueError, match="缺少计划段落"):
        generation.sections_from_model({"sections": []}, plan=plan, evidence=[])


def test_markdown_rendering_contains_labels_and_tables() -> None:
    financial_spec = next(
        s for s in generation.plan_for_depth("standard")
        if s.section_type.value == "financial"
    )
    plan = (financial_spec,)
    evidence = [_mk_slice("ev-1", "doc-1", "营业收入增长")]
    model_out = {
        "sections": [
            {"section_type": "financial", "title": "财务", "content": "收入增长…",
             "evidence_ids": ["ev-1"]},
        ]
    }
    sections = generation.sections_from_model(model_out, plan=plan, evidence=evidence)
    md = generation.assemble_report_md(
        subject="600519", sections=sections,
        metric_rows=generation.build_metric_table(
            {"营业收入": {"value": "100.5", "prior": "85.2", "unit": "亿元"}}
        ),
        current_price=None, data_cutoff="2026-08-01",
        generation_config={"depth": "quick", "template_version": "company-v1"},
    )
    assert "公司研究报告：600519" in md
    assert "【事实】" in md                       # 认知层级标签
    assert "引用[1]" in md                        # 引用可定位
    assert "营业收入" in md and "17.96" in md     # 确定性指标表（同比计算）


# —— 网关研究输出校验 ——


def test_gateway_validates_research_output_shape() -> None:
    from wws_adviser.modules.model_gateway.domain import (
        ValidationVerdict,
        validate_model_output,
    )

    # 缺 sections → REPAIR
    r1 = validate_model_output(
        {}, deterministic_summary={}, evidence_whitelist=["ev-1"], task_type="research_company",
    )
    assert r1.verdict is ValidationVerdict.REPAIR

    # evidence_id 不在白名单 → BLOCKED
    r2 = validate_model_output(
        {"sections": [{"section_type": "overview", "content": "x", "evidence_ids": ["fake"]}]},
        deterministic_summary={}, evidence_whitelist=["ev-1"], task_type="research_company",
    )
    assert r2.verdict is ValidationVerdict.BLOCKED

    # 合法 → PASS
    r3 = validate_model_output(
        {"sections": [{"section_type": "overview", "content": "x", "evidence_ids": ["ev-1"]}]},
        deterministic_summary={}, evidence_whitelist=["ev-1"], task_type="research_company",
    )
    assert r3.verdict is ValidationVerdict.PASS


# —— 执行器闭环（stub 模型）——


class _BadResearchPort:
    """返回编造证据编号的替身（触发网关 BLOCKED）。"""

    async def call(self, request: ModelRequest) -> ModelResponse:
        now = now_utc_iso()
        audit = ModelAudit(
            task_type=request.task_type, model_profile_id=request.model_profile_id,
            prompt_template_name=request.prompt_template_name,
            prompt_template_version=request.prompt_template_version,
            prompt_hash="bad", started_at=now, ended_at=now, status="ok",
        )
        return ModelResponse(
            content={"sections": [{
                "section_type": "overview", "title": "概览", "content": "编造",
                "evidence_ids": ["fabricated-id"],
            }]},
            audit=audit,
        )


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


def _login(client: TestClient) -> dict[str, str]:
    r = client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "pw12345"},
        headers={"Idempotency-Key": "login-gen-1"},
    )
    assert r.status_code == 200
    return {"x-csrf-token": r.cookies["csrf_token"], "Idempotency-Key": "gen-1"}


def test_executor_completes_company_task(migrated_client: TestClient) -> None:
    """全链路：证据 → 确定性 → 模型（stub）→ 引用校验 → 报告落盘 → API 可读。"""
    app = migrated_client.app
    with app.state.session_factory() as db:
        _seed_doc(
            db, title="600519贵州茅台2026年半年报",
            text="600519 贵州茅台营业收入增长15%，净利润增长20%。",
        )
        _seed_doc(
            db, title="600519贵州茅台利润分配公告",
            text="600519 贵州茅台每10股派发现金红利。",
        )
        db.commit()

    headers = _login(migrated_client)
    r = migrated_client.post(
        "/api/v1/research/tasks",
        json={"task_type": "company", "subject": "600519", "depth": "standard"},
        headers=headers,
    )
    assert r.status_code == 200
    task_id = r.json()["id"]

    from wws_adviser.modules.research import executor as research_executor

    with app.state.session_factory() as db:
        ran = asyncio.run(research_executor.run_pending(
            db, app.state.settings, app.state.settings.data_dir,
            model_port=app.state.model_port,
        ))
    assert ran == 1

    # 任务完成 + 报告可经 API 读取（含引用与生成配置）
    r2 = migrated_client.get(f"/api/v1/research/tasks/{task_id}", headers=headers)
    task = r2.json()
    assert task["status"] == "COMPLETED"
    assert task["progress"] == 100
    assert task["report_id"]

    r3 = migrated_client.get(f"/api/v1/research/reports/{task['report_id']}", headers=headers)
    assert r3.status_code == 200
    report = r3.json()
    assert "公司研究报告：600519" in report["content_md"]
    assert "【事实】" in report["content_md"]
    assert report["citations"], "引用清单非空"
    assert all("content_hash" in c for c in report["citations"])
    assert report["generation_config"]["template_version"] == "company-v1"
    assert report["generation_config"]["prompt_version"]


def test_executor_fails_on_fabricated_evidence(migrated_client: TestClient) -> None:
    """编造证据编号 → 网关 BLOCKED → 任务失败（不产出报告）。"""
    app = migrated_client.app
    with app.state.session_factory() as db:
        _seed_doc(db, title="600519贵州茅台2026年半年报", text="600519 贵州茅台营业收入增长15%。")
        db.commit()

    headers = _login(migrated_client)
    r = migrated_client.post(
        "/api/v1/research/tasks",
        json={"task_type": "company", "subject": "600519", "depth": "quick"},
        headers={**headers, "Idempotency-Key": "gen-bad-1"},
    )
    task_id = r.json()["id"]

    from wws_adviser.modules.research import executor as research_executor

    with app.state.session_factory() as db:
        asyncio.run(research_executor.run_pending(
            db, app.state.settings, app.state.settings.data_dir,
            model_port=_BadResearchPort(),
        ))

    with app.state.session_factory() as db:
        task = research_service.get_task(db, task_id)
        assert task is not None
        assert task.status == "FAILED"
        assert "output_invalid" in (task.error_code or "")
        assert task.report_id is None


def test_executor_fails_without_evidence(migrated_client: TestClient) -> None:
    """零证据 → insufficient_evidence（诚实失败，不产出无引用报告）。"""
    app = migrated_client.app
    headers = _login(migrated_client)
    r = migrated_client.post(
        "/api/v1/research/tasks",
        json={"task_type": "company", "subject": "000000", "depth": "quick"},
        headers={**headers, "Idempotency-Key": "gen-noev-1"},
    )
    task_id = r.json()["id"]

    from wws_adviser.modules.research import executor as research_executor

    with app.state.session_factory() as db:
        asyncio.run(research_executor.run_pending(
            db, app.state.settings, app.state.settings.data_dir,
            model_port=app.state.model_port,
        ))

    with app.state.session_factory() as db:
        task = research_service.get_task(db, task_id)
        assert task is not None
        assert task.status == "FAILED"
        assert task.error_code and task.error_code.startswith("insufficient_evidence")
