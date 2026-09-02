"""import_settlement.py --export-positions：增量转换状态导出（最后交易日期/现金/净持仓）。

对应 jgd_pdf_to_csv.py --incremental 的状态输入端（周期增量导入三步的第一步）。
"""

import importlib.util
import sys
from decimal import Decimal
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "import_settlement", Path(__file__).resolve().parents[2] / "scripts" / "import_settlement.py"
)
import_settlement = importlib.util.module_from_spec(_spec)
sys.modules["import_settlement"] = import_settlement
_spec.loader.exec_module(import_settlement)


def _make_user(db_session):
    from wws_adviser.core.ids import new_id
    from wws_adviser.core.time import now_utc_iso
    from wws_adviser.modules.identity import domain
    from wws_adviser.modules.identity.models import User

    user = User(id=new_id(), username="luc", password_hash=domain.hash_password("pw12345"),
                created_at=now_utc_iso(), updated_at=now_utc_iso(), version=1)
    db_session.add(user)
    db_session.commit()
    return user


def test_export_positions_state(db_session) -> None:
    from wws_adviser.modules.instruments import service as instruments_service
    from wws_adviser.modules.portfolio import service as portfolio_service
    from wws_adviser.modules.portfolio.domain import TransactionKind

    user = _make_user(db_session)
    portfolio_service.create_account(db_session, user_id=user.id, name="main",
                                     initial_cash=Decimal("1000"))
    inst = instruments_service.get_or_create_instrument(db_session, code="510500", name="500ETF")
    portfolio_service.record_transaction(
        db_session, user_id=user.id, instrument_id=inst.id, kind=TransactionKind.BUY,
        quantity=Decimal("100"), price=Decimal("7.804"), fee=Decimal("0.10"),
        trade_at="2026-08-24",
    )

    state = import_settlement.export_state(db_session, user)

    assert state["username"] == "luc"
    assert state["last_trade_date"] == "2026-08-24"
    # 回放现金：1000 − (100×7.804 + 0.10) = 219.50（Decimal 运算保 3 位小数精度）
    assert state["cash"] == "219.500"
    assert state["positions"] == {"510500": "100"}


def test_export_positions_empty_account(db_session) -> None:
    """无交易账户：last_trade_date=None、持仓空——增量转换端据此放行任意起点区间。"""
    from wws_adviser.modules.portfolio import service as portfolio_service

    user = _make_user(db_session)
    portfolio_service.create_account(db_session, user_id=user.id, name="main",
                                     initial_cash=Decimal("5000"))

    state = import_settlement.export_state(db_session, user)

    assert state["last_trade_date"] is None
    assert state["cash"] == "5000.00"  # 定标整数分往返（2 位小数）
    assert state["positions"] == {}


def test_export_positions_requires_account(db_session) -> None:
    user = _make_user(db_session)
    try:
        import_settlement.export_state(db_session, user)
        raise AssertionError("应拒绝无账户用户")
    except SystemExit as e:
        assert "账户不存在" in str(e)
