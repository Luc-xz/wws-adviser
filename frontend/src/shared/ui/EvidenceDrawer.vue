<script setup lang="ts">
// EvidenceDrawer（W2.5-1 / AC-05 UI 落点，REP-03-desktop 标杆）：
// 报告引用 → 证据切片回查。桌面右侧抽屉；移动端 Bottom Sheet（≤640px 媒体查询）。
// 每条引用：trust 等级徽章 + 切片定位 + 双源验证状态；点击加载证据详情
//（evidence_id → document 标题/来源），追溯链 evidence → document → content_hash。
import { computed, ref, watch } from "vue";
import client from "@/api/client";
import { EMPTY } from "@/shared/format/number";

export interface EvidenceCite {
  evidence_id?: string;
  section?: string;
  locator?: string;
  content_hash?: string;
  verified?: boolean;
  unverified_note?: string | null;
}

const props = defineProps<{
  open: boolean;
  title?: string;
  citations: EvidenceCite[];
}>();

const emit = defineEmits<{ close: [] }>();

const expandedId = ref<string | null>(null);
const detailCache = ref<Record<string, { claimText: string | null; docTitle: string | null; sourceUrl: string | null }>>({});
const loadingId = ref<string | null>(null);

const TRUST_NAMES: Record<string, string> = {
  L1: "官方披露",
  L2: "专业供应商",
  L3: "可信新闻",
  L4: "聚合转载",
  L5: "社交媒体",
};

const keyFor = (c: EvidenceCite, i: number) => c.evidence_id ?? `idx-${i}`;

const sorted = computed(() =>
  [...props.citations].sort((a, b) => Number(b.verified ?? 0) - Number(a.verified ?? 0)),
);

watch(
  () => props.open,
  (v) => {
    if (v) {
      expandedId.value = null;
      document.addEventListener("keydown", onKey);
    } else {
      document.removeEventListener("keydown", onKey);
    }
  },
);

function onKey(e: KeyboardEvent) {
  if (e.key === "Escape") emit("close");
}

async function toggle(c: EvidenceCite, i: number) {
  const key = keyFor(c, i);
  if (expandedId.value === key) {
    expandedId.value = null;
    return;
  }
  expandedId.value = key;
  if (!c.evidence_id || detailCache.value[c.evidence_id]) return;
  loadingId.value = key;
  try {
    const { data: ev } = await client.GET("/api/v1/documents/evidence/{evidence_id}", {
      params: { path: { evidence_id: c.evidence_id } },
    });
    if (!ev) throw new Error("证据获取失败");
    const { data: doc } = await client.GET("/api/v1/documents/{document_id}", {
      params: { path: { document_id: ev.document_id } },
    });
    detailCache.value[c.evidence_id] = {
      claimText: ev.claim_text ?? null,
      docTitle: doc?.title ?? null,
      sourceUrl: doc?.source_url ?? null,
    };
  } finally {
    loadingId.value = null;
  }
}
</script>

