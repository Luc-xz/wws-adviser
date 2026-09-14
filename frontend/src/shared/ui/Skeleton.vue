<script setup lang="ts">
// 骨架屏（W3-B4）：指标卡 / 持仓行 / 报告段 三类专用形态。
// 灰块呼吸动画（prefers-reduced-motion 关闭），替换单条 animate-pulse 占位。
withDefaults(
  defineProps<{
    /** metric：指标卡（小标题+大数字）；row：列表行；text：报告段落（多行） */
    variant?: "metric" | "row" | "text";
    /** row/text 形态条数 */
    lines?: number;
  }>(),
  { variant: "metric", lines: 3 },
);
</script>

<template>
  <div
    class="space-y-2"
    :data-testid="`skeleton-${variant}`"
    aria-hidden="true"
  >
    <template v-if="variant === 'metric'">
      <div class="sk h-3 w-16 rounded" />
      <div class="sk mt-2 h-7 w-32 rounded" />
      <div class="sk h-3 w-24 rounded" />
    </template>
    <template v-else-if="variant === 'row'">
      <div
        v-for="i in lines"
        :key="i"
        class="sk flex items-center gap-3 rounded-2xl p-3"
      >
        <div class="h-8 w-8 shrink-0 rounded-full bg-gray-200/70 dark:bg-gray-700/70" />
        <div class="flex-1 space-y-1.5">
          <div class="h-3 w-2/5 rounded bg-gray-200/70 dark:bg-gray-700/70" />
          <div class="h-2.5 w-1/4 rounded bg-gray-200/70 dark:bg-gray-700/70" />
        </div>
        <div class="h-3 w-16 rounded bg-gray-200/70 dark:bg-gray-700/70" />
      </div>
    </template>
    <template v-else>
      <div
        v-for="i in lines"
        :key="i"
        class="h-3 rounded bg-gray-200/70 dark:bg-gray-700/70"
        :style="{ width: i === lines ? '62%' : '100%' }"
      />
    </template>
  </div>
</template>

<style scoped>
.sk > div,
.sk:not(:has(> div)) {
  position: relative;
  overflow: hidden;
  background-color: rgb(229 231 235 / 0.6);
}
:root.dark .sk > div,
:root.dark .sk:not(:has(> div)) {
  background-color: rgb(55 65 81 / 0.5);
}
.sk > div::after,
.sk:not(:has(> div))::after {
  content: "";
  position: absolute;
  inset: 0;
  transform: translateX(-100%);
  background: linear-gradient(
    90deg,
    transparent,
    rgb(255 255 255 / 0.45),
    transparent
  );
  animation: sk-shimmer 1.4s infinite;
}
:root.dark .sk > div::after,
:root.dark .sk:not(:has(> div))::after {
  background: linear-gradient(
    90deg,
    transparent,
    rgb(255 255 255 / 0.06),
    transparent
  );
}
@keyframes sk-shimmer {
  100% {
    transform: translateX(100%);
  }
}
@media (prefers-reduced-motion: reduce) {
  .sk > div::after,
  .sk:not(:has(> div))::after {
    animation: none;
  }
}
</style>
