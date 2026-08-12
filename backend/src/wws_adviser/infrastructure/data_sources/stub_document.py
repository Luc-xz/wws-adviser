"""StubDocumentProvider：合成公告/新闻（source="stub"），禁生产。"""

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
        return []

    async def download(self, ref: DocumentRef) -> RawDocument:
        now = now_utc_iso()
        return RawDocument(
            source="stub",
            source_url=ref.source_url,
            market_time=now,
            fetched_at=now,
            received_at=now,
            source_delay_class=SourceDelayClass.DELAYED,
            kind=ref.kind,
            title=ref.title,
            content=b"stub document content",
            text="stub document content",
        )
