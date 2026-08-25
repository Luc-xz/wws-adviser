// CHAT-01 盘中建议页契约（Phase 2）：降级只显示原因不显示仓位数字；
// 发布形态显示区间/轨迹/有效期；错误不静默。
import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount, flushPromises } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";

const mockFetch = vi.hoisted(() => ({ fetchIntradayAdvice: vi.fn() }));

vi.mock("@/features/assistant/composables/queries", () => mockFetch);

import Assistant from "@/features/assistant/pages/Assistant.vue";

function mkRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/assistant", component: Assistant },
      { path: "/", component: { template: "<div/>" } },
    ],
  });
}

function mountPage() {
  return mount(Assistant, { global: { plugins: [mkRouter()] } });
}

const SUSPEND_ADVICE = {
  advice_id: "a1",
  signal_id: "",
  code: "600519",
  action: "suspend",
  state: "degraded",
  valid_from: "2026-08-25T01:00:00+00:00",
  expires_at: "2026-08-25T01:05:00+00:00",
  actionable: false,
  trigger_conditions: [],
  invalidated: false,
  invalidation_reasons: [],
  f_min: null,
  f_max: null,
  value_min: null,
  value_max: null,
  suggested_lots: null,
  reasons: ["no_calibrated_signal", "ledger_unreconciled"],
  evidence_ids: [],
  trail: [],
};

const PUBLISHED_ADVICE = {
  ...SUSPEND_ADVICE,
  action: "buy",
  state: "published",
  actionable: true,
  signal_id: "breakout-20",
  f_min: "0.02",
  f_max: "0.05",
  value_min: "2000",
  value_max: "5000",
  suggested_lots: 5,
  reasons: ["low_confidence"],
  trail: [
    { kind: "fractional_discount", note: "×0.20", before: "0.28", after: "0.056" },
    { kind: "clip_single_cap", note: "单标的上限", before: "5600", after: "5000" },
  ],
};

describe("Assistant 盘中建议页", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("降级建议：显示原因码中文释义，不显示任何仓位数字", async () => {
    mockFetch.fetchIntradayAdvice.mockResolvedValue(SUSPEND_ADVICE);
    const w = mountPage();
    await w.find('[data-testid="intraday-code"]').setValue("600519");
    await w.find('[data-testid="intraday-ask"]').trigger("submit");
    await flushPromises();

    expect(w.find('[data-testid="intraday-action-suspend"]').exists()).toBe(true);
    const reasons = w.findAll('[data-testid="intraday-reason"]');
    expect(reasons.length).toBe(2);
    expect(reasons[0].text()).toContain("无已校准信号");
    // 降级形态绝无区间区块
    expect(w.text()).not.toContain("建议仓位区间");
  });

  it("发布建议：显示区间、手数与调整轨迹", async () => {
    mockFetch.fetchIntradayAdvice.mockResolvedValue(PUBLISHED_ADVICE);
    const w = mountPage();
    await w.find('[data-testid="intraday-code"]').setValue("600519");
    await w.find('[data-testid="intraday-ask"]').trigger("submit");
    await flushPromises();

    expect(w.find('[data-testid="intraday-action-buy"]').exists()).toBe(true);
    expect(w.text()).toContain("建议仓位区间");
    const trail = w.findAll('[data-testid="intraday-trail"]');
    expect(trail.length).toBe(2);
    expect(trail[0].text()).toContain("分数凯利折扣");
    expect(trail[1].text()).toContain("单标的上限约束");
    expect(w.text()).toContain("5"); // 建议手数
  });

  it("请求失败：错误可见（不静默）", async () => {
    mockFetch.fetchIntradayAdvice.mockRejectedValue(new Error("盘中建议获取失败"));
    const w = mountPage();
    await w.find('[data-testid="intraday-code"]').setValue("600519");
    await w.find('[data-testid="intraday-ask"]').trigger("submit");
    await flushPromises();

    expect(w.find('[data-testid="intraday-error"]').text()).toContain("获取失败");
  });
});
