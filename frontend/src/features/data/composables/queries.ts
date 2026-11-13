// 采集运行查询（DATA-01「采集运行」分区，5_DATA §12 · 3_API §3.13/§3.17）。
// TanStack Vue Query 唯一服务端状态入口（doc7 §2）；手动补采为 mutation + 失效联动。
import { useQuery, useQueryClient } from "@tanstack/vue-query";
import type { Ref } from "vue";
import client from "@/api/client";

// 与 generated JobRunOut 对齐（可缺省字段按 OpenAPI 可选性声明，避免结构不兼容）
export type JobRun = {
  id: string;
  job_type: string;
  business_date: string;
  scope_key: string;
  status: string;
  attempt: number;
  max_attempts: number;
  progress?: number | null;
  error_code?: string | null;
  result_ref?: string | null;
  result_summary: Record<string, unknown>;
  item_counts: Record<string, number>;
  started_at?: string | null;
  completed_at?: string | null;
  created_at?: string | null;
};

export type SourceHealth = {
  category: string;
  status: string;
  configured: boolean;
  last_success_at: string | null;
  last_failure_at: string | null;
  consecutive_failures: number;
  last_error_code: string | null;
  last_error_message: string | null;
  latest_data: Record<string, unknown> | null;
};

export type IngestItem = {
  id: string;
  run_id: string | null;
  category: string;
  action: string;
  status: string;
  target_ref: string;
  display_name: string;
  rows_written: number | null;
  source: string | null;
  duration_ms: number | null;
  error_code: string | null;
  error_message: string | null;
  data_ref: string | null;
  created_at: string;
};

/** 源健康 + 数据集覆盖（六类别；news 恒 no_data + configured=false——FR-DATA-005 仅 stub）。 */
export function useCollectionsHealth() {
  const q = useQuery({
    queryKey: ["collections", "health"],
    queryFn: async () => {
      const { data, error } = await client.GET("/api/v1/collections/health");
      if (error || !data) throw new Error("采集健康获取失败");
      return data;
    },
  });
  return { data: q.data, isLoading: q.isLoading };
}

/** 任务列表（默认 50 条，created_at 倒序）。 */
export function useJobRuns() {
  const q = useQuery({
    queryKey: ["jobs", "list"],
    queryFn: async () => {
      const { data, error } = await client.GET("/api/v1/jobs", {
        params: { query: { limit: 50 } },
      });
      if (error || !data) throw new Error("任务列表获取失败");
      return data;
    },
  });
  return { data: q.data, isLoading: q.isLoading };
}

/** 窗口聚合（成功率/耗时/连续失败；SET-08 汇总卡共用）。 */
export function useJobStats(windowDays = 7) {
  const q = useQuery({
    queryKey: ["jobs", "stats", windowDays],
    queryFn: async () => {
      const { data, error } = await client.GET("/api/v1/jobs/stats", {
        params: { query: { window_days: windowDays } },
      });
      if (error || !data) throw new Error("任务统计获取失败");
      return data;
    },
  });
  return { data: q.data, isLoading: q.isLoading };
}

/** 批次条目明细（展开行时才查：enabled 由调用方控制）。 */
export function useJobItems(jobId: Ref<string | null>, onlyFailed = false) {
  const q = useQuery({
    queryKey: ["jobs", jobId, "items", { failed: onlyFailed }],
    enabled: () => jobId.value !== null,
    queryFn: async () => {
      const id = jobId.value;
      if (id === null) throw new Error("无批次");
      const { data, error } = await client.GET("/api/v1/jobs/{job_id}/items", {
        params: {
          path: { job_id: id },
          query: onlyFailed ? { status: "FAILED", limit: 50 } : { limit: 50 },
        },
      });
      if (error || !data) throw new Error("批次明细获取失败");
      return data;
    },
  });
  return { data: q.data, isLoading: q.isLoading };
}

/**
 * 手动补采（POST /market/bars/{id}/refresh，5_DATA §12.2 job 化批次）。
 * 仅支持 FAILED 且 data_ref 可解析出区间与标的的日线条目；完成即失效任务/健康缓存。
 */
export function useRefreshBars() {
  const qc = useQueryClient();
  async function refresh(dataRef: string): Promise<void> {
    const parsed = parseMarketRef(dataRef);
    if (!parsed) throw new Error("该条目不支持一键补采（无区间引用）");
    const { error } = await client.POST("/api/v1/market/bars/{instrument_id}/refresh", {
      params: {
        path: { instrument_id: parsed.instrumentId },
        query: { start_date: parsed.start, end_date: parsed.end },
        header: { "Idempotency-Key": crypto.randomUUID() },
      },
    });
    if (error) throw new Error("补采失败");
    await Promise.all([
      qc.invalidateQueries({ queryKey: ["jobs"] }),
      qc.invalidateQueries({ queryKey: ["collections"] }),
    ]);
  }
  return { refresh };
}

/** data_ref "market:{instrument_id}:{YYYY-MM-DD}-{YYYY-MM-DD}" → 区间（定长日期可安全切分）。 */
export function parseMarketRef(
  dataRef: string,
): { instrumentId: string; start: string; end: string } | null {
  const m = /^market:([^:]+):(\d{4}-\d{2}-\d{2})-(\d{4}-\d{2}-\d{2})$/.exec(dataRef);
  return m ? { instrumentId: m[1], start: m[2], end: m[3] } : null;
}
