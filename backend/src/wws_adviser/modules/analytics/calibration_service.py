"""校准服务：信号扫描 → 回测 → OOS 门禁 → 校准记录落库/查询（Phase 2 波6）。

流程（每日调度，CALIBRATION_SCAN job）：
    bars 加载（qfq 优先，none 兜底）→ 信号生成 → 回测 → n_eff 聚类衰减 →
    时间序切分 IS/OOS → IS 得预测 p → OOS reliability（含 Platt）→ 落库。

p 只在本服务写入（FR-ANL-003）；有效期按交易日历（trading_calendar）推进，
日历不足时退化为 +88 自然日近似并在 notes 注明。
"""

import json
import logging
from collections.abc import Mapping, Sequence
from datetime import date as Date
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from wws_adviser.core.config import Settings
from wws_adviser.core.ids import new_id
from wws_adviser.core.time import business_date, now_utc_iso
from wws_adviser.modules.analytics import signals as sig
from wws_adviser.modules.analytics.calibration import (
    CalibrationEvent,
    CalibrationItem,
    CalibrationRecord,
    CalibrationState,
    evaluate_oos,
    state_on_date,
    transition,
)
from wws_adviser.modules.analytics.models import SignalCalibration, SignalRecord
from wws_adviser.modules.instruments import models as instruments_models
from wws_adviser.modules.market_data import models as market_models
from wws_adviser.modules.market_data.domain import NormalizedBar

_logger = logging.getLogger(__name__)

# 默认 L1 信号（20 日新高 + 量能，持有 5 交易日，单边 10bps）
DEFAULT_SIGNAL = dict(
    signal_id="breakout-20", name="20日新高+量能放大", signal_class="L1",
    version="v1", lookback_days=20, horizon_days=5, cost_bps=10, universe="A_SHARE",
)

# OOS 占比（时间序切分，剩余为 IS）
OOS_FRACTION = Decimal("0.3")
CALENDAR_FALLBACK_DAYS = 88  # ~60 交易日 × 1.47 自然日近似


def seed_default_signal(db: DBSession) -> SignalRecord:
    """确保默认 L1 信号定义存在（幂等）。"""
    existing = db.scalar(
        select(SignalRecord).where(
            SignalRecord.signal_id == DEFAULT_SIGNAL["signal_id"],
            SignalRecord.version == DEFAULT_SIGNAL["version"],
        )
    )
    if existing is not None:
        return existing
    now = now_utc_iso()
    rec = SignalRecord(
        id=new_id(), created_at=now, updated_at=now, row_version=1, **DEFAULT_SIGNAL
    )
    db.add(rec)
    db.commit()
    return rec


def _to_signal_def(row: SignalRecord) -> sig.SignalDefinition:
    return sig.SignalDefinition(
        signal_id=row.signal_id, name=row.name,
        signal_class=sig.SignalClass(row.signal_class), version=row.version,
        lookback_days=row.lookback_days, horizon_days=row.horizon_days,
        cost_bps=Decimal(row.cost_bps), universe=row.universe,
    )


def load_bars_by_code(
    db: DBSession, *, adjustment: str = "qfq"
) -> dict[str, list[NormalizedBar]]:
    """全量加载日线（code → 升序 bars）。qfq 无数据时自动退回 none。"""
    def _load(adj: str) -> dict[str, list[NormalizedBar]]:
        rows = db.execute(
            select(market_models.MarketRecord, instruments_models.Instrument.code)
            .join(
                instruments_models.Instrument,
                market_models.MarketRecord.instrument_id == instruments_models.Instrument.id,
            )
            .where(market_models.MarketRecord.adjustment_type == adj)
            .order_by(market_models.MarketRecord.business_date)
        ).all()
        by_code: dict[str, list[NormalizedBar]] = {}
        for rec, code in rows:
            if rec.close is None or rec.open is None:
                continue
            by_code.setdefault(code, []).append(
                NormalizedBar(
                    business_date=Date.fromisoformat(rec.business_date),
                    open=Decimal(rec.open),
                    high=Decimal(rec.high or rec.close),
                    low=Decimal(rec.low or rec.close),
                    close=Decimal(rec.close),
                    volume=Decimal(rec.volume or 0),
                )
            )
        return by_code

    bars = _load(adjustment)
    return bars if bars else _load("none")


