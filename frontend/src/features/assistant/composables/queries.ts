// 盘中快速建议（TECH §11.3 / CHAT-01 Phase 2）：POST /assistant/intraday
import client from "@/api/client";

export interface IntradayAdvice {
  advice_id: string;
  signal_id: string;
  code: string;
  action: "buy" | "reduce" | "hold" | "suspend";
  state: "published" | "degraded" | string;
  valid_from: string;
  expires_at: string;
  actionable: boolean;
  trigger_conditions: string[];
  invalidated: boolean;
  invalidation_reasons: string[];
  f_min: string | null;
  f_max: string | null;
  value_min: string | null;
  value_max: string | null;
  suggested_lots: number | null;
  reasons: string[];
  evidence_ids: string[];
  model_explanation: string | null;
  trail: Array<{
    kind: string;
    note: string;
    before: string | null;
    after: string | null;
  }>;
}

export async function fetchIntradayAdvice(code: string): Promise<IntradayAdvice> {
  const { data, error } = await client.POST("/api/v1/assistant/intraday", {
    params: { header: { "Idempotency-Key": crypto.randomUUID() } },
    body: { code },
  });
  if (error || !data) throw new Error("盘中建议获取失败");
  return data.advice as unknown as IntradayAdvice;
}
