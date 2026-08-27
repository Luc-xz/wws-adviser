"""证据检索测试：切片、密度评分、元数据过滤（Phase 3 波2）。"""


from wws_adviser.core.ids import new_id
from wws_adviser.core.time import now_utc_iso
from wws_adviser.modules.documents.models import Document, DocumentLink
from wws_adviser.modules.instruments import service as instruments_service
from wws_adviser.modules.research import evidence as evidence_service


def _mk_doc(
    db, *, title: str, trust: str = "official", pub: str = "2026-08-01",
    code: str | None = None, text: str = "",
) -> Document:
    import hashlib
    doc = Document(
        id=new_id(), kind="announcement", title=title,
        source="test", source_url=None,
        content_sha256=hashlib.sha256(title.encode()).hexdigest(),
        trust_level=trust, quality_status="OK",
        published_at=pub, created_at=now_utc_iso(), updated_at=now_utc_iso(),
    )
    db.add(doc)
    db.flush()
    # FTS5 索引（search_documents 走虚拟表，不走 ORM）
    from wws_adviser.modules.documents.repository import index_document_fts
    index_document_fts(db, doc.id, title, text or title)
    if code:
        inst = instruments_service.get_or_create_instrument(db, code=code, name=title[:6])
        db.add(DocumentLink(
            document_id=doc.id, instrument_id=inst.id, link_type="about",
        ))
    if text:
        import pathlib
        import tempfile
        p = pathlib.Path(tempfile.mkdtemp()) / f"{doc.id}.txt"
        p.write_text(text, encoding="utf-8")
        doc.text_path = str(p)
    db.flush()
    return doc


# —— 切片 ——


def test_slice_short_document(db_session) -> None:
    """短文档：单段落不切。"""
    doc = _mk_doc(db_session, title="2026年半年报", text="营业收入增长15%。净利润增长20%。",
                  pub="2026-08-15")
    slices = evidence_service.slice_document(doc, "营业收入")
    assert len(slices) == 1
    assert "营业收入" in slices[0].text
    assert slices[0].slice_ref == "para:1"
    assert slices[0].content_hash  # 有内容哈希


def test_slice_long_document_chunked(db_session) -> None:
    """长文档：超 800 字的段落按句号二次切。"""
    long_text = "这是第一句话。" * 300  # ~1800 字
    doc = _mk_doc(db_session, title="长报告", text=long_text, pub="2026-08-01")
    slices = evidence_service.slice_document(doc, "第一句话")
    assert len(slices) > 1
    # 每片不超限
    for s in slices:
        assert len(s.text) <= evidence_service._SLICE_MAX_CHARS + 50


def test_slice_multi_paragraph(db_session) -> None:
    """多段落：按空行分段。"""
    text = "第一段：公司概况。\n\n第二段：财务数据。\n\n第三段：风险提示。"
    doc = _mk_doc(db_session, title="多段文档", text=text)
    slices = evidence_service.slice_document(doc, "公司")
    assert len(slices) >= 2
    refs = [s.slice_ref for s in slices]
    assert "para:1" in refs and "para:2" in refs


# —— 评分 ——


def test_keyword_density() -> None:
    d = evidence_service._keyword_density("营业收入增长15%", {"营业收入"})
    assert d > 0
    d0 = evidence_service._keyword_density("没有任何命中", {"营业收入"})
    assert d0 == 0.0


def test_freshness_bonus() -> None:
    from datetime import date
    today = date.today().isoformat()
    assert evidence_service._freshness_bonus(today) == 0.5
    assert evidence_service._freshness_bonus("2020-01-01") == 0.0
    assert evidence_service._freshness_bonus(None) == 0.0


def test_trust_weight_ranking(db_session) -> None:
    """official > news：同内容下可信等级高的排前面。"""
    official = _mk_doc(db_session, title="营收报告A", trust="official",
                       text="营业收入增长", pub="2026-08-20")
    news = _mk_doc(db_session, title="营收报道B", trust="news",
                   text="营业收入增长", pub="2026-08-20")
    s1 = evidence_service.slice_document(official, "营业收入")
    s2 = evidence_service.slice_document(news, "营业收入")
    assert s1[0].score > s2[0].score


# —— 元数据过滤 ——


def test_retrieve_with_instrument_filter(db_session) -> None:
    """按标的过滤：只返回关联到该标的的文档。"""
    _mk_doc(db_session, title="600519 公告", code="600519",
            text="贵州茅台营业收入", pub="2026-08-01")
    _mk_doc(db_session, title="000001 公告", code="000001",
            text="平安银行营业收入", pub="2026-08-01")
    result = evidence_service.retrieve_evidence(
        db_session, query="营业收入", instrument_code="600519",
    )
    assert all("600519" in s.title or "茅台" in s.title for s in result.slices)


def test_retrieve_with_trust_filter(db_session) -> None:
    _mk_doc(db_session, title="官方营收", trust="official", text="营收数据A", pub="2026-08-01")
    _mk_doc(db_session, title="博客猜测", trust="blog", text="营收数据B", pub="2026-08-01")
    result = evidence_service.retrieve_evidence(
        db_session, query="营收数据", trust_levels=["official"],
    )
    assert all(s.trust_level == "official" for s in result.slices)


def test_retrieve_with_since_filter(db_session) -> None:
    _mk_doc(db_session, title="新公告", pub="2026-08-20", text="最新数据")
    _mk_doc(db_session, title="旧公告", pub="2026-01-01", text="旧数据")
    result = evidence_service.retrieve_evidence(
        db_session, query="数据", since="2026-07-01",
    )
    assert all(s.published_at >= "2026-07-01" for s in result.slices)
