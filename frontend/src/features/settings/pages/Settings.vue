<script setup lang="ts">
// SET-00 设置首页（MVP）：风险阈值 + 外观（深色模式）+ 登出
import { computed } from "vue";
import { useQuery, useQueryClient } from "@tanstack/vue-query";
import { useRouter } from "vue-router";
import client from "@/api/client";
import { isDark, toggleDark } from "@/shared/theme";
import { clearAllReportCaches } from "@/shared/offline/reportCache";
import { usePushManager } from "@/shared/push/usePushManager";
import { useSessionStore } from "@/stores/session";

const session = useSessionStore();
const router = useRouter();
const qc = useQueryClient();
const push = usePushManager();

// 子页入口（SET-01~08；SET-05/07 后端缺资源，波 V4 P2 裁剪线）
const SUB_PAGES = [
  { to: "/settings/risk", label: "风险与约束", icon: "i-carbon-warning-alt" },
  { to: "/settings/data-sources", label: "数据源与质量", icon: "i-carbon-data-base" },
  { to: "/settings/models", label: "模型设置", icon: "i-carbon-model-alt" },
  { to: "/settings/notifications", label: "通知与隐私", icon: "i-carbon-notification" },
  { to: "/settings/security", label: "安全与会话", icon: "i-carbon-security" },
  { to: "/settings/system", label: "系统状态", icon: "i-carbon-information" },
] as const;

const { data: riskSettingsData, isSuccess: riskSettingsOk } = useQuery({
  queryKey: ["settings", "risk"],
  queryFn: async () => {
    const { data, error } = await client.GET("/api/v1/settings/{section}", {
      params: { path: { section: "risk" } },
    });
    if (error || !data) throw new Error("设置获取失败");
    return data as Record<string, unknown>;
  },
});

async function logout() {
  await client.POST("/api/v1/auth/logout");
  session.clear();
  qc.clear();
  // 退出登录清除报告私有缓存（doc7 §3 规则 3：离线报告不留给下一个登录者）
  await clearAllReportCaches().catch(() => undefined);
  router.push({ name: "login" });
}

const RISK_LABELS: Record<string, string> = {
  single_cap: "单标的仓位上限",
  industry_cap: "行业集中度上限",
  cash_floor: "最低现金比例",
  top_n: "前 N 持仓",
  top_n_concentration: "前 N 集中度上限",
};

const riskRows = computed(() =>
  Object.entries(riskSettingsData.value ?? {}).map(([k, v]) => ({
    key: k,
    label: RISK_LABELS[k] ?? k,
    value: String(v),
  }))
);
</script>

<template>
  <div class="space-y-6">
    <h1 class="text-h1 font-bold lg:text-h1-d">
      设置
    </h1>

    <section class="rounded-lg bg-white p-4 shadow-sm dark:bg-gray-800">
      <h2 class="text-h3 font-semibold">
        外观
      </h2>
      <div class="mt-2 flex items-center justify-between">
        <span class="text-gray-500 dark:text-gray-400 text-sm">深色模式</span>
        <button
          type="button"
          role="switch"
          :aria-checked="isDark"
          class="relative h-6 w-11 rounded-full transition-colors"
          :class="isDark ? 'bg-primary' : 'bg-gray-300'"
          data-testid="dark-toggle"
          @click="toggleDark()"
        >
          <span
            class="absolute top-0.5 h-5 w-5 rounded-full bg-white transition-all"
            :class="isDark ? 'left-[22px]' : 'left-0.5'"
          />
        </button>
      </div>
      <p class="mt-1 text-xs text-gray-400 dark:text-gray-500">
        默认跟随系统，切换后本地记忆。
      </p>
    </section>

    <section
      v-if="push.supported.value"
      class="rounded-lg bg-white p-4 shadow-sm dark:bg-gray-800"
    >
      <h2 class="text-h3 font-semibold">
        通知
      </h2>
      <div class="mt-2 flex items-center justify-between gap-3">
        <span class="text-gray-500 dark:text-gray-400 text-sm">浏览器推送（报告 / 研究完成）</span>
        <button
          type="button"
          class="appearance-none rounded-lg bg-transparent px-3 py-1.5 text-xs font-medium disabled:opacity-50"
          :class="push.state.value === 'enabled'
            ? 'bg-success/10 text-success'
            : 'bg-primary text-white'"
          :disabled="push.state.value === 'enabling' || push.state.value === 'enabled'"
          data-testid="push-enable"
          @click="push.enable()"
        >
          {{ push.state.value === 'enabled'
            ? '已开启' : push.state.value === 'denied'
              ? '权限被拒' : push.state.value === 'enabling'
                ? '开启中…' : '开启推送' }}
        </button>
      </div>
      <p class="mt-1 text-xs text-gray-400 dark:text-gray-500">
        隐私模式：锁屏只显示事件类型与计数，不含标的与金额（FR-NOTIFY-003）。
      </p>
    </section>

    <section class="rounded-lg bg-white p-4 shadow-sm dark:bg-gray-800">
      <h2 class="text-h3 font-semibold">
        风险阈值
      </h2>
      <dl
        v-if="riskRows.length"
        class="mt-2 space-y-2 text-sm"
      >
        <div
          v-for="row in riskRows"
          :key="row.key"
          class="flex justify-between"
        >
          <dt class="text-gray-500">
            {{ row.label }}
          </dt>
          <dd
            class="num"
            data-num
          >
            {{ row.value }}
          </dd>
        </div>
      </dl>
      <p
        v-else-if="riskSettingsOk"
        class="mt-2 text-sm text-gray-400"
      >
        暂无配置
      </p>
    </section>

    <!-- 子页入口（波 V4：SET-01~08 落点） -->
    <section class="rounded-lg bg-white p-2 shadow-sm dark:bg-gray-800">
      <div
        v-for="item in SUB_PAGES"
        :key="item.to"
      >
        <router-link
          :to="item.to"
          class="flex items-center justify-between rounded-md px-3 py-3 text-body text-gray-700 no-underline hover:bg-gray-50 dark:text-gray-200 dark:hover:bg-gray-700"
          :data-testid="`goto-${item.to.slice(1).replaceAll('/', '-')}`"
        >
          <span class="flex items-center gap-2.5">
            <span
              :class="[item.icon, 'text-xl text-gray-400']"
              aria-hidden="true"
            />
            {{ item.label }}
          </span>
          <span
            class="i-carbon-chevron-right text-xl text-gray-300"
            aria-hidden="true"
          />
        </router-link>
      </div>
    </section>

    <button
      type="button"
      class="w-full appearance-none rounded-lg border border-gray-200 bg-transparent py-3 text-body font-medium text-gray-600 dark:border-gray-700 dark:text-gray-300"
      data-testid="logout"
      @click="logout"
    >
      退出登录
    </button>
  </div>
</template>
