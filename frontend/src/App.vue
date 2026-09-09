<script setup lang="ts">
import { computed, onMounted } from "vue";
import { useRoute } from "vue-router";

import { AppShellDesktop } from "@/shared/ui";
import { useSessionStore } from "@/stores/session";

const session = useSessionStore();
const route = useRoute();
// 启动时探一次会话（cookie 有效则直接进入，否则跳登录）
onMounted(() => session.fetchSession());

// 登录页独立成屏（品牌表达），不套应用外壳
const bareLayout = computed(() => route.path === "/login");

const NAV_ITEMS = [
  { to: "/", title: "首页", icon: "i-carbon-home" },
  { to: "/portfolio", title: "持仓", icon: "i-carbon-portfolio" },
  { to: "/assistant", title: "助手", icon: "i-carbon-chat-bot" },
  { to: "/research", title: "研究", icon: "i-carbon-analytics" },
  { to: "/settings", title: "设置", icon: "i-carbon-settings" },
] as const;
</script>

<template>
  <router-view v-if="bareLayout" />

  <div
    v-else
    class="min-h-screen pb-[calc(64px+env(safe-area-inset-bottom))] lg:flex lg:pb-0"
  >
    <!-- 桌面外壳：侧栏 224px + 顶栏 64px（组件内部 hidden lg:flex） -->
    <AppShellDesktop />

    <!-- 主内容：桌面让位侧栏/顶栏，最大 1200px 居中（UI §5.2，左右 padding 32px） -->
    <main class="p-4 lg:mt-16 lg:ml-56 lg:w-[calc(100%-14rem)] lg:max-w-[75rem] lg:mx-auto lg:p-8">
      <router-view />
    </main>

    <!-- 移动底导航（UI §5.1：视觉高 64px + 安全区；图标 22px + 12px 标签） -->
    <nav
      class="fixed bottom-0 left-0 right-0 z-10 flex border-t border-gray-200 bg-white pb-[env(safe-area-inset-bottom)] dark:border-gray-700 dark:bg-gray-800 lg:hidden"
      aria-label="主导航"
    >
      <router-link
        v-for="item in NAV_ITEMS"
        :key="item.to"
        :to="item.to"
        class="flex flex-1 flex-col items-center justify-center gap-0.5 py-2 text-caption text-gray-500 no-underline dark:text-gray-400"
        exact-active-class="!text-primary font-medium"
      >
        <span
          :class="[item.icon, 'text-[22px] leading-none']"
          aria-hidden="true"
        />
        {{ item.title }}
      </router-link>
    </nav>
  </div>
</template>
