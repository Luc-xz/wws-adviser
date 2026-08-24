"""Analytics ORM：信号定义与校准记录（Phase 2 波6）。

- signals：版本化信号定义（FR-ANL-003：训练/统计窗口、成本假设、适用品种）。
- signal_calibrations：每信号版本一条最新校准结论（p 区间/b/n_eff/状态/Platt）。
  p 只在回测/校准服务内写入；Decimal 一律字符串存储（与 market_records 同约定）。
"""

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from wws_adviser.core.db import Base


class SignalRecord(Base):
    __tablename__ = "signals"
    __table_args__ = (sa.UniqueConstraint("signal_id", "version", name="uq_signals_id_version"),)

    id: Mapped[str] = mapped_column(sa.String(26), primary_key=True)
    signal_id: Mapped[str] = mapped_column(sa.Text, nullable=False)
    name: Mapped[str] = mapped_column(sa.Text, nullable=False)
    signal_class: Mapped[str] = mapped_column(sa.Text, nullable=False)  # L1|L2|L3|L4
    version: Mapped[str] = mapped_column(sa.Text, nullable=False)
    lookback_days: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    horizon_days: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    cost_bps: Mapped[int] = mapped_column(sa.Integer, nullable=False)  # 单边基点
    universe: Mapped[str] = mapped_column(sa.Text, nullable=False)
    created_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
    row_version: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)


class SignalCalibration(Base):
    __tablename__ = "signal_calibrations"
    __table_args__ = (
        sa.UniqueConstraint("signal_def_id", "signal_version", name="uq_calibrations_def_version"),
        sa.Index("ix_calibrations_state", "state"),
    )

    id: Mapped[str] = mapped_column(sa.String(26), primary_key=True)
    signal_def_id: Mapped[str] = mapped_column(sa.String(26), sa.ForeignKey("signals.id"), nullable=False)
    signal_id: Mapped[str] = mapped_column(sa.Text, nullable=False)   # 冗余便于查询
    signal_version: Mapped[str] = mapped_column(sa.Text, nullable=False)
    state: Mapped[str] = mapped_column(sa.Text, nullable=False)       # 校准状态机
    calibrated_on: Mapped[str] = mapped_column(sa.Text, nullable=False)
    expires_on: Mapped[str] = mapped_column(sa.Text, nullable=False)
    p_low: Mapped[str] = mapped_column(sa.Text, nullable=False)
    p_mid: Mapped[str] = mapped_column(sa.Text, nullable=False)
    p_high: Mapped[str] = mapped_column(sa.Text, nullable=False)
    b: Mapped[str] = mapped_column(sa.Text, nullable=False)
    n_eff: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    n_eff_oos: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    reliability_passed: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, default=False)
    platt_a: Mapped[float | None] = mapped_column(sa.Float)
    platt_b: Mapped[float | None] = mapped_column(sa.Float)
    notes_json: Mapped[str | None] = mapped_column(sa.Text)           # OOS 原因链等审计材料
    created_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(sa.Text, nullable=False)
    row_version: Mapped[int] = mapped_column(sa.Integer, nullable=False, default=1)
