"""领域异常基类。

service 层抛 `DomainError`（或子类）/ `OperationError`，由 api/errors.py 统一翻译为
Problem Details（见 1_REPO_STRUCTURE.md §4.2 service 边界规则）。

`code` 对应 3_API_CONTRACT.md §错误码表的枚举值，是前端分支的键。
"""

from typing import Self


class DomainError(Exception):
    """领域异常基类。子类覆盖 code/status/title。"""

    code: str = "INTERNAL_ERROR"
    status: int = 500
    title: str = "内部错误"

    def __init__(self, detail: str = "", *, reasons: list[str] | None = None) -> None:
        super().__init__(detail or self.title)
        self.detail = detail or self.title
        self.reasons = reasons or []

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)

    @classmethod
    def with_detail(cls, detail: str, *, reasons: list[str] | None = None) -> Self:
        return cls(detail, reasons=reasons)


class OperationError(DomainError):
    """通用操作错误（未明确分类的领域操作失败）。"""

    code = "INTERNAL_ERROR"
    status = 500
    title = "操作失败"
