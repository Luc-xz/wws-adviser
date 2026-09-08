<script setup lang="ts">
// LIB-01 研究与报告库（Phase 3 波7）：创建任务（公司/行业）→ 任务列表（SSE 实时进度）→
// 报告阅读（认知层级标签 + 引用可追溯）→ 导出（md / 可打印 html）。
import { computed, ref, watch } from "vue";
import {
  researchExportUrl,
  useCancelResearchTask,
  useCreateResearchTask,
  useResearchReport,
  useResearchTasks,
  type ResearchDepth,
  type ResearchTaskType,
} from "@/features/research/composables/queries";
import { useResearchTaskStatus } from "@/features/research/composables/useResearchTaskStatus";
import { renderReportMd } from "@/features/research/composables/renderMd";

const { data: taskData, isLoading: tasksLoading } = useResearchTasks();
const { create } = useCreateResearchTask();
const { cancel } = useCancelResearchTask();

const tasks = computed(() => taskData.value?.items ?? []);

// —— 创建表单 ——
const formType = ref<ResearchTaskType>("company");
const formSubject = ref("");
const formDepth = ref<ResearchDepth>("standard");
const creating = ref(false);
const createError = ref<string | null>(null);

async function submit() {
  const subject = formSubject.value.trim();
  if (!subject) { createError.value = "请输入证券代码或行业名称"; return; }
  creating.value = true;
  createError.value = null;
  try {
    const t = await create({ task_type: formType.value, subject, depth: formDepth.value });
    selectedId.value = t.id;
  } catch (e) {
    createError.value = e instanceof Error ? e.message : "创建失败";
  } finally {
    creating.value = false;
  }
}

// —— 选中任务 + 实时状态 ——
const selectedId = ref<string | null>(null);
const selectedTask = computed(() =>
  tasks.value.find((t) => t.id === selectedId.value) ?? null,
);
const liveReportId = computed(() => selectedTask.value?.report_id ?? null);
const { state: liveState, start: startStatus } = useResearchTaskStatus(
  () => selectedId.value,
);
watch(selectedId, () => { if (selectedId.value) startStatus(); });

const displayStatus = computed(() => liveState.value.status ?? selectedTask.value?.status ?? null);
const displayProgress = computed(
  () => liveState.value.progress ?? selectedTask.value?.progress ?? 0,
);

const STATUS_LABEL: Record<string, string> = {
  PENDING: "排队中", RUNNING: "生成中", COMPLETED: "已完成",
  FAILED: "失败", CANCELLED: "已取消",
};
const STATUS_CLASS: Record<string, string> = {
  PENDING: "bg-gray-100 text-gray-500",
  RUNNING: "bg-info/10 text-info",
  COMPLETED: "bg-success/10 text-success",
  FAILED: "bg-error/10 text-error",
  CANCELLED: "bg-gray-100 text-gray-400",
};
const ERROR_LABEL: Record<string, string> = {
  insufficient_evidence: "未检索到证据——请先在数据源采集相关公告/文档",
};
function errorText(code: string | null): string {
  if (!code) return "";
  if (ERROR_LABEL[code]) return ERROR_LABEL[code]!;
  if (code.startsWith("model_failed")) return `模型调用失败（${code.split(":")[1] ?? "?"}）`;
  if (code.startsWith("output_invalid")) return "模型输出未通过引用校验";
  return code;
}

// —— 报告阅读 ——
const { data: reportData, isLoading: reportLoading } = useResearchReport(
  () => liveReportId.value,
);
const reportHtml = computed(() =>
  reportData.value?.content_md ? renderReportMd(reportData.value.content_md) : "",
);
const citations = computed(() => reportData.value?.citations ?? []);

function onCancel(id: string) { void cancel(id); }
</script>

