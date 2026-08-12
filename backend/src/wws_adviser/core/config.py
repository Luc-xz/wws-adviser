"""应用配置（Pydantic Settings）。

环境变量以 `WWSE_` 为前缀（见 8_SECURITY_AND_DEPLOYMENT.md §env 分类、
1_REPO_STRUCTURE.md §7）。生产环境必须设置安全的 `WWSE_SESSION_SECRET`。
"""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, model_validator


class Settings(BaseModel):
    """运行配置。通过环境变量（WWSE_ 前缀）注入。"""

    model_config = ConfigDict(extra="ignore")

    env: str = "dev"
    expected_workers: int = 1
    data_dir: Path = Path("./data")
    session_secret: str = "dev-insecure-secret-change-in-prod"
    log_level: str = "INFO"

    @property
    def is_prod(self) -> bool:
        return self.env == "prod"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def db_url(self) -> str:
        # SQLite URL 用 posix 路径，避免 Windows 反斜杠
        return f"sqlite:///{self.db_path.as_posix()}"

    @property
    def locks_dir(self) -> Path:
        return self.data_dir / "locks"

    @property
    def scheduler_lock_path(self) -> Path:
        return self.locks_dir / "scheduler.lock"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    @model_validator(mode="after")
    def _prod_requires_real_secret(self) -> "Settings":
        if self.is_prod and self.session_secret.startswith("dev-insecure"):
            raise ValueError(
                "WWSE_SESSION_SECRET 必须在生产环境设置安全值（当前为开发占位）"
            )
        return self


def load_settings(
    *,
    env: str | None = None,
    data_dir: Path | None = None,
    session_secret: str | None = None,
) -> Settings:
    """构造 Settings。测试可用关键字参数覆盖；运行时从环境变量读。"""
    import os

    return Settings(
        env=env if env is not None else os.environ.get("WWSE_ENV", "dev"),
        expected_workers=int(os.environ.get("WWSE_EXPECTED_WORKERS", "1")),
        data_dir=data_dir if data_dir is not None else Path(
            os.environ.get("WWSE_DATA_DIR", "./data")
        ),
        session_secret=(
            session_secret if session_secret is not None else os.environ["WWSE_SESSION_SECRET"]
            if "WWSE_SESSION_SECRET" in os.environ
            else "dev-insecure-secret-change-in-prod"
        ),
        log_level=os.environ.get("WWSE_LOG_LEVEL", "INFO"),
    )
