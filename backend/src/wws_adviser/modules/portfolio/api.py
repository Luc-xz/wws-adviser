"""/api/v1 端点：accounts、transactions、CSV 导入预览/确认（3_API §3.2/§3.3）。

写操作强制 Idempotency-Key 头；CSRF 由全局中间件统一校验。
"""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, UploadFile
from sqlalchemy.orm import Session as DBSession

from wws_adviser.api.dependencies import get_current_user, get_session
from wws_adviser.core.errors import MissingIdempotencyKeyError
from wws_adviser.modules.identity.models import User
from wws_adviser.modules.portfolio import service
from wws_adviser.modules.portfolio.domain import ParsedRow, from_scaled_int
from wws_adviser.modules.portfolio.models import Account, Transaction
from wws_adviser.modules.portfolio.schemas import (
    AccountCreate,
    AccountOut,
    ImportConfirmRequest,
    ImportConfirmResponse,
    ImportPreviewResponse,
    PreviewError,
    PreviewRow,
    TransactionCreate,
    TransactionListResponse,
    TransactionOut,
)

router = APIRouter(prefix="/api/v1", tags=["portfolio"])

DBDep = Annotated[DBSession, Depends(get_session)]
UserDep = Annotated[User, Depends(get_current_user)]


def _require_idempotency_key(
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> str:
    if not idempotency_key:
        raise MissingIdempotencyKeyError()
    return idempotency_key


def _account_to_out(a: Account) -> AccountOut:
    return AccountOut(
        id=a.id,
        name=a.name,
        currency=a.currency,
        initial_cash=(
            str(from_scaled_int(a.initial_cash_minor, a.initial_cash_scale))
            if a.initial_cash_minor is not None
            else None
        ),
        current_cash=(
            str(from_scaled_int(a.current_cash_minor, a.current_cash_scale))
            if a.current_cash_minor is not None
            else None
        ),
        reconciled=a.reconciled,
        reconciled_at=a.reconciled_at,
    )


def _txn_to_out(t: Transaction) -> TransactionOut:
    return TransactionOut(
        id=t.id,
        account_id=t.account_id,
        instrument_id=t.instrument_id,
        kind=t.kind,
        direction=t.direction,
        quantity=t.quantity,
        price=t.price,
        fee=str(from_scaled_int(t.fee_minor, t.fee_scale)),
        tax=str(from_scaled_int(t.tax_minor, t.tax_scale)),
        trade_at=t.trade_at,
        external_ref=t.external_ref,
        fingerprint=t.fingerprint,
        note=t.note,
        deleted_at=t.deleted_at,
    )


def _parsed_to_preview(p: ParsedRow) -> PreviewRow:
    return PreviewRow(
        row_no=p.row_no,
        market=p.market,
        code=p.code,
        name=p.name,
        kind=p.kind.value,
        direction=p.direction.value,
        quantity=format(p.quantity, "f"),
        price=format(p.price, "f"),
        fee=format(p.fee, "f"),
        tax=format(p.tax, "f"),
        trade_at=p.trade_at,
        fingerprint=p.fingerprint,
    )


# —— Account ——


@router.get("/accounts", response_model=list[AccountOut])
async def list_accounts(db: DBDep, user: UserDep) -> list[AccountOut]:
    accounts = service.get_accounts(db, user.id)
    return [_account_to_out(a) for a in accounts]


@router.post("/accounts/{account_id}/reconcile", response_model=AccountOut)
async def reconcile_account(
    account_id: str, request: Request, db: DBDep, user: UserDep
) -> AccountOut:
    """对账确认（PRD §19 对账状态）：账本与券商核对一致后置位，
    解除盘中建议的 ledger_unreconciled 降级；后续新交易入账自动复位。"""
    account = service.mark_reconciled(
        db,
        user_id=user.id,
        account_id=account_id,
        request_id=request.headers.get("x-request-id"),
    )
    return _account_to_out(account)


@router.post("/accounts", response_model=AccountOut)
async def create_account(
    body: AccountCreate,
    request: Request,
    db: DBDep,
    user: UserDep,
    _key: Annotated[str, Depends(_require_idempotency_key)],
) -> AccountOut:
    initial = Decimal(body.initial_cash) if body.initial_cash is not None else None
    account = service.create_account(
        db,
        user_id=user.id,
        name=body.name,
        currency=body.currency,
        initial_cash=initial,
        request_id=request.headers.get("x-request-id"),
    )
    return _account_to_out(account)


# —— Transaction ——


@router.get("/transactions", response_model=TransactionListResponse)
async def list_transactions(
    db: DBDep,
    user: UserDep,
    instrument_id: str | None = None,
    kind: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> TransactionListResponse:
    result = service.list_transactions(
        db,
        user_id=user.id,
        instrument_id=instrument_id,
        kind=kind,
        cursor=cursor,
        limit=limit,
    )
    return TransactionListResponse(
        items=[_txn_to_out(t) for t in result.rows],
        next_cursor=result.next_cursor,
        has_more=result.has_more,
    )


@router.post("/transactions", response_model=TransactionOut)
async def create_transaction(
    body: TransactionCreate,
    request: Request,
    db: DBDep,
    user: UserDep,
    _key: Annotated[str, Depends(_require_idempotency_key)],
) -> TransactionOut:
    txn = service.record_transaction(
        db,
        user_id=user.id,
        instrument_id=body.instrument_id,
        kind=body.kind,
        direction=body.direction,
        quantity=Decimal(body.quantity),
        price=Decimal(body.price),
        fee=Decimal(body.fee),
        tax=Decimal(body.tax),
        trade_at=body.trade_at,
        external_ref=body.external_ref,
        note=body.note,
        request_id=request.headers.get("x-request-id"),
    )
    return _txn_to_out(txn)


@router.post("/transactions/import", response_model=ImportPreviewResponse)
async def import_preview(
    file: UploadFile,
    request: Request,
    db: DBDep,
    user: UserDep,
    _key: Annotated[str, Depends(_require_idempotency_key)],
) -> ImportPreviewResponse:
    content = await file.read()
    text = content.decode("utf-8-sig")
    result = service.import_preview(
        db,
        user_id=user.id,
        text=text,
        request_id=request.headers.get("x-request-id"),
    )
    return ImportPreviewResponse(
        batch_id=result.batch_id,
        preview=[_parsed_to_preview(p) for p in result.preview],
        errors=[PreviewError(row_no=e.row_no, message=e.message) for e in result.errors],
        duplicates=[_parsed_to_preview(p) for p in result.duplicates],
    )


@router.post("/transactions/import/confirm", response_model=ImportConfirmResponse)
async def import_confirm(
    body: ImportConfirmRequest,
    request: Request,
    db: DBDep,
    user: UserDep,
    _key: Annotated[str, Depends(_require_idempotency_key)],
) -> ImportConfirmResponse:
    result = service.import_confirm(
        db,
        user_id=user.id,
        batch_id=body.batch_id,
        fingerprints=body.fingerprints,
        request_id=request.headers.get("x-request-id"),
    )
    return ImportConfirmResponse(created=result["created"], skipped=result["skipped"])


@router.delete("/transactions/{transaction_id}")
async def delete_transaction(
    transaction_id: str,
    request: Request,
    db: DBDep,
    user: UserDep,
) -> dict[str, str]:
    service.delete_transaction(
        db,
        user_id=user.id,
        transaction_id=transaction_id,
        request_id=request.headers.get("x-request-id"),
    )
    return {"status": "ok"}
