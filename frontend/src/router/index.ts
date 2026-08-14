import { createRouter, createWebHistory } from "vue-router";

import { useSessionStore } from "@/stores/session";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/login", name: "login", component: () => import("@/features/auth/pages/Login.vue") },
    // HOME-01 首页总览
    {
      path: "/",
      name: "home",
      component: () => import("@/features/home/pages/HomeOverview.vue"),
      meta: { requiresAuth: true },
    },
    // PORT-01 持仓与自选
    {
      path: "/portfolio",
      name: "portfolio",
      component: () => import("@/features/portfolio/pages/Portfolio.vue"),
      meta: { requiresAuth: true },
    },
    // REP-01/REP-02 报告详情（开市前/收市后共用，按 report_type 区分）
    {
      path: "/reports/:id",
      name: "report-detail",
      component: () => import("@/features/reports/pages/ReportDetail.vue"),
      meta: { requiresAuth: true },
    },
    // DATA-01 数据状态中心（DataStatusBar 跳转目标）
    {
      path: "/data-status",
      name: "data-status",
      component: () => import("@/features/data/pages/DataStatus.vue"),
      meta: { requiresAuth: true },
    },
    // CHAT-01 助手首页/对话
    {
      path: "/assistant",
      name: "assistant",
      component: () => import("@/features/assistant/pages/Assistant.vue"),
      meta: { requiresAuth: true },
    },
    // LIB-01 研究与报告库
    {
      path: "/research",
      name: "research",
      component: () => import("@/features/research/pages/Library.vue"),
      meta: { requiresAuth: true },
    },
    // SET-00 设置首页
    {
      path: "/settings",
      name: "settings",
      component: () => import("@/features/settings/pages/Settings.vue"),
      meta: { requiresAuth: true },
    },
  ],
});

router.beforeEach((to) => {
  if (to.meta.requiresAuth) {
    const session = useSessionStore();
    if (!session.isAuthenticated) {
      return { name: "login", query: { redirect: to.fullPath } };
    }
  }
});

export default router;
