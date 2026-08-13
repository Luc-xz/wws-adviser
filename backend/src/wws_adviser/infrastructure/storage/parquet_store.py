"""Parquet 行情主存（polars，2_DATA_MODEL_AND_STORAGE.md §8）。

日线/净值完整历史存 Parquet；SQLite 仅存元数据索引（market_records/nav_records）。
布局：data/market/{daily,nav}/...；原子写 part.parquet.tmp → os.replace。
本波为骨架：写完整数据 + 返回 content_hash；文件级 schema/metadata 列留后续硬化。
"""

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import polars as pl

_SCHEMA_VERSION = "1"


def _rows_hash(rows: list[dict[str, Any]]) -> str:
    """行数据的稳定内容哈希（用于去重/与 SQLite 索引行关联）。"""
    payload = json.dumps(rows, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _atomic_write_parquet(df: pl.DataFrame, final_path: Path) -> None:
    final_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = final_path.with_suffix(".parquet.tmp")
    df.write_parquet(tmp_path)
    os.replace(tmp_path, final_path)


def write_bars(
    data_dir: Path,
    *,
    market: str,
    instrument_id: str,
    year: int,
    rows: list[dict[str, str]],
    adjustment_type: str = "none",
) -> str:
    """写某 instrument 某 year 的日线分区，返回 content_hash。rows 缺省列补空串。"""
    if not rows:
        return ""
    cols = ["business_date", "open", "high", "low", "close", "volume", "amount"]
    normalized = [{c: r.get(c, "") for c in cols} for r in rows]
    df = pl.DataFrame(normalized)
    final = (
        data_dir
        / "market"
        / "daily"
        / f"market={market}"
        / f"instrument={instrument_id}"
        / f"year={year}"
        / "part.parquet"
    )
    _atomic_write_parquet(df, final)
    return _rows_hash(normalized)


def read_bars(
    data_dir: Path, *, instrument_id: str, start: str | None = None, end: str | None = None
) -> list[dict[str, str]]:
    """读某 instrument 全部分区并按 [start, end]（YYYY-MM-DD，闭区间）过滤，按日期升序。"""
    pattern = f"market/daily/market=*/instrument={instrument_id}/year=*/part.parquet"
    paths = sorted(data_dir.glob(pattern))
    if not paths:
        return []
    df = pl.read_parquet([str(p) for p in paths])
    if start is not None:
        df = df.filter(pl.col("business_date") >= start)
    if end is not None:
        df = df.filter(pl.col("business_date") <= end)
    df = df.sort("business_date")
    return [{k: str(v) for k, v in row.items()} for row in df.to_dicts()]


def write_nav(
    data_dir: Path,
    *,
    instrument_id: str,
    year: int,
    rows: list[dict[str, str]],
) -> str:
    """写某 instrument 某 year 的净值分区，返回 content_hash。"""
    if not rows:
        return ""
    cols = ["nav_date", "nav", "published_at"]
    normalized = [{c: r.get(c, "") for c in cols} for r in rows]
    df = pl.DataFrame(normalized)
    final = (
        data_dir
        / "market"
        / "nav"
        / f"instrument={instrument_id}"
        / f"year={year}"
        / "part.parquet"
    )
    _atomic_write_parquet(df, final)
    return _rows_hash(normalized)


def read_nav(
    data_dir: Path, *, instrument_id: str, start: str | None = None, end: str | None = None
) -> list[dict[str, str]]:
    pattern = f"market/nav/instrument={instrument_id}/year=*/part.parquet"
    paths = sorted(data_dir.glob(pattern))
    if not paths:
        return []
    df = pl.read_parquet([str(p) for p in paths])
    if start is not None:
        df = df.filter(pl.col("nav_date") >= start)
    if end is not None:
        df = df.filter(pl.col("nav_date") <= end)
    df = df.sort("nav_date")
    return [{k: str(v) for k, v in row.items()} for row in df.to_dicts()]


SCHEMA_VERSION = _SCHEMA_VERSION
