"""StubDocumentProvider：合成公告/新闻（source="stub"），禁生产。

为闭环可测，当 scope.instrument 存在时 discover 合成 1 条公告（标题/内容由 code 派生，稳定）。
"""

from datetime import datetime

from wws_adviser.core.time import now_utc_iso
from wws_adviser.infrastructure import assert_not_prod
from wws_adviser.ports.document_source import (
    DocumentRef,
    DocumentScope,
    RawDocument,
)
from wws_adviser.ports.market_data import SourceDelayClass


class StubDocumentProvider:
    def __init__(self, *, env: str = "dev") -> None:
        assert_not_prod(env)

    async def discover(
        self, scope: DocumentScope, since: datetime
    ) -> list[DocumentRef]:
        if scope.instrument is None:
            return []
        code = scope.instrument.code
        return [
            DocumentRef(
                source_url=f"stub://announcement/{code}",
                kind="announcement",
                title=f"{code} 关于XXX的公告",
                published_at="2026-08-13",
            )
        ]

    async def download(self, ref: DocumentRef) -> RawDocument:
        now = now_utc_iso()
        body = f"{ref.title}：本公告为 stub 合成内容，用于闭环验证。"
        return RawDocument(
            source="stub",
            source_url=ref.source_url,
            market_time=now,
            fetched_at=now,
            received_at=now,
            source_delay_class=SourceDelayClass.DELAYED,
            kind=ref.kind,
            title=ref.title,
            content=body.encode("utf-8"),
            text=body,
        )
