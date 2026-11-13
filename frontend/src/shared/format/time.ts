// 时间展示格式化（DATA-01 采集运行分区 / 通用）。
// 口径：后端时间为 UTC ISO 8601；展示为本地时区；相对时间中文短句。

import { EMPTY } from "./number";

/** 相对时间：刚刚 / N分钟前 / N小时前 / 昨天 HH:mm / YYYY-MM-DD。空值返回 em-dash。 */
export function formatRelativeTime(iso: string | null | undefined, now = new Date()): string {
  if (!iso) return EMPTY;
  const t = new Date(iso);
  if (Number.isNaN(t.getTime())) return EMPTY;
  const diffMs = now.getTime() - t.getTime();
  if (diffMs < 0) return EMPTY; // 时钟偏差/未来时间不伪装成相对过去
  const min = Math.floor(diffMs / 60_000);
  if (min < 1) return "刚刚";
  if (min < 60) return `${min}分钟前`;
  const hour = Math.floor(min / 60);
  if (hour < 24) return `${hour}小时前`;
  const day = Math.floor(hour / 24);
  if (day === 1) return `昨天 ${pad(t.getHours())}:${pad(t.getMinutes())}`;
  if (day < 7) return `${day}天前`;
  return formatDate(iso);
}

/** 本地日期 YYYY-MM-DD（截断 ISO 前缀也可：已是本地语义的业务日期直接透传）。 */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return EMPTY;
  return iso.slice(0, 10);
}

/** 本地日期时间 MM-DD HH:mm（紧凑双行场景）。 */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return EMPTY;
  const t = new Date(iso);
  if (Number.isNaN(t.getTime())) return EMPTY;
  return `${pad(t.getMonth() + 1)}-${pad(t.getDate())} ${pad(t.getHours())}:${pad(t.getMinutes())}`;
}

function pad(n: number): string {
  return String(n).padStart(2, "0");
}
