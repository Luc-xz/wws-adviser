// 研究任务与报告查询（Phase 3 波7）
import type { Ref } from "vue";
import { useQuery, useQueryClient } from "@tanstack/vue-query";
import client from "@/api/client";
import { useOfflineFallback } from "@/shared/offline/useOfflineFallback";

export type ResearchTaskType = "company" | "industry";
export type ResearchDepth = "quick" | "standard" | "deep";

export interface ResearchTask {
  id: string;
  task_type: string;
  subject: string;
  depth: string;
  status: string;
  progress: number;
  error_code: string | null;
  report_id: string | null;
  created_at: string;
}

export function useResearchTasks() {
  const q = useQuery({
    queryKey: ["research-tasks"],
    queryFn: async () => {
      const { data, error } = await client.GET("/api/v1/research/tasks");
      if (error || !data) throw new Error("研究任务获取失败");
      return data;
    },
    refetchInterval: (query) => {
      // 有进行中任务时 5s 轮询兜底（SSE 失败也能前进）
      const active = (query.state.data?.items ?? []).some(
        (t) => t.status === "PENDING" || t.status === "RUNNING",
      );
      return active ? 5_000 : false;
    },
  });
  return { data: q.data, isLoading: q.isLoading };
}

async function fetchResearchReport(id: string) {
  const { data, error } = await client.GET("/api/v1/research/reports/{report_id}", {
    params: { path: { report_id: id } },
  });
  if (error || !data) throw new Error("报告获取失败");
  return data;
}

export function useResearchReport(reportId: () => string | null) {
  // Network First + 私有缓存离线回退（Phase 3.4）：研究报告生成后不可变，version=created_at
  type ReportData = Awaited<ReturnType<typeof fetchResearchReport>>;
  const offline = useOfflineFallback<ReportData>("research", () => reportId() ?? "");
  const q = useQuery({
    queryKey: ["research-report", reportId()],
    queryFn: async () => {
      const id = reportId();
      if (!id) throw new Error("无报告");
      offline.offlineCachedAt.value = null;
      try {
        const data = await fetchResearchReport(id);
        offline.writeThrough(
          data,
          String(Date.parse(data.created_at ?? "") || 1),
        );
        return data;
      } catch (err) {
        const cached = await offline.readBack();
        if (cached !== null) return cached;
        throw err;
      }
    },
    enabled: () => !!reportId(),
  });
  return {
    data: q.data,
    isLoading: q.isLoading,
    offlineCachedAt: offline.offlineCachedAt,
  };
}

export function useCreateResearchTask() {
  const qc = useQueryClient();
  async function create(input: {
    task_type: ResearchTaskType;
    subject: string;
    depth: ResearchDepth;
    peer_codes?: string[];
  }) {
    const { data, error } = await client.POST("/api/v1/research/tasks", {
      params: { header: { "Idempotency-Key": crypto.randomUUID() } },
      body: input,
    });
    if (error || !data) throw new Error("任务创建失败");
    await qc.invalidateQueries({ queryKey: ["research-tasks"] });
    return data;
  }
  return { create };
}

export function useCancelResearchTask() {
  const qc = useQueryClient();
  async function cancel(taskId: string) {
    const { data, error } = await client.POST(
      "/api/v1/research/tasks/{task_id}/cancel",
      {
        params: {
          path: { task_id: taskId },
          header: { "Idempotency-Key": crypto.randomUUID() },
        },
      },
    );
    if (error || !data) throw new Error("取消失败");
    await qc.invalidateQueries({ queryKey: ["research-tasks"] });
    return data;
  }
  return { cancel };
}

/** 导出下载地址（浏览器带 cookie 直接下载） */
export function researchExportUrl(reportId: string, format: "md" | "html"): string {
  return `/api/v1/research/reports/${reportId}/export?format=${format}`;
}

/** W2-2：公司研究语料前置检查——按代码查公告语料数（满 50 按 50+ 展示）。 */
export function useCorpusCount(
  code: Ref<string>,
  enabled: Ref<boolean>,
) {
  return useQuery({
    queryKey: ["research-corpus", code],
    enabled,
    queryFn: async () => {
      const { data: insts } = await client.GET("/api/v1/instruments", {
        params: { query: { q: code.value } },
      });
      const hit = (insts?.items ?? []).find((i) => i.code === code.value);
      if (!hit) return { count: 0, full: false };
      const { data: docs } = await client.GET("/api/v1/documents", {
        params: { query: { instrument_id: hit.id, limit: 50 } },
      });
      const n = docs?.items?.length ?? 0;
      return { count: n >= 50 ? 50 : n, full: n >= 50 };
    },
  });
}
