"""Portfolio 仓储。"""

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session as DBSession

from wws_adviser.modules.portfolio.models import Account, Transaction

# —— Account ————————————————————————————————————————————


def add_account(db: DBSession, account: Account) -> Account:
    db.add(account)
    db.flush()
    return account


def get_accounts_by_user(db: DBSession, user_id: str) -> list[Account]:
    return list(
        db.scalars(
            select(Account).where(Account.user_id == user_id).order_by(Account.created_at)
        )
    )


def get_account_by_id(db: DBSession, account_id: str) -> Account | None:
    return db.get(Account, account_id)


# —— Transaction ————————————————————————————————————————


def add_transaction(db: DBSession, txn: Transaction) -> Transaction:
    db.add(txn)
    db.flush()
    return txn


def get_transaction_by_id(db: DBSession, transaction_id: str) -> Transaction | None:
    return db.get(Transaction, transaction_id)


def get_transaction_by_fingerprint(
    db: DBSession, account_id: str, fingerprint: str
) -> Transaction | None:
    return db.scalar(
        select(Transaction).where(
            Transaction.account_id == account_id,
            Transaction.fingerprint == fingerprint,
            Transaction.deleted_at.is_(None),
        )
    )


def get_transaction_by_external_ref(
    db: DBSession, account_id: str, external_ref: str
) -> Transaction | None:
    return db.scalar(
        select(Transaction).where(
            Transaction.account_id == account_id,
            Transaction.external_ref == external_ref,
            Transaction.deleted_at.is_(None),
        )
    )


def get_existing_fingerprints(
    db: DBSession, account_id: str, fingerprints: list[str]
) -> set[str]:
    if not fingerprints:
        return set()
    rows = db.scalars(
        select(Transaction.fingerprint).where(
            Transaction.account_id == account_id,
            Transaction.fingerprint.in_(fingerprints),
            Transaction.deleted_at.is_(None),
        )
    )
    return set(rows)


def list_transactions(
    db: DBSession,
    *,
    account_id: str,
    instrument_id: str | None = None,
    kind: str | None = None,
    cursor_tuple: tuple[str, str] | None = None,
    limit: int = 50,
) -> list[Transaction]:
    """按 trade_at DESC, id DESC 游标分页。"""
    stmt = select(Transaction).where(
        Transaction.account_id == account_id,
        Transaction.deleted_at.is_(None),
    )
    if instrument_id:
        stmt = stmt.where(Transaction.instrument_id == instrument_id)
    if kind:
        stmt = stmt.where(Transaction.kind == kind)
    if cursor_tuple is not None:
        c_trade_at, c_id = cursor_tuple
        stmt = stmt.where(
            or_(
                Transaction.trade_at < c_trade_at,
                and_(Transaction.trade_at == c_trade_at, Transaction.id < c_id),
            )
        )
    stmt = stmt.order_by(Transaction.trade_at.desc(), Transaction.id.desc()).limit(limit)
    return list(db.scalars(stmt))
