"""ID 生成（ULID）。

ULID 26 位、时间有序，跨 SQLite/PG 迁移友好；python-ulid 运行时生成（非 DB 默认）。
见 1_REPO_STRUCTURE.md §8、2_DATA_MODEL_AND_STORAGE.md §4。
"""

from ulid import ULID


def new_id() -> str:
    return str(ULID())
