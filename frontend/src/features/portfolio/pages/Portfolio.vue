<script setup lang="ts">
// PORT-01 持仓与自选（UI §10.6，MVP：当前持仓 Tab）：摘要条 + 持仓卡片（按权重排序，
// hard 风险标的前置）+ 记录交易主按钮（UI 随后续波次）。空态引导。
import { computed } from "vue";
import { DataFooter, PositionRow } from "@/shared/ui";
import { formatMoney } from "@/shared/format/number";
import { usePositions, useRisk } from "@/features/home/composables/queries";

const { data: positionsData, isSuccess: positionsOk } = usePositions();
const { data: riskData } = useRisk();

const hardHitCodes = computed(
  () =>
    new Set(
      (riskData.value?.breaches ?? [])
        .filter((b) => b.level === "hard" && b.code)
        .map((b) => b.code)
    )
);

const sorted = computed(() => {
  const items = positionsData.value?.items ?? [];
  const w = (p: { weight?: string | null }) => (p.weight ? Number(p.weight) : -1);
  return [...items].sort(
    (a, b) =>
      Number(hardHitCodes.value.has(b.code)) - Number(hardHitCodes.value.has(a.code)) ||
      w(b) - w(a)
  );
});

const summaryStrip = computed(() => {
  const d = positionsData.value;
  if (!d) return null;
  const mv = (d.items ?? []).reduce(
    (acc, p) => acc + (p.market_value ? Number(p.market_value) : 0),
    0
  );
  return {
    marketValue: formatMoney(mv.toFixed(2)),
    cash: formatMoney(d.cash),
    count: d.items?.length ?? 0,
  };
});

function recordTrade() {
  // TODO(后续波次): 交易记录 UI（CSV 导入/手工录入，后端 /transactions 已就绪）
}
</script>

<template>
  <div class="space-y-3">
    <div class="flex items-center justify-between">
      <h1 class="text-lg font-semibold">
        持仓
      </h1>
      <button
        type="button"
        class="rounded-lg bg-primary px-3 py-2 text-sm font-medium text-white"
        data-testid="record-trade"
        @click="recordTrade"
      >
        记录交易
      </button>
    </div>

    <!-- 空态引导 -->
    <div
      v-if="positionsOk && !positionsData?.items?.length"
      class="rounded-xl bg-white p-6 text-center shadow-sm"
      data-testid="empty-guide"
    >
      <p class="font-medium">
        暂无持仓
      </p>
      <p class="mt-1 text-sm text-gray-500">
        记录第一笔交易后即可查看持仓与成本。
      </p>
    </div>

    <template v-else>
      <!-- 摘要条 -->
      <div
        v-if="summaryStrip"
        class="grid grid-cols-3 gap-2 text-center"
      >
        <div class="rounded-xl bg-white p-3 shadow-sm">
          <div class="text-xs text-gray-500">
            持仓市值
          </div>
          <div
            class="mt-1 font-semibold num"
            data-num
          >
            {{ summaryStrip.marketValue }}
          </div>
        </div>
        <div class="rounded-xl bg-white p-3 shadow-sm">
          <div class="text-xs text-gray-500">
            现金
          </div>
          <div
            class="mt-1 font-semibold num"
            data-num
          >
            {{ summaryStrip.cash }}
          </div>
        </div>
        <div class="rounded-xl bg-white p-3 shadow-sm">
          <div class="text-xs text-gray-500">
            持仓数
          </div>
          <div
            class="mt-1 font-semibold num"
            data-num
          >
            {{ summaryStrip.count }}
          </div>
        </div>
      </div>
      <DataFooter as-of="最新估值" />

      <!-- 持仓卡片（hard 风险前置标注） -->
      <div class="space-y-2">
        <div
          v-for="p in sorted"
          :key="p.instrument_id"
          class="relative"
        >
          <span
            v-if="hardHitCodes.has(p.code)"
            class="absolute right-2 top-2 z-1 rounded bg-risk-critical px-1.5 py-0.5 text-xs text-white"
          >
            风险
          </span>
          <PositionRow
            :code="p.code"
            :name="p.name"
            :quantity="p.quantity"
            :avg-cost="p.avg_cost"
            :market-value="p.market_value"
            :weight="p.weight"
            :freshness="p.freshness"
          />
        </div>
      </div>
      <p class="text-center text-xs text-gray-400">
        排序：风险优先 · 权重从高到低
      </p>
    </template>
  </div>
</template>
