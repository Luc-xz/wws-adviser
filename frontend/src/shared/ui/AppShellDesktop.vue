<script setup lang="ts">
// 桌面外壳（UI §5.2，波 V2）：左侧导航 224px 固定 + 顶栏 64px。
// 主内容最大 1200px 居中由 App.vue 承担；本组件只管侧栏与顶栏。
import { computed } from "vue";
import { useRoute } from "vue-router";

import { useSessionStore } from "@/stores/session";

const route = useRoute();
const session = useSessionStore();

const NAV_ITEMS = [
  { to: "/", title: "首页", icon: "i-material-symbols-home-rounded" },
  { to: "/portfolio", title: "持仓", icon: "i-material-symbols-payments-rounded" },
  { to: "/assistant", title: "助手", icon: "i-material-symbols-smart-toy-rounded" },
  { to: "/research", title: "研究", icon: "i-material-symbols-monitoring-rounded" },
  { to: "/settings", title: "设置", icon: "i-material-symbols-settings-rounded" },
] as const;

const pageTitle = computed(() => (route.meta.title as string | undefined) ?? "");
</script>

<template>
  <aside class="hidden lg:flex fixed left-0 top-0 bottom-0 z-20 w-56 flex-col border-r border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-800">
    <!-- Logo 区（64px 与顶栏对齐） -->
    <div class="flex h-16 items-center gap-2 px-6">
      <span class="inline-block h-6 w-6 rounded-md bg-primary text-white text-label font-bold leading-6 text-center">W</span>
      <span class="text-h3 font-semibold">WWS Adviser</span>
    </div>
    <nav
      class="mt-2 flex-1 space-y-1 px-3"
      aria-label="主导航（桌面）"
    >
      <router-link
        v-for="item in NAV_ITEMS"
        :key="item.to"
        :to="item.to"
        class="flex items-center gap-3 rounded-md px-3 py-2.5 text-body text-gray-600 transition-colors hover:bg-gray-50 hover:text-text dark:text-gray-300 dark:hover:bg-gray-700"
        exact-active-class="!bg-primary/10 !text-primary font-medium"
      >
        <span
          :class="[item.icon, 'text-xl']"
          aria-hidden="true"
        />
        {{ item.title }}
      </router-link>
    </nav>
    <div class="border-t border-gray-200 px-6 py-3 text-caption text-gray-400 dark:border-gray-700">
      个人投资顾问 · 单账户
    </div>
  </aside>

  <!-- 顶栏：面包屑/页面标题 + 会话区 -->
  <header class="hidden lg:flex fixed left-56 right-0 top-0 z-10 h-16 items-center justify-between border-b border-gray-200 bg-white/90 px-8 backdrop-blur dark:border-gray-700 dark:bg-gray-800/90">
    <h1 class="truncate text-h3 font-semibold">
      {{ pageTitle }}
    </h1>
    <div class="flex items-center gap-3 text-label text-gray-500 dark:text-gray-400">
      <span
        v-if="session.isAuthenticated"
        class="inline-flex items-center gap-1.5"
        data-testid="topbar-session"
      >
        <span
          class="i-material-symbols-person-rounded text-xl"
          aria-hidden="true"
        />
        已登录
      </span>
      <router-link
        v-else
        to="/login"
        class="text-primary hover:underline"
      >
        登录
      </router-link>
    </div>
  </header>
</template>