def _expiry_date(db: DBSession, calibrated_on: str, ttl_days: int) -> tuple[str, str]:
    """校准有效期：交易日历取第 ttl 个交易日；日历不足退化为自然日近似。"""
    rows = db.scalars(
        select(market_models.TradingCalendar.date)
        .where(
            market_models.TradingCalendar.market == "CN",
            market_models.TradingCalendar.is_trading_day.is_(True),
            market_models.TradingCalendar.date > calibrated_on,
        )
        .order_by(market_models.TradingCalendar.date)
        .limit(ttl_days)
    ).all()
    if len(rows) >= ttl_days:
        return rows[-1], "calendar"
    fb = Date.fromisoformat(calibrated_on) + timedelta(days=CALENDAR_FALLBACK_DAYS)
    fallback = fb.isoformat()
    return fallback, "calendar_fallback_approx"


def run_calibration_scan(
    db: DBSession,
    settings: Settings,
    *,
    bars_by_code: Mapping[str, Sequence[NormalizedBar]] | None = None,
) -> dict[str, object]:
    """对全部信号定义执行校准扫描并落库。bars 可注入（测试）或从 DB 加载。"""
    seed_default_signal(db)
    bars = dict(bars_by_code) if bars_by_code is not None else load_bars_by_code(db)
    today = business_date().isoformat()
    results: dict[str, object] = {"instruments": len(bars), "signals": {}}

    for row in db.scalars(select(SignalRecord)).all():
        definition = _to_signal_def(row)
        instances = sig.breakout_signals(definition, bars)
        outcomes = sig.backtest(definition, instances, bars)
        n_eff_all, _ = sig.cluster_decay(instances, definition.horizon_days)

        # 时间序切分：出场日排序后取后 30% 为 OOS
        ordered = sorted(outcomes, key=lambda o: o.exit_date)
        n_oos = int(Decimal(len(ordered)) * OOS_FRACTION) if ordered else 0
        if ordered and n_oos == 0:
            n_oos = 1
        is_outcomes, oos_outcomes = ordered[: len(ordered) - n_oos], ordered[len(ordered) - n_oos :]

        signal_result: dict[str, object] = {
            "instances": len(instances), "outcomes": len(outcomes), "n_eff": n_eff_all,
        }
        window = {
            "is_count": len(is_outcomes), "oos_count": len(oos_outcomes),
            "first_exit": ordered[0].exit_date.isoformat() if ordered else None,
            "last_exit": ordered[-1].exit_date.isoformat() if ordered else None,
        }
        if not oos_outcomes or not is_outcomes:
            _persist(db, row, state=CalibrationState.UNCALIBRATED, stats=None,
                     n_eff=n_eff_all, n_eff_oos=0, reliability=False,
                     notes={"reasons": ["样本不足以完成 IS/OOS 切分"], "window": window},
                     calibrated_on=today, settings=settings)
            signal_result["state"] = CalibrationState.UNCALIBRATED.value
            results["signals"][row.signal_id] = signal_result  # type: ignore[index]
            continue

        is_stats = sig.summarize(is_outcomes, definition.signal_id)
        oos_stats = sig.summarize(oos_outcomes, definition.signal_id)
        oos_instances = [i for i in instances if i.code in {o.instance.code for o in oos_outcomes}]
        n_eff_oos, _ = sig.cluster_decay(oos_instances, definition.horizon_days)
        # 预测取 IS 口径 p_mid；OOS 事实用于 reliability
        items = [CalibrationItem(is_stats.p_mid, o.win) for o in oos_outcomes]
        verdict = evaluate_oos(oos_stats, items, n_eff_oos=n_eff_oos)
        state = (
            transition(CalibrationState.CALIBRATING, CalibrationEvent.PASS_OOS)
            if verdict.passed
            else transition(CalibrationState.CALIBRATING, CalibrationEvent.FAIL_OOS)
        )
        _persist(
            db, row, state=state, stats=oos_stats,
            n_eff=n_eff_all, n_eff_oos=n_eff_oos,
            reliability=verdict.reliability.passed,
            notes={"reasons": list(verdict.reasons), "platt_applied": verdict.platt_applied,
                   "window": window},
            calibrated_on=today, settings=settings,
        )
        signal_result.update({
            "state": state.value, "n_eff_oos": n_eff_oos,
            "p_mid": str(oos_stats.p_mid), "b": str(oos_stats.b),
        })
        results["signals"][row.signal_id] = signal_result  # type: ignore[index]

    db.commit()
    _logger.info("校准扫描完成：%s", results)
    return results


