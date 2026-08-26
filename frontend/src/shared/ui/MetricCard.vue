<script setup lang="ts">
// 指标卡（UI §9）：标题 + 值（字符串十进制，仅展示）+ 副文
defineProps<{
  label: string;
  value: string;
  sub?: string;
  /** up/down 仅行情语境（红涨绿跌 + 符号），非行情场景不传 */
  tone?: "up" | "down" | "flat";
}>();
</script>

<template>
  <div
    class="rounded-xl bg-white dark:bg-gray-800 p-3 shadow-sm"
    data-testid="metric-card"
  >
    <div class="text-xs text-gray-500 dark:text-gray-400 dark:text-gray-500">
      {{ label }}
    </div>
    <div
      class="mt-1 text-lg font-semibold num"
      data-num
      :class="{
        'text-market-up': tone === 'up',
        'text-market-down': tone === 'down',
      }"
    >
      {{ value }}
    </div>
    <div
      v-if="sub"
      class="mt-0.5 text-xs text-gray-400 dark:text-gray-500"
    >
      {{ sub }}
    </div>
  </div>
</template>
