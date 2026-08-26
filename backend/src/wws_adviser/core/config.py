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
    # 波2 运行配置（见 ADR-0010）
    session_ttl_days: int = 14
    reauth_window_minutes: int = 15
    login_rate_limit_max: int = 5
    login_rate_limit_window_seconds: int = 300
    job_lease_ttl_seconds: int = 300
    job_max_attempts: int = 3
    # 波2 行情采集运行配置（5_DATA_INGESTION_AND_QUALITY.md §5/§13）
    market_data_source: str = "stub"  # stub | akshare（akshare 需装 optional extra）
    document_source: str = "stub"  # stub | akshare（公告/新闻，同 market_data 选源模式）
    # 波4 风险硬上限默认（PRD FR-ANL-002；/settings/risk 持久化 + PATCH 留后续小波次）
    risk_single_cap: float = 0.30  # 单标的最大仓位
    risk_industry_cap: float = 0.40  # 单行业最大仓位
    risk_cash_floor: float = 0.10  # 最低现金比例
    risk_top_n: int = 5
    risk_top_n_concentration: float = 0.60  # 前 N 大持仓集中度
    # 波6 模型网关（通用 OpenAI-compatible；key 只经 env 引用，绝不落库/日志）
    model_source: str = "stub"  # stub | openai
    model_base_url: str = ""
    model_name: str = ""
    model_api_key_ref: str = "WWSE_MODEL_API_KEY"  # env 变量名（引用）
    model_temperature: float = 0.2
    model_max_tokens: int = 2048
    model_timeout: float = 90.0
    model_retry: int = 1
    # 波6 通知（邮件 SMTP 587/465，已确认；凭据只经 env 引用）
    notifier_source: str = "stub"  # stub | smtp
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_key_ref: str = "WWSE_SMTP_KEY"  # env 变量名（引用）
    smtp_from_addr: str = ""
    smtp_to_addr: str = ""
    smtp_use_tls: bool = True
    notification_privacy_mode: bool = True  # 锁屏通知不含标的/金额/动作
    # 波8 部署：同源静态（PWA dist；空=不挂载，开发用 vite dev/proxy）；执行器轮询间隔
    static_dir: Path | None = None
    executor_poll_seconds: int = 30
    # TODO(Phase2): 盘中新鲜度门禁实际生效；日线口径波2 已用 DAILY 规则
    intraday_freshness_threshold_seconds: int = 180
    clock_skew_threshold_seconds: int = 5  # 偏移超阈值 → warning + health 标 skew
    clock_skew_ntp_host: str = "ntp.aliyun.com"  # SNTP 源；空串=禁用（UDP 被拦时设空）
    nav_published_freshness_hours: int = 24

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
        session_ttl_days=int(os.environ.get("WWSE_SESSION_TTL_DAYS", "14")),
        reauth_window_minutes=int(os.environ.get("WWSE_REAUTH_WINDOW_MIN", "15")),
        login_rate_limit_max=int(os.environ.get("WWSE_LOGIN_RATE_LIMIT_MAX", "5")),
        login_rate_limit_window_seconds=int(
            os.environ.get("WWSE_LOGIN_RATE_LIMIT_WINDOW_SEC", "300")
        ),
        job_lease_ttl_seconds=int(os.environ.get("WWSE_JOB_LEASE_TTL_SEC", "300")),
        job_max_attempts=int(os.environ.get("WWSE_JOB_MAX_ATTEMPTS", "3")),
        market_data_source=os.environ.get("WWSE_MARKET_DATA_SOURCE", "stub"),
        document_source=os.environ.get("WWSE_DOCUMENT_SOURCE", "stub"),
        risk_single_cap=float(os.environ.get("WWSE_RISK_SINGLE_CAP", "0.30")),
        risk_industry_cap=float(os.environ.get("WWSE_RISK_INDUSTRY_CAP", "0.40")),
        risk_cash_floor=float(os.environ.get("WWSE_RISK_CASH_FLOOR", "0.10")),
        risk_top_n=int(os.environ.get("WWSE_RISK_TOP_N", "5")),
        risk_top_n_concentration=float(os.environ.get("WWSE_RISK_TOP_N_CONC", "0.60")),
        model_source=os.environ.get("WWSE_MODEL_SOURCE", "stub"),
        model_base_url=os.environ.get("WWSE_MODEL_BASE_URL", ""),
        model_name=os.environ.get("WWSE_MODEL_NAME", ""),
        model_api_key_ref=os.environ.get("WWSE_MODEL_API_KEY_REF", "WWSE_MODEL_API_KEY"),
        model_temperature=float(os.environ.get("WWSE_MODEL_TEMPERATURE", "0.2")),
        model_max_tokens=int(os.environ.get("WWSE_MODEL_MAX_TOKENS", "2048")),
        model_timeout=float(os.environ.get("WWSE_MODEL_TIMEOUT", "90")),
        model_retry=int(os.environ.get("WWSE_MODEL_RETRY", "1")),
        notifier_source=os.environ.get("WWSE_NOTIFIER_SOURCE", "stub"),
        smtp_host=os.environ.get("WWSE_SMTP_HOST", ""),
        smtp_port=int(os.environ.get("WWSE_SMTP_PORT", "587")),
        smtp_user=os.environ.get("WWSE_SMTP_USER", ""),
        smtp_key_ref=os.environ.get("WWSE_SMTP_KEY_REF", "WWSE_SMTP_KEY"),
        smtp_from_addr=os.environ.get("WWSE_SMTP_FROM", ""),
        smtp_to_addr=os.environ.get("WWSE_SMTP_TO", ""),
        smtp_use_tls=os.environ.get("WWSE_SMTP_USE_TLS", "1") not in ("0", "false", "no"),
        notification_privacy_mode=os.environ.get("WWSE_NOTIFY_PRIVACY", "1")
        not in ("0", "false", "no"),
        static_dir=Path(os.environ["WWSE_STATIC_DIR"])
        if os.environ.get("WWSE_STATIC_DIR")
        else None,
        executor_poll_seconds=int(os.environ.get("WWSE_EXECUTOR_POLL_SEC", "30")),
        intraday_freshness_threshold_seconds=int(
            os.environ.get("WWSE_INTRADAY_FRESHNESS_SEC", "180")
        ),
        clock_skew_threshold_seconds=int(os.environ.get("WWSE_CLOCK_SKEW_SEC", "5")),
        clock_skew_ntp_host=os.environ.get("WWSE_CLOCK_SKEW_NTP_HOST", "ntp.aliyun.com"),
        nav_published_freshness_hours=int(os.environ.get("WWSE_NAV_FRESHNESS_HOURS", "24")),
    )
