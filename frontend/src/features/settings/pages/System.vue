<script setup lang="ts">
// SET-08 系统状态（波 V4）：/health/live+ready+dependencies 概览。
// job_runs 近况：无列表 API（仅单查 /jobs/{id}），本页先交付依赖健康主线。
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { PageHeader } from "@/shared/ui";

const router = useRouter();

interface DepItem {
  name: string;
  status?: string;
  [k: string]: unknown;
}

const live = ref<"…" | "ok" | "fail">("…");
const ready = ref<"…" | "ok" | "fail">("…");
const deps = ref<DepItem[]>([]);
const loading = ref(true);

async function probe(path: string): Promise<boolean> {
  try {
    const r = await fetch(path);
    return r.ok;
  } catch {
    return false;
  }
}

onMounted(async () => {
  const [l, r] = await Promise.all([probe("/health/live"), probe("/health/ready")]);
  live.value = l ? "ok" : "fail";
  ready.value = r ? "ok" : "fail";
  try {
    const res = await fetch("/health/dependencies");
    if (res.ok) {
      const data = (await res.json()) as Record<string, unknown>;
      deps.value = Object.entries(data).map(([name, v]) => ({
        name,
        status: typeof v === "object" && v !== null ? String((v as Record<string, unknown>).status ?? "—") : String(v),
        detail: v,
      }));
    }
  } catch {
    /* 依赖健康不可达不阻塞本页 */
  }
  loading.value = false;
});

function badge(s: "…" | "ok" | "fail"): string {
  return s === "ok" ? "bg-success/10 text-success" : s === "fail" ? "bg-error/10 text-error" : "bg-gray-100 text-gray-400 dark:bg-gray-700";
}
</script>

<template>
  <div class="space-y-6">
    <PageHeader
      title="系统状态"
      subtitle="进程存活 / 就绪 / 数据源与模型依赖"
      back
      @back="router.back()"
    />

    <div class="grid grid-cols-2 gap-2">
      <div class="rounded-2xl bg-white p-4 shadow-sm dark:bg-gray-800">
        <div class="text-label text-gray-500 dark:text-gray-400">
          存活（live）
        </div>
        <span
          class="mt-1 inline-block rounded-sm px-1.5 py-0.5 text-caption"
          :class="badge(live)"
        >{{ live === "ok" ? "正常" : live === "fail" ? "异常" : "检测中" }}</span>
      </div>
      <div class="rounded-2xl bg-white p-4 shadow-sm dark:bg-gray-800">
        <div class="text-label text-gray-500 dark:text-gray-400">
          就绪（ready）
        </div>
        <span
          class="mt-1 inline-block rounded-sm px-1.5 py-0.5 text-caption"
          :class="badge(ready)"
        >{{ ready === "ok" ? "正常" : ready === "fail" ? "异常（DB/迁移）" : "检测中" }}</span>
      </div>
    </div>

    <section class="space-y-2">
      <h2 class="text-h3 font-semibold lg:text-h3-d">
        依赖健康
      </h2>
      <p
        v-if="loading"
        class="text-caption text-gray-400"
      >
        检测中…
      </p>
      <div
        v-else-if="!deps.length"
        class="rounded-2xl bg-white p-6 text-center text-body text-gray-400 shadow-sm dark:bg-gray-800 dark:text-gray-500"
      >
        依赖详情不可用（仅登录用户可见）。
      </div>
      <div
        v-for="d in deps"
        :key="d.name"
        class="flex items-center justify-between rounded-2xl bg-white p-3 shadow-sm dark:bg-gray-800"
      >
        <span class="text-body font-medium">{{ d.name }}</span>
        <span class="text-caption text-gray-500 dark:text-gray-400">{{ d.status ?? "—" }}</span>
      </div>
    </section>

    <p class="text-center text-caption text-gray-400 dark:text-gray-500">
      任务近况（job_runs 成功率/耗时）由 runtime_stats 提供，随 SET-08 后续补全。
    </p>
  </div>
</template>
