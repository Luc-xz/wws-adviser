<script setup lang="ts">
// REP-01/REP-02 报告详情（UI §10.17/10.18 共用骨架）：头部（类型/日期/状态/版本/降级标记）→
// 执行摘要 → 风险 → 持仓 → 模型解读（有则显，无则降级提示）→ 来源与版本尾注。
// 生成/重新生成：POST /reports/generate + useJobStatus 轮询（SSE 兜底就绪）→ 完成跳新报告。
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useQueryClient } from "@tanstack/vue-query";
import { DataFooter, MetricCard, PositionRow, RiskAlert } from "@/shared/ui";
import { EMPTY, formatMoney, formatPercent } from "@/shared/format/number";
import { useReport, useGenerateReport } from "@/features/reports/composables/queries";
import { useJobStatus } from "@/shared/sse/useJobStatus";

const route = useRoute();
const router = useRouter();
const qc = useQueryClient();

const reportId = computed(() => String(route.params.id ?? ""));
const { data: reportData, isLoading: reportLoading } = useReport(() => reportId.value);

const detail = computed(() => reportData.value);
const content = computed(() => {
  const c = detail.value?.content as Record<string, any> | null | undefined;
  return c ?? null;
});
const header = computed(() => content.value?.header as Record<string, any> | undefined);
const summarySection = computed(() => content.value?.summary as Record<string, any> | undefined);
const riskItems = computed(
  () => (content.value?.risk as Array<Record<string, any>>) ?? []
);
const positionItems = computed(
  () => (content.value?.positions as Array<Record<string, any>>) ?? []
);
const modelSection = computed(
  () => (content.value?.model as Record<string, any> | null) ?? null
);
const degradationFlags = computed(() => detail.value?.degradation_flags ?? header.value?.degradation_flags ?? []);

const title = computed(() =>
  detail.value?.report_type === "post_market" ? "收市后复盘" : "开市前报告"
);
const incomplete = computed(
  () => detail.value?.status === "PARTIAL" || degradationFlags.value.length > 0
);

const FLAG_NAMES: Record<string, string> = {
  market_data_missing: "行情数据缺失",
  documents_unavailable: "公告数据缺失",
  model_unavailable: "模型不可用（降级）",
};

// —— 生成 / 重新生成（轮询兜底）——
const { generate } = useGenerateReport();
const activeJobId = ref<string | null>(null);
const { state: jobState, start: startJob } = useJobStatus(() => activeJobId.value);

async function regenerate() {
  const rt = detail.value?.report_type === "post_market" ? "post_market" : "pre_market";
  const resp = await generate(rt, detail.value?.business_date);
  if (resp.report) {
    // 内联执行已完成 → 直接进新报告
    await qc.invalidateQueries({ queryKey: ["report"] });
    router.replace(`/reports/${resp.report.id}`);
    return;
  }
  activeJobId.value = resp.job_run_id;
  startJob();
}

// 轮询到终态 → 刷新报告列表并返回首页查看最新报告（RES-02：可离开此页）
watch(
  () => jobState.value.status,
  async (s) => {
    if (s === "COMPLETED" || s === "PARTIAL" || s === "FAILED") {
      await qc.invalidateQueries({ queryKey: ["reports"] });
      if (s !== "FAILED") router.push({ name: "home" });
    }
  }
);
</script>

