<script setup lang="ts">
// 风险提示条（UI §9 / ENFORCEMENT_CONTRACT TC-RA）：level 徽标 + 实际/上限；hard=Critical 前置语义
import { computed } from "vue";

const props = defineProps<{
  rule: string;
  level: string; // hard | soft
  actual: string;
  limit: string;
  code?: string | null;
  industry?: string | null;
}>();

const RULE_NAMES: Record<string, string> = {
  single_cap: "单标的仓位超限",
  industry_cap: "行业集中度超限",
  cash_floor: "现金比例低于下限",
  top_n_concentration: "前 N 持仓集中",
};

const ruleName = computed(() => RULE_NAMES[props.rule] ?? props.rule);
const subject = computed(() => props.code ?? props.industry ?? null);
</script>

<template>
  <div
    class="rounded-lg border-l-4 px-3 py-2 text-sm"
    :class="{
      'border-risk-critical bg-risk-critical/5': level === 'hard',
      'border-risk-warning bg-risk-warning/5': level !== 'hard',
    }"
    role="alert"
    data-testid="risk-alert"
  >
    <span
      class="mr-2 inline-block rounded px-1.5 py-0.5 text-xs font-medium text-white"
      :class="{ 'bg-risk-critical': level === 'hard', 'bg-risk-warning': level !== 'hard' }"
    >
      {{ level === "hard" ? "硬限制" : "软限制" }}
    </span>
    <span class="font-medium">{{ ruleName }}</span>
    <span
      v-if="subject"
      class="text-gray-500"
    >（{{ subject }}）</span>
    <div
      class="mt-1 num text-xs text-gray-600"
      data-num
    >
      当前 {{ actual }} / 上限 {{ limit }}
    </div>
  </div>
</template>
