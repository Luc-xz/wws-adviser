<script setup lang="ts">
// HOME-01 首页总览（UI §10.3 / 基准卡 baseline/HOME-01-card.md）：30 秒掌握组合/
// 头部风险/今日焦点。移动端顺序：问候+业务日期+刷新 → 数据状态 → 组合摘要大卡 →
// 风险聚合条 → 持仓概览 → 最新报告。空账户显示导入引导（绝不显示假 ¥0）；
// 离线禁用刷新（AC-08）。建议区已拆至 /advice（HOME-02，计划 §10-Q1 同类决策）。
import { computed, ref } from "vue";
import { useQueryClient } from "@tanstack/vue-query";
import { DataStatusBar, DataFooter, PositionRow, RiskAlert } from "@/shared/ui";
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

const { data: summaryData, isSuccess: summaryOk, isLoading: summaryLoading } = useSummary();
const { data: riskData } = useRisk();
const { data: qualityData } = useMarketQuality();
const { data: positionsData } = usePositions();
const { data: reportsData } = useReports();

const hasAccount = computed(
  () => summaryData.value !== undefined && summaryData.value.total_assets !== "0"
);

const pnlTotal = computed(() => summaryData.value?.pnl_total ?? null);
const pnlTone = computed(() =>
  pnlTotal.value === null ? undefined : Number(pnlTotal.value) >= 0 ? "up" : "down"
);

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

const WEEKDAYS = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"] as const;

