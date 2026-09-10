// 历史建议记录（HOME-02 列表 / CHAT-02 详情）：GET /advice 系列（3_API §3.9）
import { useQuery } from "@tanstack/vue-query";
import client from "@/api/client";

export interface AdviceRecord {
  advice_id: string;
  signal_id: string;
  code: string;
  action: "buy" | "reduce" | "hold" | "suspend" | string;
  state: "published" | "degraded" | "blocked" | string;
  valid_from: string;
  expires_at: string;
  actionable: boolean;
  invalidated: boolean;
  f_min: string | null;
  f_max: string | null;
  value_min: string | null;
  value_max: string | null;
  suggested_lots: number | null;
  reasons: string[];
  evidence_ids: string[];
  trail: Array<{
    kind: string;
    note: string;
    before: string | null;
    after: string | null;
  }>;
  model_explanation: string | null;
  verdict: string | null;
  evaluated_at: string | null;
  evaluation: {
    spec_version?: string | null;
    reasons?: string[];
    direction_return?: string | null;
    horizon?: number | null;
  } | null;
  created_at: string;
}

export interface AdviceRecordPage {
  items: AdviceRecord[];
  next_cursor: string | null;
  has_more: boolean;
}

export async function fetchAdviceRecords(params: {
  code?: string;
  action?: string;
  state?: string;
  cursor?: string;
  limit?: number;
}): Promise<AdviceRecordPage> {
  const { data, error } = await client.GET("/api/v1/advice", {
    params: { query: params },
  });
  if (error || !data) throw new Error("建议记录获取失败");
  return data as AdviceRecordPage;
}

export async function fetchAdviceRecord(id: string): Promise<AdviceRecord> {
  const { data, error } = await client.GET("/api/v1/advice/{record_id}", {
    params: { path: { record_id: id } },
  });
  if (error || !data) throw new Error("建议详情获取失败");
  return data as AdviceRecord;
}

export function useAdviceRecord(id: string) {
  const q = useQuery({
    queryKey: ["advice", "record", id],
    queryFn: () => fetchAdviceRecord(id),
  });
  return { data: q.data, isLoading: q.isLoading, error: q.error };
}
