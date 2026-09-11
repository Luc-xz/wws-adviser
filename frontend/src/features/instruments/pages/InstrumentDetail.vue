<script setup lang="ts">
// PORT-02 标的/持仓详情（波 V4）：基本信息 + 日线 TrendChart + 持仓明细（若持有）
// + 相关公告（documents）。后端 bars/documents/positions 全就绪。
import { computed, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useQuery, useQueryClient } from "@tanstack/vue-query";
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

// 信号覆盖透视（W2-5 / Q1 决策）：当日是否触发 + 校准状态 + 人话注解
const instCode = computed(() => inst.value?.code ?? "");
const { data: coverage } = useQuery({
  queryKey: ["signal-coverage", instCode.value],
  enabled: computed(() => instCode.value.length > 0),
  queryFn: async () => {
    const { data, error } = await client.GET(
      "/api/v1/assistant/coverage/{code}",
      { params: { path: { code: instCode.value } } },
    );
    if (error || !data) throw new Error("信号覆盖获取失败");
    return data;
  },
});

// 加入/移出自选（W2.5-4；PUT 整体替换语义，CSRF 由 client 中间件注入）
const qc = useQueryClient();
const { data: watchlist } = useQuery({
  queryKey: ["watchlist"],
  queryFn: async () => {
    const { data } = await client.GET("/api/v1/settings/watchlist");
    return data?.codes ?? [];
  },
});
const inWatchlist = computed(() => watchlist.value?.includes(instCode.value));
const watchBusy = ref(false);
async function toggleWatch() {
  if (!instCode.value || watchBusy.value) return;
  watchBusy.value = true;
  try {
    const cur = watchlist.value ?? [];
    const next = inWatchlist.value
      ? cur.filter((c) => c !== instCode.value)
      : [...cur, instCode.value];
    const { error } = await client.PUT("/api/v1/settings/watchlist", {
      body: { codes: next },
    });
    if (error) throw new Error("自选更新失败");
    await qc.invalidateQueries({ queryKey: ["watchlist"] });
  } finally {
    watchBusy.value = false;
  }
}
</script>

<template>
  <div class="space-y-6">
    <PageHeader
      :title="inst ? `${inst.name} ${inst.code}` : '标的详情'"
      :subtitle="inst ? `${inst.market} · ${inst.kind} · 价格精度 ${inst.price_scale}` : ''"
      back
      @back="router.back()"
    >
      <template #actions>
        <button
          v-if="instCode"
          type="button"
          class="rounded-md border px-2.5 py-1 text-caption font-medium"
          :class="inWatchlist
            ? 'border-success text-success'
            : 'border-primary text-primary hover:bg-primary/5'"
          :disabled="watchBusy"
          data-testid="watch-toggle"
          @click="toggleWatch"
        >
          {{ watchBusy ? "…" : inWatchlist ? "✓ 已自选" : "+ 加入自选" }}
        </button>
      </template>
    </PageHeader>

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

    <!-- 信号覆盖（W2-5）：解释为什么没有正向建议 -->
    <section
      v-if="coverage"
      class="space-y-2 rounded-lg bg-white p-4 shadow-sm dark:bg-gray-800"
      data-testid="signal-coverage"
    >
      <h2 class="text-h3 font-semibold">
        盘中建议状态
      </h2>
      <dl class="grid grid-cols-2 gap-2 text-body">
        <div>
          <dt class="text-caption text-gray-400 dark:text-gray-500">
            当日信号触发
          </dt>
          <dd class="mt-0.5 font-medium">
            {{ coverage.signal_triggered_today ? "是" : "否" }}
            <span
              v-if="coverage.signal_id"
              class="ml-1 text-caption text-gray-400"
            >（{{ coverage.signal_id }}）</span>
          </dd>
        </div>
        <div>
          <dt class="text-caption text-gray-400 dark:text-gray-500">
            校准状态
          </dt>
          <dd class="mt-0.5 font-medium">
            {{ coverage.calibration_state ?? "无信号在校准中" }}
            <span
              v-if="coverage.calibration_expires_on"
              class="ml-1 text-caption text-gray-400"
            >（有效期至 {{ coverage.calibration_expires_on }}）</span>
          </dd>
        </div>
      </dl>
      <p class="text-caption text-gray-500 dark:text-gray-400">
        {{ coverage.note }}
      </p>
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
