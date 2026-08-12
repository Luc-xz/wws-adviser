"""文档/报告对象存储抽象（本地 FS 实现）。

内容寻址 sha256（技术架构 §7.5）。路径服务端生成（防穿越），存相对 /data 的路径
便于容器移植。
"""

from typing import Protocol


class ObjectStore(Protocol):
    def put(self, content: bytes, kind: str, ext: str = "bin") -> str:
        """存内容，返回相对 /data 的路径（按 sha256 内容寻址）。"""
        ...

    def get(self, relative_path: str) -> bytes: ...

    def exists(self, relative_path: str) -> bool: ...
