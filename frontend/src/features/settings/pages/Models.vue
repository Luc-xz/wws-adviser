<script setup lang="ts">
// SET-03 模型与任务路由（波 V4）：掩码展示（key 只显 env 引用名，8_SECURITY §5）+
// 可编辑字段保存（base_url/model/temperature/max_tokens/timeout/retry）。
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import client from "@/api/client";
import { PageHeader } from "@/shared/ui";

const router = useRouter();
const loading = ref(true);
const saving = ref(false);
const error = ref("");
const saved = ref(false);
const raw = ref<Record<string, unknown>>({});

const EDITABLE = [
  { key: "model_base_url", label: "Base URL", placeholder: "https://…/v1" },
  { key: "model_name", label: "模型名", placeholder: "" },
  { key: "model_temperature", label: "温度（0~1）", placeholder: "0.2" },
  { key: "model_max_tokens", label: "最大输出 tokens", placeholder: "2048" },
  { key: "model_timeout", label: "超时（秒）", placeholder: "90" },
  { key: "model_retry", label: "重试次数", placeholder: "1" },
] as const;

const keyRef = ref("");

onMounted(async () => {
  try {
    const { data, error: err } = await client.GET("/api/v1/settings/{section}", {
      params: { path: { section: "models" } },
    });
    if (err || !data) throw new Error("读取失败");
    const d = data as Record<string, unknown>;
    raw.value = d;
    keyRef.value = String(d.model_api_key_ref ?? d.model_api_key ?? "—");
    for (const f of EDITABLE) {
      const v = d[f.key];
      if (v !== undefined && v !== null) (raw.value as Record<string, unknown>)[`_${f.key}`] = String(v);
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : "读取失败";
  } finally {
    loading.value = false;
  }
});

function val(key: string): string {
  return String(raw.value[`_${key}`] ?? "");
}

function setVal(key: string, v: string) {
  raw.value[`_${key}`] = v;
}

async function save() {
  saving.value = true;
  error.value = "";
  saved.value = false;
  try {
    const body: Record<string, string> = {};
    for (const f of EDITABLE) if (val(f.key) !== "") body[f.key] = val(f.key);
    const { error: err } = await client.PATCH("/api/v1/settings/{section}", {
      params: { path: { section: "models" } },
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
      title="模型与任务路由"
      subtitle="密钥只存 env 引用名，绝不回显明文（8_SECURITY §5）"
      back
      @back="router.back()"
    />

    <div
      v-if="loading"
      class="h-48 animate-pulse rounded-lg bg-gray-100 dark:bg-gray-700"
    />
    <form
      v-else
      class="space-y-4 rounded-2xl bg-white p-4 shadow-sm dark:bg-gray-800"
      @submit.prevent="save"
    >
      <div class="rounded-md bg-gray-50 px-3 py-2 text-caption text-gray-500 dark:bg-gray-700 dark:text-gray-400">
        API 密钥引用：{{ keyRef }}（只读——明文仅存环境变量）
      </div>
      <label
        v-for="f in EDITABLE"
        :key="f.key"
        class="block"
      >
        <span class="text-label text-gray-500 dark:text-gray-400">{{ f.label }}</span>
        <input
          :value="val(f.key)"
          :placeholder="f.placeholder"
          class="mt-1 w-full rounded-md border border-gray-200 bg-transparent px-3 py-2 text-body outline-none focus:border-primary dark:border-gray-700"
          :data-testid="`model-${f.key}`"
          @input="setVal(f.key, ($event.target as HTMLInputElement).value)"
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
      >
        已保存
      </p>
      <button
        type="submit"
        class="w-full appearance-none rounded-md bg-primary py-2.5 text-body font-medium text-white disabled:opacity-40"
        :disabled="saving"
      >
        {{ saving ? "保存中…" : "保存" }}
      </button>
    </form>
  </div>
</template>