<template>
  <div class="space-y-3">
    <!-- 头部 -->
    <div class="rounded-xl bg-white p-4 shadow-sm">
      <div class="flex items-center justify-between">
        <h1 class="text-lg font-semibold">
          {{ title }}
        </h1>
        <span
          class="rounded px-1.5 py-0.5 text-xs"
          :class="incomplete ? 'bg-risk-warning/10 text-risk-warning' : 'bg-success/10 text-success'"
          :data-testid="incomplete ? 'report-incomplete' : 'report-complete'"
        >
          {{ incomplete ? "不完整" : "已完成" }}
        </span>
      </div>
      <p class="mt-1 text-xs text-gray-400">
        {{ detail?.business_date }} · v{{ detail?.version }} · 生成于 {{ detail?.generated_at }}
      </p>
      <!-- 降级标记（AC-02：公告源失败→标记不完整） -->
      <div
        v-if="degradationFlags.length"
        class="mt-2 space-y-1"
      >
        <p
          v-for="f in degradationFlags"
          :key="f"
          class="rounded bg-risk-warning/5 px-2 py-1 text-xs text-risk-warning"
        >
          ⚠ {{ FLAG_NAMES[f] ?? f }}
        </p>
      </div>
      <button
        type="button"
        class="mt-3 w-full rounded-lg border border-primary py-2 text-sm font-medium text-primary disabled:opacity-40"
        data-testid="regenerate"
        :disabled="jobState.source !== 'idle' && !jobState.status"
        @click="regenerate"
      >
        {{ detail ? "重新生成" : "生成" }}
      </button>
      <p
        v-if="jobState.source === 'polling'"
        class="mt-2 text-center text-xs text-gray-400"
      >
        任务进行中（{{ jobState.status ?? "..." }}）· 可离开此页
      </p>
    </div>

    <div
      v-if="!content"
      class="rounded-xl bg-white p-6 text-center text-sm text-gray-400 shadow-sm"
    >
      {{ reportLoading ? "加载中…" : "报告内容不可用" }}
    </div>

    <template v-else>
      <!-- 执行摘要 -->
      <section
        v-if="summarySection"
        class="space-y-2"
      >
        <h2 class="text-sm font-medium text-gray-600">
          执行摘要
        </h2>
        <div class="grid grid-cols-2 gap-2">
          <MetricCard
            label="总资产"
            :value="summarySection.total_assets ?? EMPTY"
          />
          <MetricCard
            label="现金比例"
            :value="summarySection.cash_ratio ? formatPercent(summarySection.cash_ratio) : EMPTY"
          />
          <MetricCard
            label="累计盈亏"
            :value="summarySection.pnl_total ? formatMoney(summarySection.pnl_total) : EMPTY"
          />
          <MetricCard
            label="集中度"
            :value="summarySection.concentration ?? EMPTY"
          />
        </div>
      </section>

      <!-- 风险 -->
      <section class="space-y-2">
        <h2 class="text-sm font-medium text-gray-600">
          风险
        </h2>
        <RiskAlert
          v-for="(b, i) in riskItems"
          :key="i"
          :rule="String(b.rule)"
          :level="String(b.level)"
          :actual="String(b.actual)"
          :limit="String(b.limit)"
          :code="b.code ?? null"
          :industry="b.industry ?? null"
        />
        <p
          v-if="!riskItems.length"
          class="rounded-xl bg-white p-3 text-sm text-gray-400 shadow-sm"
        >
          未触发风险限制
        </p>
      </section>

      <!-- 持仓（移动卡片式） -->
      <section
        v-if="positionItems.length"
        class="space-y-2"
      >
        <h2 class="text-sm font-medium text-gray-600">
          持仓
        </h2>
        <PositionRow
          v-for="p in positionItems"
          :key="p.instrument_id"
          :code="String(p.code)"
          :name="String(p.name)"
          :quantity="String(p.quantity)"
          :avg-cost="String(p.avg_cost)"
          :market-value="p.market_value ?? null"
          :weight="p.weight ?? null"
          :freshness="String(p.freshness)"
        />
      </section>

      <!-- 模型解读（有则显；降级时显提示） -->
      <section
        v-if="modelSection"
        class="space-y-2"
      >
        <h2 class="text-sm font-medium text-gray-600">
          解读
        </h2>
        <div class="rounded-xl bg-white p-3 text-sm leading-relaxed shadow-sm">
          {{ modelSection.summary }}
        </div>
      </section>
      <section
        v-else-if="degradationFlags.includes('model_unavailable')"
        class="space-y-2"
      >
        <h2 class="text-sm font-medium text-gray-600">
          解读
        </h2>
        <div class="rounded-xl bg-risk-warning/5 p-3 text-sm text-risk-warning">
          模型暂不可用，以上为确定性摘要（可点击「重新生成」重试）。
        </div>
      </section>

      <!-- 来源与版本尾注 -->
      <div class="rounded-xl bg-white p-3 text-xs text-gray-400 shadow-sm">
        <p>来源 {{ detail?.sources_count ?? 0 }} 项</p>
        <p class="mt-1">
          schema {{ header?.schema_version ?? detail?.schema_version }} ·
          组合算法 {{ header?.portfolio_version }} · 风险规则 {{ header?.risk_ruleset_version }} ·
          提示词 {{ header?.prompt_version ?? "—" }}
        </p>
        <p class="mt-1">
          本报告含个人研究性内容，不构成投资建议。
        </p>
      </div>
      <DataFooter
        :as-of="detail?.generated_at ?? null"
        :source="`v${detail?.version ?? 1}`"
      />
    </template>
  </div>
</template>
