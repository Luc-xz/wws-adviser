<script setup lang="ts">
// TX-03 CSV 导入向导（波 V4 §8.0 留白承接 / jgd 三步闭环 012360b）：
// ① 选文件 → POST /transactions/import（multipart）预览
// ② 校验回显（preview / errors / duplicates 分区展示，勾选要导入的行）
// ③ POST /import/confirm（batch_id + fingerprints）→ 完成跳流水
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import client from "@/api/client";
import { PageHeader } from "@/shared/ui";

const router = useRouter();

type PreviewRow = Record<string, unknown> & { fingerprint?: string };

const step = ref<1 | 2 | 3>(1);
const STEPS = ["选择文件", "校验回显", "完成"] as const;
const file = ref<File | null>(null);
const batchId = ref("");
const preview = ref<PreviewRow[]>([]);
const errors = ref<Record<string, unknown>[]>([]);
const duplicates = ref<Record<string, unknown>[]>([]);
const checked = ref<Set<string>>(new Set());
const busy = ref(false);
const error = ref("");
const importedCount = ref<number | null>(null);

const allChecked = computed(
  () => preview.value.length > 0 && checked.value.size === validFingerprints.value.length
);
const validFingerprints = computed(() =>
  preview.value
    .map((r) => (typeof r.fingerprint === "string" ? r.fingerprint : ""))
    .filter(Boolean)
);

function pickFile(e: Event) {
  const input = e.target as HTMLInputElement;
  file.value = input.files?.[0] ?? null;
}

async function upload() {
  if (!file.value) return;
  busy.value = true;
  error.value = "";
  try {
    const fd = new FormData();
    fd.append("file", file.value);
    // openapi-fetch multipart：FormData 透传（运行时设 boundary）
    const { data, error: err } = await client.POST("/api/v1/transactions/import", {
      body: fd as unknown as { file: string },
    });
    if (err || !data) throw new Error("导入预览失败");
    batchId.value = data.batch_id;
    preview.value = (data.preview ?? []) as PreviewRow[];
    errors.value = (data.errors ?? []) as Record<string, unknown>[];
    duplicates.value = (data.duplicates ?? []) as Record<string, unknown>[];
    checked.value = new Set(validFingerprints.value); // 默认全选可导入行
    step.value = 2;
  } catch (e) {
    error.value = e instanceof Error ? e.message : "上传失败";
  } finally {
    busy.value = false;
  }
}

function toggle(fp: string) {
  const next = new Set(checked.value);
  if (next.has(fp)) next.delete(fp);
  else next.add(fp);
  checked.value = next;
}

function toggleAll() {
  checked.value =
    allChecked.value ? new Set() : new Set(validFingerprints.value);
}

