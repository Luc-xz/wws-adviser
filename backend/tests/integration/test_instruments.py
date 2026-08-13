"""Instruments 服务层测试：get_or_create 幂等、搜索（db_session，无认证）。"""

from sqlalchemy import select

from wws_adviser.modules.instruments import service as instruments_service
from wws_adviser.modules.instruments.models import Instrument


def test_get_or_create_idempotent(db_session) -> None:
    a = instruments_service.get_or_create_instrument(db_session, code="600519", name="贵州茅台")
    b = instruments_service.get_or_create_instrument(db_session, code="600519", name="贵州茅台")
    db_session.commit()
    assert a.id == b.id  # 同 (market, code) 返回同一行
    assert a.market == "SSE"
    assert a.kind == "STOCK"
    rows = list(db_session.scalars(select(Instrument)))
    assert len(rows) == 1


def test_get_or_create_infers_etf(db_session) -> None:
    inst = instruments_service.get_or_create_instrument(
        db_session, code="510300", name="沪深300ETF"
    )
    db_session.commit()
    assert inst.market == "SSE"
    assert inst.kind == "ETF"


def test_search_by_code_or_name(db_session) -> None:
    instruments_service.get_or_create_instrument(db_session, code="600519", name="贵州茅台")
    instruments_service.get_or_create_instrument(db_session, code="000001", name="平安银行")
    db_session.commit()

    by_code = instruments_service.search_instruments(db_session, q="6005")
    assert len(by_code) == 1
    assert by_code[0].code == "600519"

    by_name = instruments_service.search_instruments(db_session, q="平安")
    assert len(by_name) == 1
    assert by_name[0].code == "000001"

    sse = instruments_service.search_instruments(db_session, market="SSE")
    assert {i.code for i in sse} == {"600519"}
