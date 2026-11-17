<script setup lang="ts">
// DATA-01 数据状态中心（UI §9 DataStatusBar 跳转目标 / 基准卡 baseline/DATA-01-card.md）：
// 「数据质量」= 各标的行情/净值质量与新鲜度 + 多源冲突（Phase 3.3）；
// 「采集运行」= 批次(job_runs)→条目(ingest_items)→源健康(source_health) 过程态下钻
//（采集监控面板波2，5_DATA §12）。消解操作在 SET-02，本页展示 + 引导。
import { useQuery } from "@tanstack/vue-query";
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import client from "@/api/client";
import {
  useCollectionsHealth,
  useJobItems,
  useJobRuns,
  useJobStats,
  useRefreshBars,
} from "@/features/data/composables/queries";
import type { JobRun, SourceHealth } from "@/features/data/composables/queries";
import { useMarketQuality } from "@/features/home/composables/queries";
import { formatCount, formatMoney, formatRate } from "@/shared/format/number";
import { formatDuration, EMPTY } from "@/shared/format/number";
import { formatRelativeTime } from "@/shared/format/time";
import { DataFooter, PageHeader, Skeleton } from "@/shared/ui";

const router = useRouter();

// —— 分区 tab（深链 ?tab=runs 直达采集运行）——
type Tab = "quality" | "runs";
const tab = ref<Tab>((router.currentRoute.value.query.tab === "runs" ? "runs" : "quality"));
function switchTab(t: Tab): void {
  tab.value = t;
}

// —— 数据质量 tab（既有主线）——
const { data: qualityData, isLoading: qualityLoading } = useMarketQuality();

const auditOpen = ref(false);
const { data: auditData } = useQuery({
  queryKey: ["audit-events"],
  queryFn: async () => {
    const { data, error } = await client.GET("/api/v1/audit-events", {
      params: { query: { limit: 50 } },
    });
    if (error || !data) throw new Error("审计获取失败");
    return data;
  },
});
const auditRows = computed(() => auditData.value?.items ?? []);

const { data: conflictsData } = useQuery({
  queryKey: ["market", "conflicts"],
  queryFn: async () => {
    const { data, error } = await client.GET("/api/v1/market/conflicts");
    if (error || !data) throw new Error("冲突列表获取失败");
    return data;
  },
});

const openConflicts = (conflictsData.value?.items ?? []).filter(
  (c) => c.status !== "RESOLVED"
);

function statusClass(s: string): string {
  if (s === "OK") return "bg-success/10 text-success";
  if (s === "DELAYED") return "bg-risk-warning/10 text-risk-warning";
  if (s === "CONFLICT") return "bg-risk-critical/10 text-risk-critical";
  return "bg-error/10 text-error";
}

const STATUS_NAMES: Record<string, string> = {
  OK: "正常",
  DELAYED: "延迟",
  MISSING: "缺失",
  CONFLICT: "多源冲突",
  PARSE_FAILED: "解析失败",
  SOURCE_UNAVAILABLE: "源不可用",
};

// —— 采集运行 tab ——
const { data: statsData, isLoading: statsLoading } = useJobStats(7);
const { data: healthData, isLoading: healthLoading } = useCollectionsHealth();
const { data: jobsData, isLoading: jobsLoading } = useJobRuns();
const jobRows = computed(() => jobsData.value?.items ?? []);
const healthRows = computed(() => healthData.value?.sources ?? []);

// 展开下钻：一次只展开一个批次（条目查询按批次缓存）
const expandedId = ref<string | null>(null);
const expandedJobId = computed(() => expandedId.value);
const { data: itemsData, isLoading: itemsLoading } = useJobItems(expandedJobId);
const onlyFailed = ref(false);
const itemRows = computed(() => {
  const rows = itemsData.value?.items ?? [];
  return onlyFailed.value ? rows.filter((i) => i.status === "FAILED") : rows;
});
function toggleJob(id: string): void {
  expandedId.value = expandedId.value === id ? null : id;
  onlyFailed.value = false;
}

