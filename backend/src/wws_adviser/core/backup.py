"""备份骨架。

用 SQLite Online Backup API 产出一致性副本（见 2_DATA_MODEL_AND_STORAGE.md §7 备份）。
Phase 0 仅实现 DB 一致性拷贝；job 锁、文件 manifest、加密、恢复演练在波2/波5 接入。
"""

import sqlite3
from pathlib import Path


def backup_database(src_db: Path, dest_db: Path) -> Path:
    """用 Online Backup API 把 src 拷贝到 dest，返回 dest 路径。

    src.backup(dst) 在 WAL 模式下产出事务一致快照，避免直接复制 db 文件导致
    WAL 与主库不一致（2_DATA_MODEL_AND_STORAGE.md §7 硬约束）。
    """
    dest_db.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(str(src_db))
    dst = sqlite3.connect(str(dest_db))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return dest_db
