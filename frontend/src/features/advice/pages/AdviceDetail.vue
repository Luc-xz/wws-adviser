<script setup lang="ts">
// CHAT-02 建议详情（UI §10.13）：完整建议卡 + 目标区间条 + 凯利过程（默认折叠，
// 一位小数 + 固定诚实旁注 + 拒绝原因显式化）+ 证据 + 评价回读。
// 偏差（基准卡登记）：当前仓位未随记录持久化 → 区间条只画目标带；
// 「记录我的实际操作」为写操作（acknowledge 端点未交付）→ 不做占位表单。
import { computed, ref } from "vue";
import { useRoute } from "vue-router";
import { DataFooter, MetricCard, PageHeader } from "@/shared/ui";
import { EMPTY, formatMoney } from "@/shared/format/number";
import { ACTION_META, TRAIL_NAMES, VERDICT_NAMES, reasonText } from "../meta";
import { useAdviceRecord, type AdviceRecord } from "../composables/queries";

const route = useRoute();
const recordId = route.params.id as string;
const { data: advice, isLoading, error } = useAdviceRecord(recordId);

const kellyOpen = ref(false);

// 仓位一位小数（UI §8.1 / §10.13 反精确化）：后端存分数（0–1）
function formatRatio(v: string | null | undefined): string {
  if (v == null || v === "") return EMPTY;
  return `${(Number(v) * 100).toFixed(1)}%`;
}

const actionMeta = computed(() =>
  ACTION_META[advice.value?.action ?? ""] ?? ACTION_META.hold,
);
const isExpired = computed(() =>
  advice.value ? advice.value.expires_at < new Date().toISOString() : false,
);
const hasInterval = computed(() =>
  advice.value?.f_min != null && advice.value?.f_max != null,
);

// 区间条几何（0–100% 刻度上的目标带；min/max clamp 防越界）
const band = computed(() => {
  const a = advice.value;
  if (!a || !hasInterval.value) return null;
  const lo = Math.min(100, Math.max(0, Number(a.f_min) * 100));
  const hi = Math.min(100, Math.max(lo, Number(a.f_max) * 100));
  return { left: lo, width: hi - lo };
});

// 凯利摘要「理论 X% → 风控后 Y%～Z%」：理论值取首个折扣步的 before
const kellySummary = computed(() => {
  const a = advice.value;
  if (!a || !hasInterval.value) return null;
  const first = a.trail.find((s) => s.before != null);
  const theory = first?.before ?? null;
  return {
    theory: theory != null ? formatRatio(theory) : EMPTY,
    final: `${formatRatio(a.f_min)} ～ ${formatRatio(a.f_max)}`,
  };
});
</script>