<template>
  <Teleport to="body">
    <Transition name="ed-fade">
      <div
        v-if="open"
        class="ed-backdrop"
        data-testid="evidence-backdrop"
        @click="emit('close')"
      />
    </Transition>
    <Transition name="ed-slide">
      <aside
        v-if="open"
        class="ed-panel"
        role="dialog"
        aria-label="报告依据"
        data-testid="evidence-drawer"
      >
        <div class="flex items-center justify-between border-b border-gray-100 px-4 py-3 dark:border-gray-700">
          <div>
            <h2 class="text-h3 font-semibold">
              报告依据
            </h2>
            <p
              v-if="title"
              class="mt-0.5 text-caption text-gray-400"
            >
              {{ title }}
            </p>
          </div>
          <button
            type="button"
            class="rounded p-1.5 text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700"
            aria-label="关闭"
            data-testid="evidence-close"
            @click="emit('close')"
          >
            <span class="i-carbon-close text-lg block" />
          </button>
        </div>

        <p class="px-4 pt-2 text-caption text-gray-400 dark:text-gray-500">
          追溯链：引用[编号] → 证据切片（来源等级 + 定位）→ 原文文档 → 内容哈希可复盘。
        </p>

        <ol class="flex-1 overflow-y-auto px-4 py-3 space-y-2">
          <li
            v-for="(c, i) in sorted"
            :key="keyFor(c, i)"
            class="rounded-lg border border-gray-100 dark:border-gray-700"
          >
            <button
              type="button"
              class="flex w-full items-center gap-2 px-3 py-2 text-left"
              :data-testid="`evidence-item-${i}`"
              @click="toggle(c, i)"
            >
              <span class="text-caption font-semibold text-gray-400 dark:text-gray-500">
                [{{ i + 1 }}]
              </span>
              <span
                class="rounded px-1.5 py-0.5 text-[10px] font-medium"
                :class="c.verified
                  ? 'bg-success/10 text-success'
                  : 'bg-risk-warning/10 text-risk-warning'"
              >
                {{ c.verified ? "已双源验证" : "未验证" }}
              </span>
              <span
                v-if="c.locator"
                class="text-caption text-gray-400"
              >{{ c.locator }}</span>
              <span
                v-if="c.section"
                class="text-caption text-gray-300 dark:text-gray-600"
              >· {{ c.section }}</span>
              <span class="ml-auto i-carbon-chevron-down text-gray-300" />
            </button>
            <div
              v-if="expandedId === keyFor(c, i)"
              class="border-t border-gray-100 px-3 py-2 text-caption dark:border-gray-700"
              data-testid="evidence-detail"
            >
              <template v-if="!c.evidence_id">
                <p class="text-gray-400">
                  该引用无证据切片 ID（{{ c.unverified_note ?? EMPTY }}）。
                </p>
              </template>
              <template v-else-if="loadingId === keyFor(c, i)">
                <p class="text-gray-400">
                  加载证据详情…
                </p>
              </template>
              <dl
                v-else-if="detailCache[c.evidence_id!]"
                class="space-y-1"
              >
                <div>
                  <dt class="text-gray-400">
                    原文标题
                  </dt>
                  <dd class="mt-0.5 font-medium text-gray-700 dark:text-gray-200">
                    {{ detailCache[c.evidence_id!].docTitle ?? EMPTY }}
                  </dd>
                </div>
                <div>
                  <dt class="text-gray-400">
                    切片原文
                  </dt>
                  <dd class="mt-0.5 text-gray-600 dark:text-gray-300">
                    {{ detailCache[c.evidence_id!].claimText ?? EMPTY }}
                  </dd>
                </div>
                <div>
                  <dt class="text-gray-400">
                    内容哈希
                  </dt>
                  <dd class="mt-0.5 text-gray-500 num">
                    {{ c.content_hash ?? EMPTY }}
                  </dd>
                </div>
              </dl>
            </div>
          </li>
        </ol>

        <div class="border-t border-gray-100 px-4 py-2 text-caption text-gray-400 dark:border-gray-700 dark:text-gray-500">
          共 {{ citations.length }} 条引用 · 等级含义：L1 官方披露 / L2 专业供应商 / L3 可信新闻
        </div>
      </aside>
    </Transition>
  </Teleport>
</template>

<style scoped>
.ed-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(16, 24, 40, 0.45);
  z-index: 50;
}
.ed-panel {
  position: fixed;
  z-index: 51;
  background: var(--color-surface, #fff);
  display: flex;
  flex-direction: column;
}
/* 移动：Bottom Sheet（REVIEW_REPORT §4.4 要求形态） */
@media (max-width: 639px) {
  .ed-panel {
    left: 0;
    right: 0;
    bottom: 0;
    max-height: 85vh;
    width: 100%;
    border-radius: 16px 16px 0 0;
  }
}
/* 桌面：右侧抽屉 */
@media (min-width: 640px) {
  .ed-panel {
    top: 0;
    right: 0;
    bottom: 0;
    width: 400px;
    box-shadow: -8px 0 24px rgba(16, 24, 40, 0.15);
  }
}
.ed-fade-enter-active,
.ed-fade-leave-active {
  transition: opacity 0.15s ease;
}
.ed-fade-enter-from,
.ed-fade-leave-to {
  opacity: 0;
}
.ed-slide-enter-active,
.ed-slide-leave-active {
  transition: transform 0.2s ease;
}
.ed-slide-enter-from,
.ed-slide-leave-to {
  transform: translateY(100%);
}
@media (min-width: 640px) {
  .ed-slide-enter-from,
  .ed-slide-leave-to {
    transform: translateX(100%);
  }
}
</style>
