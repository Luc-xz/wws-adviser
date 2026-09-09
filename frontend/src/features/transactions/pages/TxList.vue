<script setup lang="ts">
// TX-01 交易流水（波 V4；计划 §10-Q2 决策：全量流水 + 筛选独立页，
// PORT 流水 Tab 保留持仓视角摘要）。筛选：类型 / 标的；keyset 游标加载更多。
import { ref, watch } from "vue";
import client from "@/api/client";
import { PageHeader } from "@/shared/ui";
import { EMPTY, formatMoney } from "@/shared/format/number";
import { KIND_NAMES, TX_KINDS, type TxKind, type TxRow } from "../composables/queries";
import { useInstrumentMap } from "@/features/portfolio/composables/queries";

const kindFilter = ref<TxKind | "">("");
const instrumentFilter = ref("");
const rows = ref<import("../composables/queries").TxRow[]>([]);
const cursor = ref<string | null>(null);
const hasMore = ref(false);
const loading = ref(false);
const error = ref("");
const loaded = ref(false);

const { data: instrumentMap } = useInstrumentMap();

function instLabel(instrumentId: string): string {
  const inst = instrumentMap.value?.get(instrumentId);
  return inst ? `${inst.name} ${inst.code}` : instrumentId.slice(0, 8);
}

async function load(reset: boolean) {
  loading.value = true;
  error.value = "";
  try {
    const { data, error: err } = await client.GET("/api/v1/transactions", {
      params: {
        query: {
          kind: (kindFilter.value || undefined) as TxKind | undefined,
          instrument_id: instrumentFilter.value || undefined,
          cursor: reset ? undefined : (cursor.value ?? undefined),
          limit: 50,
        },
      },
    });
    if (err) {
      // 404 = 尚无账户（后端账户域语义）→ 空列表而非错误
      if ((err as { status?: number }).status === 404) {
        rows.value = [];
        cursor.value = null;
        hasMore.value = false;
        loaded.value = true;
        return;
      }
      throw new Error("流水获取失败");
    }
    rows.value = reset
      ? (data.items as TxRow[])
      : [...rows.value, ...(data.items as TxRow[])];
    cursor.value = data.next_cursor ?? null;
    hasMore.value = data.has_more;
    loaded.value = true;
  } catch (e) {
    error.value = e instanceof Error ? e.message : "加载失败";
  } finally {
    loading.value = false;
  }
}

watch([kindFilter, instrumentFilter], () => void load(true), { immediate: true });

function rowAmount(q: string, p: string): string {
  const v = Number(q) * Number(p);
  return Number.isFinite(v) ? formatMoney(v.toFixed(2)) : EMPTY;
}
</script>

<template>
  <div class="space-y-6">
    <PageHeader
      title="交易流水"
      subtitle="全量记录 · 指纹去重 · 类型与标的筛选"
      back
    >
      <template #actions>
        <router-link
          to="/transactions/new"
          class="rounded-md bg-primary px-3 py-2 text-label font-medium text-white"
          data-testid="goto-new-tx"
        >
          记录交易
        </router-link>
        <router-link
          to="/transactions/import"
          class="rounded-md border border-gray-200 px-3 py-2 text-label text-gray-600 dark:border-gray-600 dark:text-gray-300"
        >
          导入
        </router-link>
      </template>
    </PageHeader>

    <!-- 筛选 -->
    <div class="flex flex-wrap items-center gap-2">
      <select
        v-model="kindFilter"
        class="rounded-md border border-gray-200 bg-transparent px-2 py-1.5 text-label dark:border-gray-600"
        data-testid="tx-filter-kind"
      >
        <option value="">
          全部类型
        </option>
        <option
          v-for="k in TX_KINDS"
          :key="k"
          :value="k"
        >
          {{ KIND_NAMES[k] }}
        </option>
      </select>
      <input
        v-model="instrumentFilter"
        placeholder="按标的 ID 筛选"
        class="w-48 rounded-md border border-gray-200 bg-transparent px-2 py-1.5 text-label dark:border-gray-600"
        data-testid="tx-filter-instrument"
      >
    </div>

    <p
      v-if="error"
      class="text-caption text-error"
    >
      {{ error }}
    </p>

    <div
      v-if="loaded && !rows.length && !loading"
      class="rounded-lg bg-white p-6 text-center text-body text-gray-400 shadow-sm dark:bg-gray-800 dark:text-gray-500"
      data-testid="tx-empty"
    >
      暂无匹配的流水
    </div>

    <div
      v-else
      class="divide-y divide-gray-100 overflow-hidden rounded-lg bg-white shadow-sm dark:divide-gray-700 dark:bg-gray-800"
      data-testid="tx-list"
    >
      <div
        v-for="t in rows"
        :key="t.id"
        class="flex items-center justify-between px-4 py-3"
      >
        <div class="min-w-0">
          <div class="flex items-center gap-2">
            <span
              class="rounded-sm px-1.5 py-0.5 text-caption font-medium"
              :class="t.direction === 'IN'
                ? 'bg-primary/10 text-primary'
                : 'bg-action-reduce/10 text-action-reduce'"
            >
              {{ KIND_NAMES[t.kind] ?? t.kind }}
            </span>
            <span class="truncate text-body font-medium">{{ instLabel(t.instrument_id) }}</span>
          </div>
          <div
            class="mt-1 text-caption text-gray-500 num dark:text-gray-400"
            data-num
          >
            {{ t.trade_at.slice(0, 10) }} · 数量 {{ t.quantity }} @ {{ t.price }}
            <template v-if="Number(t.fee) + Number(t.tax) > 0">
              · 费税 {{ formatMoney((Number(t.fee) + Number(t.tax)).toFixed(2)) }}
            </template>
          </div>
        </div>
        <div class="shrink-0 text-right">
          <div
            class="text-body font-medium num"
            data-num
          >
            {{ rowAmount(t.quantity, t.price) }}
          </div>
        </div>
      </div>
    </div>

    <button
      v-if="hasMore"
      type="button"
      class="w-full appearance-none rounded-md border border-gray-200 py-2.5 text-label text-gray-600 disabled:opacity-40 dark:border-gray-600 dark:text-gray-300"
      :disabled="loading"
      data-testid="tx-more"
      @click="load(false)"
    >
      {{ loading ? "加载中…" : "加载更多" }}
    </button>
    <p
      v-if="loaded && rows.length"
      class="text-center text-caption text-gray-400 dark:text-gray-500"
    >
      共 {{ rows.length }} 条{{ hasMore ? "（可继续加载）" : "" }}
    </p>
  </div>
</template>