// 手动补采（仅 FAILED 日线条目且 data_ref 可解析出区间）
const { refresh } = useRefreshBars();
const refreshingId = ref<string | null>(null);
const refreshError = ref<string | null>(null);
const PARSE = /^market:([^:]+):(\d{4}-\d{2}-\d{2})-(\d{4}-\d{2}-\d{2})$/;
function canRefresh(dataRef: string | null): boolean {
  return dataRef !== null && PARSE.test(dataRef);
}
async function onRefresh(itemId: string, dataRef: string): Promise<void> {
  refreshingId.value = itemId;
  refreshError.value = null;
  try {
    await refresh(dataRef);
  } catch (e) {
    refreshError.value = e instanceof Error ? e.message : "补采失败";
  } finally {
    refreshingId.value = null;
  }
}

const CATEGORY_NAMES: Record<string, string> = {
  quote: "行情快照",
  bar: "日线",
  nav: "净值",
  calendar: "交易日历",
  document: "公告",
  news: "新闻",
  index_quote: "指数快照",
  index_bar: "指数日K",
  sector_flow: "板块资金流",
};

const JOB_TYPE_NAMES: Record<string, string> = {
  pre_market: "开市前报告",
  post_market: "收市后报告",
  data_maintenance: "数据维护（采集）",
  calibration_scan: "校准扫描",
  advice_review: "建议评价",
  ingest_manual: "手动补采",
  backup: "备份",
  market_env_intraday: "市场环境采集（盘中）",
  market_env_eod: "市场环境采集（日终）",
  overseas_morning: "外围市场采集（晨间）",
};

const JOB_STATUS_NAMES: Record<string, string> = {
  PENDING: "排队中",
  RUNNING: "进行中",
  RETRY_WAIT: "等待重试",
  COMPLETED: "已完成",
  PARTIAL: "部分完成",
  FAILED: "失败",
  CANCELLED: "已取消",
};

const ITEM_STATUS_NAMES: Record<string, string> = {
  OK: "成功",
  PARTIAL: "部分",
  SKIPPED: "跳过",
  FAILED: "失败",
};

function jobStatusClass(s: string): string {
  if (s === "COMPLETED") return "bg-success/10 text-success";
  if (s === "PARTIAL") return "bg-risk-warning/10 text-risk-warning";
  if (s === "FAILED") return "bg-error/10 text-error";
  if (s === "RUNNING") return "bg-online/10 text-online";
  return "bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-300";
}

function itemStatusClass(s: string): string {
  if (s === "OK") return "bg-success/10 text-success";
  if (s === "SKIPPED") return "bg-gray-100 text-gray-400 dark:bg-gray-700 dark:text-gray-400";
  if (s === "PARTIAL") return "bg-risk-warning/10 text-risk-warning";
  return "bg-error/10 text-error";
}

// ADR-0009：在线/健康语义只用 online teal，禁止复用行情涨跌色
function healthClass(s: string): string {
  if (s === "ok") return "bg-online/10 text-online";
  if (s === "degraded") return "bg-risk-warning/10 text-risk-warning";
  if (s === "unavailable") return "bg-error/10 text-error";
  return "bg-gray-100 text-gray-400 dark:bg-gray-700 dark:text-gray-400";
}

const HEALTH_NAMES: Record<string, string> = {
  ok: "正常",
  degraded: "降级",
  unavailable: "不可用",
  no_data: "无记录",
};

function healthMeta(s: SourceHealth): { label: string; sub: string } {
  const name = CATEGORY_NAMES[s.category] ?? s.category;
  if (!s.configured) return { label: name, sub: "未配置真实数据源（仅占位）" };
  const last = s.last_success_at ? `最近成功 ${formatRelativeTime(s.last_success_at)}` : "尚无成功记录";
  const fail = s.consecutive_failures > 0 ? ` · 连续失败 ${formatCount(s.consecutive_failures)} 次` : "";
  let coverage = "";
  const ld = s.latest_data as
    | { latest_business_date?: string | null; rows_7d?: number | null; total?: number | null }
    | null;
  if (ld) {
    if (s.category === "document") {
      coverage = `共 ${formatCount(ld.total ?? null)} 篇 · 近7天 +${formatCount(ld.rows_7d ?? null)}`;
    } else if (ld.latest_business_date) {
      coverage = `最新 ${ld.latest_business_date}`;
      if (ld.rows_7d !== null && ld.rows_7d !== undefined) {
        coverage += ` · 近7天 ${formatCount(ld.rows_7d)} 行`;
      }
    }
  }
  return { label: name, sub: [last + fail, coverage || null].filter(Boolean).join(" · ") };
}

