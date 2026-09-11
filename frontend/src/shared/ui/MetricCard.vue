<script setup lang="ts">
// 指标卡（UI §9）：标题 + 值（字符串十进制，仅展示）+ 副文
// W3-A3：可选图标容器（原型摘要卡右上角彩色 icon 容器）——icon 类名 + 容器色调
defineProps<{
  label: string;
  value: string;
  sub?: string;
  /** up/down 仅行情语境（红涨绿跌 + 符号），非行情场景不传 */
  tone?: "up" | "down" | "flat";
  /** 可选图标（material-symbols-rounded 类名），渲染右上角彩色容器 */
  icon?: string;
  /** 图标容器色调（容器底 10% + 图标语义色） */
  iconTone?: "primary" | "success" | "warning" | "risk";
}>();

const TONE_CLS: Record<string, string> = {
  primary: "bg-primary/10 text-primary",
  success: "bg-success/10 text-success",
  warning: "bg-risk-warning/10 text-risk-warning",
  risk: "bg-risk-critical/10 text-risk-critical",
};
</script>

<template>
  <div
    class="rounded-2xl bg-white dark:bg-gray-800 p-3 shadow-sm"
    data-testid="metric-card"
  >
    <div class="flex items-start justify-between gap-2">
      <div class="text-xs text-gray-500 dark:text-gray-400">
        {{ label }}
      </div>
      <span
        v-if="icon"
        class="shrink-0 rounded-lg p-1.5"
        :class="TONE_CLS[iconTone ?? 'primary']"
        aria-hidden="true"
      >
        <span :class="icon" class="block text-base" />
      </span>
    </div>
    <div
      class="mt-1 text-lg font-semibold num"
      data-num
      data-context="quote"
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
