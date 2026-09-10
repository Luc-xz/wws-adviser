// HOME-01 页面契约（ENFORCEMENT_CONTRACT TC-GS/离线规则）：空账户导入引导、绝不显示假 ¥0、
// 离线禁用刷新。通过 vi.mock 屏蔽 queries 组合式（不依赖服务端）。
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ref } from "vue";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";

const mockQueries = vi.hoisted(() => ({
  useSummary: vi.fn(),
  useRisk: vi.fn(),
  useMarketQuality: vi.fn(),
  usePositions: vi.fn(),
  useReports: vi.fn(),
}));

vi.mock("@/features/home/composables/queries", () => mockQueries);

import HomeOverview from "@/features/home/pages/HomeOverview.vue";

function mkRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/", component: HomeOverview },
      { path: "/portfolio", component: { template: "<div/>" } },
      { path: "/advice", component: { template: "<div/>" } },
      { path: "/data-status", component: { template: "<div/>" } },
    ],
  });
}

function mountHome() {
  return mount(HomeOverview, {
    global: {
      plugins: [mkRouter(), [VueQueryPlugin, { queryClient: new QueryClient() }]],
    },
  });
}

// 真 ref：模板对 setup 绑定的 ref 自动解包——平对象 {value} 不会解包，
// 曾使数值断言恒为 —（波V3 基准卡数值断言暴露）。
const okQuery = (data: unknown) => ({
  data: ref(data),
  isSuccess: true,
  isLoading: false,
});

beforeEach(() => {
  mockQueries.useSummary.mockReturnValue(okQuery(null));
  mockQueries.useRisk.mockReturnValue(okQuery({ breaches: [] }));
  mockQueries.useMarketQuality.mockReturnValue(okQuery({ items: [] }));
  mockQueries.usePositions.mockReturnValue(okQuery({ items: [], cash: "0", total_assets: "0" }));
  mockQueries.useReports.mockReturnValue(okQuery({ items: [] }));
});

describe("HOME-01 空账户与离线契约", () => {
  it("TC-GS-01 空账户渲染导入引导（empty-guide），绝不显示假 ¥0", async () => {
    mockQueries.useSummary.mockReturnValue(okQuery({ total_assets: "0", cash_ratio: "1" }));
    const w = mountHome();
    await flushPromises();
    expect(w.find("[data-testid='empty-guide']").exists()).toBe(true);
    expect(w.text()).not.toContain("¥0");
    expect(w.find("[data-testid='metric-card']").exists()).toBe(false);
  });

  it("TC-GS-02 summary 404（无账户）空标记 null 同样落导入引导，不落入数据模板", async () => {
    mockQueries.useSummary.mockReturnValue(okQuery(null));
    const w = mountHome();
    await flushPromises();
    expect(w.find("[data-testid='empty-guide']").exists()).toBe(true);
    // 数据模板以 total-assets 占位暴露（全 — 的假数据卡）
    expect(w.find("[data-testid='total-assets']").exists()).toBe(false);
  });

  it("离线（navigator.onLine=false）禁用刷新按钮", async () => {
    const spy = vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    mockQueries.useSummary.mockReturnValue(
      okQuery({ total_assets: "100000.00", cash_ratio: "0.40", pnl_total: "150" })
    );
    mockQueries.usePositions.mockReturnValue(
      okQuery({ items: [], cash: "60000", total_assets: "100000" })
    );
    const w = mountHome();
    await flushPromises();
    const btn = w.find("[data-testid='refresh']");
    expect(btn.exists()).toBe(true);
    expect(btn.attributes("disabled")).toBeDefined();
    spy.mockRestore();
  });

  it("有数据时渲染摘要卡与数据状态条", async () => {
    mockQueries.useSummary.mockReturnValue(
      okQuery({ total_assets: "100000.00", cash_ratio: "0.40", pnl_total: "150", concentration: "0.25" })
    );
    mockQueries.usePositions.mockReturnValue(
      okQuery({
        items: [
          { instrument_id: "i1", code: "600519", name: "贵州茅台", quantity: "100", avg_cost: "1000", market_value: "1200", weight: "0.012", freshness: "2026-08-13" },
        ],
        cash: "60000",
        total_assets: "100000",
      })
    );
    mockQueries.useMarketQuality.mockReturnValue(
      okQuery({ items: [{ quality_status: "OK" }] })
    );
    const w = mountHome();
    await flushPromises();
    // 波V3 基准卡：摘要为单张大卡（Display 总资产 + 盈亏 tone + 两列副指标）
    expect(w.find("[data-testid='total-assets']").text()).toContain("100000.00");
    expect(w.find("[data-testid='pnl-total']").text()).not.toBe("—");
    expect(w.find("[data-testid='risk-summary-bar']").exists()).toBe(false); // 无风险数据不出聚合条
    expect(w.find("[data-testid='data-status-bar']").exists()).toBe(true);
    expect(w.find("[data-testid='position-row']").exists()).toBe(true);
  });
});