function jobDurationMs(j: JobRun): number | null {
  if (!j.started_at || !j.completed_at) return null;
  const ms = new Date(j.completed_at).getTime() - new Date(j.started_at).getTime();
  return Number.isNaN(ms) ? null : Math.max(0, ms);
}

/** result_ref 摘要 → 中文一行（数字过 formatCount；未知格式返回原 ref）。 */
function summaryText(j: JobRun): string {
  const s = j.result_summary as Record<string, unknown>;
  const kind = typeof s.kind === "string" ? s.kind : null;
  if (kind === "bars") return `日线 成功${formatCount(num(s.ok))} / 失败${formatCount(num(s.failed))}`;
  if (kind === "docs") {
    return `公告 收${formatCount(num(s.ingested))} 更${formatCount(num(s.updated))} 跳${formatCount(num(s.skipped))}`;
  }
  if (kind === "nav") return `净值 ${String(s.ref ?? EMPTY)} 条`;
  if (kind === "report") return "已生成报告";
  if (kind === "skipped") return "跳过（非交易日）";
  if (kind && typeof s.n === "number") return `${kind} ${formatCount(s.n)}`;
  return j.result_ref ?? EMPTY;
}

function num(v: unknown): number | null {
  return typeof v === "number" ? v : null;
}
</script>

