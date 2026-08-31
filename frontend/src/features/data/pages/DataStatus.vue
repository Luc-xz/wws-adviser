<script setup lang="ts">
// DATA-01 数据状态中心（UI §9 DataStatusBar 跳转目标）：各标的行情/净值质量与新鲜度
import { useMarketQuality } from "@/features/home/composables/queries";
import { DataFooter } from "@/shared/ui";

const { data: qualityData, isLoading: qualityLoading } = useMarketQuality();

function statusClass(s: string): string {
  if (s === "OK") return "bg-success/10 text-success";
  if (s === "DELAYED") return "bg-risk-warning/10 text-risk-warning";
  return "bg-error/10 text-error";
}
</script>

<template>
  <div class="space-y-3">
    <h1 class="text-lg font-semibold">
      数据状态
    </h1>

    <div
      v-if="!qualityData?.items?.length"
      class="rounded-xl bg-white dark:bg-gray-800 p-6 text-center text-sm text-gray-400 dark:text-gray-500 shadow-sm"
    >
      {{ qualityLoading ? "加载中…" : "暂无数据源记录（采集后展示）" }}
    </div>

    <div
      v-for="(e, i) in qualityData?.items ?? []"
      :key="i"
      class="flex items-center justify-between rounded-xl bg-white dark:bg-gray-800 p-3 shadow-sm"
    >
      <div>
        <div
          class="text-sm font-medium num"
          data-num
        >
          {{ e.instrument_id }}
        </div>
        <div class="text-xs text-gray-400 dark:text-gray-500">
          {{ e.series === "bar" ? "日线" : "净值" }} · 来源 {{ e.source }}
        </div>
      </div>
      <div class="text-right">
        <span
          class="rounded px-1.5 py-0.5 text-xs"
          :class="statusClass(e.quality_status)"
        >
          {{ e.quality_status }}
        </span>
        <div
          class="mt-1 text-xs text-gray-400 dark:text-gray-500 num"
          data-num
        >
          {{ e.business_date ?? e.nav_date ?? "—" }}
        </div>
      </div>
    </div>

    <DataFooter as-of="最近采集" />
  </div>
</template>
