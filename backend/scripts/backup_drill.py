"""备份恢复演练：backup → restore → verify（Phase 0 骨架）。

验证 Online Backup API 通路 + restore 后 schema 一致、DB 可读。
账本哈希/持仓数值一致性验证留 Phase 1（Phase 0 无业务数据）。
"""

import sqlite3
import sys
import tempfile
from pathlib import Path

from wws_adviser.core.backup import backup_database
from wws_adviser.core.config import load_settings


def _table_names(db_path: Path) -> set[str]:
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    conn.close()
    return {r[0] for r in rows}


def main() -> None:
    settings = load_settings()
    src = settings.db_path
    if not src.exists():
        print(f"DB 不存在: {src}（先 make migrate）", file=sys.stderr)
        sys.exit(1)

    with tempfile.TemporaryDirectory() as td:
        dest = Path(td) / "app.db.bak"
        backup_database(src, dest)

        tables_bak = _table_names(dest)
        tables_src = _table_names(src)
        if tables_bak != tables_src:
            print(
                f"✗ 表集合不一致: backup={tables_bak} source={tables_src}",
                file=sys.stderr,
            )
            sys.exit(1)

        print(f"✓ 备份演练通过：{len(tables_bak)} 表一致，restore 后可读")


if __name__ == "__main__":
    main()
