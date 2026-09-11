<script setup lang="ts">
// DATA-01 数据状态中心（UI §9 DataStatusBar 跳转目标 / 基准卡 baseline/DATA-01-card.md）：
// 各标的行情/净值质量与新鲜度 + 多源冲突（Phase 3.3 data_conflicts）。
// 消解操作在 SET-02（波 V4 落地），本页展示 + 引导。
import { useQuery } from "@tanstack/vue-query";
import { useRouter } from "vue-router";
import client from "@/api/client";
import { useMarketQuality } from "@/features/home/composables/queries";
import { formatMoney } from "@/shared/format/number";
import { DataFooter, PageHeader } from "@/shared/ui";

const router = useRouter();
const { data: qualityData, isLoading: qualityLoading } = useMarketQuality();

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
</script>

<template>
  <div class="space-y-6">
    <PageHeader
      title="数据状态"
      subtitle="行情 / 净值质量与新鲜度 · 多源交叉验证结果"
      back
      @back="router.back()"
    />

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
      class="rounded-lg bg-white p-6 text-center text-body text-gray-400 shadow-sm dark:bg-gray-800 dark:text-gray-500"
    >
      {{ qualityLoading ? "加载中…" : "暂无数据源记录（采集后展示）" }}
    </div>

    <div
      v-for="(e, i) in qualityData?.items ?? []"
      :key="i"
      class="flex items-center justify-between rounded-lg bg-white p-4 shadow-sm dark:bg-gray-800"
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

    <DataFooter as-of="最近采集" />
  </div>
</template>