def _persist(
    db: DBSession,
    signal_row: SignalRecord,
    *,
    state: CalibrationState,
    stats: sig.BacktestStats | None,
    n_eff: int,
    n_eff_oos: int,
    reliability: bool,
    notes: dict[str, object],
    calibrated_on: str,
    settings: Settings,
) -> None:
    expires_on, expiry_basis = _expiry_date(
        db, calibrated_on, ttl_days=settings.calibration_ttl_trading_days
    )
    notes = {**notes, "expiry_basis": expiry_basis}
    existing = db.scalar(
        select(SignalCalibration).where(
            SignalCalibration.signal_def_id == signal_row.id,
            SignalCalibration.signal_version == signal_row.version,
        )
    )
    now = now_utc_iso()
    if existing is None:
        db.add(SignalCalibration(
            id=new_id(), signal_def_id=signal_row.id, signal_id=signal_row.signal_id,
            signal_version=signal_row.version, state=state.value,
            calibrated_on=calibrated_on, expires_on=expires_on,
            p_low=str(stats.p_low if stats else 0), p_mid=str(stats.p_mid if stats else 0),
            p_high=str(stats.p_high if stats else 0), b=str(stats.b if stats else 0),
            n_eff=n_eff, n_eff_oos=n_eff_oos, reliability_passed=reliability,
            platt_a=None, platt_b=None,
            notes_json=json.dumps(notes, ensure_ascii=False),
            created_at=now, updated_at=now, row_version=1,
        ))
    else:
        existing.state = state.value
        existing.calibrated_on = calibrated_on
        existing.expires_on = expires_on
        if stats is not None:
            existing.p_low = str(stats.p_low)
            existing.p_mid = str(stats.p_mid)
            existing.p_high = str(stats.p_high)
            existing.b = str(stats.b)
        existing.n_eff, existing.n_eff_oos = n_eff, n_eff_oos
        existing.reliability_passed = reliability
        existing.notes_json = json.dumps(notes, ensure_ascii=False)
        existing.updated_at = now
        existing.row_version += 1


def latest_valid_calibration(
    db: DBSession, signal_id: str, *, as_of: str | None = None
) -> CalibrationRecord | None:
    """最新校准记录（读时判定过期）。无记录 → None。"""
    record, _row_id = latest_valid_calibration_with_row(db, signal_id, as_of=as_of)
    return record


def latest_valid_calibration_with_row(
    db: DBSession, signal_id: str, *, as_of: str | None = None
) -> tuple[CalibrationRecord | None, str | None]:
    """同 latest_valid_calibration，附带 ORM 行 id（供 Advice 证据引用）。"""
    row = db.scalar(
        select(SignalCalibration)
        .where(SignalCalibration.signal_id == signal_id)
        .order_by(SignalCalibration.updated_at.desc())
        .limit(1)
    )
    if row is None:
        return None, None
    raw = CalibrationRecord(
        signal_id=row.signal_id, signal_version=row.signal_version,
        state=CalibrationState(row.state),
        calibrated_on=row.calibrated_on, expires_on=row.expires_on,
        p_low=Decimal(row.p_low), p_mid=Decimal(row.p_mid), p_high=Decimal(row.p_high),
        b=Decimal(row.b), n_eff=row.n_eff, n_eff_oos=row.n_eff_oos,
        reliability_passed=row.reliability_passed,
    )
    # 读时过期：CALIBRATED_OOS 过期视同 STALE（凯利关卡 1 消费）
    record = CalibrationRecord(
        signal_id=raw.signal_id, signal_version=raw.signal_version,
        state=state_on_date(raw, as_of or business_date().isoformat()),
        calibrated_on=raw.calibrated_on, expires_on=raw.expires_on,
        p_low=raw.p_low, p_mid=raw.p_mid, p_high=raw.p_high,
        b=raw.b, n_eff=raw.n_eff, n_eff_oos=raw.n_eff_oos,
        reliability_passed=raw.reliability_passed,
    )
    return record, row.id
