// 报告详情 + 生成（doc7 §2）；详情走 Network First + 私有缓存离线回退（Phase 3.4）
import { useQuery, useQueryClient } from "@tanstack/vue-query";
import client from "@/api/client";
import { useOfflineFallback } from "@/shared/offline/useOfflineFallback";

async function fetchReport(reportId: string) {
  const { data, error } = await client.GET("/api/v1/reports/{report_id}", {
    params: { path: { report_id: reportId } },
  });
  if (error || !data) throw new Error("报告获取失败");
  return data;
}

export function useReport(reportId: () => string) {
  type ReportData = Awaited<ReturnType<typeof fetchReport>>;
  const offline = useOfflineFallback<ReportData>("daily", reportId);
  const q = useQuery({
    queryKey: ["report", reportId()],
    queryFn: async () => {
      offline.offlineCachedAt.value = null;
      try {
        const data = await fetchReport(reportId());
        offline.writeThrough(data, String(data.version ?? "1"));
        return data;
      } catch (err) {
        const cached = await offline.readBack();
        if (cached !== null) return cached;
        throw err;
      }
    },
  });
  return {
    data: q.data,
    isSuccess: q.isSuccess,
    isLoading: q.isLoading,
    offlineCachedAt: offline.offlineCachedAt,
  };
}

export function useGenerateReport() {
  const qc = useQueryClient();
  async function generate(reportType: "pre_market" | "post_market", businessDate?: string) {
    const { data, error } = await client.POST("/api/v1/reports/generate", {
      params: { header: { "Idempotency-Key": crypto.randomUUID() } },
      body: { report_type: reportType, ...(businessDate ? { business_date: businessDate } : {}) },
    });
    if (error || !data) throw new Error("报告生成请求失败");
    await qc.invalidateQueries({ queryKey: ["reports"] });
    return data;
  }
  return { generate };
}
