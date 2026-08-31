// 持仓页服务端状态（doc7 §2：TanStack Vue Query 唯一入口）
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import type { Ref } from "vue";
import client from "@/api/client";

// —— 流水（交易列表，keyset 分页；首页取最新一页）——

export function useTransactions() {
  const q = useQuery({
    queryKey: ["transactions"],
    queryFn: async () => {
      const { data, error } = await client.GET("/api/v1/transactions", {
        params: { query: { limit: 50 } },
      });
      if (error || !data) throw new Error("流水获取失败");
      return data;
    },
  });
  return { data: q.data, isSuccess: q.isSuccess, isLoading: q.isLoading };
}

// —— 持仓快照历史（趋势图：realized_pnl 按日聚合，确定性数据）——

export function usePositionsHistory() {
  const q = useQuery({
    queryKey: ["positions", "history"],
    queryFn: async () => {
      const { data, error } = await client.GET("/api/v1/positions/history", {
        params: { query: { limit: 200 } },
      });
      if (error || !data) throw new Error("持仓历史获取失败");
      return data;
    },
  });
  return { data: q.data, isSuccess: q.isSuccess };
}

// —— 自选（watchlist：GET 读 + PUT 整体替换）——

export function useWatchlist() {
  const q = useQuery({
    queryKey: ["watchlist"],
    queryFn: async () => {
      const { data, error } = await client.GET("/api/v1/settings/watchlist");
      if (error || !data) throw new Error("自选获取失败");
      return data.codes;
    },
  });
  return { data: q.data, isSuccess: q.isSuccess, isLoading: q.isLoading };
}

export function useSaveWatchlist() {
  const qc = useQueryClient();
  const m = useMutation({
    mutationFn: async (codes: string[]) => {
      const { data, error } = await client.PUT("/api/v1/settings/watchlist", {
        body: { codes },
      });
      if (error || !data) throw new Error("自选保存失败");
      return data.codes;
    },
    onSuccess: (codes) => qc.setQueryData(["watchlist"], codes),
  });
  return m;
}

// —— 标的名表（流水/自选行 code→name 解析）——

export interface InstrumentLite {
  id: string;
  code: string;
  name: string;
}

export function useInstrumentMap() {
  const q = useQuery({
    queryKey: ["instruments", "map"],
    queryFn: async () => {
      const { data, error } = await client.GET("/api/v1/instruments");
      if (error || !data) throw new Error("标的获取失败");
      const map = new Map<string, InstrumentLite>();
      for (const it of data.items ?? []) {
        map.set(it.id, { id: it.id, code: it.code, name: it.name });
        map.set(it.code, { id: it.id, code: it.code, name: it.name });
      }
      return map;
    },
    staleTime: 5 * 60 * 1000,
  });
  return { data: q.data, isSuccess: q.isSuccess };
}

// —— 自选行情（逐 code 并发拉快照；stub 源也返回确定性价）——

export interface WatchQuote {
  code: string;
  price: string | null;
  changePct: string | null;
}

export function useWatchQuotes(codes: Ref<string[]>) {
  const q = useQuery({
    queryKey: ["watch-quotes", codes],
    queryFn: async (): Promise<WatchQuote[]> => {
      const results = await Promise.all(
        codes.value.map(async (code): Promise<WatchQuote> => {
          try {
            const { data, error } = await client.GET("/api/v1/market-data/quotes/{code}", {
              params: { path: { code } },
            });
            if (error || !data) return { code, price: null, changePct: null };
            return { code, price: data.price, changePct: data.change_pct };
          } catch {
            return { code, price: null, changePct: null }; // 单只失败不拖垮整列
          }
        })
      );
      return results;
    },
    enabled: () => codes.value.length > 0,
    staleTime: 30 * 1000,
  });
  return { data: q.data, isLoading: q.isLoading };
}
