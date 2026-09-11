<script setup lang="ts">
// CHAT-01 盘中快速建议（Phase 2 / TECH §11.3）→ W2.5-2 对话流形态：
// 消息流（用户问询 + 助手建议卡）+ 底部输入；后端 /assistant/intraday 仍无状态，
// 会话历史仅本页内存（刷新即清，不落库——避免第二份建议存储）。
// 展示契约（FR-ANL-004）：动作 + 仓位区间（非单点）+ 调整轨迹（折扣/约束原因链）+
// 有效期与触发/失效条件；降级时只显示原因码，不显示任何仓位数字。
import { computed, nextTick, ref } from "vue";
import { DataFooter, MetricCard } from "@/shared/ui";
import { EMPTY, formatMoney, formatPercent } from "@/shared/format/number";
import { ACTION_META, TRAIL_NAMES, reasonText } from "@/features/advice/meta";
import {
  fetchIntradayAdvice,
  type IntradayAdvice,
} from "@/features/assistant/composables/queries";

interface ChatMessage {
  id: number;
  role: "user" | "assistant";
  code?: string;
  advice?: IntradayAdvice;
  error?: string;
  at: string;
}

const code = ref("");
const messages = ref<ChatMessage[]>([]);
const loading = ref(false);
const error = ref<string | null>(null);
const listEl = ref<HTMLElement | null>(null);
let seq = 0;

// AC-08：盘中建议离线不可用（SW 对 /api NetworkOnly，入口也禁用）
const online = ref(typeof navigator === "undefined" ? true : navigator.onLine);
if (typeof navigator !== "undefined") {
  window.addEventListener("online", () => (online.value = true));
  window.addEventListener("offline", () => (online.value = false));
}

const nowHM = () => new Date().toISOString().slice(11, 19);

async function scrollToEnd() {
  await nextTick();
  listEl.value?.scrollTo({ top: listEl.value.scrollHeight, behavior: "smooth" });
}

async function ask() {
  const c = code.value.trim();
  if (!c || loading.value) return;
  messages.value.push({ id: ++seq, role: "user", code: c, at: nowHM() });
  code.value = "";
  loading.value = true;
  error.value = null;
  try {
    const advice = await fetchIntradayAdvice(c);
    messages.value.push({ id: ++seq, role: "assistant", code: c, advice, at: nowHM() });
  } catch (e) {
    const msg = e instanceof Error ? e.message : "请求失败";
    error.value = msg;
    messages.value.push({ id: ++seq, role: "assistant", code: c, error: msg, at: nowHM() });
  } finally {
    loading.value = false;
    void scrollToEnd();
  }
}

function metaOf(m: ChatMessage) {
  return ACTION_META[m.advice?.action ?? ""] ?? ACTION_META.hold;
}
function hasInterval(m: ChatMessage) {
  return m.advice?.f_min != null && m.advice?.f_max != null;
}
</script>

