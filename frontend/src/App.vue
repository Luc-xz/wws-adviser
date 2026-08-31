<script setup lang="ts">
import { onMounted } from "vue";

import { useSessionStore } from "@/stores/session";

const session = useSessionStore();
// 启动时探一次会话（cookie 有效则直接进入，否则跳登录）
onMounted(() => session.fetchSession());
</script>

<template>
  <div class="app-shell">
    <nav
      class="nav"
      aria-label="主导航"
    >
      <router-link to="/">
        首页
      </router-link>
      <router-link to="/portfolio">
        持仓
      </router-link>
      <router-link to="/assistant">
        助手
      </router-link>
      <router-link to="/research">
        研究
      </router-link>
      <router-link to="/settings">
        设置
      </router-link>
    </nav>
    <main class="content">
      <router-view />
    </main>
  </div>
</template>

<style scoped>
.app-shell {
  min-height: 100vh;
  padding-bottom: calc(64px + env(safe-area-inset-bottom));
}
.nav {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  height: calc(64px + env(safe-area-inset-bottom));
  display: flex;
  background: var(--color-surface);
  border-top: 1px solid var(--color-border);
  padding-bottom: env(safe-area-inset-bottom);
  z-index: 10;
}
.nav a {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  text-decoration: none;
  color: var(--color-text-muted);
  font-size: 14px;
}
.nav a.router-link-active {
  color: var(--color-primary);
  font-weight: 600;
}
.content {
  padding: 16px;
}
@media (min-width: 1024px) {
  .app-shell {
    display: flex;
    padding-bottom: 0;
  }
  .nav {
    position: static;
    flex-direction: column;
    width: 224px;
    height: 100vh;
    border-top: none;
    border-right: 1px solid var(--color-border);
    padding-bottom: 0;
  }
  .nav a {
    padding: 16px 24px;
    justify-content: flex-start;
  }
  .content {
    flex: 1;
    padding: 32px;
    max-width: 1200px;
  }
}
</style>
