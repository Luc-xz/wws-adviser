<script setup lang="ts">
// TX-02 新建/编辑交易（UI §10 对应页 / 波 V4 §8.0 留白承接）：
// 8 种交易类型（BUY/SELL/DIVIDEND/SPLIT/SUBSCRIBE/REDEEM/ADJUST/FEE），
// direction 仅买卖两类需要；提交走幂等 POST /transactions，成功回 TX-01。
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import client from "@/api/client";
import { PageHeader } from "@/shared/ui";
import {
  KIND_NAMES,
  KIND_NEEDS_DIRECTION,
  TX_KINDS,
  useCreateTransaction,
  type TxKind,
} from "../composables/queries";

const router = useRouter();
const create = useCreateTransaction();

const kind = ref<TxKind>("BUY");
const instrumentId = ref("");
const direction = ref<"IN" | "OUT">("IN");
const quantity = ref("");
const price = ref("");
const fee = ref("");
const tax = ref("");
const tradeAt = ref(new Date().toISOString().slice(0, 16));
const note = ref("");
const error = ref("");

const needsDirection = computed(() => KIND_NEEDS_DIRECTION.includes(kind.value));

function validate(): string | null {
  if (!instrumentId.value.trim()) return "请填写标的 ID";
  if (!(Number(quantity.value) > 0)) return "数量须大于 0";
  if (!(Number(price.value) >= 0)) return "价格不合法";
  if (!tradeAt.value) return "请选择成交时间";
  return null;
}

async function submit() {
  error.value = "";
  const v = validate();
  if (v) {
    error.value = v;
    return;
  }
  try {
    // W4 可用性修复：标的输入支持 6 位代码（自动解析 ID），也接受完整 ID
    let instId = instrumentId.value.trim();
    if (/^\d{6}$/.test(instId)) {
      const { data: insts, error: qErr } = await client.GET("/api/v1/instruments", {
        params: { query: { q: instId } },
      });
      const hit = (insts?.items ?? []).find((i) => i.code === instId);
      if (qErr || !hit) {
        error.value = `标的代码 ${instId} 不存在，请先在数据源导入或检查代码`;
        return;
      }
      instId = hit.id;
    }
    await create.mutateAsync({
      instrument_id: instId,
      kind: kind.value,
      direction: needsDirection.value ? direction.value : null,
      quantity: quantity.value,
      price: price.value,
      fee: fee.value || "0",
      tax: tax.value || "0",
      trade_at: new Date(tradeAt.value).toISOString(),
      note: note.value || null,
    });
    await router.push("/transactions");
  } catch (e) {
    error.value = e instanceof Error ? e.message : "提交失败";
  }
}
</script>

<template>
  <div class="space-y-6">
    <PageHeader
      title="记录交易"
      subtitle="8 种交易类型 · 移动加权平均成本即时重算"
      back
      @back="router.back()"
    />

    <form
      class="space-y-4 rounded-2xl bg-white p-4 shadow-sm dark:bg-gray-800"
      data-testid="tx-form"
      @submit.prevent="submit"
    >
      <div>
        <label
          class="text-label text-gray-500 dark:text-gray-400"
          for="tx-instrument"
        >交易类型</label>
        <div class="mt-1 flex flex-wrap gap-2">
          <button
            v-for="k in TX_KINDS"
            :key="k"
            type="button"
            class="rounded-sm border px-2.5 py-1.5 text-label font-medium"
            :class="kind === k
              ? 'border-primary bg-primary/10 text-primary'
              : 'border-gray-200 text-gray-600 dark:border-gray-600 dark:text-gray-300'"
            :data-testid="`kind-${k}`"
            @click="kind = k"
          >
            {{ KIND_NAMES[k] }}
          </button>
        </div>
      </div>

      <div
        v-if="needsDirection"
        class="flex items-center gap-3"
      >
        <span class="text-label text-gray-500 dark:text-gray-400">方向</span>
        <label class="flex items-center gap-1 text-body">
          <input
            v-model="direction"
            type="radio"
            value="IN"
            name="direction"
          >买入（流入）
        </label>
        <label class="flex items-center gap-1 text-body">
          <input
            v-model="direction"
            type="radio"
            value="OUT"
            name="direction"
          >卖出（流出）
        </label>
      </div>

      <label class="block">
        <span class="text-label text-gray-500 dark:text-gray-400">标的 ID</span>
        <input
          id="tx-instrument"
          v-model="instrumentId"
          placeholder="标的 ID（自选页/标的详情可复制）"
          class="mt-1 w-full rounded-md border border-gray-200 bg-transparent px-3 py-2 text-body outline-none focus:border-primary dark:border-gray-700"
          data-testid="tx-instrument"
        >
      </label>

      <div class="grid grid-cols-2 gap-3">
        <label class="block">
          <span class="text-label text-gray-500 dark:text-gray-400">数量</span>
          <input
            v-model="quantity"
            inputmode="decimal"
            class="mt-1 w-full rounded-md border border-gray-200 bg-transparent px-3 py-2 text-body num outline-none focus:border-primary dark:border-gray-700"
            data-testid="tx-quantity"
          >
        </label>
        <label class="block">
          <span class="text-label text-gray-500 dark:text-gray-400">价格</span>
          <input
            v-model="price"
            inputmode="decimal"
            class="mt-1 w-full rounded-md border border-gray-200 bg-transparent px-3 py-2 text-body num outline-none focus:border-primary dark:border-gray-700"
            data-testid="tx-price"
          >
        </label>
        <label class="block">
          <span class="text-label text-gray-500 dark:text-gray-400">费用（可选）</span>
          <input
            v-model="fee"
            inputmode="decimal"
            class="mt-1 w-full rounded-md border border-gray-200 bg-transparent px-3 py-2 text-body num outline-none focus:border-primary dark:border-gray-700"
          >
        </label>
        <label class="block">
          <span class="text-label text-gray-500 dark:text-gray-400">税（可选）</span>
          <input
            v-model="tax"
            inputmode="decimal"
            class="mt-1 w-full rounded-md border border-gray-200 bg-transparent px-3 py-2 text-body num outline-none focus:border-primary dark:border-gray-700"
          >
        </label>
      </div>

      <label class="block">
        <span class="text-label text-gray-500 dark:text-gray-400">成交时间</span>
        <input
          v-model="tradeAt"
          type="datetime-local"
          class="mt-1 w-full rounded-md border border-gray-200 bg-transparent px-3 py-2 text-body outline-none focus:border-primary dark:border-gray-700"
          data-testid="tx-trade-at"
        >
      </label>

      <label class="block">
        <span class="text-label text-gray-500 dark:text-gray-400">备注（可选）</span>
        <input
          v-model="note"
          class="mt-1 w-full rounded-md border border-gray-200 bg-transparent px-3 py-2 text-body outline-none focus:border-primary dark:border-gray-700"
        >
      </label>

      <p
        v-if="error"
        class="text-caption text-error"
        data-testid="tx-error"
      >
        {{ error }}
      </p>

      <button
        type="submit"
        class="w-full appearance-none rounded-md bg-primary py-2.5 text-body font-medium text-white disabled:opacity-40"
        :disabled="create.isPending.value"
        data-testid="tx-submit"
      >
        {{ create.isPending.value ? "提交中…" : "保存交易" }}
      </button>
    </form>
  </div>
</template>
