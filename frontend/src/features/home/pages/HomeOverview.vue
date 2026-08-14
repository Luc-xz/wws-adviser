<script setup lang="ts">
// HOME-01 首页总览（UI §10.3）：30 秒掌握组合/头部风险/今日焦点。移动端顺序：
// 问候+业务日期+刷新 → 数据状态 → 摘要 → 风险 → 持仓概览 → 最新报告。
// 空账户显示导入引导（绝不显示假 ¥0）；离线禁用刷新（AC-08）。
import { computed, ref } from "vue";
import { useQueryClient } from "@tanstack/vue-query";
import { DataStatusBar, DataFooter, MetricCard, PositionRow, RiskAlert } from "@/shared/ui";
import { EMPTY, formatMoney, formatPercent } from "@/shared/format/number";
import {
  useMarketQuality,
  usePositions,
  useReports,
  useRisk,
  useSummary,
} from "@/features/home/composables/queries";

const qc = useQueryClient();
const offline = ref(typeof navigator !== "undefined" ? !navigator.onLine : false);

const { data: summaryData, isSuccess: summaryOk } = useSummary();
const { data: riskData } = useRisk();
const { data: qualityData } = useMarketQuality();
const { data: positionsData } = usePositions();
const { data: reportsData } = useReports();

const hasAccount = computed(
  () => summaryData.value !== undefined && summaryData.value.total_assets !== "0"
);

const pnlTotal = computed(() => summaryData.value?.pnl_total ?? null);

const topPositions = computed(() => {
  const items = positionsData.value?.items ?? [];
  const w = (p: { weight?: string | null }) => (p.weight ? Number(p.weight) : -1);
  return [...items].sort((a, b) => w(b) - w(a)).slice(0, 5);
});

const qualityEntries = computed(() => qualityData.value?.items ?? []);

const sortedBreaches = computed(() =>
  [...(riskData.value?.breaches ?? [])].sort((x, y) =>
    x.level === y.level ? 0 : x.level === "hard" ? -1 : 1
  )
);

function greeting(): string {
  const h = new Date().getHours();
  if (h < 6) return "凌晨好";
  if (h < 12) return "早上好";
  if (h < 18) return "下午好";
  return "晚上好";
}

async function refresh() {
  if (offline.value) return;
  await Promise.all([
    qc.invalidateQueries({ queryKey: ["analytics"] }),
    qc.invalidateQueries({ queryKey: ["positions"] }),
    qc.invalidateQueries({ queryKey: ["market"] }),
    qc.invalidateQueries({ queryKey: ["reports"] }),
  ]);
}

function reportTitle(t: string): string {
  return t === "pre_market" ? "开市前报告" : "收市后复盘";
}
</script>

<template>
  <div class="space-y-3">
    <!-- 问候 + 刷新（离线禁用，AC-08） -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-lg font-semibold">
          {{ greeting() }}
        </h1>
        <p class="text-xs text-gray-400">
          {{ new Date().toLocaleDateString("zh-CN") }}
        </p>
      </div>
      <button
        type="button"
        class="rounded-lg border border-gray-200 px-3 py-2 text-sm disabled:opacity-40"
        :disabled="offline"
        data-testid="refresh"
        @click="refresh"
      >
        刷新
      </button>
    </div>

    <!-- 空账户：导入引导（绝不显示假 ¥0） -->
    <div
      v-if="summaryOk && !hasAccount"
      class="rounded-xl bg-white p-6 text-center shadow-sm"
      data-testid="empty-guide"
    >
      <p class="font-medium">
        还没有持仓数据
      </p>
      <p class="mt-1 text-sm text-gray-500">
        导入券商 CSV 或手工录入交易后，这里将展示组合概览。
      </p>
    </div>

    <template v-else>
      <!-- 数据状态条 -->
      <DataStatusBar
        :entries="qualityEntries"
        :offline="offline"
      />

      <!-- 摘要 -->
      <div class="grid grid-cols-3 gap-2">
        <MetricCard
          label="总资产"
          :value="summaryData?.total_assets ?? EMPTY"
        />
        <MetricCard
          label="累计盈亏"
          :value="pnlTotal !== null ? formatMoney(pnlTotal) : EMPTY"
          :tone="pnlTotal !== null ? (Number(pnlTotal) >= 0 ? 'up' : 'down') : undefined"
        />
        <MetricCard
          label="现金比例"
          :value="summaryData?.cash_ratio ? formatPercent(summaryData.cash_ratio) : EMPTY"
        />
      </div>
      <DataFooter
        v-if="summaryData"
        as-of="最新估值"
        :source="`集中度 ${summaryData.concentration ?? EMPTY}`"
      />

      <!-- 风险（hard 前置） -->
      <section
        v-if="sortedBreaches.length"
        class="space-y-2"
      >
        <h2 class="text-sm font-medium text-gray-600">
          风险提示
        </h2>
        <RiskAlert
          v-for="(b, i) in sortedBreaches"
          :key="i"
          :rule="b.rule"
          :level="b.level"
          :actual="b.actual"
          :limit="b.limit"
          :code="b.code"
          :industry="b.industry"
        />
      </section>

      <!-- 持仓概览 top5 -->
      <section
        v-if="topPositions.length"
        class="space-y-2"
      >
        <div class="flex items-center justify-between">
          <h2 class="text-sm font-medium text-gray-600">
            持仓概览
          </h2>
          <router-link
            to="/portfolio"
            class="text-xs text-primary"
          >
            全部 ›
          </router-link>
        </div>
        <PositionRow
          v-for="p in topPositions"
          :key="p.instrument_id"
          :code="p.code"
          :name="p.name"
          :quantity="p.quantity"
          :avg-cost="p.avg_cost"
          :market-value="p.market_value"
          :weight="p.weight"
          :freshness="p.freshness"
        />
      </section>

      <!-- 最新报告 -->
      <section
        v-if="reportsData?.items?.length"
        class="space-y-2"
      >
        <h2 class="text-sm font-medium text-gray-600">
          最新报告
        </h2>
        <router-link
          v-for="r in reportsData.items.slice(0, 3)"
          :key="r.id"
          :to="`/reports/${r.id}`"
          class="block rounded-xl bg-white p-3 shadow-sm"
        >
          <div class="flex items-center justify-between">
            <span class="font-medium">{{ reportTitle(r.report_type) }}</span>
            <span
              class="rounded px-1.5 py-0.5 text-xs"
              :class="
                r.status === 'RENDERED'
                  ? 'bg-success/10 text-success'
                  : 'bg-risk-warning/10 text-risk-warning'
              "
            >
              {{ r.status === "RENDERED" ? "已完成" : "不完整" }}
            </span>
          </div>
          <div class="mt-1 text-xs text-gray-400">
            {{ r.business_date }} · v{{ r.version }}
          </div>
        </router-link>
      </section>
    </template>
  </div>
</template>
