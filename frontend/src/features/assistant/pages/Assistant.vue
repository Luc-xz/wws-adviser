<script setup lang="ts">
// CHAT-01 盘中快速建议（Phase 2 / TECH §11.3）：输入标的代码 → 条件式建议卡片。
// 展示契约（FR-ANL-004）：动作 + 仓位区间（非单点）+ 调整轨迹（折扣/约束原因链）+
// 有效期与触发/失效条件；降级时只显示原因码，不显示任何仓位数字。
import { computed, ref } from "vue";
import { DataFooter, MetricCard } from "@/shared/ui";
import { EMPTY, formatMoney, formatPercent } from "@/shared/format/number";
import {
  fetchIntradayAdvice,
  type IntradayAdvice,
} from "@/features/assistant/composables/queries";

const code = ref("");
const advice = ref<IntradayAdvice | null>(null);
const loading = ref(false);
const error = ref<string | null>(null);

const ACTION_META: Record<string, { label: string; cls: string }> = {
  buy: { label: "提升风险预算（区间）", cls: "bg-market-up/10 text-market-up" },
  reduce: { label: "降低风险预算", cls: "bg-market-down/10 text-market-down" },
  hold: { label: "维持 / 观察", cls: "bg-gray-100 text-gray-600" },
  suspend: { label: "暂停建议", cls: "bg-risk-warning/10 text-risk-warning" },
};

const REASON_NAMES: Record<string, string> = {
  data_stale: "行情过期或不可用",
  market_abnormal: "标的停牌或异常",
  ledger_unreconciled: "账本未对账",
  no_calibrated_signal: "无已校准信号（样本外校准未通过或未跑）",
  calibration_uncalibrated: "信号未完成样本外校准",
  calibration_stale: "校准已过期/失效",
  calibration_expired: "校准已过有效期",
  calibration_failed: "概率校准未通过（reliability）",
  insufficient_samples: "样本外有效样本不足（<30）",
  non_positive_payoff: "平均盈利不高于平均亏损",
  extreme_payoff: "盈亏比极端（区间下限）",
  low_confidence: "样本量偏少（半折扣）",
  wide_p_interval: "概率区间过宽（取保守端）",
  negative_edge: "无正边际（目标 0）",
  rounding_imprecise: "无法安全取整至手数（只显示区间）",
};

const TRAIL_NAMES: Record<string, string> = {
  fractional_discount: "分数凯利折扣",
  low_confidence_halving: "样本不足半折扣",
  wide_p_interval: "概率区间过宽",
  confidence_discount: "置信折扣",
  liquidity_discount: "流动性折扣",
  clip_cash_floor: "现金下限约束",
  clip_single_cap: "单标的上限约束",
  clip_industry_cap: "行业上限约束",
  clip_portfolio: "组合波动/回撤约束",
};

function reasonText(r: string): string {
  if (r.startsWith("gate:")) return `发布检查未过：${r.slice(5)}`;
  return REASON_NAMES[r] ?? r;
}

const actionMeta = computed(
  () => ACTION_META[advice.value?.action ?? ""] ?? ACTION_META.hold,
);
const hasInterval = computed(
  () => advice.value?.f_min != null && advice.value?.f_max != null,
);

