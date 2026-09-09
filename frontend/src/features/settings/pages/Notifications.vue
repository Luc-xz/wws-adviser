<script setup lang="ts">
// SET-04 通知与隐私（波 V4）：通知渠道状态 + 隐私模式开关 + 浏览器推送开启
// （usePushManager，Phase 3.5 已接后端；FR-NOTIFY-003 隐私锁屏脱敏说明）。
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import client from "@/api/client";
import { PageHeader } from "@/shared/ui";
import { usePushManager } from "@/shared/push/usePushManager";

const router = useRouter();
const push = usePushManager();

const loading = ref(true);
const saving = ref(false);
const error = ref("");
const notifierSource = ref("");
const privacyMode = ref(true);
const saved = ref(false);

onMounted(async () => {
  try {
    const { data, error: err } = await client.GET("/api/v1/settings/{section}", {
      params: { path: { section: "notifications" } },
    });
    if (!err && data) {
      const d = data as Record<string, unknown>;
      notifierSource.value = String(d.notifier_source ?? "stub");
      privacyMode.value = d.privacy_mode !== false && d.notification_privacy_mode !== false;
    }
  } catch {
    /* 首屏失败按默认态展示 */
  } finally {
    loading.value = false;
  }
});

async function savePrivacy() {
  saving.value = true;
  error.value = "";
  try {
    const { error: err } = await client.PATCH("/api/v1/settings/{section}", {
      params: { path: { section: "notifications" } },
      body: { privacy_mode: privacyMode.value },
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
      title="通知与隐私"
      subtitle="渠道状态 · 锁屏脱敏 · 浏览器推送"
      back
      @back="router.back()"
    />

    <section class="rounded-lg bg-white p-4 shadow-sm dark:bg-gray-800">
      <h2 class="text-h3 font-semibold">
        通知渠道
      </h2>
      <p class="mt-1 text-body text-gray-500 dark:text-gray-400">
        当前渠道：{{ notifierSource || "…" }}
        <span
          v-if="notifierSource === 'stub'"
          class="text-caption text-gray-400"
        >（测试渠道——生产请配置 SMTP / 企微 / Server酱）</span>
      </p>
      <p class="mt-1 text-caption text-gray-400 dark:text-gray-500">
        通知事件：开市前/收市后报告完成或失败 · 重大公告与硬风险 · 数据源持续不可用 · 研究任务终态（FR-NOTIFY-002）。
      </p>
    </section>

    <section class="rounded-lg bg-white p-4 shadow-sm dark:bg-gray-800">
      <div class="flex items-center justify-between">
        <div class="min-w-0">
          <h2 class="text-h3 font-semibold">
            隐私模式
          </h2>
          <p class="mt-1 text-caption text-gray-500 dark:text-gray-400">
            开启后锁屏通知只显示事件类型与计数，不含标的、金额、动作（FR-NOTIFY-003）。
          </p>
        </div>
        <button
          type="button"
          role="switch"
          :aria-checked="privacyMode"
          class="relative h-6 w-11 shrink-0 appearance-none rounded-full transition-colors"
          :class="privacyMode ? 'bg-primary' : 'bg-gray-300'"
          data-testid="privacy-toggle"
          @click="privacyMode = !privacyMode"
        >
          <span
            class="absolute top-0.5 h-5 w-5 rounded-full bg-white transition-all"
            :class="privacyMode ? 'left-[22px]' : 'left-0.5'"
          />
        </button>
      </div>
      <button
        type="button"
        class="mt-3 w-full appearance-none rounded-md border border-primary py-2 text-body font-medium text-primary disabled:opacity-40"
        :disabled="saving || loading"
        data-testid="privacy-save"
        @click="savePrivacy"
      >
        {{ saving ? "保存中…" : saved ? "已保存" : "保存隐私设置" }}
      </button>
      <p
        v-if="error"
        class="mt-2 text-caption text-error"
      >
        {{ error }}
      </p>
    </section>

    <section
      v-if="push.supported.value"
      class="rounded-lg bg-white p-4 shadow-sm dark:bg-gray-800"
    >
      <div class="flex items-center justify-between gap-3">
        <div class="min-w-0">
          <h2 class="text-h3 font-semibold">
            浏览器推送
          </h2>
          <p class="mt-1 text-caption text-gray-500 dark:text-gray-400">
            需 VAPID 已配置（服务端 env）；权限被拒时到浏览器设置重置。
          </p>
        </div>
        <button
          type="button"
          class="shrink-0 appearance-none rounded-md px-3 py-1.5 text-label font-medium disabled:opacity-50"
          :class="push.state.value === 'enabled' ? 'bg-success/10 text-success' : 'bg-primary text-white'"
          :disabled="push.state.value === 'enabling' || push.state.value === 'enabled'"
          data-testid="push-enable-set04"
          @click="push.enable()"
        >
          {{ push.state.value === 'enabled' ? '已开启' : push.state.value === 'denied' ? '权限被拒' : push.state.value === 'enabling' ? '开启中…' : '开启' }}
        </button>
      </div>
    </section>
  </div>
</template>
