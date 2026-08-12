"""SQLAlchemy engine / session 与 SQLite PRAGMA。

PRAGMA（连接级，见 2_DATA_MODEL_AND_STORAGE.md §1）：
    journal_mode=WAL, foreign_keys=ON, busy_timeout=5000, synchronous=NORMAL
"""

from collections.abc import Iterator

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from wws_adviser.core.config import Settings


def _set_sqlite_pragmas(dbapi_conn: object, _connection_record: object) -> None:
    cursor = dbapi_conn.cursor()  # type: ignore[attr-defined]
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


def create_app_engine(settings: Settings) -> Engine:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        settings.db_url,
        echo=False,
        connect_args={"check_same_thread": False},
    )
    if engine.dialect.name == "sqlite":
        event.listen(engine, "connect", _set_sqlite_pragmas)
    return engine


def check_db_writable(engine: Engine) -> bool:
    """health/ready 用：能否在 DB 上完成一次写。用 TEMP TABLE 避免污染主库。"""
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE TEMP TABLE _writable_probe (x INTEGER)"))
            conn.execute(text("INSERT INTO _writable_probe (x) VALUES (1)"))
        return True
    except Exception:
        # 健康探针：任何写失败都视为不可写，不向上抛
        return False


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, class_=Session)


class Base(DeclarativeBase):
    """所有 ORM 模型的共享基类（波2 起 modules/*/models.py 继承）。"""


def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """事务作用域上下文（service 层事务边界模式）。"""
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