<template>
  <div class="space-y-6">
    <PageHeader
      title="数据状态"
      subtitle="数据质量与新鲜度 · 采集运行与健康"
      back
      @back="router.back()"
    />

    <!-- 分区 tab（W4 采集监控面板）：质量=结果态，运行=过程态 -->
    <div
      class="flex rounded-full bg-gray-100 p-1 dark:bg-gray-800"
      role="tablist"
      data-testid="data-status-tabs"
    >
      <button
        type="button"
        role="tab"
        :aria-selected="tab === 'quality'"
        class="flex-1 rounded-full py-1.5 text-caption transition-colors"
        :class="tab === 'quality'
          ? 'bg-white font-semibold text-primary shadow-sm dark:bg-gray-700'
          : 'text-gray-500 dark:text-gray-400'"
        data-testid="tab-quality"
        @click="switchTab('quality')"
      >
        数据质量
      </button>
      <button
        type="button"
        role="tab"
        :aria-selected="tab === 'runs'"
        class="flex-1 rounded-full py-1.5 text-caption transition-colors"
        :class="tab === 'runs'
          ? 'bg-white font-semibold text-primary shadow-sm dark:bg-gray-700'
          : 'text-gray-500 dark:text-gray-400'"
        data-testid="tab-runs"
        @click="switchTab('runs')"
      >
        采集运行
      </button>
    </div>

    <!-- ==================== 数据质量（结果态，既有主线） ==================== -->
    <template v-if="tab === 'quality'">
      <!-- 多源冲突（Phase 3.3）：UNRESOLVED 优先展示 -->
      <section
        v-if="openConflicts.length"
        class="space-y-2"
      >
        <h2 class="text-h3 font-semibold lg:text-h3-d">
          多源数据冲突
        </h2>
        <div
          v-for="c in openConflicts"
          :key="c.id"
          class="rounded-lg bg-risk-critical/5 p-4 dark:bg-risk-critical/10"
          data-testid="conflict-row"
        >
          <div class="flex items-center justify-between">
            <span
              class="text-body font-medium num"
              data-num
            >
              {{ c.instrument_id }}
            </span>
            <span
              class="rounded-sm px-1.5 py-0.5 text-caption"
              :class="c.status === 'UNRESOLVED'
                ? 'bg-risk-critical/10 text-risk-critical'
                : 'bg-risk-warning/10 text-risk-warning'"
            >
              {{ c.status === "UNRESOLVED" ? "无法消解" : "待消解" }}
            </span>
          </div>
          <div
            class="mt-1 text-caption text-gray-500 num dark:text-gray-400"
            data-num
          >
            {{ c.business_date }} · {{ c.field }}：{{ c.source_a }}={{ formatMoney(c.value_a, 4) }} vs
            {{ c.source_b }}={{ formatMoney(c.value_b, 4) }}
          </div>
        </div>
        <p class="text-caption text-gray-400 dark:text-gray-500">
          冲突期间相关标的建议自动暂停；消解入口在 设置 → 数据源与质量（SET-02）。
        </p>
      </section>

      <div
        v-if="!qualityData?.items?.length"
        class="rounded-2xl bg-white p-6 text-center text-body text-gray-400 shadow-sm dark:bg-gray-800 dark:text-gray-500"
      >
        {{ qualityLoading ? "加载中…" : "暂无数据源记录（采集后展示）" }}
      </div>

      <div
        v-for="(e, i) in qualityData?.items ?? []"
        :key="i"
        class="flex items-center justify-between rounded-2xl bg-white p-4 shadow-sm dark:bg-gray-800"
      >
        <div>
          <div
            class="text-body font-medium num"
            data-num
          >
            {{ e.instrument_id }}
          </div>
          <div class="text-caption text-gray-400 dark:text-gray-500">
            {{ e.series === "bar" ? "日线" : "净值" }} · 来源 {{ e.source }}
          </div>
        </div>
        <div class="text-right">
          <span
            class="rounded-sm px-1.5 py-0.5 text-caption"
            :class="statusClass(e.quality_status)"
          >
            {{ STATUS_NAMES[e.quality_status] ?? e.quality_status }}
          </span>
          <div
            class="mt-1 text-caption text-gray-400 num dark:text-gray-500"
            data-num
          >
            截至 {{ e.business_date ?? e.nav_date ?? "—" }}
          </div>
        </div>
      </div>

      <!-- W2.5-5：审计日志（折叠面板） -->
      <section class="rounded-2xl bg-white p-4 shadow-sm dark:bg-gray-800">
        <button
          type="button"
          class="flex w-full items-center justify-between text-h3 font-semibold"
          data-testid="audit-toggle"
          @click="auditOpen = !auditOpen"
        >
          <span>审计日志（近 50 条）</span>
          <span class="text-caption text-gray-400">{{ auditOpen ? "收起" : "展开" }}</span>
        </button>
        <ol
          v-if="auditOpen"
          class="mt-3 space-y-1 text-caption"
          data-testid="audit-list"
        >
          <li
            v-for="e in auditRows"
            :key="e.id"
            class="flex items-baseline gap-2 border-b border-gray-50 py-1 dark:border-gray-700"
          >
            <span class="num text-gray-400">{{ e.occurred_at.slice(5, 16).replace("T", " ") }}</span>
            <span class="font-medium text-gray-600 dark:text-gray-300">{{ e.action }}</span>
            <span
              v-if="e.target_type"
              class="text-gray-400"
            >{{ e.target_type }}#{{ (e.target_id ?? "").slice(0, 8) }}</span>
          </li>
          <li
            v-if="!auditRows.length"
            class="text-gray-400"
          >
            暂无审计事件。
          </li>
        </ol>
      </section>
    </template>

    <!-- ==================== 采集运行（过程态，波2 新增） ==================== -->
    <template v-else>
      <!-- 近7日任务聚合 -->
      <section class="space-y-2">
        <h2 class="text-h3 font-semibold lg:text-h3-d">
          近 7 日任务
        </h2>
        <Skeleton
          v-if="statsLoading"
          variant="row"
          :lines="1"
        />
        <div
          v-else-if="statsData"
          class="grid grid-cols-3 gap-2"
          data-testid="jobs-stats"
        >
          <div class="rounded-2xl bg-white p-3 text-center shadow-sm dark:bg-gray-800">
            <div class="text-label text-gray-500 dark:text-gray-400">
              任务数
            </div>
            <div class="mt-1 text-h2 font-semibold num dark:text-gray-100">
              {{ formatCount(statsData.total) }}
            </div>
          </div>
          <div class="rounded-2xl bg-white p-3 text-center shadow-sm dark:bg-gray-800">
            <div class="text-label text-gray-500 dark:text-gray-400">
              成功率
            </div>
            <div class="mt-1 text-h2 font-semibold num dark:text-gray-100">
              {{ statsData.success_rate === null ? EMPTY : formatRate(statsData.success_rate) }}
            </div>
          </div>
          <div class="rounded-2xl bg-white p-3 text-center shadow-sm dark:bg-gray-800">
            <div class="text-label text-gray-500 dark:text-gray-400">
              平均耗时
            </div>
            <div class="mt-1 text-h2 font-semibold num dark:text-gray-100">
              {{ formatDuration(statsData.avg_duration_ms) }}
            </div>
          </div>
        </div>
        <p
          v-if="statsData?.consecutive_failures"
          class="text-caption text-risk-warning dark:text-risk-warning"
          data-testid="jobs-streak"
        >
          <template
            v-for="(n, jt, idx) in statsData.consecutive_failures"
            :key="jt"
          >
            {{ idx > 0 ? "；" : "" }}{{ JOB_TYPE_NAMES[jt] ?? jt }} 连续失败
            {{ formatCount(n) }} 次
          </template>
        </p>
      </section>

      <!-- 数据源健康（六类别；news 如实暴露未配置） -->
      <section class="space-y-2">
        <h2 class="text-h3 font-semibold lg:text-h3-d">
          数据源健康
        </h2>
        <Skeleton
          v-if="healthLoading"
          variant="row"
          :lines="3"
        />
        <div
          v-else
          class="space-y-2"
          data-testid="source-health-list"
        >
          <div
            v-for="s in healthRows"
            :key="s.category"
            class="flex items-center justify-between rounded-2xl bg-white p-4 shadow-sm dark:bg-gray-800"
            :data-testid="`source-health-${s.category}`"
          >
            <div class="min-w-0">
              <div class="text-body font-medium">
                {{ healthMeta(s).label }}
              </div>
              <div class="truncate text-caption text-gray-400 dark:text-gray-500">
                {{ healthMeta(s).sub }}
              </div>
            </div>
            <span
              class="ml-2 shrink-0 rounded-sm px-1.5 py-0.5 text-caption"
              :class="healthClass(s.status)"
            >
              {{ HEALTH_NAMES[s.status] ?? s.status }}
            </span>
          </div>
        </div>
      </section>

      <!-- 任务运行近况（批次 → 条目两级下钻） -->
      <section class="space-y-2">
        <h2 class="text-h3 font-semibold lg:text-h3-d">
          任务运行近况
        </h2>
        <Skeleton
          v-if="jobsLoading"
          variant="row"
          :lines="4"
        />
        <div
          v-else-if="!jobRows.length"
          class="rounded-2xl bg-white p-6 text-center text-body text-gray-400 shadow-sm dark:bg-gray-800 dark:text-gray-500"
          data-testid="jobs-empty"
        >
          暂无任务记录（定时任务 15:20 后与手动补采在此展示）。
        </div>
        <div
          v-else
          class="space-y-2"
          data-testid="job-runs-list"
        >
          <div
            v-for="j in jobRows"
            :key="j.id"
            class="rounded-2xl bg-white shadow-sm dark:bg-gray-800"
          >
            <button
              type="button"
              class="flex w-full items-center justify-between p-4 text-left"
              :data-testid="`job-run-${j.id}`"
              :aria-expanded="expandedId === j.id"
              @click="toggleJob(j.id)"
            >
              <div class="min-w-0">
                <div class="text-body font-medium">
                  {{ JOB_TYPE_NAMES[j.job_type] ?? j.job_type }}
                  <span class="ml-1 text-caption font-normal text-gray-400 num dark:text-gray-500">
                    {{ j.business_date }}
                  </span>
                </div>
                <div class="mt-0.5 truncate text-caption text-gray-400 dark:text-gray-500">
                  {{ summaryText(j) }}<template v-if="jobDurationMs(j) !== null">
                    · {{ formatDuration(jobDurationMs(j)) }}
                  </template>
                  <template v-if="j.error_code">
                    · {{ j.error_code }}
                  </template>
                </div>
              </div>
              <div class="ml-2 flex shrink-0 items-center gap-2">
                <span
                  class="rounded-sm px-1.5 py-0.5 text-caption"
                  :class="jobStatusClass(j.status)"
                >
                  {{ JOB_STATUS_NAMES[j.status] ?? j.status }}
                </span>
                <span class="text-caption text-gray-300 dark:text-gray-600">
                  {{ expandedId === j.id ? "▲" : "▼" }}
                </span>
              </div>
            </button>

            <!-- 批次条目明细 -->
            <div
              v-if="expandedId === j.id"
              class="border-t border-gray-100 p-4 dark:border-gray-700"
              :data-testid="`job-items-${j.id}`"
            >
              <div class="mb-2 flex items-center justify-between">
                <div class="flex gap-1">
                  <button
                    type="button"
                    class="rounded-full px-2.5 py-1 text-caption"
                    :class="!onlyFailed
                      ? 'bg-primary/10 font-medium text-primary'
                      : 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'"
                    @click="onlyFailed = false"
                  >
                    全部
                  </button>
                  <button
                    type="button"
                    class="rounded-full px-2.5 py-1 text-caption"
                    :class="onlyFailed
                      ? 'bg-error/10 font-medium text-error'
                      : 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'"
                    @click="onlyFailed = true"
                  >
                    仅失败
                  </button>
                </div>
                <span class="text-caption text-gray-400 dark:text-gray-500">
                  成功 {{ formatCount(j.item_counts.OK ?? null) }} · 失败
                  {{ formatCount(j.item_counts.FAILED ?? null) }} · 跳过
                  {{ formatCount(j.item_counts.SKIPPED ?? null) }}
                </span>
              </div>
              <Skeleton
                v-if="itemsLoading"
                variant="text"
                :lines="3"
              />
              <p
                v-else-if="!itemRows.length"
                class="text-caption text-gray-400 dark:text-gray-500"
              >
                该批次早于明细记录功能上线，仅有聚合计数（5_DATA §12.4）。
              </p>
              <ul
                v-else
                class="space-y-1.5"
              >
                <li
                  v-for="it in itemRows"
                  :key="it.id"
                  class="rounded-lg bg-gray-50 p-2.5 dark:bg-gray-700/50"
                  :data-testid="`ingest-item-${it.id}`"
                >
                  <div class="flex items-start justify-between gap-2">
                    <span class="min-w-0 flex-1 text-caption">
                      {{ it.display_name }}
                    </span>
                    <span
                      class="shrink-0 rounded-sm px-1.5 py-0.5 text-caption"
                      :class="itemStatusClass(it.status)"
                    >
                      {{ ITEM_STATUS_NAMES[it.status] ?? it.status }}
                    </span>
                  </div>
                  <div class="mt-1 flex flex-wrap items-center gap-x-2 text-caption text-gray-400 dark:text-gray-500">
                    <span v-if="it.rows_written !== null">采集 {{ formatCount(it.rows_written) }} 行</span>
                    <span v-if="it.source">源 {{ it.source }}</span>
                    <span v-if="it.duration_ms !== null">{{ formatDuration(it.duration_ms) }}</span>
                    <span
                      v-if="it.error_code"
                      class="text-error"
                    >{{ it.error_code }}{{ it.error_message ? `：${it.error_message}` : "" }}</span>
                    <button
                      v-if="it.status === 'FAILED' && canRefresh(it.data_ref)"
                      type="button"
                      class="ml-auto rounded-sm bg-primary/10 px-2 py-0.5 text-caption font-medium text-primary disabled:opacity-50"
                      :disabled="refreshingId !== null"
                      :data-testid="`item-refresh-${it.id}`"
                      @click="it.data_ref && onRefresh(it.id, it.data_ref)"
                    >
                      {{ refreshingId === it.id ? "补采中…" : "手动补采" }}
                    </button>
                  </div>
                </li>
              </ul>
              <p
                v-if="refreshError"
                class="mt-2 text-caption text-error"
                data-testid="refresh-error"
              >
                {{ refreshError }}
              </p>
            </div>
          </div>
        </div>
      </section>
    </template>

    <DataFooter as-of="最近采集" />
  </div>
</template>