async function ask() {
  const c = code.value.trim();
  if (!c) return;
  loading.value = true;
  error.value = null;
  advice.value = null;
  try {
    advice.value = await fetchIntradayAdvice(c);
  } catch (e) {
    error.value = e instanceof Error ? e.message : "请求失败";
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="space-y-3">
    <section class="rounded-xl bg-white p-4 shadow-sm">
      <h1 class="text-lg font-semibold">
        盘中问询
      </h1>
      <p class="mt-1 text-xs text-gray-400">
        条件式建议 + 有效期控制；凯利仓位为区间估计（组合层风险预算），非精确值。
      </p>
      <form
        class="mt-3 flex gap-2"
        @submit.prevent="ask"
      >
        <input
          v-model="code"
          type="text"
          inputmode="numeric"
          placeholder="证券代码，如 600519"
          class="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm"
          data-testid="intraday-code"
        >
        <button
          type="submit"
          class="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
          data-testid="intraday-ask"
          :disabled="loading || !code.trim()"
        >
          {{ loading ? "查询中…" : "查询建议" }}
        </button>
      </form>
      <p
        v-if="error"
        class="mt-2 text-sm text-risk-warning"
        data-testid="intraday-error"
      >
        {{ error }}
      </p>
    </section>

    <template v-if="advice">
      <!-- 动作与状态 -->
      <section class="rounded-xl bg-white p-4 shadow-sm">
        <div class="flex items-center justify-between">
          <span
            class="rounded px-2 py-1 text-sm font-medium"
            :class="actionMeta.cls"
            :data-testid="`intraday-action-${advice.action}`"
          >
            {{ actionMeta.label }}
          </span>
          <span class="text-xs text-gray-400">
            {{ advice.code }} · 信号 {{ advice.signal_id || "—" }}
          </span>
        </div>
        <p class="mt-2 text-xs text-gray-400">
          有效期 {{ advice.valid_from.slice(11, 19) }} → {{ advice.expires_at.slice(11, 19) }}
          （{{ advice.actionable ? "可操作" : "当前不可操作" }}）
        </p>
        <p
          v-for="t in advice.trigger_conditions"
          :key="t"
          class="mt-1 text-xs text-gray-500"
        >
          触发条件：{{ t }}
        </p>
      </section>

      <!-- 仓位区间（非单点；降级不显示任何数字） -->
      <section
        v-if="hasInterval"
        class="space-y-2"
      >
        <h2 class="text-sm font-medium text-gray-600">
          建议仓位区间（组合占比）
        </h2>
        <div class="grid grid-cols-2 gap-2">
          <MetricCard
            label="区间下限"
            :value="advice.f_min ? formatPercent(advice.f_min) : EMPTY"
          />
          <MetricCard
            label="区间上限"
            :value="advice.f_max ? formatPercent(advice.f_max) : EMPTY"
          />
          <MetricCard
            label="金额区间"
            :value="advice.value_min && advice.value_max
              ? `${formatMoney(advice.value_min, 0)} ~ ${formatMoney(advice.value_max, 0)}`
              : EMPTY"
          />
          <MetricCard
            label="建议手数"
            :value="advice.suggested_lots != null ? String(advice.suggested_lots) : EMPTY"
            :sub="advice.suggested_lots == null ? '无法安全取整，仅显示区间' : undefined"
          />
        </div>
      </section>

      <!-- 原因链（降级原因 / 折扣标记） -->
      <section
        v-if="advice.reasons.length"
        class="space-y-2"
      >
        <h2 class="text-sm font-medium text-gray-600">
          原因与标记
        </h2>
        <div class="space-y-1">
          <p
            v-for="r in advice.reasons"
            :key="r"
            class="rounded-xl bg-white p-2 text-xs shadow-sm"
            :class="advice.action === 'suspend' ? 'text-risk-warning' : 'text-gray-500'"
            data-testid="intraday-reason"
          >
            {{ reasonText(r) }}
          </p>
        </div>
      </section>

      <!-- 调整轨迹（计算输入 → 折扣 → 约束 → 最终区间） -->
      <section
        v-if="advice.trail.length"
        class="space-y-2"
      >
        <h2 class="text-sm font-medium text-gray-600">
          计算轨迹
        </h2>
        <div class="rounded-xl bg-white p-3 text-xs shadow-sm">
          <p
            v-for="(s, i) in advice.trail"
            :key="i"
            class="py-0.5 text-gray-600"
            data-testid="intraday-trail"
          >
            {{ i + 1 }}. {{ TRAIL_NAMES[s.kind] ?? s.kind }}：{{ s.note }}
            <span v-if="s.before && s.after">
              （{{ s.before }} → {{ s.after }}）
            </span>
          </p>
        </div>
      </section>

      <!-- 模型一句话解读（可选；失败时后端自动省略，不阻断建议） -->
      <section
        v-if="advice.model_explanation"
        class="space-y-2"
      >
        <h2 class="text-sm font-medium text-gray-600">
          解读
        </h2>
        <div class="rounded-xl bg-white p-3 text-sm leading-relaxed shadow-sm">
          {{ advice.model_explanation }}
        </div>
      </section>

      <p class="rounded-xl bg-white p-3 text-xs text-gray-400 shadow-sm">
        区间来自全市场同类信号回测（Wilson 置信区间）与分数凯利折扣，为风险预算参考，
        不构成投资建议；模型语言不参与概率估计。
      </p>
      <DataFooter
        :as-of="advice.valid_from"
        :source="`advice/${advice.advice_id.slice(0, 8)}`"
      />
    </template>
  </div>
</template>
