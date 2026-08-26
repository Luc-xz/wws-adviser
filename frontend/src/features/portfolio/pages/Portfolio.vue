<script setup lang="ts">
// PORT-01 持仓页（UI §10.6）：持仓 | 流水 | 自选 三 Tab。
// 持仓=摘要条+风险前置持仓卡+累计已实现盈亏趋势（/positions/history 按日聚合）；
// 流水=交易列表（keyset 首页）；自选=watchlist 增删+快照价（技术债清理：波7 留白）。
import { computed, ref } from "vue";
import { formatMoney, formatPercent } from "@/shared/format/number";
import { DataFooter, PositionRow, TrendChart } from "@/shared/ui";
import { usePositions, useRisk } from "@/features/home/composables/queries";
import {
  useInstrumentMap,
  usePositionsHistory,
  useSaveWatchlist,
  useTransactions,
  useWatchQuotes,
  useWatchlist,
} from "../composables/queries";

type Tab = "positions" | "transactions" | "watchlist";
const activeTab = ref<Tab>("positions");
const tabs: { key: Tab; label: string }[] = [
  { key: "positions", label: "持仓" },
  { key: "transactions", label: "流水" },
  { key: "watchlist", label: "自选" },
];

// —— 持仓 ——
const { data: positionsData, isSuccess: positionsOk } = usePositions();
const { data: riskData } = useRisk();

const hardHitCodes = computed(
  () =>
    new Set(
      (riskData.value?.breaches ?? [])
        .filter((b) => b.level === "hard" && b.code)
        .map((b) => b.code)
    )
);

const sorted = computed(() => {
  const items = positionsData.value?.items ?? [];
  const w = (p: { weight?: string | null }) => (p.weight ? Number(p.weight) : -1);
  return [...items].sort(
    (a, b) =>
      Number(hardHitCodes.value.has(b.code)) - Number(hardHitCodes.value.has(a.code)) ||
      w(b) - w(a)
  );
});

const summaryStrip = computed(() => {
  const d = positionsData.value;
  if (!d) return null;
  const mv = (d.items ?? []).reduce(
    (acc, p) => acc + (p.market_value ? Number(p.market_value) : 0),
    0
  );
  return {
    marketValue: formatMoney(mv.toFixed(2)),
    cash: formatMoney(d.cash),
    count: d.items?.length ?? 0,
  };
});

function recordTrade() {
  // TODO(后续波次): 手工录入表单/CSV 导入 UI（后端 /transactions 已就绪）
}

// 趋势：各标的 realized_pnl 快照按日求和（组合累计已实现盈亏，近 30 个快照日）
const { data: historyData } = usePositionsHistory();
const trend = computed(() => {
  const items = historyData.value?.items ?? [];
  if (!items.length) return null;
  const byDate = new Map<string, number>();
  for (const it of items) {
    byDate.set(it.business_date, (byDate.get(it.business_date) ?? 0) + Number(it.realized_pnl));
  }
  const dates = [...byDate.keys()].sort().slice(-30);
  if (!dates.length) return null;
  return {
    dates,
    values: dates.map((d) => Math.round((byDate.get(d) ?? 0) * 100) / 100),
  };
});

// —— 流水 ——
const { data: txData, isSuccess: txOk } = useTransactions();
const { data: instrumentMap } = useInstrumentMap();

function instLabel(instrumentId: string): string {
  const inst = instrumentMap.value?.get(instrumentId);
  return inst ? `${inst.name} ${inst.code}` : instrumentId.slice(0, 8);
}

const txRows = computed(() =>
  (txData.value?.items ?? []).map((t) => ({
    id: t.id,
    tradeAt: t.trade_at.slice(0, 10),
    isBuy: t.direction === "BUY",
    kind: t.kind,
    inst: instLabel(t.instrument_id),
    quantity: formatMoney(t.quantity, 2),
    price: formatMoney(t.price, 2),
    fee: formatMoney((Number(t.fee) + Number(t.tax)).toFixed(2)),
  }))
);

// —— 自选 ——
const { data: watchCodes, isSuccess: watchOk } = useWatchlist();
const watchCodesRef = computed(() => watchCodes.value ?? []);
const { data: quotes } = useWatchQuotes(watchCodesRef);
const saveWatchlist = useSaveWatchlist();
const newCode = ref("");
const watchError = ref("");

function watchLabel(code: string): string {
  return instrumentMap.value?.get(code)?.name || code;
}

function watchQuote(code: string): { price: string | null; changePct: string | null } | undefined {
  return quotes.value?.find((q) => q.code === code);
}