/** 业务日期展示（UI §8.1）：中文短日期 + 星期，替代 toLocaleDateString 的 2026/6/9 形态 */
const todayLabel = computed(() => {
  const d = new Date();
  return `${d.getMonth() + 1}月${d.getDate()}日 · ${WEEKDAYS[d.getDay()]}`;
});

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
  <div class="space-y-6">
    <!-- 问候 + 业务日期 + 刷新（离线禁用，AC-08） -->
    <div class="flex items-start justify-between">
      <div>
        <h1 class="text-h1 font-bold lg:text-h1-d">
          {{ greeting() }}
        </h1>
        <p class="mt-0.5 text-label text-gray-500 dark:text-gray-400">
          {{ todayLabel }}
        </p>
      </div>
      <button
        type="button"
        class="appearance-none rounded-md border border-gray-200 bg-white px-3 py-2 text-label text-gray-600 disabled:opacity-40 dark:bg-gray-800 dark:border-gray-700 dark:text-gray-300"
        :disabled="offline"
        data-testid="refresh"
        @click="refresh"
      >
        刷新
      </button>
    </div>

    <!-- 加载骨架（DoD 四态：加载） -->
    <div
      v-if="summaryLoading"
      class="space-y-6"
      data-testid="home-loading"
    >
      <div class="h-24 animate-pulse rounded-lg bg-gray-100 dark:bg-gray-700" />
      <div class="h-16 animate-pulse rounded-lg bg-gray-100 dark:bg-gray-700" />
    </div>

    <!-- 空账户：导入引导（绝不显示假 ¥0） -->
    <div
      v-else-if="summaryOk && !hasAccount"
      class="rounded-lg bg-white p-6 text-center shadow-sm dark:bg-gray-800"
      data-testid="empty-guide"
    >
      <p class="text-h3 font-semibold">
        还没有持仓数据
      </p>
      <p class="mt-1 text-body text-gray-500 dark:text-gray-400">
        导入券商 CSV 或手工录入交易后，这里将展示组合概览。
      </p>
    </div>

    <template v-else>
      <!-- 数据状态条 -->
      <DataStatusBar
        :entries="qualityEntries"
        :offline="offline"
      />

      <!-- 组合摘要大卡（基准卡 §2.3：Display 数字 + 盈亏 tone + 两列副指标） -->
      <section class="rounded-lg bg-white p-4 shadow-sm dark:bg-gray-800">
        <div class="flex items-end justify-between gap-3">
          <div class="min-w-0">
            <div class="text-label text-gray-500 dark:text-gray-400">
              总资产
            </div>
            <div
              class="mt-1 truncate text-display font-bold num lg:text-display-d"
              data-num
              data-testid="total-assets"
            >
              {{ summaryData?.total_assets ?? EMPTY }}
            </div>
          </div>
          <div class="shrink-0 text-right">
            <div class="text-label text-gray-500 dark:text-gray-400">
              累计盈亏
            </div>
            <div
              class="mt-1 text-h3 font-semibold num"
              data-num
              :class="{
                'text-market-up': pnlTone === 'up',
                'text-market-down': pnlTone === 'down',
              }"
              data-testid="pnl-total"
            >
              {{ pnlTotal !== null ? formatMoney(pnlTotal) : EMPTY }}
            </div>
          </div>
        </div>
        <div class="mt-3 grid grid-cols-2 gap-2 border-t border-gray-100 pt-3 dark:border-gray-700">
          <div>
            <div class="text-caption text-gray-400 dark:text-gray-500">
              现金比例
            </div>
            <div
              class="mt-0.5 text-body font-medium num"
              data-num
            >
              {{ summaryData?.cash_ratio ? formatPercent(summaryData.cash_ratio) : EMPTY }}
            </div>
          </div>
          <div>
            <div class="text-caption text-gray-400 dark:text-gray-500">
              集中度
            </div>
            <div
              class="mt-0.5 text-body font-medium num"
              data-num
            >
              {{ summaryData?.concentration ?? EMPTY }}
            </div>
          </div>
        </div>
        <DataFooter
          v-if="summaryData"
          class="mt-3"
          as-of="最新估值"
          source="持仓成本法：移动加权平均"
        />
      </section>

      <!-- 风险聚合条 + 明细（hard 前置；Critical 固定前置于内容前） -->
      <section
        v-if="sortedBreaches.length"
        class="space-y-2"
      >
        <router-link
          to="/portfolio"
          class="flex items-center justify-between rounded-lg px-4 py-3"
          :class="sortedBreaches.some((b) => b.level === 'hard')
            ? 'bg-risk-critical/10 text-risk-critical'
            : 'bg-risk-warning/10 text-risk-warning'"
          data-testid="risk-summary-bar"
        >
          <span class="text-body font-medium">
            {{ sortedBreaches.length }} 项风险需要处理
          </span>
          <span
            class="i-carbon-chevron-right text-xl"
            aria-hidden="true"
          />
        </router-link>
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
          <h2 class="text-h3 font-semibold lg:text-h3-d">
            持仓概览
          </h2>
          <router-link
            to="/portfolio"
            class="text-label text-primary"
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
          :to="`/instruments/${p.instrument_id}`"
        />
      </section>

      <!-- 最新报告 -->
      <section
        v-if="reportsData?.items?.length"
        class="space-y-2"
      >
        <h2 class="text-h3 font-semibold lg:text-h3-d">
          最新报告
        </h2>
        <router-link
          v-for="r in reportsData.items.slice(0, 3)"
          :key="r.id"
          :to="`/reports/${r.id}`"
          class="block rounded-lg bg-white p-4 shadow-sm dark:bg-gray-800"
        >
          <div class="flex items-center justify-between">
            <span class="text-body font-medium">{{ reportTitle(r.report_type) }}</span>
            <span
              class="rounded-sm px-1.5 py-0.5 text-caption"
              :class="
                r.status === 'RENDERED'
                  ? 'bg-success/10 text-success'
                  : 'bg-risk-warning/10 text-risk-warning'
              "
            >
              {{ r.status === "RENDERED" ? "已完成" : "不完整" }}
            </span>
          </div>
          <div class="mt-1 text-caption text-gray-400 dark:text-gray-500">
            {{ r.business_date }} · v{{ r.version }}
          </div>
        </router-link>
      </section>
    </template>
  </div>
</template>