<template>
  <div class="space-y-4">
    <h1 class="text-lg font-semibold">
      研究
    </h1>

    <!-- 创建任务 -->
    <form
      class="rounded-xl bg-white p-4 shadow-sm space-y-3"
      data-testid="research-create-form"
      @submit.prevent="submit"
    >
      <div class="flex flex-wrap gap-2">
        <label class="flex items-center gap-1 text-sm">
          <input
            v-model="formType"
            type="radio"
            value="company"
            data-testid="research-type-company"
          >
          公司研究
        </label>
        <label class="flex items-center gap-1 text-sm">
          <input
            v-model="formType"
            type="radio"
            value="industry"
            data-testid="research-type-industry"
          >
          行业研究
        </label>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <input
          v-model="formSubject"
          type="text"
          class="flex-1 min-w-48 rounded-lg border border-gray-200 px-3 py-2 text-sm"
          :placeholder="formType === 'company' ? '证券代码，如 600519' : '行业名称，如 白酒'"
          data-testid="research-subject-input"
        >
        <select
          v-model="formDepth"
          class="rounded-lg border border-gray-200 px-2 py-2 text-sm"
          data-testid="research-depth-select"
        >
          <option value="quick">
            快速（3 段）
          </option>
          <option value="standard">
            标准（全量）
          </option>
          <option value="deep">
            深度（全量）
          </option>
        </select>
        <button
          type="submit"
          class="rounded-lg bg-primary px-4 py-2 text-sm text-white disabled:opacity-50"
          :disabled="creating"
          data-testid="research-submit"
        >
          {{ creating ? "创建中…" : "开始研究" }}
        </button>
      </div>
      <p
        v-if="createError"
        class="text-xs text-error"
        data-testid="research-create-error"
      >
        {{ createError }}
      </p>
    </form>

    <!-- 任务列表 -->
    <div
      v-if="!tasks.length"
      class="rounded-xl bg-white p-6 text-center text-sm text-gray-400 shadow-sm"
    >
      {{ tasksLoading ? "加载中…" : "暂无研究任务——创建一个试试" }}
    </div>
    <div
      v-for="t in tasks"
      :key="t.id"
      class="rounded-xl bg-white p-3 shadow-sm flex items-center justify-between gap-3 cursor-pointer"
      :class="{ 'ring-2 ring-primary/40': t.id === selectedId }"
      data-testid="research-task-row"
      @click="selectedId = t.id"
    >
      <div class="min-w-0">
        <div class="text-sm font-medium truncate">
          {{ t.task_type === 'company' ? '公司' : '行业' }} · {{ t.subject }}
          <span class="text-xs text-gray-400">（{{ t.depth }}）</span>
        </div>
        <div
          v-if="t.id === selectedId && displayStatus === 'RUNNING'"
          class="mt-1 flex items-center gap-2"
        >
          <div class="h-1.5 flex-1 rounded bg-gray-100 overflow-hidden">
            <div
              class="h-full bg-info transition-all"
              :style="{ width: `${displayProgress}%` }"
              data-testid="research-progress-bar"
            />
          </div>
          <span class="text-xs text-gray-400 num">{{ displayProgress }}%</span>
          <span class="text-xs text-gray-300">· {{ liveState.source === 'sse' ? '实时' : '轮询' }}</span>
        </div>
        <div
          v-else-if="t.error_code"
          class="mt-1 text-xs text-error"
        >
          {{ errorText(t.error_code) }}
        </div>
      </div>
      <div class="flex items-center gap-2 shrink-0">
        <span
          class="rounded px-1.5 py-0.5 text-xs"
          :class="STATUS_CLASS[t.id === selectedId ? (displayStatus ?? t.status) : t.status]"
        >
          {{ STATUS_LABEL[t.id === selectedId ? (displayStatus ?? t.status) : t.status] ?? t.status }}
        </span>
        <button
          v-if="t.status === 'PENDING'"
          type="button"
          class="text-xs text-gray-400 underline"
          @click.stop="onCancel(t.id)"
        >
          取消
        </button>
      </div>
    </div>

    <!-- 报告阅读 -->
    <div
      v-if="selectedTask && (selectedTask.report_id || liveReportId)"
      class="rounded-xl bg-white p-4 shadow-sm space-y-3"
      data-testid="research-report-panel"
    >
      <div class="flex items-center justify-between">
        <h2 class="text-base font-semibold">
          {{ selectedTask.task_type === 'company' ? '公司研究报告' : '行业研究报告' }} · {{ selectedTask.subject }}
        </h2>
        <div class="flex gap-2">
          <a
            :href="researchExportUrl(liveReportId!, 'md')"
            class="rounded border border-gray-200 px-2 py-1 text-xs text-gray-500"
            download
          >导出 MD</a>
          <a
            :href="researchExportUrl(liveReportId!, 'html')"
            class="rounded border border-gray-200 px-2 py-1 text-xs text-gray-500"
            target="_blank"
          >导出 HTML（可打印 PDF）</a>
        </div>
      </div>
      <p
        v-if="reportLoading"
        class="text-sm text-gray-400"
      >
        报告加载中…
      </p>
      <!-- 内容经 renderReportMd 全文转义后注入（XSS 已防） -->
      <div class="research-md text-sm leading-relaxed">
        <!-- eslint-disable-next-line vue/no-v-html -->
        <div v-html="reportHtml" />
      </div>
      <div
        v-if="citations.length"
        class="border-t border-gray-100 pt-2"
        data-testid="research-citations"
      >
        <div class="text-xs font-medium text-gray-500 mb-1">
          引用清单（{{ citations.length }} 条 · 内容哈希可复盘）
        </div>
        <ol class="text-xs text-gray-400 space-y-0.5 list-decimal list-inside">
          <li
            v-for="(c, i) in citations"
            :key="i"
          >
            {{ c.locator }} · {{ c.verified ? '已双源验证' : (c.unverified_note ?? '未验证') }}
          </li>
        </ol>
      </div>
    </div>
  </div>
</template>

<style scoped>
.research-md :deep(h1) { font-size: 1.1rem; font-weight: 600; margin: 0.5rem 0; }
.research-md :deep(h2) { font-size: 0.95rem; font-weight: 600; margin: 1rem 0 0.25rem; }
.research-md :deep(blockquote) {
  border-left: 3px solid #d1d5db; padding: 0.1rem 0.6rem; margin: 0.25rem 0;
  color: #6b7280; font-size: 0.75rem; background: #f9fafb;
}
.research-md :deep(table) { border-collapse: collapse; margin: 0.5rem 0; font-size: 0.8rem; }
.research-md :deep(th), .research-md :deep(td) {
  border: 1px solid #e5e7eb; padding: 0.2rem 0.5rem;
}
.research-md :deep(th) { background: #f9fafb; }
.research-md :deep(ul) { list-style: disc; padding-left: 1.2rem; }
</style>