function addWatch() {
  const code = newCode.value.trim();
  watchError.value = "";
  if (!/^\d{6}$/.test(code)) {
    watchError.value = "请输入 6 位数字代码";
    return;
  }
  if (watchCodesRef.value.includes(code)) {
    watchError.value = "已在自选中";
    return;
  }
  saveWatchlist.mutate([...watchCodesRef.value, code], {
    onError: () => (watchError.value = "保存失败，请重试"),
  });
  newCode.value = "";
}

function removeWatch(code: string) {
  saveWatchlist.mutate(watchCodesRef.value.filter((c) => c !== code));
}
</script>

<template>
  <div class="space-y-3">
    <div class="flex items-center justify-between">
      <h1 class="text-lg font-semibold">
        持仓
      </h1>
      <button
        v-if="activeTab === 'positions'"
        type="button"
        class="rounded-lg bg-primary px-3 py-2 text-sm font-medium text-white"
        data-testid="record-trade"
        @click="recordTrade"
      >
        记录交易
      </button>
    </div>

    <!-- Tab 栏 -->
    <div
      class="flex rounded-xl bg-white p-1 shadow-sm dark:bg-gray-800"
      role="tablist"
    >
      <button
        v-for="t in tabs"
        :key="t.key"
        type="button"
        role="tab"
        class="flex-1 rounded-lg py-2 text-sm font-medium transition-colors"
        :class="
          activeTab === t.key
            ? 'bg-primary text-white'
            : 'text-gray-600 dark:text-gray-300'
        "
        :data-testid="`tab-${t.key}`"
        :aria-selected="activeTab === t.key"
        @click="activeTab = t.key"
      >
        {{ t.label }}
      </button>
    </div>

    <!-- ===== 持仓 Tab ===== -->
    <template v-if="activeTab === 'positions'">
      <!-- 空态引导 -->
      <div
        v-if="positionsOk && !positionsData?.items?.length"
        class="rounded-xl bg-white p-6 text-center shadow-sm dark:bg-gray-800"
        data-testid="empty-guide"
      >
        <p class="font-medium">
          暂无持仓
        </p>
        <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">
          记录第一笔交易后即可查看持仓与成本。
        </p>
      </div>

      <template v-else>
        <!-- 摘要条 -->
        <div
          v-if="summaryStrip"
          class="grid grid-cols-3 gap-2 text-center"
        >
          <div class="rounded-xl bg-white p-3 shadow-sm dark:bg-gray-800">
            <div class="text-xs text-gray-500 dark:text-gray-400">
              持仓市值
            </div>
            <div
              class="mt-1 font-semibold num"
              data-num
            >
              {{ summaryStrip.marketValue }}
            </div>
          </div>
          <div class="rounded-xl bg-white p-3 shadow-sm dark:bg-gray-800">
            <div class="text-xs text-gray-500 dark:text-gray-400">
              现金
            </div>
            <div
              class="mt-1 font-semibold num"
              data-num
            >
              {{ summaryStrip.cash }}
            </div>
          </div>
          <div class="rounded-xl bg-white p-3 shadow-sm dark:bg-gray-800">
            <div class="text-xs text-gray-500 dark:text-gray-400">
              持仓数
            </div>
            <div
              class="mt-1 font-semibold num"
              data-num
            >
              {{ summaryStrip.count }}
            </div>
          </div>
        </div>

        <!-- 累计已实现盈亏趋势 -->
        <div
          v-if="trend"
          class="rounded-xl bg-white p-3 shadow-sm dark:bg-gray-800"
          data-testid="realized-trend"
        >
          <div class="mb-1 flex items-baseline justify-between">
            <span class="text-sm font-medium">累计已实现盈亏</span>
            <span class="text-xs text-gray-500 dark:text-gray-400">近 {{ trend.dates.length }} 个快照日</span>
          </div>
          <TrendChart
            :dates="trend.dates"
            :values="trend.values"
            label="累计已实现盈亏"
          />
        </div>

        <DataFooter as-of="最新估值" />

        <!-- 持仓卡片（hard 风险前置标注） -->
        <div class="space-y-2">
          <div
            v-for="p in sorted"
            :key="p.instrument_id"
            class="relative"
          >
            <span
              v-if="hardHitCodes.has(p.code)"
              class="absolute right-2 top-2 z-1 rounded bg-risk-critical px-1.5 py-0.5 text-xs text-white"
            >
              风险
            </span>
            <PositionRow
              :code="p.code"
              :name="p.name"
              :quantity="p.quantity"
              :avg-cost="p.avg_cost"
              :market-value="p.market_value"
              :weight="p.weight"
              :freshness="p.freshness"
            />
          </div>
        </div>
        <p class="text-center text-xs text-gray-400 dark:text-gray-500">
          排序：风险优先 · 权重从高到低
        </p>
      </template>
    </template>

    <!-- ===== 流水 Tab ===== -->
    <template v-else-if="activeTab === 'transactions'">
      <div
        v-if="txOk && !txRows.length"
        class="rounded-xl bg-white p-6 text-center shadow-sm dark:bg-gray-800"
        data-testid="tx-empty"
      >
        <p class="font-medium">
          暂无交易流水
        </p>
        <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">
          通过 API 或导入记录的交易会显示在这里。
        </p>
      </div>
      <div
        v-else
        class="divide-y divide-gray-100 overflow-hidden rounded-xl bg-white shadow-sm dark:divide-gray-700 dark:bg-gray-800"
        data-testid="tx-list"
      >
        <div
          v-for="t in txRows"
          :key="t.id"
          class="flex items-center justify-between px-4 py-3"
        >
          <div class="min-w-0">
            <div class="flex items-center gap-2">
              <span
                class="rounded px-1.5 py-0.5 text-xs font-medium"
                :class="
                  t.isBuy
                    ? 'bg-primary/10 text-primary'
                    : 'bg-action-reduce/10 text-action-reduce'
                "
              >
                {{ t.isBuy ? "买入" : "卖出" }}
              </span>
              <span class="truncate text-sm font-medium">{{ t.inst }}</span>
            </div>
            <div
              class="mt-1 text-xs text-gray-500 dark:text-gray-400 num"
              data-num
            >
              {{ t.tradeAt }} · 数量 {{ t.quantity }} @ {{ t.price }} · 费税 {{ t.fee }}
            </div>
          </div>
        </div>
      </div>
      <p class="text-center text-xs text-gray-400 dark:text-gray-500">
        最新 50 条 · 更多历史经 API 分页获取
      </p>
    </template>

    <!-- ===== 自选 Tab ===== -->
    <template v-else>
      <!-- 新增 -->
      <div class="rounded-xl bg-white p-4 shadow-sm dark:bg-gray-800">
        <form
          class="flex gap-2"
          @submit.prevent="addWatch"
        >
          <input
            v-model="newCode"
            inputmode="numeric"
            maxlength="6"
            placeholder="输入 6 位代码，如 600519"
            class="min-w-0 flex-1 rounded-lg border border-gray-200 bg-transparent px-3 py-2 text-sm outline-none focus:border-primary dark:border-gray-700"
            data-testid="watch-input"
          >
          <button
            type="submit"
            class="rounded-lg bg-primary px-3 py-2 text-sm font-medium text-white"
            data-testid="watch-add"
          >
            添加
          </button>
        </form>
        <p
          v-if="watchError"
          class="mt-2 text-xs text-error"
          data-testid="watch-error"
        >
          {{ watchError }}
        </p>
      </div>

      <div
        v-if="watchOk && !watchCodesRef.length"
        class="rounded-xl bg-white p-6 text-center shadow-sm dark:bg-gray-800"
        data-testid="watch-empty"
      >
        <p class="font-medium">
          自选为空
        </p>
        <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">
          添加关注的标的，快速查看最新价。
        </p>
      </div>
      <div
        v-else
        class="divide-y divide-gray-100 overflow-hidden rounded-xl bg-white shadow-sm dark:divide-gray-700 dark:bg-gray-800"
        data-testid="watch-list"
      >
        <div
          v-for="w in watchCodesRef"
          :key="w"
          class="flex items-center justify-between px-4 py-3"
        >
          <div class="min-w-0">
            <div class="truncate text-sm font-medium">
              {{ watchLabel(w) }}
            </div>
            <div
              class="mt-0.5 text-xs text-gray-500 dark:text-gray-400 num"
              data-num
            >
              {{ w }} · {{ watchQuote(w)?.price ?? "—" }}
              <template v-if="watchQuote(w)?.changePct">
                （{{ formatPercent(watchQuote(w)?.changePct) }}%）
              </template>
            </div>
          </div>
          <button
            type="button"
            class="shrink-0 rounded px-2 py-1 text-xs text-gray-500 hover:text-error dark:text-gray-400"
            :data-testid="`watch-remove-${w}`"
            @click="removeWatch(w)"
          >
            移除
          </button>
        </div>
      </div>
      <p class="text-center text-xs text-gray-400 dark:text-gray-500">
        行情为最近一次快照，非实时报价
      </p>
    </template>
  </div>
</template>
