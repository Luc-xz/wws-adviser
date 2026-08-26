"""一次性脚本：修正 luc 账户初始现金 + service 层导入交割单 CSV（VPS 容器内运行）。"""

from decimal import Decimal

from sqlalchemy import select

from wws_adviser.core.config import load_settings
from wws_adviser.core.db import create_app_engine, make_session_factory
from wws_adviser.modules.identity.models import User
from wws_adviser.modules.portfolio import service as portfolio_service
from wws_adviser.modules.portfolio.domain import to_scaled_int

settings = load_settings()
engine = create_app_engine(settings)
factory = make_session_factory(engine)
with factory() as db:
    luc = db.scalar(select(User).where(User.username == "luc"))
    assert luc is not None, "用户 luc 不存在"
    account = portfolio_service.get_user_account(db, luc.id)
    assert account is not None

    # 1) 修正初始现金（交割单反推 80644.78）；current_cash 同步为期末余额
    account.initial_cash_minor = to_scaled_int(Decimal("80644.78"))
    account.current_cash_minor = to_scaled_int(Decimal("31152.66"))
    db.commit()
    print("账户已修正: initial=80644.78, current=31152.66")

    # 2) 导入（预览 → 确认）
    text = open("/tmp/jgd.csv", encoding="utf-8-sig").read()
    preview = portfolio_service.import_preview(
        db, user_id=luc.id, text=text, request_id="jgd-import-1"
    )
    print(
        f"预览: 可导入 {len(preview.preview)} 行, "
        f"错误 {len(preview.errors)}, 重复 {len(preview.duplicates)}"
    )
    for e in preview.errors[:10]:
        print("  错误:", e.row_no, e.message)
    if preview.errors:
        raise SystemExit("存在错误行，中止（不确认）")
    fps = [p.fingerprint for p in preview.preview]
    result = portfolio_service.import_confirm(
        db, user_id=luc.id, batch_id=preview.batch_id,
        fingerprints=fps, request_id="jgd-import-1",
    )
    print(f"确认: {result}")
    db.commit()
engine.dispose()
