<script setup lang="ts">
// SET-01 风险与约束（波 V4）：阈值展示 + 编辑保存（PATCH /settings/risk，写审计）。
// 语义与 PORT 摘要一致：single_cap/industry_cap/cash_floor/top_n/top_n_concentration。
import { onMounted, ref } from "vue";
import client from "@/api/client";
import { PageHeader } from "@/shared/ui";
import { useRouter } from "vue-router";

const router = useRouter();
const loading = ref(true);
const saving = ref(false);
const error = ref("");
const saved = ref(false);

const FIELDS = [
  { key: "single_cap", label: "单标的仓位上限", pct: true },
  { key: "industry_cap", label: "行业集中度上限", pct: true },
  { key: "cash_floor", label: "最低现金比例", pct: true },
  { key: "top_n", label: "前 N 持仓", pct: false },
  { key: "top_n_concentration", label: "前 N 集中度上限", pct: true },
] as const;

const values = ref<Record<string, string>>({});

onMounted(async () => {
  try {
    const { data, error: err } = await client.GET("/api/v1/settings/{section}", {
      params: { path: { section: "risk" } },
    });
    if (err || !data) throw new Error("读取失败");
    const d = data as Record<string, unknown>;
    for (const f of FIELDS) values.value[f.key] = String(d[f.key] ?? "");
  } catch (e) {
    error.value = e instanceof Error ? e.message : "读取失败";
  } finally {
    loading.value = false;
  }
});

async function save() {
  saving.value = true;
  error.value = "";
  saved.value = false;
  try {
    const body: Record<string, string> = {};
    for (const f of FIELDS) if (values.value[f.key] !== "") body[f.key] = values.value[f.key];
    const { error: err } = await client.PATCH("/api/v1/settings/{section}", {
      params: { path: { section: "risk" } },
      body,
    });
    if (err) throw new Error("保存失败");
    saved.value = true;
    setTimeout(() => (saved.value = false), 2000);
  } catch (e) {
    error.value = e instanceof Error ? e.message : "保存失败";
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <div class="space-y-6">
    <PageHeader
      title="风险与约束"
      subtitle="硬限制即时生效 · 修改写审计"
      back
      @back="router.back()"
    />

    <div
      v-if="loading"
      class="h-48 animate-pulse rounded-lg bg-gray-100 dark:bg-gray-700"
    />
    <form
      v-else
      class="space-y-4 rounded-lg bg-white p-4 shadow-sm dark:bg-gray-800"
      @submit.prevent="save"
    >
      <label
        v-for="f in FIELDS"
        :key="f.key"
        class="block"
      >
        <span class="text-label text-gray-500 dark:text-gray-400">
          {{ f.label }}{{ f.pct ? "（小数，如 0.30）" : "" }}
        </span>
        <input
          v-model="values[f.key]"
          inputmode="decimal"
          class="mt-1 w-full rounded-md border border-gray-200 bg-transparent px-3 py-2 text-body num outline-none focus:border-primary dark:border-gray-700"
          :data-testid="`risk-${f.key}`"
        >
      </label>
      <p
        v-if="error"
        class="text-caption text-error"
      >
        {{ error }}
      </p>
      <p
        v-if="saved"
        class="text-caption text-success"
        data-testid="risk-saved"
      >
        已保存（写审计）
      </p>
      <button
        type="submit"
        class="w-full appearance-none rounded-md bg-primary py-2.5 text-body font-medium text-white disabled:opacity-40"
        :disabled="saving"
        data-testid="risk-save"
      >
        {{ saving ? "保存中…" : "保存" }}
      </button>
    </form>
  </div>
</template>
