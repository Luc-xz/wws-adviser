// 报告详情 + 生成（doc7 §2）
import { useQuery, useQueryClient } from "@tanstack/vue-query";
import client from "@/api/client";

export function useReport(reportId: () => string) {
  const q = useQuery({
    queryKey: ["report", reportId()],
    queryFn: async () => {
      const { data, error } = await client.GET("/api/v1/reports/{report_id}", {
        params: { path: { report_id: reportId() } },
      });
      if (error || !data) throw new Error("报告获取失败");
      return data;
    },
  });
  return { data: q.data, isSuccess: q.isSuccess, isLoading: q.isLoading };
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
