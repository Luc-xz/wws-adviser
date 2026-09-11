<script setup lang="ts">
// HOME-02 今日行动与风险（UI §10.4）：承接首页「查看全部」。
// 今日行动 Tab = 建议记录列表（有效期内在前、更早折叠历史）；风险 Tab = 硬限制
// 前置的风险明细（analytics/risk breaches，Critical 置顶）。不提供批量执行。
import { computed, ref, watch } from "vue";
import { PageHeader, RiskAlert } from "@/shared/ui";
import { EMPTY } from "@/shared/format/number";
import { ACTION_META, reasonText } from "../meta";
import {
  fetchAdviceRecords,
  type AdviceRecord,
} from "../composables/queries";
import { useRisk } from "@/features/home/composables/queries";

type Tab = "actions" | "risk";
const activeTab = ref<Tab>("actions");
const tabs: { key: Tab; label: string }[] = [
  { key: "actions", label: "今日行动" },
  { key: "risk", label: "风险" },
];

const ACTION_FILTERS = [
  { value: "", label: "全部动作" },
  { value: "buy", label: "提升预算" },
  { value: "reduce", label: "降低预算" },
  { value: "hold", label: "维持观察" },
  { value: "suspend", label: "暂停" },
];

const actionFilter = ref("");
const codeFilter = ref("");
const rows = ref<AdviceRecord[]>([]);
const cursor = ref<string | null>(null);
const hasMore = ref(false);
const loading = ref(false);
const error = ref("");
const loaded = ref(false);
const showHistory = ref(false);

const { data: riskData } = useRisk();

const now = new Date();
function isToday(iso: string): boolean {
  return iso.slice(0, 10) === now.toISOString().slice(0, 10);
}
function isLive(a: AdviceRecord): boolean {
  return a.actionable && a.expires_at > now.toISOString();
}

// 分组：当日记录直接展示；更早/已失效折叠「历史」（UI §10.4）
const todayRows = computed(() => rows.value.filter((r) => isToday(r.created_at)));
const liveRows = computed(() =>
  [...todayRows.value].sort((a, b) => Number(isLive(b)) - Number(isLive(a))),
);
const historyRows = computed(() =>
  rows.value.filter((r) => !isToday(r.created_at)),
);

const sortedBreaches = computed(() => {
  const list = [...(riskData.value?.breaches ?? [])];
  list.sort((x, y) => (x.level === "hard" ? -1 : 0) - (y.level === "hard" ? -1 : 0));
  return list;
});

async function load(reset: boolean) {
  loading.value = true;
  error.value = "";
  try {
    const page = await fetchAdviceRecords({
      action: actionFilter.value || undefined,
      code: codeFilter.value.trim() || undefined,
      cursor: reset ? undefined : (cursor.value ?? undefined),
      limit: 50,
    });
    rows.value = reset ? page.items : [...rows.value, ...page.items];
    cursor.value = page.next_cursor;
    hasMore.value = page.has_more;
    loaded.value = true;
  } catch (e) {
    error.value = e instanceof Error ? e.message : "加载失败";
  } finally {
    loading.value = false;
  }
}

watch([actionFilter, codeFilter], () => void load(true), { immediate: true });

function actionMeta(a: AdviceRecord) {
  return ACTION_META[a.action] ?? ACTION_META.hold;
}

function timeOf(iso: string): string {
  return iso.slice(11, 19);
}

const lastChecked = computed(() =>
  rows.value.length ? rows.value[0].created_at.replace("T", " ").slice(0, 19) : EMPTY,
);
</script>

