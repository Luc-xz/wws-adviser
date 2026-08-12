"""基础设施层：端口的适配器实现（SQLAlchemy、HTTP 数据源、模型 SDK、文件系统）。

stub_* 适配器返回合成数据（source="stub"），禁生产（5_DATA_INGESTION_AND_QUALITY.md §2）。
"""


def assert_not_prod(env: str) -> None:
    """stub 适配器构造时调用：生产环境直接拒绝。"""
    if env == "prod":
        raise RuntimeError("stub 适配器禁用于生产环境（见 5_DATA_INGESTION_AND_QUALITY.md §2）")
