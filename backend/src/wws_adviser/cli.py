"""管理 CLI（无公开注册入口；首个用户通过此 CLI 创建，见 8_SECURITY §3）。

用法：
    python -m wws_adviser.cli admin create-user --username <name>
"""

import argparse
import getpass
import sys

from wws_adviser.core.config import load_settings
from wws_adviser.core.db import create_app_engine, make_session_factory
from wws_adviser.core.ids import new_id
from wws_adviser.core.time import now_utc_iso
from wws_adviser.modules.identity import domain
from wws_adviser.modules.identity.models import User
from wws_adviser.modules.identity.repository import get_user_by_username


def create_user(username: str, password: str) -> None:
    settings = load_settings()
    engine = create_app_engine(settings)
    factory = make_session_factory(engine)
    with factory() as db:
        if get_user_by_username(db, username) is not None:
            print(f"用户名已存在: {username}", file=sys.stderr)
            sys.exit(1)
        db.add(
            User(
                id=new_id(),
                username=username,
                password_hash=domain.hash_password(password),
                created_at=now_utc_iso(),
                updated_at=now_utc_iso(),
                version=1,
            )
        )
        db.commit()
        print(f"已创建用户: {username}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="wws-adviser")
    sub = parser.add_subparsers(dest="cmd", required=True)
    admin = sub.add_parser("admin", help="管理命令")
    admin_sub = admin.add_subparsers(dest="admin_cmd", required=True)
    create = admin_sub.add_parser("create-user", help="创建用户")
    create.add_argument("--username", required=True)
    create.add_argument("--password", help="密码（不传则交互式输入）")
    args = parser.parse_args()

    if args.cmd == "admin" and args.admin_cmd == "create-user":
        password = args.password or getpass.getpass("密码: ")
        if not password:
            print("密码不能为空", file=sys.stderr)
            sys.exit(1)
        create_user(args.username, password)


if __name__ == "__main__":
    main()
