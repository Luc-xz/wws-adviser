import { Decimal } from "decimal.js";

/** 真正的数学负号 U+2212，替代 ASCII '-'（ENFORCEMENT_CONTRACT §2.1）。 */
const MINUS = "\u2212";
/** em-dash 空值（ENFORCEMENT_CONTRACT §2.1 / UI §8.2）。 */
export const EMPTY = "\u2014";

/**
 * 格式化金额。空值返回 em-dash；负数用 U+2212；千分位。
 * @param scale 小数位（金额=2, A股价格=2, 港股=3, 基金净值=6, 数量=6）
 */
export function formatMoney(
  v: string | null | undefined,
  scale = 2,
): string {
  if (v === null || v === undefined || v === "") return EMPTY;
  const d = new Decimal(v);
  const neg = d.isNegative();
  const abs = d.abs().toFixed(scale);
  const grouped = abs.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return (neg ? MINUS : "") + grouped;
}

/** 涨跌幅，带符号（A 股红涨绿跌由 CSS class 决定，不在数值里）。 */
export function formatPercent(
  v: string | null | undefined,
  scale = 2,
): string {
  if (v === null || v === undefined || v === "") return EMPTY;
  const d = new Decimal(v);
  const sign = d.isZero() ? "" : d.isPositive() ? "+" : MINUS;
  return sign + d.abs().toFixed(scale) + "%";
}

/**
 * 格式化百分比数值（0~1 小数，如后端 success_rate=0.8751）。
 * 供统计卡等非行情百分比展示（行情涨跌用 formatPercent，语义不同）。
 */
export function formatRate(v: number | null | undefined, scale = 1): string {
  if (v === null || v === undefined) return EMPTY;
  return `${(v * 100).toFixed(scale)}%`;
}

/** 计数（千分位）；空/无效返回 em-dash。采集条数/任务数等非金额整数。 */
export function formatCount(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return EMPTY;
  return v.toLocaleString("zh-CN");
}

/** 耗时（毫秒）：<1s 以 ms 计，其余一位小数秒/分。采集耗时/任务耗时展示。 */
export function formatDuration(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return EMPTY;
  if (v < 1000) return `${v}ms`;
  if (v < 60_000) return `${(v / 1000).toFixed(1)}s`;
  return `${(v / 60_000).toFixed(1)}min`;
}
