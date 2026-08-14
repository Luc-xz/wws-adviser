<script setup lang="ts">
// DATA 状态条（UI §9 / ENFORCEMENT_CONTRACT §4 TC-DSB）：4 态 data-state，点击跳 DATA-01
import { computed } from "vue";
import { useRouter } from "vue-router";

const props = defineProps<{
  /** 各标的最新质量状态（/market/quality） */
  entries: { quality_status: string; fetched_at?: string | null }[];
  /** 是否离线（navigator.onLine 由页面传入便于测试） */
  offline?: boolean;
}>();

const router = useRouter();

type State = "normal" | "degraded" | "stale" | "offline";
const state = computed<State>(() => {
  if (props.offline) return "offline";
  if (props.entries.length === 0) return "degraded"; // 无数据 = 数据未接入
  const bad = props.entries.filter((e) => e.quality_status !== "OK");
  if (bad.length === props.entries.length) return "degraded";
  if (bad.length > 0) return "stale";
  return "normal";
});

const label = computed(() => {
  switch (state.value) {
    case "offline":
      return "离线——实时数据不可用";
    case "degraded":
      return "数据不可用——部分功能受限";
    case "stale":
      return `${props.entries.filter((e) => e.quality_status !== "OK").length} 项数据异常`;
    default:
      return "数据正常";
  }
});

function go() {
  router.push("/data-status");
}
</script>

<template>
  <button
    type="button"
    class="w-full flex items-center gap-2 rounded-lg px-3 py-2 text-sm"
    :class="{
      'bg-risk-warning/10 text-risk-warning': state === 'stale',
      'bg-error/10 text-error': state === 'degraded',
      'bg-success/10 text-success': state === 'normal',
      'bg-gray-100 text-gray-500': state === 'offline',
    }"
    :data-state="state"
    data-testid="data-status-bar"
    @click="go"
  >
    <span aria-hidden="true">{{ state === "normal" ? "✓" : "⚠" }}</span>
    <span class="flex-1 text-left">{{ label }}</span>
    <span class="text-xs opacity-70">详情 ›</span>
  </button>
</template>