async function confirmImport() {
  busy.value = true;
  error.value = "";
  try {
    const { data, error: err } = await client.POST("/api/v1/transactions/import/confirm", {
      params: { header: { "Idempotency-Key": crypto.randomUUID() } },
      body: { batch_id: batchId.value, fingerprints: [...checked.value] },
    });
    if (err || !data) throw new Error("导入确认失败");
    importedCount.value = checked.value.size;
    step.value = 3;
  } catch (e) {
    error.value = e instanceof Error ? e.message : "确认失败";
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div class="space-y-6">
    <PageHeader
      title="CSV 导入"
      subtitle="预览校验 → 勾选确认 → 指纹幂等去重"
      back
    />

    <!-- 步骤指示 -->
    <div class="flex items-center gap-2 text-label">
      <template
        v-for="(label, i) in STEPS"
        :key="label"
      >
        <span
          v-if="i > 0"
          class="i-carbon-chevron-right text-gray-300"
          aria-hidden="true"
        />
        <span
          class="rounded-sm px-2 py-1"
          :class="step === i + 1 ? 'bg-primary/10 text-primary font-medium' : 'text-gray-400'"
        >
          {{ i + 1 }}. {{ label }}
        </span>
      </template>
    </div>

    <!-- 步骤 1：选文件 -->
    <div
      v-if="step === 1"
      class="rounded-lg bg-white p-4 shadow-sm dark:bg-gray-800"
    >
      <input
        type="file"
        accept=".csv"
        class="text-body"
        data-testid="import-file"
        @change="pickFile"
      >
      <p class="mt-2 text-caption text-gray-400 dark:text-gray-500">
        支持券商对账单 CSV；导入前先预览校验，不会直接入库。
      </p>
      <p
        v-if="error"
        class="mt-2 text-caption text-error"
      >
        {{ error }}
      </p>
      <button
        type="button"
        class="mt-3 w-full appearance-none rounded-md bg-primary py-2.5 text-body font-medium text-white disabled:opacity-40"
        :disabled="!file || busy"
        data-testid="import-upload"
        @click="upload"
      >
        {{ busy ? "解析中…" : "上传并预览" }}
      </button>
    </div>

    <!-- 步骤 2：校验回显 -->
    <template v-else-if="step === 2">
      <div class="rounded-lg bg-white p-4 shadow-sm dark:bg-gray-800">
        <div class="flex items-center justify-between">
          <h2 class="text-h3 font-semibold">
            可导入 {{ preview.length }} 条
          </h2>
          <label class="flex items-center gap-1.5 text-label text-gray-500 dark:text-gray-400">
            <input
              type="checkbox"
              :checked="allChecked"
              @change="toggleAll"
            > 全选
          </label>
        </div>
        <div class="mt-2 divide-y divide-gray-100 dark:divide-gray-700">
          <label
            v-for="(r, i) in preview"
            :key="i"
            class="flex items-center gap-2 py-2 text-body"
          >
            <input
              type="checkbox"
              :checked="r.fingerprint ? checked.has(r.fingerprint) : false"
              :disabled="!r.fingerprint"
              @change="r.fingerprint && toggle(r.fingerprint)"
            >
            <span
              class="min-w-0 flex-1 truncate text-caption num"
              data-num
            >
              {{ JSON.stringify(r) }}
            </span>
          </label>
          <p
            v-if="!preview.length"
            class="py-2 text-caption text-gray-400"
          >
            无可导入行
          </p>
        </div>
      </div>

      <div
        v-if="errors.length || duplicates.length"
        class="space-y-2"
      >
        <div
          v-if="errors.length"
          class="rounded-lg bg-error/5 p-4 text-caption text-error"
        >
          校验失败 {{ errors.length }} 条（已跳过）：
          <pre class="mt-1 overflow-x-auto whitespace-pre-wrap">{{ JSON.stringify(errors) }}</pre>
        </div>
        <div
          v-if="duplicates.length"
          class="rounded-lg bg-risk-warning/5 p-4 text-caption text-risk-warning"
        >
          疑似重复 {{ duplicates.length }} 条（指纹已存在，跳过）
        </div>
      </div>

      <p
        v-if="error"
        class="text-caption text-error"
      >
        {{ error }}
      </p>
      <button
        type="button"
        class="w-full appearance-none rounded-md bg-primary py-2.5 text-body font-medium text-white disabled:opacity-40"
        :disabled="!checked.size || busy"
        data-testid="import-confirm"
        @click="confirmImport"
      >
        {{ busy ? "导入中…" : `确认导入 ${checked.size} 条` }}
      </button>
    </template>

    <!-- 步骤 3：完成 -->
    <div
      v-else
      class="rounded-lg bg-white p-6 text-center shadow-sm dark:bg-gray-800"
      data-testid="import-done"
    >
      <p class="text-h3 font-semibold text-success">
        导入完成
      </p>
      <p class="mt-1 text-body text-gray-500 dark:text-gray-400">
        已入库 {{ importedCount }} 条记录，持仓已重算。
      </p>
      <router-link
        to="/transactions"
        class="mt-4 inline-block rounded-md bg-primary px-4 py-2 text-body font-medium text-white"
      >
        查看流水
      </router-link>
    </div>
  </div>
</template>