<template>
  <div class="space-y-6">
    <PageHeader
      title="今日行动与风险"
      subtitle="按优先级处理有效建议与风险阻塞项"
      back
    />

    <!-- Tab 栏（基准卡：品牌色下划线激活态） -->
    <div
      class="flex border-b border-gray-200 dark:border-gray-700"
      role="tablist"
    >
      <button
        v-for="t in tabs"
        :key="t.key"
        type="button"
        role="tab"
        class="-mb-px flex-1 appearance-none border-x-0 border-t-0 border-b-2 bg-transparent py-2.5 text-body font-medium transition-colors"
        :class="
          activeTab === t.key
            ? 'border-primary text-primary'
            : 'border-transparent text-gray-500 dark:text-gray-400'
        "
        :data-testid="`tab-${t.key}`"
        :aria-selected="activeTab === t.key"
        @click="activeTab = t.key"
      >
        {{ t.label }}
        <span
          v-if="t.key === 'risk' && sortedBreaches.length"
          class="ml-1 rounded-full px-1.5 text-caption"
          :class="sortedBreaches.some((b) => b.level === 'hard')
            ? 'bg-risk-critical/10 text-risk-critical'
            : 'bg-risk-warning/10 text-risk-warning'"
        >
          {{ sortedBreaches.length }}
        </span>
      </button>
    </div>

    <!-- ===== 今日行动 Tab ===== -->
    <template v-if="activeTab === 'actions'">
      <!-- 筛选 -->
      <div class="flex flex-wrap items-center gap-2">
        <select
          v-model="actionFilter"
          class="rounded-md border border-gray-200 bg-transparent px-2 py-1.5 text-label dark:border-gray-600"
          data-testid="advice-filter-action"
        >
          <option
            v-for="f in ACTION_FILTERS"
            :key="f.value"
            :value="f.value"
          >
            {{ f.label }}
          </option>
        </select>
        <input
          v-model="codeFilter"
          placeholder="按标的代码筛选"
          class="w-44 rounded-md border border-gray-200 bg-transparent px-2 py-1.5 text-label dark:border-gray-600"
          data-testid="advice-filter-code"
        >
      </div>

      <p
        v-if="error"
        class="text-caption text-error"
      >
        {{ error }}
      </p>

      <!-- 空态：不使用庆祝动画 -->
      <div
        v-if="loaded && !rows.length && !loading"
        class="rounded-2xl bg-white p-6 text-center text-body text-gray-400 shadow-sm dark:bg-gray-800 dark:text-gray-500"
        data-testid="advice-empty"
      >
        当前没有需要处理的行动
        <p class="mt-2 text-caption text-gray-400 dark:text-gray-500">
          最近检查 {{ lastChecked }} · 可前往
          <router-link
            to="/assistant"
            class="text-primary"
          >
            盘中问询
          </router-link>或
          <router-link
            to="/research"
            class="text-primary"
          >
            研究
          </router-link>
        </p>
      </div>

      <template v-else>
        <!-- 当日建议（有效期内在前） -->
        <div
          v-if="liveRows.length"
          class="divide-y divide-gray-100 overflow-hidden rounded-2xl bg-white shadow-sm dark:divide-gray-700 dark:bg-gray-800"
          data-testid="advice-list"
        >
          <router-link
            v-for="a in liveRows"
            :key="a.advice_id"
            :to="`/advice/${a.advice_id}`"
            class="flex items-center justify-between px-4 py-3"
            :data-testid="`advice-row-${a.advice_id}`"
          >
            <div class="min-w-0">
              <div class="flex items-center gap-2">
                <span
                  class="rounded-sm px-1.5 py-0.5 text-caption font-medium"
                  :class="actionMeta(a).cls"
                >
                  {{ actionMeta(a).label }}
                </span>
                <span
                  v-if="isLive(a)"
                  class="rounded-sm bg-primary/10 px-1.5 py-0.5 text-caption text-primary"
                >有效</span>
                <span class="truncate text-body font-medium num">{{
                  a.code
                }}</span>
              </div>
              <div class="mt-1 truncate text-caption text-gray-500 dark:text-gray-400">
                <template v-if="a.reasons.length">
                  {{ reasonText(a.reasons[0]) }}
                </template>
                <template v-else-if="a.f_max != null">
                  目标区间上限 {{ a.f_max }}
                </template>
                <template v-else>
                  —
                </template>
              </div>
            </div>
            <div class="shrink-0 text-right text-caption text-gray-400 dark:text-gray-500 num">
              {{ timeOf(a.created_at) }}
            </div>
          </router-link>
        </div>

        <!-- 历史记录（默认折叠；UI §10.4 已过期/失效 → 历史状态） -->
        <div
          v-if="historyRows.length"
          class="space-y-2"
        >
          <button
            type="button"
            class="flex w-full items-center justify-between rounded-2xl bg-white px-4 py-3 text-label text-gray-600 shadow-sm dark:bg-gray-800 dark:text-gray-300"
            data-testid="advice-history-toggle"
            @click="showHistory = !showHistory"
          >
            <span>历史记录（{{ historyRows.length }}）</span>
            <span
              class="i-material-symbols-expand-more-rounded text-lg transition-transform"
              :class="showHistory ? 'rotate-180' : ''"
              aria-hidden="true"
            />
          </button>
          <div
            v-if="showHistory"
            class="divide-y divide-gray-100 overflow-hidden rounded-2xl bg-white shadow-sm dark:divide-gray-700 dark:bg-gray-800"
            data-testid="advice-history-list"
          >
            <router-link
              v-for="a in historyRows"
              :key="a.advice_id"
              :to="`/advice/${a.advice_id}`"
              class="flex items-center justify-between px-4 py-3"
            >
              <div class="min-w-0">
                <div class="flex items-center gap-2">
                  <span
                    class="rounded-sm px-1.5 py-0.5 text-caption font-medium"
                    :class="actionMeta(a).cls"
                  >
                    {{ actionMeta(a).label }}
                  </span>
                  <span class="truncate text-body font-medium num">{{ a.code }}</span>
                </div>
                <div class="mt-1 text-caption text-gray-500 dark:text-gray-400">
                  {{ a.created_at.slice(0, 10) }} ·
                  {{ a.reasons.length ? reasonText(a.reasons[0]) : "—" }}
                </div>
              </div>
              <div class="shrink-0 text-right text-caption text-gray-400 dark:text-gray-500">
                <span v-if="a.verdict">已评价</span>
                <span v-else-if="a.invalidated">已失效</span>
                <span v-else>已过期</span>
              </div>
            </router-link>
          </div>
        </div>

        <button
          v-if="hasMore"
          type="button"
          class="w-full appearance-none rounded-md border border-gray-200 py-2.5 text-label text-gray-600 disabled:opacity-40 dark:border-gray-600 dark:text-gray-300"
          :disabled="loading"
          data-testid="advice-more"
          @click="load(false)"
        >
          {{ loading ? "加载中…" : "加载更多" }}
        </button>
      </template>
    </template>

    <!-- ===== 风险 Tab（硬限制前置；hard 截断 + soft 告警明细） ===== -->
    <template v-else>
      <div
        v-if="!sortedBreaches.length"
        class="rounded-2xl bg-white p-6 text-center text-body text-gray-400 shadow-sm dark:bg-gray-800 dark:text-gray-500"
        data-testid="advice-risk-empty"
      >
        当前没有触发的风险项
      </div>
      <RiskAlert
        v-for="(b, i) in sortedBreaches"
        v-else
        :key="i"
        :rule="b.rule"
        :level="b.level"
        :actual="b.actual"
        :limit="b.limit"
        :code="b.code"
        :industry="b.industry"
      />
    </template>
  </div>
</template>
