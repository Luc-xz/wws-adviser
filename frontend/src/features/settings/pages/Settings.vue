<script setup lang="ts">
// SET-00 设置首页（MVP）：风险阈值（GET /settings/risk）+ 登出（POST /auth/logout）
import { computed } from "vue";
import { useQuery, useQueryClient } from "@tanstack/vue-query";
import { useRouter } from "vue-router";
import client from "@/api/client";
import { useSessionStore } from "@/stores/session";

const session = useSessionStore();
const router = useRouter();
const qc = useQueryClient();

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
  <div class="space-y-3">
    <h1 class="text-lg font-semibold">
      设置
    </h1>

    <section class="rounded-xl bg-white p-4 shadow-sm">
      <h2 class="text-sm font-medium text-gray-600">
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

    <button
      type="button"
      class="w-full rounded-xl border border-gray-200 py-3 text-sm font-medium text-gray-600"
      data-testid="logout"
      @click="logout"
    >
      退出登录
    </button>
  </div>
</template>
