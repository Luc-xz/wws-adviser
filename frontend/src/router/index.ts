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
      meta: { requiresAuth: true, title: "首页" },
    },
    // PORT-01 持仓与自选
    {
      path: "/portfolio",
      name: "portfolio",
      component: () => import("@/features/portfolio/pages/Portfolio.vue"),
      meta: { requiresAuth: true, title: "持仓与自选" },
    },
    // REP-01/REP-02 报告详情（开市前/收市后共用，按 report_type 区分）
    {
      path: "/reports/:id",
      name: "report-detail",
      component: () => import("@/features/reports/pages/ReportDetail.vue"),
      meta: { requiresAuth: true, title: "报告" },
    },
    // DATA-01 数据状态中心（DataStatusBar 跳转目标）
    {
      path: "/data-status",
      name: "data-status",
      component: () => import("@/features/data/pages/DataStatus.vue"),
      meta: { requiresAuth: true, title: "数据状态" },
    },
    // CHAT-01 助手首页/对话
    {
      path: "/assistant",
      name: "assistant",
      component: () => import("@/features/assistant/pages/Assistant.vue"),
      meta: { requiresAuth: true, title: "助手" },
    },
    // LIB-01 研究与报告库
    {
      path: "/research",
      name: "research",
      component: () => import("@/features/research/pages/Library.vue"),
      meta: { requiresAuth: true, title: "研究" },
    },
    // SET-00 设置首页
    {
      path: "/settings",
      name: "settings",
      component: () => import("@/features/settings/pages/Settings.vue"),
      meta: { requiresAuth: true, title: "设置" },
    },
  ],
});

// 会话探针只跑一次：硬刷新/直链进受保护页时，守卫须等 cookie 会话探明再判
// （否则有效会话也被踢回登录页——PWA 重开必现，波V3 走查发现）
let sessionProbed = false;

router.beforeEach(async (to) => {
  if (to.meta.requiresAuth) {
    const session = useSessionStore();
    if (!session.isAuthenticated && !sessionProbed) {
      sessionProbed = true;
      await session.fetchSession();
    }
    if (!session.isAuthenticated) {
      return { name: "login", query: { redirect: to.fullPath } };
    }
  }
});

// 文档标题跟随路由（顶栏面包屑同源 meta.title）
router.afterEach((to) => {
  const title = to.meta.title as string | undefined;
  document.title = title ? `${title} · WWS Adviser` : "WWS Adviser";
});

export default router;
