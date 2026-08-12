"""文档源端口（DocumentProvider：discover/download）与原始 DTO。"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from wws_adviser.ports.market_data import InstrumentRef, SourceDelayClass


@dataclass(frozen=True)
class DocumentRef:
    source_url: str
    kind: str
    title: str
    published_at: str


@dataclass(frozen=True)
class DocumentScope:
    instrument: InstrumentRef | None = None
    kinds: list[str] | None = None


@dataclass(frozen=True)
class RawDocument:
    source: str
    source_url: str
    market_time: str
    fetched_at: str
    received_at: str
    source_delay_class: SourceDelayClass
    kind: str
    title: str
    content: bytes
    text: str | None = None


class DocumentProvider(Protocol):
    async def discover(
        self, scope: DocumentScope, since: datetime
    ) -> list[DocumentRef]: ...

    async def download(self, ref: DocumentRef) -> RawDocument: ...
