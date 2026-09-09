// 交易流水 / 记录 / 导入 + 账户对账查询（波 V4：TX-01/02/03 · ACC-01）
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";

import client from "@/api/client";

export const TX_KINDS = [
  "BUY",
  "SELL",
  "DIVIDEND",
  "SPLIT",
  "SUBSCRIBE",
  "REDEEM",
  "ADJUST",
  "FEE",
] as const;
export type TxKind = (typeof TX_KINDS)[number];

export const KIND_NAMES: Record<TxKind, string> = {
  BUY: "买入",
  SELL: "卖出",
  DIVIDEND: "分红",
  SPLIT: "拆分",
  SUBSCRIBE: "申购",
  REDEEM: "赎回",
  ADJUST: "调整",
  FEE: "费用",
};

/** 需要 direction 的类型（买卖）；申赎/分红等按 kind 语义定方向，后端不收 */
export const KIND_NEEDS_DIRECTION: TxKind[] = ["BUY", "SELL"];

export interface TxRow {
  id: string;
  account_id: string;
  instrument_id: string;
  kind: TxKind;
  direction: string;
  quantity: string;
  price: string;
  fee: string;
  tax: string;
  trade_at: string;
  note: string | null;
}

export function useTransactions(filters: {
  instrumentId?: () => string | undefined;
  kind?: () => string | undefined;
  limit?: () => number;
}) {
  return useQuery({
    queryKey: ["transactions", filters.instrumentId?.() ?? "", filters.kind?.() ?? ""],
    queryFn: async () => {
      const { data, error } = await client.GET("/api/v1/transactions", {
        params: {
          query: {
            instrument_id: filters.instrumentId?.() || undefined,
            kind: (filters.kind?.() as TxKind) || undefined,
            limit: filters.limit?.() ?? 50,
          },
        },
      });
      if (error || !data) throw new Error("交易流水获取失败");
      return data;
    },
  });
}

export interface CreateTxBody {
  instrument_id: string;
  kind: TxKind;
  direction?: "IN" | "OUT" | null;
  quantity: string;
  price: string;
  fee: string;
  tax: string;
  trade_at: string;
  external_ref?: string | null;
  note?: string | null;
}

export function useCreateTransaction() {
  const qc = useQueryClient();
  return useMutation({
    // body 类型对齐 generated（可空字段显式 null 兼容）
    mutationFn: async (body: CreateTxBody) => {
      const { data, error } = await client.POST("/api/v1/transactions", {
        params: { header: { "Idempotency-Key": crypto.randomUUID() } },
        body,
      });
      if (error || !data) throw new Error("交易记录失败");
      return data;
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["transactions"] });
      void qc.invalidateQueries({ queryKey: ["positions"] });
      void qc.invalidateQueries({ queryKey: ["analytics"] });
    },
  });
}

export interface ImportPreviewRow {
  row: number;
  status?: string;
  [k: string]: unknown;
}

export function useImportPreview() {
  return useMutation({
    mutationFn: async (file: File) => {
      const { data, error } = await client.POST("/api/v1/transactions/import", {
        // openapi-fetch：FormData 直接作 body（multipart 由运行时设边界）
        body: { file } as unknown as { file: string },
      });
      if (error || !data) throw new Error("导入预览失败");
      return data;
    },
  });
}

export function useImportConfirm() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: { batch_id: string; fingerprints: string[] }) => {
      const { data, error } = await client.POST("/api/v1/transactions/import/confirm", {
        params: { header: { "Idempotency-Key": crypto.randomUUID() } },
        body: input,
      });
      if (error || !data) throw new Error("导入确认失败");
      return data;
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["transactions"] });
      void qc.invalidateQueries({ queryKey: ["positions"] });
      void qc.invalidateQueries({ queryKey: ["analytics"] });
    },
  });
}

export interface AccountRow {
  id: string;
  name: string;
  currency: string;
  reconciled?: boolean;
  [k: string]: unknown;
}

export function useAccounts() {
  return useQuery({
    queryKey: ["accounts"],
    queryFn: async () => {
      const { data, error } = await client.GET("/api/v1/accounts");
      if (error || !data) throw new Error("账户获取失败");
      return data as AccountRow[];
    },
  });
}

export function useReconcile() {
  const qc = useQueryClient();
  return useMutation({
    // 后端无 requestBody（POST 即确认，写审计）
    mutationFn: async (accountId: string) => {
      const { data, error } = await client.POST("/api/v1/accounts/{account_id}/reconcile", {
        params: { path: { account_id: accountId } },
      });
      if (error || !data) throw new Error("对账确认失败");
      return data;
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["accounts"] });
    },
  });
}
