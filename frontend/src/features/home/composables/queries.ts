// 首页服务端状态（doc7 §2：TanStack Vue Query 唯一入口）
// 返回值统一解构（data 为顶层 ref，模板自动解包）
import { useQuery } from "@tanstack/vue-query";
import client from "@/api/client";

export function useSummary() {
  const q = useQuery({
    queryKey: ["analytics", "summary"],
    queryFn: async () => {
      const { data, error } = await client.GET("/api/v1/analytics/summary");
      if (error || !data) throw new Error("摘要获取失败");
      return data;
    },
  });
  return { data: q.data, isSuccess: q.isSuccess, isLoading: q.isLoading, refetch: q.refetch };
}

export function useRisk() {
  const q = useQuery({
    queryKey: ["analytics", "risk"],
    queryFn: async () => {
      const { data, error } = await client.GET("/api/v1/analytics/risk");
      if (error || !data) throw new Error("风险获取失败");
      return data;
    },
  });
  return { data: q.data, isSuccess: q.isSuccess, isLoading: q.isLoading };
}

export function useMarketQuality() {
  const q = useQuery({
    queryKey: ["market", "quality"],
    queryFn: async () => {
      const { data, error } = await client.GET("/api/v1/market/quality");
      if (error || !data) throw new Error("数据质量获取失败");
      return data;
    },
  });
  return { data: q.data, isSuccess: q.isSuccess, isLoading: q.isLoading };
}

export function usePositions() {
  const q = useQuery({
    queryKey: ["positions"],
    queryFn: async () => {
      const { data, error } = await client.GET("/api/v1/positions");
      if (error || !data) throw new Error("持仓获取失败");
      return data;
    },
  });
  return { data: q.data, isSuccess: q.isSuccess, isLoading: q.isLoading };
}

export function useReports() {
  const q = useQuery({
    queryKey: ["reports"],
    queryFn: async () => {
      const { data, error } = await client.GET("/api/v1/reports");
      if (error || !data) throw new Error("报告获取失败");
      return data;
    },
  });
  return { data: q.data, isSuccess: q.isSuccess, isLoading: q.isLoading };
}
