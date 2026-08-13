"""Portfolio DTO（金额/数量/价格以字符串传输，2_DATA_MODEL §5）。"""

from pydantic import BaseModel

from wws_adviser.modules.portfolio.domain import Direction, TransactionKind

# —— Account ——


class AccountCreate(BaseModel):
    name: str
    currency: str = "CNY"
    initial_cash: str | None = None  # decimal 字符串


class AccountOut(BaseModel):
    id: str
    name: str
    currency: str
    initial_cash: str | None = None
    current_cash: str | None = None
    reconciled: bool
    reconciled_at: str | None = None


# —— Transaction ——


class TransactionCreate(BaseModel):
    instrument_id: str
    kind: TransactionKind
    direction: Direction | None = None  # 缺省由 kind 推导
    quantity: str
    price: str
    fee: str = "0"
    tax: str = "0"
    trade_at: str
    external_ref: str | None = None
    note: str | None = None


class TransactionOut(BaseModel):
    id: str
    account_id: str
    instrument_id: str
    kind: str
    direction: str
    quantity: str
    price: str
    fee: str
    tax: str
    trade_at: str
    external_ref: str | None = None
    fingerprint: str
    note: str | None = None
    deleted_at: str | None = None


class TransactionListResponse(BaseModel):
    items: list[TransactionOut]
    next_cursor: str | None = None
    has_more: bool = False


# —— CSV 导入 ——


class PreviewRow(BaseModel):
    row_no: int
    market: str
    code: str
    name: str
    kind: str
    direction: str
    quantity: str
    price: str
    fee: str
    tax: str
    trade_at: str
    fingerprint: str


class PreviewError(BaseModel):
    row_no: int
    message: str


class ImportPreviewResponse(BaseModel):
    batch_id: str
    preview: list[PreviewRow]
    errors: list[PreviewError]
    duplicates: list[PreviewRow]


class ImportConfirmRequest(BaseModel):
    batch_id: str
    fingerprints: list[str]


class ImportConfirmResponse(BaseModel):
    created: int
    skipped: int
