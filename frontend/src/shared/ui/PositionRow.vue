<script setup lang="ts">
// 持仓行/卡（UI §9 PositionRow）：代码/名称/数量/市值/权重/新鲜度；空值 = —
// 可选 to：传入路由则整行可点（PORT-02 标的详情，波 V4）。
import { EMPTY, formatPercent } from "@/shared/format/number";
import { useRouter } from "vue-router";

defineProps<{
  code: string;
  name: string;
  quantity: string;
  avgCost: string;
  marketValue?: string | null;
  weight?: string | null;
  freshness: string; // business_date 或 "missing"
  /** 标的详情路由（instrument_id）；传入即整行可点 */
  to?: string;
}>();

const router = useRouter();
</script>

<template>
  <div
    class="flex items-center gap-3 rounded-lg bg-white p-3 shadow-sm dark:bg-gray-800"
    :class="to ? 'cursor-pointer transition-colors hover:bg-gray-50 dark:hover:bg-gray-700' : ''"
    data-testid="position-row"
    @click="to && router.push(to)"
  >
    <div class="min-w-0 flex-1">
      <div class="flex items-baseline gap-2">
        <span class="font-medium">{{ name }}</span>
        <span class="text-caption text-gray-400 dark:text-gray-500">{{ code }}</span>
        <span
          v-if="to"
          class="i-carbon-chevron-right text-gray-300"
          aria-hidden="true"
        />
      </div>
      <div
        class="mt-0.5 text-caption text-gray-500 num dark:text-gray-400"
        data-num
      >
        数量 {{ quantity }} · 成本 {{ avgCost }}
      </div>
    </div>
    <div class="text-right">
      <div
        class="text-body font-medium num"
        data-num
      >
        {{ marketValue ?? EMPTY }}
      </div>
      <div
        class="text-caption text-gray-500 num dark:text-gray-400"
        data-num
      >
        {{ weight ? formatPercent(weight) : EMPTY }}
      </div>
      <div
        class="text-caption"
        :class="freshness === 'missing' ? 'text-risk-warning' : 'text-gray-400 dark:text-gray-500'"
      >
        {{ freshness === "missing" ? "无行情" : freshness }}
      </div>
    </div>
  </div>
</template>