<template>
  <div class="flex flex-col space-y-4">
    <section class="rounded-lg bg-white p-4 shadow-sm dark:bg-gray-800">
      <h1 class="text-h1 font-bold lg:text-h1-d">
        盘中问询
      </h1>
      <p class="mt-1 text-xs text-gray-400">
        条件式建议 + 有效期控制；凯利仓位为区间估计（组合层风险预算），非精确值。
      </p>
    </section>

    <!-- 对话流 -->
    <div
      ref="listEl"
      class="flex-1 space-y-3 overflow-y-auto lg:max-h-[62vh]"
      data-testid="chat-stream"
    >
      <p
        v-if="!messages.length"
        class="py-10 text-center text-sm text-gray-400 dark:text-gray-500"
        data-testid="chat-empty"
      >
        输入标的代码开始问询。建议仅信号触发日给出（风控设计）。
      </p>

      <template
        v-for="m in messages"
        :key="m.id"
      >
        <!-- 用户气泡 -->
        <div
          v-if="m.role === 'user'"
          class="flex justify-end"
        >
          <div class="max-w-[80%] rounded-2xl rounded-br-sm bg-primary/10 px-3 py-2 text-sm text-primary dark:bg-primary/20">
            {{ m.code }} 盘中怎么操作？
            <span class="mt-0.5 block text-right text-[10px] text-gray-400">{{ m.at }}</span>
          </div>
        </div>

        <!-- 助手：错误 -->
        <div
          v-else-if="m.error"
          class="flex"
        >
          <div
            class="max-w-[90%] rounded-2xl rounded-bl-sm bg-white p-3 text-sm text-risk-warning shadow-sm dark:bg-gray-800"
            data-testid="intraday-error"
          >
            {{ m.error }}
            <span class="mt-0.5 block text-[10px] text-gray-400">{{ m.at }}</span>
          </div>
        </div>

        <!-- 助手：建议卡 -->
        <div
          v-else-if="m.advice"
          class="flex"
        >
          <div class="w-full max-w-full space-y-3 rounded-2xl rounded-bl-sm bg-gray-50 p-3 dark:bg-gray-800/60">
            <div class="flex items-center justify-between">
              <span
                class="rounded px-2 py-1 text-sm font-medium"
                :class="metaOf(m).cls"
                :data-testid="`intraday-action-${m.advice.action}`"
              >
                {{ metaOf(m).label }}
              </span>
              <span class="text-xs text-gray-400">
                {{ m.advice.code }} · 信号 {{ m.advice.signal_id || "—" }} · {{ m.at }}
              </span>
            </div>
            <p class="text-xs text-gray-400">
              有效期 {{ m.advice.valid_from.slice(11, 19) }} → {{ m.advice.expires_at.slice(11, 19) }}
              （{{ m.advice.actionable ? "可操作" : "当前不可操作" }}）
            </p>
            <p
              v-for="t in m.advice.trigger_conditions"
              :key="t"
              class="text-xs text-gray-500"
            >
              触发条件：{{ t }}
            </p>

            <!-- 仓位区间（非单点；降级不显示任何数字） -->
            <div
              v-if="hasInterval(m)"
              class="space-y-2"
            >
              <h3 class="text-sm font-medium text-gray-600">
                建议仓位区间（组合占比）
              </h3>
              <div class="grid grid-cols-2 gap-2">
                <MetricCard
                  label="区间下限"
                  :value="m.advice.f_min ? formatPercent(m.advice.f_min) : EMPTY"
                />
                <MetricCard
                  label="区间上限"
                  :value="m.advice.f_max ? formatPercent(m.advice.f_max) : EMPTY"
                />
                <MetricCard
                  label="金额区间"
                  :value="m.advice.value_min && m.advice.value_max
                    ? `${formatMoney(m.advice.value_min, 0)} ~ ${formatMoney(m.advice.value_max, 0)}`
                    : EMPTY"
                />
                <MetricCard
                  label="建议手数"
                  :value="m.advice.suggested_lots != null ? String(m.advice.suggested_lots) : EMPTY"
                  :sub="m.advice.suggested_lots == null ? '无法安全取整，仅显示区间' : undefined"
                />
              </div>
            </div>

            <!-- 原因链 -->
            <div
              v-if="m.advice.reasons.length"
              class="space-y-1"
            >
              <p
                v-for="r in m.advice.reasons"
                :key="r"
                class="rounded-lg bg-white p-2 text-xs shadow-sm dark:bg-gray-800"
                :class="m.advice.action === 'suspend' ? 'text-risk-warning' : 'text-gray-500'"
                data-testid="intraday-reason"
              >
                {{ reasonText(r) }}
              </p>
              <p
                v-if="m.advice.action === 'suspend' && m.advice.reasons.includes('no_calibrated_signal')"
                class="text-caption text-gray-400 dark:text-gray-500"
                data-testid="intraday-suspend-note"
              >
                说明：A 股建议需先通过概率校准（AC-07 风控门槛），正向建议只在信号触发日给出；
                未覆盖/未触发的标的一律暂停而不给数量——这是设计行为，不是系统故障。
              </p>
            </div>

            <!-- 调整轨迹 -->
            <div
              v-if="m.advice.trail.length"
              class="rounded-lg bg-white p-3 text-xs shadow-sm dark:bg-gray-800"
            >
              <p
                v-for="(s, i) in m.advice.trail"
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

            <!-- 模型解读（失败时后端自动省略） -->
            <div
              v-if="m.advice.model_explanation"
              class="rounded-lg bg-white p-3 text-sm leading-relaxed shadow-sm dark:bg-gray-800"
            >
              {{ m.advice.model_explanation }}
            </div>

            <p class="text-[10px] leading-relaxed text-gray-400 dark:text-gray-500">
              区间来自回测置信区间与分数凯利折扣，为风险预算参考，不构成投资建议。
            </p>
            <DataFooter
              :as-of="m.advice.valid_from"
              :source="`advice/${m.advice.advice_id.slice(0, 8)}`"
            />
          </div>
        </div>
      </template>

      <!-- 查询中占位 -->
      <div
        v-if="loading"
        class="flex"
      >
        <div
          class="rounded-2xl rounded-bl-sm bg-white px-4 py-3 shadow-sm dark:bg-gray-800"
          data-testid="chat-loading"
        >
          <span class="inline-block h-2 w-2 animate-pulse rounded-full bg-gray-300" />
          <span class="ml-2 text-xs text-gray-400">正在生成建议…</span>
        </div>
      </div>
    </div>

    <!-- 底部输入（粘底） -->
    <form
      class="sticky bottom-0 flex gap-2 border-t border-gray-100 bg-gray-50 py-3 dark:border-gray-700 dark:bg-[var(--color-bg)]"
      @submit.prevent="ask"
    >
      <input
        v-model="code"
        type="text"
        inputmode="numeric"
        placeholder="证券代码，如 600519"
        class="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-800"
        data-testid="intraday-code"
      >
      <button
        type="submit"
        class="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
        data-testid="intraday-ask"
        :disabled="loading || !code.trim() || !online"
      >
        {{ loading ? "查询中…" : online ? "问询" : "离线" }}
      </button>
    </form>
    <p
      v-if="!online"
      class="text-xs text-gray-400"
      data-testid="intraday-offline"
    >
      当前离线：盘中行情与建议须实时数据，恢复网络后可用（AC-08）。
    </p>
  </div>
</template>
