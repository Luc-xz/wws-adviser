"""本地 FS 对象存储：内容寻址 sha256（技术架构 §7.5）。

真实实现（非 stub）。按 data/documents/{kind}/{sha[0:2]}/{sha}.{ext} 存储；
服务端生成路径防穿越；.tmp→rename 原子写；DB 存相对 /data 的路径。
"""

import hashlib
import os
from pathlib import Path


class LocalObjectStore:
    """按 sha256 内容寻址的本地对象存储（实现 ports.object_store.ObjectStore 协议）。"""

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir

    def _rel_path(self, sha: str, kind: str, ext: str) -> str:
        return os.path.join("documents", kind, sha[:2], f"{sha}.{ext}")

    def _safe_abs(self, relative_path: str) -> Path:
        abs_path = (self._data_dir / relative_path).resolve()
        base = self._data_dir.resolve()
        if base not in abs_path.parents and abs_path != base:
            raise ValueError(f"路径越界（防穿越拒绝）：{relative_path}")
        return abs_path

    def put(self, content: bytes, kind: str, ext: str = "bin") -> str:
        sha = hashlib.sha256(content).hexdigest()
        rel = self._rel_path(sha, kind, ext)
        abs_path = self._data_dir / rel
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = abs_path.with_name(abs_path.name + ".tmp")
        tmp.write_bytes(content)
        tmp.replace(abs_path)  # 原子写
        return rel

    def get(self, relative_path: str) -> bytes:
        return self._safe_abs(relative_path).read_bytes()

    def exists(self, relative_path: str) -> bool:
        return self._safe_abs(relative_path).exists()
