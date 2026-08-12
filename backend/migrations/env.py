"""Alembic 运行环境。

sqlalchemy.url 从应用配置注入（不硬编码在 alembic.ini）。
Phase 0 无 ORM models，target_metadata 暂为 None —— 仅手动迁移生效；
波2 引入 modules/*/models.py 后接入 Base.metadata，开启 autogenerate。
"""

from alembic import context
from sqlalchemy import engine_from_config, pool

from wws_adviser.core.config import load_settings

config = context.config

_settings = load_settings()
_settings.data_dir.mkdir(parents=True, exist_ok=True)
config.set_main_option("sqlalchemy.url", _settings.db_url)

# Phase 0：无 ORM metadata。波2 改为各模块 models 的 Base.metadata。
target_metadata = None


def run_migrations_offline() -> None:
    context.configure(
        url=_settings.db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
