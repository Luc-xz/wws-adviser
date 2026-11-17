<script setup lang="ts">
// SET-08 系统状态（波 V4）：/health/live+ready+dependencies 概览。
// W4 采集监控面板：任务近况改由 GET /jobs/stats 真数据（原"runtime_stats 后续补全"注释兑现）。
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { useJobStats } from "@/features/data/composables/queries";
import { formatCount, formatDuration, formatRate, EMPTY } from "@/shared/format/number";
import { PageHeader } from "@/shared/ui";

const router = useRouter();

interface DepItem {
  name: string;
  status?: string;
  [k: string]: unknown;
}

const live = ref<"…" | "ok" | "fail">("…");
const ready = ref<"…" | "ok" | "fail">("…");
const deps = ref<DepItem[]>([]);
const loading = ref(true);

async function probe(path: string): Promise<boolean> {
  try {
    const r = await fetch(path);
    return r.ok;
  } catch {
    return false;
  }
}

onMounted(async () => {
  const [l, r] = await Promise.all([probe("/health/live"), probe("/health/ready")]);
  live.value = l ? "ok" : "fail";
  ready.value = r ? "ok" : "fail";
  try {
    const res = await fetch("/health/dependencies");
    if (res.ok) {
      const data = (await res.json()) as Record<string, unknown>;
      deps.value = Object.entries(data).map(([name, v]) => ({
        name,
        status: typeof v === "object" && v !== null ? String((v as Record<string, unknown>).status ?? "—") : String(v),
        detail: v,
      }));
    }
  } catch {
    /* 依赖健康不可达不阻塞本页 */
  }
  loading.value = false;
});

function badge(s: "…" | "ok" | "fail"): string {
  return s === "ok" ? "bg-success/10 text-success" : s === "fail" ? "bg-error/10 text-error" : "bg-gray-100 text-gray-400 dark:bg-gray-700";
}

// 任务近况（近 7 日聚合；DATA-01「采集运行」同一数据源）
const { data: jobStats, isLoading: jobStatsLoading } = useJobStats(7);

const JOB_TYPE_NAMES: Record<string, string> = {
  pre_market: "开市前报告",
  post_market: "收市后报告",
  data_maintenance: "数据维护",
  calibration_scan: "校准扫描",
  advice_review: "建议评价",
  ingest_manual: "手动补采",
  backup: "备份",
  market_env_intraday: "市场环境采集（盘中）",
  market_env_eod: "市场环境采集（日终）",
  overseas_morning: "外围市场采集（晨间）",
};
</script>

<template>
  <div class="space-y-6">
    <PageHeader
      title="系统状态"
      subtitle="进程存活 / 就绪 / 数据源与模型依赖"
      back
      @back="router.back()"
    />

    <div class="grid grid-cols-2 gap-2">
      <div class="rounded-2xl bg-white p-4 shadow-sm dark:bg-gray-800">
        <div class="text-label text-gray-500 dark:text-gray-400">
          存活（live）
        </div>
        <span
          class="mt-1 inline-block rounded-sm px-1.5 py-0.5 text-caption"
          :class="badge(live)"
        >{{ live === "ok" ? "正常" : live === "fail" ? "异常" : "检测中" }}</span>
      </div>
      <div class="rounded-2xl bg-white p-4 shadow-sm dark:bg-gray-800">
        <div class="text-label text-gray-500 dark:text-gray-400">
          就绪（ready）
        </div>
        <span
          class="mt-1 inline-block rounded-sm px-1.5 py-0.5 text-caption"
          :class="badge(ready)"
        >{{ ready === "ok" ? "正常" : ready === "fail" ? "异常（DB/迁移）" : "检测中" }}</span>
      </div>
    </div>

    <section class="space-y-2">
      <h2 class="text-h3 font-semibold lg:text-h3-d">
        依赖健康
      </h2>
      <p
        v-if="loading"
        class="text-caption text-gray-400"
      >
        检测中…
      </p>
      <div
        v-else-if="!deps.length"
        class="rounded-2xl bg-white p-6 text-center text-body text-gray-400 shadow-sm dark:bg-gray-800 dark:text-gray-500"
      >
        依赖详情不可用（仅登录用户可见）。
      </div>
      <div
        v-for="d in deps"
        :key="d.name"
        class="flex items-center justify-between rounded-2xl bg-white p-3 shadow-sm dark:bg-gray-800"
      >
        <span class="text-body font-medium">{{ d.name }}</span>
        <span class="text-caption text-gray-500 dark:text-gray-400">{{ d.status ?? "—" }}</span>
      </div>
    </section>

    <!-- 任务近况（近 7 日；W4 采集监控面板，技术架构 §16.3 轻量统计落地） -->
    <section class="space-y-2">
      <h2 class="text-h3 font-semibold lg:text-h3-d">
        任务近况（近 7 日）
      </h2>
      <p
        v-if="jobStatsLoading"
        class="text-caption text-gray-400"
      >
        统计中…
      </p>
      <template v-else-if="jobStats">
        <div
          class="grid grid-cols-3 gap-2"
          data-testid="system-job-stats"
        >
          <div class="rounded-2xl bg-white p-3 text-center shadow-sm dark:bg-gray-800">
            <div class="text-label text-gray-500 dark:text-gray-400">
              任务数
            </div>
            <div class="mt-1 text-h2 font-semibold num dark:text-gray-100">
              {{ formatCount(jobStats.total) }}
            </div>
          </div>
          <div class="rounded-2xl bg-white p-3 text-center shadow-sm dark:bg-gray-800">
            <div class="text-label text-gray-500 dark:text-gray-400">
              成功率
            </div>
            <div class="mt-1 text-h2 font-semibold num dark:text-gray-100">
              {{ jobStats.success_rate === null ? EMPTY : formatRate(jobStats.success_rate) }}
            </div>
          </div>
          <div class="rounded-2xl bg-white p-3 text-center shadow-sm dark:bg-gray-800">
            <div class="text-label text-gray-500 dark:text-gray-400">
              平均耗时
            </div>
            <div class="mt-1 text-h2 font-semibold num dark:text-gray-100">
              {{ formatDuration(jobStats.avg_duration_ms) }}
            </div>
          </div>
        </div>
        <p
          v-if="Object.keys(jobStats.consecutive_failures).length"
          class="text-caption text-risk-warning"
        >
          <template
            v-for="(n, jt, idx) in jobStats.consecutive_failures"
            :key="jt"
          >
            {{ idx > 0 ? "；" : "" }}{{ JOB_TYPE_NAMES[jt] ?? jt }} 连续失败
            {{ formatCount(n) }} 次
          </template>
        </p>
        <p
          v-else-if="!jobStats.total"
          class="text-caption text-gray-400 dark:text-gray-500"
        >
          暂无任务记录。
        </p>
      </template>
      <p
        v-else
        class="text-caption text-gray-400 dark:text-gray-500"
      >
        任务统计不可用（需登录）。
      </p>
      <!-- 入口（W4 增补）：SET-08 只有汇总，批次/条目下钻在 DATA-01「采集运行」 -->
      <router-link
        to="/data-status?tab=runs"
        class="flex items-center justify-between rounded-2xl bg-white p-4 shadow-sm dark:bg-gray-800"
        data-testid="system-collections-link"
      >
        <span class="text-body font-medium">任务批次与采集条目明细</span>
        <span class="text-caption text-gray-400">数据状态 · 采集运行 ›</span>
      </router-link>
    </section>
  </div>
</template>
