"""Portfolio 服务：账户、交易录入、CSV 导入预览/确认。事务边界在此。

并发安全：单 worker 下「预查 SELECT → 插入」足以去重；多 worker 需补 UNIQUE 冲突捕获
（jobs 模式）。导入预览→确认的暂存为进程内 dict（MVP 单 worker），未来硬化可下沉到
pending_transactions 表（2_DATA_MODEL §6.2）。
"""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session as DBSession

from wws_adviser.core.errors import DomainError
from wws_adviser.core.ids import new_id
from wws_adviser.core.time import now_utc_iso
from wws_adviser.modules.audit import service as audit_service
from wws_adviser.modules.instruments import service as instruments_service
from wws_adviser.modules.instruments.domain import infer_market
from wws_adviser.modules.portfolio import repository
from wws_adviser.modules.portfolio.domain import (
    Direction,
    ImportPreviewExpiredError,
    ParsedRow,
    PositionsResult,
    RowError,
    TransactionKind,
    TxnInput,
    compute_fingerprint,
    compute_position_series,
    compute_positions,
    decimal_str,
    decode_cursor,
    encode_cursor,
    from_scaled_int,
    kind_to_direction,
    parse_csv_rows,
    to_scaled_int,
)
from wws_adviser.modules.portfolio.models import Account, PositionSnapshot, Transaction

# 单进程暂存：idempotency_key -> {fingerprint: ParsedRow}
_import_staging: dict[str, dict[str, ParsedRow]] = {}


def reset_import_staging() -> None:
    """测试用：清空导入暂存。"""
    _import_staging.clear()


class AccountNotFoundError(DomainError):
    code = "NOT_FOUND"
    status = 404
    title = "账户不存在"


class TransactionNotFoundError(DomainError):
    code = "NOT_FOUND"
    status = 404
    title = "交易不存在"


class InstrumentNotFoundError(DomainError):
    code = "NOT_FOUND"
    status = 404
    title = "标的不存在"


@dataclass(frozen=True)
class TransactionListResult:
    rows: list[Transaction]
    next_cursor: str | None
    has_more: bool


@dataclass(frozen=True)
class ImportPreviewResult:
    batch_id: str
    preview: list[ParsedRow]
    errors: list[RowError]
    duplicates: list[ParsedRow]


def _get_user_account(db: DBSession, user_id: str) -> Account:
    accounts = repository.get_accounts_by_user(db, user_id)
    if not accounts:
        raise AccountNotFoundError("用户尚未创建账户，请先创建账户")
    return accounts[0]


def get_user_account(db: DBSession, user_id: str) -> Account:
    """公开入口：取用户（唯一）账户。供 analytics 等跨模块用。"""
    return _get_user_account(db, user_id)


def get_account_by_id(db: DBSession, account_id: str) -> Account | None:
    """公开入口：按 id 取账户。供 reports（冻结快照）等跨模块用。"""
    return repository.get_account_by_id(db, account_id)


def list_position_snapshots(
    db: DBSession,
    *,
    account_id: str,
    instrument_id: str | None = None,
    limit: int = 100,
) -> list[PositionSnapshot]:
    """持仓快照历史（供 analytics /positions/history）。"""
    return repository.list_snapshots(
        db, account_id=account_id, instrument_id=instrument_id, limit=limit
    )


# —— Account ——


def create_account(
    db: DBSession,
    *,
    user_id: str,
    name: str,
    currency: str = "CNY",
    initial_cash: Decimal | None = None,
    request_id: str | None = None,
) -> Account:
    """MVP 单用户单账户：已有则直接返回（幂等）。"""
    existing = repository.get_accounts_by_user(db, user_id)
    if existing:
        return existing[0]
    initial_minor = to_scaled_int(initial_cash) if initial_cash is not None else None
    account = Account(
        id=new_id(),
        user_id=user_id,
        name=name,
        currency=currency,
        initial_cash_minor=initial_minor,
        current_cash_minor=initial_minor,
        reconciled=False,
        created_at=now_utc_iso(),
        updated_at=now_utc_iso(),
        version=1,
    )
    repository.add_account(db, account)
    audit_service.append_event(
        db,
        action="account_created",
        target_type="account",
        target_id=account.id,
        after={"name": name, "currency": currency},
        request_id=request_id,
    )
    db.commit()
    return account


def get_accounts(db: DBSession, user_id: str) -> list[Account]:
    return repository.get_accounts_by_user(db, user_id)


# —— Transaction ——


