// HOME-02 / CHAT-02 建议记录页契约（2026-09-10 补页）：
// 列表 = 当日分组 + 历史折叠 + 降级不显数字；详情 = 拒绝原因显式化 +
// 凯利一位小数 + 固定诚实旁注 + footer 句式（截至·来源·有效至）。
import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";
import { QueryClient, VueQueryPlugin } from "@tanstack/vue-query";

const mockAdvice = vi.hoisted(() => ({
  fetchAdviceRecords: vi.fn(),
  fetchAdviceRecord: vi.fn(),
  useAdviceRecord: vi.fn(),
}));

vi.mock("@/features/advice/composables/queries", () => mockAdvice);

const mockHome = vi.hoisted(() => ({ useRisk: vi.fn() }));
vi.mock("@/features/home/composables/queries", () => mockHome);

import { ref } from "vue";
import AdviceList from "@/features/advice/pages/AdviceList.vue";
import AdviceDetail from "@/features/advice/pages/AdviceDetail.vue";

function mkRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/", component: { template: "<div/>" } },
      { path: "/advice", component: AdviceList },
      { path: "/advice/:id", component: AdviceDetail },
    ],
  });
}

function mountList() {
  return mount(AdviceList, {
    global: { plugins: [mkRouter(), [VueQueryPlugin, { queryClient: new QueryClient() }]] },
  });
}

async function mountDetail(id = "rec1") {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/advice/:id", component: AdviceDetail }],
  });
  router.push(`/advice/${id}`);
  await router.isReady();
  return mount(AdviceDetail, {
    global: { plugins: [router, [VueQueryPlugin, { queryClient: new QueryClient() }]] },
  });
}

const okRef = (data: unknown) => ({ data: ref(data), isLoading: false, error: null });

const today = new Date().toISOString().slice(0, 10);
const SUSPEND_RECORD = {
  advice_id: "s1", signal_id: "", code: "600519", action: "suspend",
  state: "degraded",
  valid_from: `${today}T01:00:00+00:00`, expires_at: `${today}T01:10:00+00:00`,
  actionable: false, invalidated: false,
  f_min: null, f_max: null, value_min: null, value_max: null, suggested_lots: null,
  reasons: ["no_calibrated_signal"], evidence_ids: [], trail: [],
  model_explanation: null, verdict: null, evaluated_at: null, evaluation: null,
  created_at: `${today}T01:00:00+00:00`,
};

const PUBLISHED_RECORD = {
  ...SUSPEND_RECORD,
  advice_id: "p1", action: "buy", state: "published", actionable: true,
  signal_id: "breakout-20",
  f_min: "0.025", f_max: "0.030", value_min: "2500", value_max: "3000",
  suggested_lots: 2, reasons: [],
  trail: [
    { kind: "fractional_discount", note: "×0.20", before: "0.15", after: "0.03" },
    { kind: "clip_single_cap", note: "单标的上限", before: "3000", after: "3000" },
  ],
  verdict: "direction_correct", evaluated_at: "2026-09-28T08:30:00+00:00",
  evaluation: { spec_version: "1", reasons: ["窗口收益为正"], direction_return: "0.031", horizon: 5 },
};

describe("HOME-02 建议列表页", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockHome.useRisk.mockReturnValue(okRef({ breaches: [] }));
  });

  it("当日降级建议显示原因码释义，不显示任何仓位数字", async () => {
    mockAdvice.fetchAdviceRecords.mockResolvedValue({
      items: [SUSPEND_RECORD], next_cursor: null, has_more: false,
    });
    const w = mountList();
    await flushPromises();

    expect(w.find("[data-testid='advice-list']").exists()).toBe(true);
    expect(w.text()).toContain("无已校准信号");
    expect(w.text()).not.toContain("%"); // 降级形态无区间数字
  });

  it("非当日记录折叠进历史区，默认不可见", async () => {
    const old = {
      ...SUSPEND_RECORD,
      created_at: "2026-08-20T01:00:00+00:00",
    };
    mockAdvice.fetchAdviceRecords.mockResolvedValue({
      items: [old], next_cursor: null, has_more: false,
    });
    const w = mountList();
    await flushPromises();

    expect(w.find("[data-testid='advice-history-toggle']").exists()).toBe(true);
    expect(w.find("[data-testid='advice-history-list']").exists()).toBe(false);
    expect(w.text()).toContain("历史记录（1）");
  });

  it("空态：显示引导文案，不使用庆祝动画", async () => {
    mockAdvice.fetchAdviceRecords.mockResolvedValue({
      items: [], next_cursor: null, has_more: false,
    });
    const w = mountList();
    await flushPromises();

    expect(w.find("[data-testid='advice-empty']").exists()).toBe(true);
    expect(w.text()).toContain("当前没有需要处理的行动");
  });
});

describe("CHAT-02 建议详情页", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("发布形态：区间条 + 凯利摘要一位小数 + 固定诚实旁注 + footer 句式", async () => {
    mockAdvice.useAdviceRecord.mockReturnValue(okRef(PUBLISHED_RECORD));
    const w = await mountDetail();
    await flushPromises();

    // 区间条与一位小数（0.025 → 2.5%，反精确化）
    expect(w.find("[data-testid='advice-band']").exists()).toBe(true);
    expect(w.find("[data-testid='advice-band-range']").text()).toContain("2.5% ～ 3.0%");
    // 凯利折叠摘要：理论 0.15 → 风控后 2.5% ～ 3.0%
    expect(w.find("[data-testid='advice-kelly-summary']").text())
      .toContain("理论 15.0% → 风控后 2.5% ～ 3.0%");
    // 固定旁注（硬性，不得省略）
    expect(w.text()).toContain("基于历史信号回测的概率估计，存在样本与模型不确定性，仅作风险预算参考");
    // footer 句式：截至 · 来源 · 有效期至
    const footer = w.find("[data-testid='data-footer']").text();
    expect(footer).toContain("截至");
    expect(footer).toContain("来源 advice/p1");
    expect(footer).toContain("有效期至");
    // 评价回读
    expect(w.find("[data-testid='advice-verdict']").text()).toContain("方向正确");
  });

  it("降级形态：显式列出拒绝原因类别，无区间条无凯利区", async () => {
    mockAdvice.useAdviceRecord.mockReturnValue(okRef(SUSPEND_RECORD));
    const w = await mountDetail();
    await flushPromises();

    expect(w.find("[data-testid='advice-detail-action-suspend']").exists()).toBe(true);
    const reasons = w.findAll("[data-testid='advice-detail-reason']");
    expect(reasons).toHaveLength(1);
    expect(reasons[0].text()).toContain("无已校准信号");
    expect(w.find("[data-testid='advice-band']").exists()).toBe(false);
    expect(w.find("[data-testid='advice-kelly-toggle']").exists()).toBe(false);
    expect(w.find("[data-testid='advice-verdict-pending']").exists()).toBe(true);
  });
});
