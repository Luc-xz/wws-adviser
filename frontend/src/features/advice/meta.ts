// 建议展示元数据（CHAT-01 实时 / HOME-02 列表 / CHAT-02 详情 共用）：
// 动作徽标、降级原因码 → 中文说明、调整轨迹步骤名。
export const ACTION_META: Record<string, { label: string; cls: string }> = {
  buy: { label: "提升风险预算（区间）", cls: "bg-market-up/10 text-market-up" },
  reduce: { label: "降低风险预算", cls: "bg-market-down/10 text-market-down" },
  hold: { label: "维持 / 观察", cls: "bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300" },
  suspend: { label: "暂停建议", cls: "bg-risk-warning/10 text-risk-warning" },
};

export const REASON_NAMES: Record<string, string> = {
  data_stale: "行情过期或不可用",
  data_conflict: "多源数据冲突未消解",
  market_abnormal: "标的停牌或异常",
  ledger_unreconciled: "账本未对账",
  no_calibrated_signal: "该标的当日无已校准信号触发——按风控设计不给凯利建议（正向建议仅信号触发日给出，非故障）",
  calibration_uncalibrated: "信号未完成样本外校准",
  calibration_stale: "校准已过期/失效",
  calibration_expired: "校准已过有效期",
  calibration_failed: "概率校准未通过（reliability）",
  insufficient_samples: "样本外有效样本不足（<30）",
  non_positive_payoff: "平均盈利不高于平均亏损",
  extreme_payoff: "盈亏比极端（区间下限）",
  low_confidence: "样本量偏少（半折扣）",
  wide_p_interval: "概率区间过宽（取保守端）",
  negative_edge: "无正边际（目标 0）",
  rounding_imprecise: "无法安全取整至手数（只显示区间）",
};

export const TRAIL_NAMES: Record<string, string> = {
  fractional_discount: "分数凯利折扣",
  low_confidence_halving: "样本不足半折扣",
  wide_p_interval: "概率区间过宽",
  confidence_discount: "置信折扣",
  liquidity_discount: "流动性折扣",
  clip_cash_floor: "现金下限约束",
  clip_single_cap: "单标的上限约束",
  clip_industry_cap: "行业上限约束",
  clip_portfolio: "组合波动/回撤约束",
};

export const VERDICT_NAMES: Record<string, string> = {
  reasonable_untriggered: "条件未出现（避免错误触发，合理）",
  direction_correct: "方向正确",
  direction_wrong: "方向错误",
  avoided_loss: "减仓避免损失",
  reduced_too_early: "减仓过早",
  actionable_later: "进入可操作状态",
  still_observing: "仍在观察",
  suspend_unwarranted: "暂停不当（本该给建议）",
  suspend_warranted: "暂停合理",
  inconclusive: "事实缺失，无法判定",
};

export function reasonText(r: string): string {
  if (r.startsWith("gate:")) return `发布检查未过：${r.slice(5)}`;
  return REASON_NAMES[r] ?? r;
}
