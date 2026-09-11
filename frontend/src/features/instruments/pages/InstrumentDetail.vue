<script setup lang="ts">
// PORT-02 标的/持仓详情（波 V4）：基本信息 + 日线 TrendChart + 持仓明细（若持有）
// + 相关公告（documents）。后端 bars/documents/positions 全就绪。
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useQuery } from "@tanstack/vue-query";
import client from "@/api/client";
import { EMPTY, formatMoney, formatPercent } from "@/shared/format/number";
import { DataFooter, PageHeader, TrendChart } from "@/shared/ui";

const route = useRoute();
const router = useRouter();
const instrumentId = computed(() => String(route.params.id ?? ""));

const { data: inst } = useQuery({
  queryKey: ["instrument", instrumentId.value],
  queryFn: async () => {
    const { data, error } = await client.GET("/api/v1/instruments/{instrument_id}", {
      params: { path: { instrument_id: instrumentId.value } },
    });
    if (error || !data) throw new Error("标的信息获取失败");
    return data;
  },
});

const { data: bars } = useQuery({
  queryKey: ["instrument-bars", instrumentId.value],
  queryFn: async () => {
    const { data, error } = await client.GET("/api/v1/market/bars/{instrument_id}", {
      params: { path: { instrument_id: instrumentId.value } },
    });
    if (error || !data) throw new Error("日线获取失败");
    return data;
  },
});

const trend = computed(() => {
  const items = ((bars.value as { items?: { business_date: string; close: string }[] })?.items ?? []).slice();
  if (!items.length) return null;
  const dates = items.map((b) => b.business_date);
  const values = items.map((b) => Number(b.close));
  return { dates, values };
});

const lastClose = computed(() => {
  const items = ((bars.value as { items?: { close: string }[] })?.items ?? []);
  return items.length ? items[items.length - 1].close : null;
});

const { data: positions } = useQuery({
  queryKey: ["positions"],
  queryFn: async () => {
    const { data, error } = await client.GET("/api/v1/positions");
    if (error || !data) throw new Error("持仓获取失败");
    return data;
  },
});

const holding = computed(() =>
  (positions.value?.items ?? []).find((p) => p.instrument_id === instrumentId.value)
);

const { data: docs } = useQuery({
  queryKey: ["instrument-docs", instrumentId.value],
  queryFn: async () => {
    const { data, error } = await client.GET("/api/v1/documents", {
      params: { query: { instrument_id: instrumentId.value, limit: 10 } },
    });
    if (error || !data) throw new Error("公告获取失败");
    return data;
  },
});

function docTitle(d: { title?: string }): string {
  return d.title ?? "（无标题）";
}
</script>

<template>
  <div class="space-y-6">
    <PageHeader
      :title="inst ? `${inst.name} ${inst.code}` : '标的详情'"
      :subtitle="inst ? `${inst.market} · ${inst.kind} · 价格精度 ${inst.price_scale}` : ''"
      back
      @back="router.back()"
    />

    <!-- 行情 -->
    <section class="rounded-lg bg-white p-4 shadow-sm dark:bg-gray-800">
      <div class="flex items-baseline justify-between">
        <h2 class="text-h3 font-semibold">
          日线收盘
        </h2>
        <span
          v-if="lastClose"
          class="text-h3 font-semibold num"
          data-num
        >{{ formatMoney(lastClose) }}</span>
        <span
          v-else
          class="text-h3 num"
        >{{ EMPTY }}</span>
      </div>
      <TrendChart
        v-if="trend"
        class="mt-2"
        :dates="trend.dates"
        :values="trend.values"
        label="收盘价"
      />
      <p
        v-else
        class="mt-2 text-caption text-gray-400 dark:text-gray-500"
      >
        暂无日线（采集后展示）。
      </p>
      <DataFooter as-of="最近采集" />
    </section>

    <!-- 持仓明细（若持有） -->
    <section
      v-if="holding"
      class="rounded-lg bg-white p-4 shadow-sm dark:bg-gray-800"
    >
      <h2 class="text-h3 font-semibold">
        我的持仓
      </h2>
      <dl class="mt-2 grid grid-cols-2 gap-3 text-body sm:grid-cols-4">
        <div>
          <dt class="text-caption text-gray-400 dark:text-gray-500">
            数量
          </dt>
          <dd
            class="mt-0.5 font-medium num"
            data-num
          >
            {{ formatMoney(holding.quantity, 2) }}
          </dd>
        </div>
        <div>
          <dt class="text-caption text-gray-400 dark:text-gray-500">
            成本
          </dt>
          <dd
            class="mt-0.5 font-medium num"
            data-num
          >
            {{ formatMoney(holding.avg_cost) }}
          </dd>
        </div>
        <div>
          <dt class="text-caption text-gray-400 dark:text-gray-500">
            市值
          </dt>
          <dd
            class="mt-0.5 font-medium num"
            data-num
          >
            {{ formatMoney(holding.market_value) }}
          </dd>
        </div>
        <div>
          <dt class="text-caption text-gray-400 dark:text-gray-500">
            权重
          </dt>
          <dd
            class="mt-0.5 font-medium num"
            data-num
          >
            {{ holding.weight ? formatPercent(holding.weight) : EMPTY }}
          </dd>
        </div>
      </dl>
    </section>

    <!-- 相关公告 -->
    <section class="space-y-2">
      <h2 class="text-h3 font-semibold lg:text-h3-d">
        相关公告与文档
      </h2>
      <div
        v-if="!(docs?.items?.length)"
        class="rounded-lg bg-white p-6 text-center text-body text-gray-400 shadow-sm dark:bg-gray-800 dark:text-gray-500"
      >
        暂无相关文档。
      </div>
      <router-link
        v-for="d in docs?.items ?? []"
        :key="d.id"
        to="#"
        class="block rounded-lg bg-white p-4 shadow-sm dark:bg-gray-800"
        @click.prevent
      >
        <div class="flex items-center justify-between gap-2">
          <span class="truncate text-body font-medium">{{ docTitle(d) }}</span>
          <span
            class="shrink-0 text-caption text-gray-400 num dark:text-gray-500"
            data-num
          >
            {{ d.published_at?.slice(0, 10) ?? "—" }}
          </span>
        </div>
        <div class="mt-0.5 text-caption text-gray-400 dark:text-gray-500">
          {{ d.kind }} · 来源 {{ d.source }}
        </div>
      </router-link>
    </section>
  </div>
</template>