def record_transaction(
    db: DBSession,
    *,
    user_id: str,
    instrument_id: str,
    kind: TransactionKind,
    direction: Direction | None = None,
    quantity: Decimal,
    price: Decimal,
    fee: Decimal = Decimal("0"),
    tax: Decimal = Decimal("0"),
    trade_at: str,
    external_ref: str | None = None,
    note: str | None = None,
    request_id: str | None = None,
) -> Transaction:
    """手工录入：fingerprint + external_ref 预查去重（命中返已存在，不建第二行）。"""
    account = _get_user_account(db, user_id)
    instrument = instruments_service.get_instrument(db, instrument_id)
    if instrument is None:
        raise InstrumentNotFoundError(instrument_id)
    direct = direction or kind_to_direction(kind)
    fingerprint = compute_fingerprint(
        market=instrument.market,
        code=instrument.code,
        kind=kind,
        direction=direct,
        quantity=quantity,
        price=price,
        fee=fee,
        trade_at=trade_at,
    )
    existing = repository.get_transaction_by_fingerprint(db, account.id, fingerprint)
    if existing is not None:
        return existing
    if external_ref:
        by_ref = repository.get_transaction_by_external_ref(db, account.id, external_ref)
        if by_ref is not None:
            return by_ref
    txn = _build_transaction(
        account_id=account.id,
        instrument_id=instrument_id,
        kind=kind,
        direction=direct,
        quantity=quantity,
        price=price,
        fee=fee,
        tax=tax,
        trade_at=trade_at,
        fingerprint=fingerprint,
        external_ref=external_ref,
        note=note,
    )
    repository.add_transaction(db, txn)
    audit_service.append_event(
        db,
        action="transaction_recorded",
        target_type="transaction",
        target_id=txn.id,
        after={"kind": kind.value, "trade_at": trade_at},
        request_id=request_id,
    )
    db.commit()
    rebuild_snapshots(db, account_id=account.id, instrument_id=instrument_id)
    return txn


