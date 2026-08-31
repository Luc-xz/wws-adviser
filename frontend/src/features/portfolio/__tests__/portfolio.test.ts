// PORT-01 三 Tab 契约（技术债清理：流水/自选留白落地）：Tab 切换、流水渲染、
// 自选增删校验。通过 vi.mock 屏蔽 queries 组合式（不依赖服务端）。
import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";
import { ref } from "vue";

const mockQueries = vi.hoisted(() => ({
  usePositions: vi.fn(),
  useRisk: vi.fn(),
  usePositionsHistory: vi.fn(),
  useTransactions: vi.fn(),
  useInstrumentMap: vi.fn(),
  useWatchlist: vi.fn(),
  useWatchQuotes: vi.fn(),
  useSaveWatchlist: vi.fn(),
}));

vi.mock("@/features/home/composables/queries", () => ({
  usePositions: mockQueries.usePositions,
  useRisk: mockQueries.useRisk,
}));
vi.mock("../composables/queries", () => mockQueries);

import Portfolio from "@/features/portfolio/pages/Portfolio.vue";

function mountPage() {
  return mount(Portfolio, {
    global: {
      plugins: [[VueQueryPlugin, { queryClient: new QueryClient() }]],
    },
  });
}

// 与真实组合式一致：data 必须是真 ref（模板自动解包 / script 手动 .value）
const okQuery = (data: unknown) => ({ data: ref(data), isSuccess: true, isLoading: false });

beforeEach(() => {
  mockQueries.usePositions.mockReturnValue(
    okQuery({ items: [], cash: "60000", total_assets: "60000" })
  );
  mockQueries.useRisk.mockReturnValue(okQuery({ breaches: [] }));
  mockQueries.usePositionsHistory.mockReturnValue(okQuery({ items: [] }));
  mockQueries.useTransactions.mockReturnValue(okQuery({ items: [], has_more: false }));
  const instMap = new Map([
    ["i1", { id: "i1", code: "600519", name: "贵州茅台" }],
    ["600519", { id: "i1", code: "600519", name: "贵州茅台" }],
  ]);
  mockQueries.useInstrumentMap.mockReturnValue({ data: { value: instMap } });
  mockQueries.useWatchlist.mockReturnValue(okQuery(["600519"]));
  mockQueries.useWatchQuotes.mockReturnValue({
    data: { value: [{ code: "600519", price: "1500.00", changePct: "1.20" }] },
    isLoading: false,
  });
  mockQueries.useSaveWatchlist.mockReturnValue({ mutate: vi.fn() });
});

describe("PORT-01 持仓 | 流水 | 自选", () => {
  it("默认持仓 Tab：空持仓显示引导，趋势卡无数据不渲染", async () => {
    const w = mountPage();
    await flushPromises();
    expect(w.find("[data-testid='tab-positions']").exists()).toBe(true);
    expect(w.find("[data-testid='empty-guide']").exists()).toBe(true);
    expect(w.find("[data-testid='realized-trend']").exists()).toBe(false);
  });

  it("流水 Tab：渲染交易行（方向徽标 + 数量价格费税）", async () => {
    mockQueries.useTransactions.mockReturnValue(
      okQuery({
        has_more: false,
        next_cursor: null,
        items: [
          {
            id: "t1",
            account_id: "a1",
            instrument_id: "i1",
            kind: "BUY",
            direction: "BUY",
            quantity: "100",
            price: "1500.00",
            fee: "5.00",
            tax: "0.00",
            trade_at: "2026-08-25T09:31:00+08:00",
            fingerprint: "f",
          },
        ],
      })
    );
    const w = mountPage();
    await flushPromises();
    await w.find("[data-testid='tab-transactions']").trigger("click");
    await flushPromises();
    const list = w.find("[data-testid='tx-list']");
    expect(list.exists()).toBe(true);
    expect(list.text()).toContain("买入");
    expect(list.text()).toContain("贵州茅台 600519");
    expect(list.text()).toContain("数量 100.00 @ 1,500.00");
  });

  it("自选 Tab：非 6 位代码输入被拒绝且不提交", async () => {
    const mutate = vi.fn();
    mockQueries.useSaveWatchlist.mockReturnValue({ mutate });
    const w = mountPage();
    await flushPromises();
    await w.find("[data-testid='tab-watchlist']").trigger("click");
    await flushPromises();

    const input = w.find("[data-testid='watch-input']");
    await input.setValue("60051A");
    await w.find("[data-testid='watch-add']").trigger("submit");
    await flushPromises();
    expect(w.find("[data-testid='watch-error']").text()).toContain("6 位数字代码");
    expect(mutate).not.toHaveBeenCalled();
  });

  it("自选 Tab：合法新代码追加提交（保序去重由后端负责）", async () => {
    const mutate = vi.fn();
    mockQueries.useSaveWatchlist.mockReturnValue({ mutate });
    const w = mountPage();
    await flushPromises();
    await w.find("[data-testid='tab-watchlist']").trigger("click");
    await flushPromises();

    await w.find("[data-testid='watch-input']").setValue("510300");
    await w.find("[data-testid='watch-add']").trigger("submit");
    await flushPromises();
    expect(mutate).toHaveBeenCalledWith(["600519", "510300"], expect.anything());
  });

  it("有持仓时持仓 Tab 渲染趋势卡（history 聚合）", async () => {
    mockQueries.usePositions.mockReturnValue(
      okQuery({
        items: [
          { instrument_id: "i1", code: "600519", name: "贵州茅台", quantity: "100", avg_cost: "1000", market_value: "120000", weight: "0.6", freshness: "2026-08-25" },
        ],
        cash: "60000",
        total_assets: "180000",
      })
    );
    mockQueries.usePositionsHistory.mockReturnValue(
      okQuery({
        items: [
          { business_date: "2026-08-24", instrument_id: "i1", quantity: "100", avg_cost: "1000", realized_pnl: "120" },
          { business_date: "2026-08-25", instrument_id: "i1", quantity: "100", avg_cost: "1000", realized_pnl: "200" },
        ],
      })
    );
    const w = mountPage();
    await flushPromises();
    expect(w.find("[data-testid='realized-trend']").exists()).toBe(true);
    expect(w.text()).toContain("累计已实现盈亏");
  });
});
