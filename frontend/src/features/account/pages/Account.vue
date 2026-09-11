<script setup lang="ts">
// ACC-01 账户与对账（波 V4 / reconcile be0c497）：账户列表 + 对账状态 +
// 确认对账（POST 幂等写审计）。对账未确认 = ledger_unreconciled 建议死锁来源。
import { computed, ref } from "vue";
import { useQuery } from "@tanstack/vue-query";
import client from "@/api/client";
import { PageHeader } from "@/shared/ui";
import { useAccounts, useReconcile, type AccountRow } from "@/features/transactions/composables/queries";
// 复用交易域 composable（同客户端同查询域）

const { data: accounts, isLoading, isSuccess } = useAccounts();
const reconcile = useReconcile();
const confirmingId = ref<string | null>(null);

async function confirm(a: AccountRow) {
  confirmingId.value = a.id;
  try {
    await reconcile.mutateAsync(a.id);
  } finally {
    confirmingId.value = null;
  }
}

function isReconciled(a: AccountRow): boolean {
  return Boolean((a as { reconciled?: boolean }).reconciled);
}

// W2.5-6：对账统计——最新成交日 + 自上次对账以来的新增交易笔数
const { data: txData } = useQuery({
  queryKey: ["transactions-all"],
  queryFn: async () => {
    const { data, error } = await client.GET("/api/v1/transactions");
    if (error || !data) throw new Error("流水获取失败");
    return data;
  },
});

const statsByAccount = computed(() => {
  const out: Record<string, { count: number; latest: string; newSince: number }> = {};
  for (const a of accounts.value ?? []) {
    const txs = (txData.value?.items ?? []).filter(
      (t) => t.account_id === a.id && !t.deleted_at,
    );
    const latest = txs.reduce((m, t) => (t.trade_at > m ? t.trade_at : m), "");
    const reconciledAt = (a as { reconciled_at?: string | null }).reconciled_at;
    const newSince = reconciledAt
      ? txs.filter((t) => t.trade_at > reconciledAt).length
      : txs.length;
    out[a.id] = { count: txs.length, latest: latest.slice(0, 10), newSince };
  }
  return out;
});
</script>

<template>
  <div class="space-y-6">
    <PageHeader
      title="账户与对账"
      subtitle="对账确认是盘中建议的前置条件（ledger_unreconciled 解除）"
      back
    />

    <div
      v-if="isLoading"
      class="h-20 animate-pulse rounded-lg bg-gray-100 dark:bg-gray-700"
    />

    <div
      v-else-if="isSuccess && !accounts?.length"
      class="rounded-lg bg-white p-6 text-center text-body text-gray-400 shadow-sm dark:bg-gray-800 dark:text-gray-500"
      data-testid="account-empty"
    >
      暂无账户——通过 CLI 或交易记录创建。
    </div>

    <div
      v-for="a in accounts ?? []"
      :key="a.id"
      class="rounded-lg bg-white p-4 shadow-sm dark:bg-gray-800"
      data-testid="account-row"
    >
      <div class="flex items-center justify-between">
        <div class="min-w-0">
          <div class="text-body font-medium">
            {{ a.name }}
          </div>
          <div
            class="mt-0.5 text-caption text-gray-400 dark:text-gray-500 num"
            data-num
          >
            币种 {{ a.currency }}
          </div>
        </div>
        <span
          class="shrink-0 rounded-sm px-1.5 py-0.5 text-caption"
          :class="isReconciled(a) ? 'bg-success/10 text-success' : 'bg-risk-warning/10 text-risk-warning'"
          :data-testid="`account-status-${a.id}`"
        >
          {{ isReconciled(a) ? "已对账" : "未对账" }}
        </span>
      </div>
      <dl
        class="mt-3 grid grid-cols-3 gap-2 text-caption"
        data-testid="account-stats"
      >
        <div>
          <dt class="text-gray-400">
            交易笔数
          </dt>
          <dd class="mt-0.5 font-medium num">
            {{ statsByAccount[a.id]?.count ?? 0 }}
          </dd>
        </div>
        <div>
          <dt class="text-gray-400">
            最新成交
          </dt>
          <dd class="mt-0.5 font-medium num">
            {{ statsByAccount[a.id]?.latest || "—" }}
          </dd>
        </div>
        <div>
          <dt class="text-gray-400">
            对账后新增
          </dt>
          <dd
            class="mt-0.5 font-medium num"
            :class="(statsByAccount[a.id]?.newSince ?? 0) > 0 ? 'text-risk-warning' : ''"
          >
            {{ statsByAccount[a.id]?.newSince ?? 0 }} 笔
          </dd>
        </div>
      </dl>
      <button
        v-if="!isReconciled(a)"
        type="button"
        class="mt-3 w-full appearance-none rounded-md border border-primary py-2 text-body font-medium text-primary disabled:opacity-40"
        :disabled="confirmingId === a.id"
        :data-testid="`reconcile-${a.id}`"
        @click="confirm(a)"
      >
        {{ confirmingId === a.id ? "确认中…" : "确认对账（与券商核对一致）" }}
      </button>
    </div>

    <p
      v-if="reconcile.isError.value"
      class="text-caption text-error"
      data-testid="reconcile-error"
    >
      对账确认失败，请重试。
    </p>

    <p class="text-center text-caption text-gray-400 dark:text-gray-500">
      对账语义：账户现金与持仓与券商端核对一致；确认后写审计，可随时重新核对。
    </p>
  </div>
</template>
