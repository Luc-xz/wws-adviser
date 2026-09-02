"""交割单 CSV 导入（VPS 容器内运行，复用导入器校验/指纹/审计，无需 HTTP 密码）。

用法（在 VPS 上）——周期增量导入三步：
    # 1) 导出服务器状态（持仓/现金/最后交易日期，重定向到文件或直接内联）
    docker exec deploy-wws-1 python /app/backend/scripts/import_settlement.py \
        --export-positions --username luc > state.json
    # 2) 本地转换（剔除期初合成 + 对账校验，详见 jgd_pdf_to_csv.py）
    uv run --with pdfplumber python scripts/jgd_pdf_to_csv.py 新单.pdf \
        --incremental state.json -o tx.csv
    # 3) 上传导入
    docker cp tx.csv deploy-wws-1:/tmp/tx.csv
    docker exec deploy-wws-1 python /app/backend/scripts/import_settlement.py \
        /tmp/tx.csv --username luc

首次导入（空账户）：第 2 步不带 --incremental 转换，按其「推算初始现金」输出
先设好账户初始现金，再走第 3 步。

行为：
- 预览（错误/重复/可导入行数）→ 有错误即中止 → 确认导入
- 首次导入前须先设好账户初始现金（经交割单反推，见 jgd_pdf_to_csv.py 输出）
- 重复导入同一 CSV 安全（指纹去重）；但**不要导入区间重叠的不同 PDF**
  （聚合边界不同会产生不同指纹导致双计）——每次导「上次之后」的区间；
  增量转换会按 last_trade_date 自动拦截重叠
- --export-positions：打印 {"last_trade_date", "cash", "positions"} JSON 到 stdout
  （cash 为回放推导值，可能含历史亚分尾差；转换端现金闭合容差 0.01）
"""

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from wws_adviser.core.config import load_settings
from wws_adviser.core.db import create_app_engine, make_session_factory
from wws_adviser.modules.identity.models import User
from wws_adviser.modules.instruments.models import Instrument
from wws_adviser.modules.portfolio import service as portfolio_service
from wws_adviser.modules.portfolio.models import Transaction


def export_state(db: Session, user: User) -> dict:
    """增量转换所需的服务器状态：最后交易日期 + 回放现金 + 各代码净持仓。"""
    try:
        account = portfolio_service.get_user_account(db, user.id)
    except portfolio_service.AccountNotFoundError:
        raise SystemExit("账户不存在——先建账户再导出状态") from None
    state = portfolio_service.get_position_state(db, account.id)
    ids = list(state.positions)
    id_to_code = (
        {
            inst.id: inst.code
            for inst in db.scalars(select(Instrument).where(Instrument.id.in_(ids)))
        }
        if ids
        else {}
    )
    positions = {
        id_to_code[iid]: str(p.qty)
        for iid, p in state.positions.items()
        if p.qty != 0 and iid in id_to_code
    }
    last = db.scalar(
        select(Transaction.trade_at)
        .where(Transaction.account_id == account.id, Transaction.deleted_at.is_(None))
        .order_by(Transaction.trade_at.desc())
        .limit(1)
    )
    return {
        "username": user.username,
        "last_trade_date": last,
        "cash": str(state.cash),
        "positions": positions,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="交割单 CSV 导入（service 层）")
    ap.add_argument("csv_path", nargs="?", default=None)
    ap.add_argument("--username", default="luc")
    ap.add_argument("--request-id", default=None)
    ap.add_argument(
        "--export-positions", action="store_true",
        help="导出增量转换状态 JSON（last_trade_date/cash/positions）到 stdout 后退出",
    )
    args = ap.parse_args()

    settings = load_settings()
    engine = create_app_engine(settings)
    factory = make_session_factory(engine)
    try:
        with factory() as db:
            user = db.scalar(select(User).where(User.username == args.username))
            if user is None:
                raise SystemExit(f"用户 {args.username} 不存在")
            if args.export_positions:
                print(json.dumps(export_state(db, user), ensure_ascii=False))
                return
            if args.csv_path is None:
                raise SystemExit("缺少 CSV 路径（或改用 --export-positions）")

            text = Path(args.csv_path).read_text(encoding="utf-8-sig")
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