def list_transactions(
    db: DBSession,
    *,
    user_id: str,
    instrument_id: str | None = None,
    kind: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> TransactionListResult:
    account = _get_user_account(db, user_id)
    cursor_tuple = decode_cursor(cursor) if cursor else None
    rows = repository.list_transactions(
        db,
        account_id=account.id,
        instrument_id=instrument_id,
        kind=kind,
        cursor_tuple=cursor_tuple,
        limit=limit + 1,
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = (
        encode_cursor(page[-1].trade_at, page[-1].id) if has_more and page else None
    )
    return TransactionListResult(rows=page, next_cursor=next_cursor, has_more=has_more)


def delete_transaction(
    db: DBSession,
    *,
    user_id: str,
    transaction_id: str,
    request_id: str | None = None,
) -> None:
    account = _get_user_account(db, user_id)
    txn = repository.get_transaction_by_id(db, transaction_id)
    if txn is None or txn.account_id != account.id or txn.deleted_at is not None:
        raise TransactionNotFoundError(transaction_id)
    txn.deleted_at = now_utc_iso()
    txn.updated_at = now_utc_iso()
    txn.version += 1
    audit_service.append_event(
        db,
        action="transaction_deleted",
        target_type="transaction",
        target_id=transaction_id,
        request_id=request_id,
    )
    db.commit()
    rebuild_snapshots(db, account_id=account.id, instrument_id=txn.instrument_id)


# —— 持仓快照重建（波4）——

COST_METHOD_VERSION = "MWAC_v1"
SNAPSHOT_ALGO_VERSION = "v1"


def _to_txn_input(row: Transaction) -> TxnInput:
    return TxnInput(
        instrument_id=row.instrument_id,
        kind=TransactionKind(row.kind),
        direction=Direction(row.direction),
        quantity=Decimal(row.quantity),
        price=Decimal(row.price),
        fee=from_scaled_int(row.fee_minor, row.fee_scale),
        tax=from_scaled_int(row.tax_minor, row.tax_scale),
        trade_at=row.trade_at,
    )


def rebuild_snapshots(
    db: DBSession, *, account_id: str, instrument_id: str | None = None
) -> None:
    """重建持仓快照：删该账户（或指定标的）全部快照 → 回放交易 → 逐 trade_at 落快照。

    market_value/unrealized/weight 留空（由 analytics 叠加行情估值时填）。
    """
    inst_ids = [instrument_id] if instrument_id else repository.list_instrument_ids(db, account_id)
    now = now_utc_iso()
    for inst_id in inst_ids:
        rows = repository.list_transactions(
            db, account_id=account_id, instrument_id=inst_id, limit=100000
        )
        repository.delete_snapshots_for_instrument(db, account_id, inst_id)
        series = compute_position_series([_to_txn_input(r) for r in rows])
        for trade_at, st in series:
            repository.upsert_snapshot(
                db,
                PositionSnapshot(
                    id=new_id(),
                    account_id=account_id,
                    instrument_id=inst_id,
                    business_date=trade_at,
                    quantity=decimal_str(st.qty),
                    available_qty=decimal_str(st.qty),
                    avg_cost_minor=to_scaled_int(st.avg_cost),
                    realized_pnl_minor=to_scaled_int(st.realized_pnl),
                    unrealized_pnl_minor=None,
                    market_value_minor=None,
                    weight=None,
                    cost_method_version=COST_METHOD_VERSION,
                    snapshot_algo_version=SNAPSHOT_ALGO_VERSION,
                    created_at=now,
                    updated_at=now,
                    version=1,
                ),
            )
    db.commit()


def get_position_state(db: DBSession, account_id: str) -> PositionsResult:
    """当前持仓状态（确定性回放）：返回每标的 PositionState + 账户现金。"""
    account = repository.get_account_by_id(db, account_id)
    initial = (
        from_scaled_int(account.initial_cash_minor, account.initial_cash_scale)
        if account is not None and account.initial_cash_minor is not None
        else Decimal(0)
    )
    rows = repository.list_transactions(db, account_id=account_id, limit=100000)
    return compute_positions([_to_txn_input(r) for r in rows], initial_cash=initial)


# —— CSV 导入 ——


def import_preview(
    db: DBSession,
    *,
    user_id: str,
    text: str,
    request_id: str | None = None,
) -> ImportPreviewResult:
    """解析 + 校验 + 查既有指纹 → 暂存可导入行，返回 batch_id 串起确认。只读 DB（不落交易）。"""
    account = _get_user_account(db, user_id)
    parsed, errors = parse_csv_rows(
        text, market_for_code=lambda code: infer_market(code).value
    )
    fingerprints = [p.fingerprint for p in parsed]
    existing = repository.get_existing_fingerprints(db, account.id, fingerprints)
    importable = [p for p in parsed if p.fingerprint not in existing]
    duplicates = [p for p in parsed if p.fingerprint in existing]
    batch_id = new_id()
    _import_staging[batch_id] = {p.fingerprint: p for p in importable}
    return ImportPreviewResult(
        batch_id=batch_id, preview=importable, errors=errors, duplicates=duplicates
    )


def import_confirm(
    db: DBSession,
    *,
    user_id: str,
    batch_id: str,
    fingerprints: list[str],
    request_id: str | None = None,
) -> dict[str, int]:
    """确认导入：按预览暂存(batch_id) + 既有指纹去重，逐行建标的 + 落交易。"""
    account = _get_user_account(db, user_id)
    staged = _import_staging.get(batch_id)
    if staged is None:
        raise ImportPreviewExpiredError("导入预览已过期或不存在，请重新预览")
    existing = repository.get_existing_fingerprints(db, account.id, fingerprints)
    created = 0
    skipped = 0
    touched_instruments: set[str] = set()
    for fp in fingerprints:
        if fp in existing:
            skipped += 1
            continue
        row = staged.get(fp)
        if row is None:
            skipped += 1
            continue
        instrument = instruments_service.get_or_create_instrument(
            db, code=row.code, name=row.name
        )
        txn = _build_transaction(
            account_id=account.id,
            instrument_id=instrument.id,
            kind=row.kind,
            direction=row.direction,
            quantity=row.quantity,
            price=row.price,
            fee=row.fee,
            tax=row.tax,
            trade_at=row.trade_at,
            fingerprint=row.fingerprint,
            external_ref=None,
            note=None,
        )
        repository.add_transaction(db, txn)
        touched_instruments.add(instrument.id)
        created += 1
        audit_service.append_event(
            db,
            action="transaction_imported",
            target_type="transaction",
            target_id=txn.id,
            after={"code": row.code, "kind": row.kind.value, "trade_at": row.trade_at},
            request_id=request_id,
        )
    db.commit()
    _import_staging.pop(batch_id, None)
    for inst_id in touched_instruments:
        rebuild_snapshots(db, account_id=account.id, instrument_id=inst_id)
    return {"created": created, "skipped": skipped}


def _build_transaction(
    *,
    account_id: str,
    instrument_id: str,
    kind: TransactionKind,
    direction: Direction,
    quantity: Decimal,
    price: Decimal,
    fee: Decimal,
    tax: Decimal,
    trade_at: str,
    fingerprint: str,
    external_ref: str | None,
    note: str | None,
) -> Transaction:
    from wws_adviser.modules.portfolio.domain import decimal_str

    return Transaction(
        id=new_id(),
        account_id=account_id,
        instrument_id=instrument_id,
        kind=kind.value,
        direction=direction.value,
        quantity=decimal_str(quantity),
        price=decimal_str(price),
        fee_minor=to_scaled_int(fee),
        tax_minor=to_scaled_int(tax),
        trade_at=trade_at,
        external_ref=external_ref,
        fingerprint=fingerprint,
        note=note,
        created_at=now_utc_iso(),
        updated_at=now_utc_iso(),
        version=1,
    )
