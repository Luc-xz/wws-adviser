<script setup lang="ts">
// SET-02 数据源与质量（波 V4 / Phase 3.3 SET-02 消解 UI 落点）：
// 冲突列表（UNRESOLVED 优先）+ 人工选源消解（幂等）+ 采集源状态摘要。
import { computed, ref } from "vue";
import { useQuery, useQueryClient } from "@tanstack/vue-query";
import { useRouter } from "vue-router";
import client from "@/api/client";
import { formatMoney } from "@/shared/format/number";
import { PageHeader } from "@/shared/ui";

const router = useRouter();
const qc = useQueryClient();

const { data: conflictsData, isLoading } = useQuery({
  queryKey: ["market", "conflicts"],
  queryFn: async () => {
    const { data, error } = await client.GET("/api/v1/market/conflicts");
    if (error || !data) throw new Error("冲突列表获取失败");
    return data;
  },
});

const { data: qualityData } = useQuery({
  queryKey: ["market-quality"],
  queryFn: async () => {
    const { data, error } = await client.GET("/api/v1/market/quality");
    if (error || !data) throw new Error("质量获取失败");
    return data;
  },
});

const rows = computed(() => conflictsData.value?.items ?? []);
const picking = ref<string | null>(null);
const busyId = ref<string | null>(null);
const error = ref("");

async function resolve(conflictId: string, winner: string) {
  busyId.value = conflictId;
  error.value = "";
  try {
    const { error: err } = await client.POST("/api/v1/market/conflicts/{conflict_id}/resolve", {
      params: { path: { conflict_id: conflictId }, header: { "Idempotency-Key": crypto.randomUUID() } },
      body: { winner, note: "manual" },
    });
    if (err) throw new Error("消解失败");
    picking.value = null;
    await qc.invalidateQueries({ queryKey: ["market", "conflicts"] });
  } catch (e) {
    error.value = e instanceof Error ? e.message : "消解失败";
  } finally {
    busyId.value = null;
  }
}
</script>

<template>
  <div class="space-y-6">
    <PageHeader
      title="数据源与质量"
      subtitle="多源冲突消解（SET-02）· 采集源质量一览"
      back
      @back="router.back()"
    />

    <!-- 冲突消解（Phase 3.3 落点） -->
    <section class="space-y-2">
      <h2 class="text-h3 font-semibold lg:text-h3-d">
        多源冲突
      </h2>
      <p
        v-if="isLoading"
        class="text-caption text-gray-400"
      >
        加载中…
      </p>
      <div
        v-else-if="!rows.length"
        class="rounded-2xl bg-white p-6 text-center text-body text-gray-400 shadow-sm dark:bg-gray-800 dark:text-gray-500"
        data-testid="conflicts-empty"
      >
        暂无冲突——多源比对未发现超容差差异。
      </div>
      <div
        v-for="c in rows"
        :key="c.id"
        class="rounded-2xl bg-white p-4 shadow-sm dark:bg-gray-800"
        data-testid="conflict-admin-row"
      >
        <div class="flex items-center justify-between">
          <span
            class="text-body font-medium num"
            data-num
          >{{ c.instrument_id }}</span>
          <span
            class="rounded-sm px-1.5 py-0.5 text-caption"
            :class="c.status === 'RESOLVED' ? 'bg-success/10 text-success' : 'bg-risk-warning/10 text-risk-warning'"
          >
            {{ c.status === "RESOLVED" ? "已消解" : c.status === "UNRESOLVED" ? "无法消解" : "待消解" }}
          </span>
        </div>
        <div
          class="mt-1 text-caption text-gray-500 num dark:text-gray-400"
          data-num
        >
          {{ c.business_date }} · {{ c.field }} · {{ c.source_a }}={{ formatMoney(c.value_a, 4) }} vs
          {{ c.source_b }}={{ formatMoney(c.value_b, 4) }}
        </div>
        <div
          v-if="c.status === 'RESOLVED' && c.resolved_by"
          class="mt-1 text-caption text-gray-400 dark:text-gray-500"
        >
          消解：{{ c.resolved_by }}{{ c.resolved_at ? ` · ${c.resolved_at.slice(0, 10)}` : "" }}
        </div>
        <div
          v-if="c.status !== 'RESOLVED' && picking !== c.id"
          class="mt-2"
        >
          <button
            type="button"
            class="appearance-none rounded-md border border-primary px-3 py-1.5 text-label font-medium text-primary"
            :data-testid="`conflict-pick-${c.id}`"
            @click="picking = c.id"
          >
            消解此冲突
          </button>
        </div>
        <div
          v-if="picking === c.id"
          class="mt-2 flex flex-wrap items-center gap-2"
        >
          <button
            v-for="src in [c.source_a, c.source_b]"
            :key="src"
            type="button"
            class="appearance-none rounded-md border border-primary px-3 py-1.5 text-label text-primary disabled:opacity-40"
            :disabled="busyId === c.id"
            :data-testid="`resolve-${src}`"
            @click="resolve(c.id, src)"
          >
            采用 {{ src }}（{{ formatMoney(src === c.source_a ? c.value_a : c.value_b, 4) }})
          </button>
          <button
            type="button"
            class="appearance-none rounded-md px-2 py-1.5 text-label text-gray-400"
            @click="picking = null"
          >
            取消
          </button>
        </div>
      </div>
      <p
        v-if="error"
        class="text-caption text-error"
      >
        {{ error }}
      </p>
    </section>

    <!-- 采集源质量 -->
    <section class="space-y-2">
      <h2 class="text-h3 font-semibold lg:text-h3-d">
        标的数据质量
      </h2>
      <div
        v-for="(e, i) in qualityData?.items ?? []"
        :key="i"
        class="flex items-center justify-between rounded-2xl bg-white p-3 shadow-sm dark:bg-gray-800"
      >
        <span
          class="text-body num"
          data-num
        >{{ e.instrument_id }} · {{ e.series === "bar" ? "日线" : "净值" }}</span>
        <span
          class="text-caption text-gray-500 num dark:text-gray-400"
          data-num
        >
          {{ e.quality_status }} · {{ e.business_date ?? e.nav_date ?? "—" }}
        </span>
      </div>
    </section>
  </div>
</template>
