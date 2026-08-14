<script setup lang="ts">
// 持仓行/卡（UI §9 PositionRow）：代码/名称/数量/市值/权重/新鲜度；空值 = —
import { EMPTY, formatPercent } from "@/shared/format/number";

defineProps<{
  code: string;
  name: string;
  quantity: string;
  avgCost: string;
  marketValue?: string | null;
  weight?: string | null;
  freshness: string; // business_date 或 "missing"
}>();
</script>

<template>
  <div
    class="flex items-center gap-3 rounded-xl bg-white p-3 shadow-sm"
    data-testid="position-row"
  >
    <div class="min-w-0 flex-1">
      <div class="flex items-baseline gap-2">
        <span class="font-medium">{{ name }}</span>
        <span class="text-xs text-gray-400">{{ code }}</span>
      </div>
      <div
        class="mt-0.5 text-xs text-gray-500 num"
        data-num
      >
        数量 {{ quantity }} · 成本 {{ avgCost }}
      </div>
    </div>
    <div class="text-right">
      <div
        class="num font-medium"
        data-num
      >
        {{ marketValue ?? EMPTY }}
      </div>
      <div
        class="text-xs text-gray-500 num"
        data-num
      >
        {{ weight ? formatPercent(weight) : EMPTY }}
      </div>
      <div
        class="text-xs"
        :class="freshness === 'missing' ? 'text-risk-warning' : 'text-gray-400'"
      >
        {{ freshness === "missing" ? "无行情" : freshness }}
      </div>
    </div>
  </div>
</template>