<template>
  <div class="space-y-6">
    <PageHeader
      title="建议详情"
      subtitle="条件式建议 · 原因链与计算轨迹可审计"
      back
    />

    <p
      v-if="isLoading"
      class="text-body text-gray-400"
    >
      加载中…
    </p>
    <p
      v-else-if="error"
      class="text-body text-error"
      data-testid="advice-detail-error"
    >
      {{ error instanceof Error ? error.message : "加载失败" }}
    </p>

    <template v-else-if="advice">
      <!-- 动作与状态（完整 Advice Card 头部） -->
      <section class="rounded-2xl bg-white p-4 shadow-sm dark:bg-gray-800">
        <div class="flex items-center justify-between">
          <span
            class="rounded px-2 py-1 text-sm font-medium"
            :class="actionMeta.cls"
            :data-testid="`advice-detail-action-${advice.action}`"
          >
            {{ actionMeta.label }}
          </span>
          <span
            v-if="advice.invalidated"
            class="rounded-sm bg-risk-warning/10 px-1.5 py-0.5 text-caption text-risk-warning"
          >已失效</span>
          <span
            v-else-if="isExpired"
            class="rounded-sm bg-gray-100 px-1.5 py-0.5 text-caption text-gray-500 dark:bg-gray-700 dark:text-gray-400"
          >已过期</span>
          <span
            v-else-if="advice.actionable"
            class="rounded-sm bg-primary/10 px-1.5 py-0.5 text-caption text-primary"
          >有效</span>
        </div>
        <p class="mt-2 text-xs text-gray-400 num">
          {{ advice.code }} · 信号 {{ advice.signal_id || "—" }}
        </p>
        <p class="mt-1 text-xs text-gray-400 num">
          生成 {{ advice.created_at.replace("T", " ").slice(0, 19) }} ·
          有效期至 {{ advice.expires_at.replace("T", " ").slice(0, 19) }}
        </p>
      </section>

      <!-- 目标区间条（水平带，非仪表盘；当前仓位未持久化 → 只画目标带） -->
      <section
        v-if="hasInterval && band"
        class="space-y-2 rounded-2xl bg-white p-4 shadow-sm dark:bg-gray-800"
      >
        <h2 class="text-sm font-medium text-gray-600 dark:text-gray-300">
          目标风险预算区间
        </h2>
        <div
          class="relative h-6 rounded bg-gray-100 dark:bg-gray-700"
          data-testid="advice-band"
        >
          <div
            class="absolute inset-y-0 rounded bg-primary/40"
            :style="{ left: `${band.left}%`, width: `${Math.max(band.width, 1)}%` }"
          />
        </div>
        <div class="flex justify-between text-caption text-gray-400 num">
          <span>0%</span>
          <span
            class="text-primary"
            data-testid="advice-band-range"
          >{{ formatRatio(advice.f_min) }} ～ {{ formatRatio(advice.f_max) }}</span>
          <span>100%</span>
        </div>
        <div class="grid grid-cols-2 gap-2">
          <MetricCard
            label="金额区间"
            :value="advice.value_min && advice.value_max
              ? `${formatMoney(advice.value_min, 0)} ~ ${formatMoney(advice.value_max, 0)}`
              : EMPTY"
          />
          <MetricCard
            label="建议手数"
            :value="advice.suggested_lots != null ? String(advice.suggested_lots) : EMPTY"
            :sub="advice.suggested_lots == null && hasInterval
              ? '无法安全取整，仅显示区间' : undefined"
          />
        </div>
      </section>

      <!-- 原因与标记（拒绝/暂停显式列原因类别，不静默） -->
      <section
        v-if="advice.reasons.length"
        class="space-y-2"
      >
        <h2 class="text-sm font-medium text-gray-600 dark:text-gray-300">
          原因与标记
        </h2>
        <div class="space-y-1">
          <p
            v-for="r in advice.reasons"
            :key="r"
            class="rounded-2xl bg-white p-2 text-xs shadow-sm dark:bg-gray-800"
            :class="advice.action === 'suspend' ? 'text-risk-warning' : 'text-gray-500 dark:text-gray-400'"
            data-testid="advice-detail-reason"
          >
            {{ reasonText(r) }}
          </p>
        </div>
      </section>

      <!-- 凯利计算过程（默认折叠；一位小数 + 固定诚实旁注，反精确化硬性约束） -->
      <section
        v-if="advice.trail.length"
        class="space-y-2"
      >
        <button
          type="button"
          class="flex w-full items-center justify-between rounded-2xl bg-white px-4 py-3 text-left shadow-sm dark:bg-gray-800"
          data-testid="advice-kelly-toggle"
          @click="kellyOpen = !kellyOpen"
        >
          <span
            class="text-sm font-medium text-gray-600 dark:text-gray-300"
            data-testid="advice-kelly-summary"
          >{{
            kellySummary
              ? `理论 ${kellySummary.theory} → 风控后 ${kellySummary.final}`
              : "计算轨迹"
          }}</span>
          <span
            class="i-material-symbols-expand-more-rounded text-lg text-gray-400 transition-transform"
            :class="kellyOpen ? 'rotate-180' : ''"
            aria-hidden="true"
          />
        </button>
        <div
          v-if="kellyOpen"
          class="rounded-2xl bg-white p-3 text-xs shadow-sm dark:bg-gray-800"
        >
          <p
            v-for="(s, i) in advice.trail"
            :key="i"
            class="py-0.5 text-gray-600 dark:text-gray-300"
            data-testid="advice-trail-step"
          >
            {{ i + 1 }}. {{ TRAIL_NAMES[s.kind] ?? s.kind }}：{{ s.note }}
            <span
              v-if="s.before && s.after"
              class="num"
            >（{{ s.before }} → {{ s.after }}）</span>
          </p>
        </div>
        <p class="text-caption text-gray-400 dark:text-gray-500">
          基于历史信号回测的概率估计，存在样本与模型不确定性，仅作风险预算参考
        </p>
      </section>

      <!-- 模型一句话解读（可选） -->
      <section
        v-if="advice.model_explanation"
        class="space-y-2"
      >
        <h2 class="text-sm font-medium text-gray-600 dark:text-gray-300">
          解读
        </h2>
        <div class="rounded-2xl bg-white p-3 text-sm leading-relaxed shadow-sm dark:bg-gray-800">
          {{ advice.model_explanation }}
        </div>
      </section>

      <!-- 事实和证据（引用 IDs，可经研究库回溯） -->
      <section class="space-y-2">
        <h2 class="text-sm font-medium text-gray-600 dark:text-gray-300">
          事实和证据
        </h2>
        <div class="rounded-2xl bg-white p-3 text-xs shadow-sm dark:bg-gray-800">
          <p
            v-if="!advice.evidence_ids.length"
            class="text-gray-400 dark:text-gray-500"
          >
            无（暂停形态不携带关键数字）
          </p>
          <p
            v-for="e in advice.evidence_ids"
            :key="e"
            class="py-0.5 text-gray-600 num dark:text-gray-300"
            data-testid="advice-evidence"
          >
            {{ e }}
          </p>
        </div>
      </section>

      <!-- 评价回读（FR-REV-003 观察窗口后；未评价如实显示） -->
      <section class="space-y-2">
        <h2 class="text-sm font-medium text-gray-600 dark:text-gray-300">
          建议评价
        </h2>
        <div
          v-if="advice.verdict"
          class="rounded-2xl bg-white p-3 text-xs shadow-sm dark:bg-gray-800"
          data-testid="advice-verdict"
        >
          <p class="text-body font-medium">
            {{ VERDICT_NAMES[advice.verdict] ?? advice.verdict }}
          </p>
          <p
            v-for="r in advice.evaluation?.reasons ?? []"
            :key="r"
            class="mt-1 text-gray-500 dark:text-gray-400"
          >
            {{ r }}
          </p>
          <p
            v-if="advice.evaluation?.direction_return"
            class="mt-1 text-gray-400 num"
          >
            窗口收益 {{ (Number(advice.evaluation.direction_return) * 100).toFixed(1) }}%
            · 持有 {{ advice.evaluation?.horizon ?? "—" }} 个交易日
          </p>
          <p
            v-if="advice.evaluated_at"
            class="mt-1 text-caption text-gray-400 num"
          >
            评价于 {{ advice.evaluated_at.replace("T", " ").slice(0, 19) }}
          </p>
        </div>
        <p
          v-else
          class="rounded-2xl bg-white p-3 text-xs text-gray-400 shadow-sm dark:bg-gray-800 dark:text-gray-500"
          data-testid="advice-verdict-pending"
        >
          待评价（建议到期 {{ advice.evaluation ? "" : "且观察窗口（10 自然日）" }}结束后按动作口径评价）
        </p>
      </section>

      <p class="rounded-2xl bg-white p-3 text-xs text-gray-400 shadow-sm dark:bg-gray-800 dark:text-gray-500">
        区间来自全市场同类信号回测（Wilson 置信区间）与分数凯利折扣，为风险预算参考，
        不构成投资建议；模型语言不参与概率估计。
      </p>
      <DataFooter
        :as-of="advice.valid_from.replace('T', ' ').slice(0, 19)"
        :source="`advice/${advice.advice_id.slice(0, 8)}`"
        :valid-until="advice.expires_at.replace('T', ' ').slice(0, 19)"
      />
    </template>
  </div>
</template>
