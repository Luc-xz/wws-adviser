"""交割单 CSV 导入（VPS 容器内运行，复用导入器校验/指纹/审计，无需 HTTP 密码）。

用法（在 VPS 上）：
    docker cp 新单.csv deploy-wws-1:/tmp/tx.csv
    docker cp backend/scripts/import_settlement.py deploy-wws-1:/tmp/
    docker exec deploy-wws-1 python /tmp/import_settlement.py /tmp/tx.csv --username luc

行为：
- 预览（错误/重复/可导入行数）→ 有错误即中止 → 确认导入
- 首次导入前须先设好账户初始现金（经交割单反推，见 jgd_pdf_to_csv.py 输出）
- 重复导入同一 CSV 安全（指纹去重）；但**不要导入区间重叠的不同 PDF**
  （聚合边界不同会产生不同指纹导致双计）——每次导「上次之后」的区间
"""

import argparse
import sys
from pathlib import Path

from sqlalchemy import select

from wws_adviser.core.config import load_settings
from wws_adviser.core.db import create_app_engine, make_session_factory
from wws_adviser.modules.identity.models import User
from wws_adviser.modules.portfolio import service as portfolio_service


def main() -> None:
    ap = argparse.ArgumentParser(description="交割单 CSV 导入（service 层）")
    ap.add_argument("csv_path")
    ap.add_argument("--username", default="luc")
    ap.add_argument("--request-id", default=None)
    args = ap.parse_args()

    text = Path(args.csv_path).read_text(encoding="utf-8-sig")
    settings = load_settings()
    engine = create_app_engine(settings)
    factory = make_session_factory(engine)
    try:
        with factory() as db:
            user = db.scalar(select(User).where(User.username == args.username))
            if user is None:
                raise SystemExit(f"用户 {args.username} 不存在")
            account = portfolio_service.get_user_account(db, user.id)
            if account is None:
                raise SystemExit("账户不存在——首次导入前请先建账户并设初始现金")

            preview = portfolio_service.import_preview(
                db, user_id=user.id, text=text,
                request_id=args.request_id or f"settlement-{account.id[:8]}",
            )
            print(f"预览: 可导入 {len(preview.preview)} 行, "
                  f"错误 {len(preview.errors)}, 重复 {len(preview.duplicates)}")
            for e in preview.errors[:10]:
                print("  错误:", e.row_no, e.message)
            if preview.errors:
                raise SystemExit("存在错误行，已中止（未导入任何数据）")
            if not preview.preview:
                print("无可导入行（全部为重复？）——结束")
                return

            fps = [p.fingerprint for p in preview.preview]
            result = portfolio_service.import_confirm(
                db, user_id=user.id, batch_id=preview.batch_id,
                fingerprints=fps, request_id=args.request_id,
            )
            print(f"确认: {result}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
