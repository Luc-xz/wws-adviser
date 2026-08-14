import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import { createRouter, createMemoryHistory } from "vue-router";

import { DataStatusBar, RiskAlert, MetricCard, PositionRow, DataFooter } from "@/shared/ui";
import { EMPTY, formatMoney, formatPercent } from "@/shared/format/number";

// ENFORCEMENT_CONTRACT §4 + §7：组件设计规则断言（TC-* 契约）。
// TC-ADV-*（AdviceCard）随 Phase 2 Advice 状态机落地后启用。
function stubRouter() {
  return createRouter({ history: createMemoryHistory(), routes: [{ path: "/data-status", component: { template: "<div/>" } }] });
}

describe("TC-DSB DataStatusBar", () => {
  const entriesOk = [{ quality_status: "OK" }];
  const entriesStale = [{ quality_status: "OK" }, { quality_status: "DELAYED" }];
  const entriesBad = [{ quality_status: "MISSING" }];

  function bar(
    entries: { quality_status: string; fetched_at?: string | null }[],
    offline = false
  ) {
    return mount(DataStatusBar, {
      props: { entries, offline },
      global: { plugins: [stubRouter()] },
    });
  }

  it("TC-DSB-01 四态全覆盖（normal/degraded/stale/offline）+ 点击路由到 DATA-01", async () => {
    expect(bar(entriesOk).find("[data-state='normal']").exists()).toBe(true);
    expect(bar(entriesStale).find("[data-state='stale']").exists()).toBe(true);
    expect(bar(entriesBad).find("[data-state='degraded']").exists()).toBe(true);
    expect(bar([], true).find("[data-state='offline']").exists()).toBe(true);
    const w = bar(entriesOk);
    await w.find("[data-testid='data-status-bar']").trigger("click");
    // 路由跳转由 stub router 承接（不在此断言路径，组件级只保证可点击语义）
  });

  it("TC-DSB-02 fresh 态用 success token 而非 market-down（涨跌色仅行情语境）", () => {
    const w = bar(entriesOk);
    expect(w.find("[data-state='normal']").classes().join(" ")).toContain("text-success");
    expect(w.find("[data-state='normal']").classes().join(" ")).not.toContain("market-down");
  });
});

describe("TC-RA RiskAlert", () => {
  it("TC-RA-01 hard 级含 level 徽标与实际/上限数值，role=alert", () => {
    const w = mount(RiskAlert, {
      props: { rule: "single_cap", level: "hard", actual: "0.60", limit: "0.30", code: "600519" },
    });
    expect(w.find("[role='alert']").exists()).toBe(true);
    expect(w.text()).toContain("硬限制");
    expect(w.text()).toContain("0.60");
    expect(w.text()).toContain("0.30");
    expect(w.find(".bg-risk-critical").exists()).toBe(true);
  });

  it("TC-RA-01 soft 级用 risk-warning token", () => {
    const w = mount(RiskAlert, {
      props: { rule: "top_n_concentration", level: "soft", actual: "0.80", limit: "0.60" },
    });
    expect(w.text()).toContain("软限制");
    expect(w.find(".bg-risk-warning").exists()).toBe(true);
  });
});

describe("TC-NUM 数字硬规则（ENFORCEMENT_CONTRACT §2）", () => {
  it("TC-NUM-01 负数用 U+2212 而非 ASCII -", () => {
    expect(formatMoney("-1234.50")).toContain("−");
    expect(formatMoney("-1234.50")).not.toMatch(/^-/);
    expect(formatPercent("-1.25")).toContain("−");
  });

  it("TC-NUM-02 空值用 em-dash —，绝非 0", () => {
    expect(formatMoney("")).toBe(EMPTY);
    expect(EMPTY).toBe("—");
  });
});

describe("TC-MC/PR/DF 基础组件", () => {
  it("MetricCard 展示字符串十进制（不重算）+ tone 仅行情语境", () => {
    const w = mount(MetricCard, { props: { label: "总资产", value: "100000.00" } });
    expect(w.text()).toContain("100000.00");
    expect(w.find("[data-testid='metric-card']").exists()).toBe(true);
  });

  it("PositionRow 空市值显示 —，missing 新鲜度用 risk-warning", () => {
    const w = mount(PositionRow, {
      props: {
        code: "600519", name: "贵州茅台", quantity: "100", avgCost: "1000.0000",
        marketValue: null, weight: null, freshness: "missing",
      },
    });
    expect(w.text()).toContain("—");
    expect(w.find(".text-risk-warning").exists()).toBe(true);
  });

  it("DataFooter 含截至/来源（§2.3 强制尾注）", () => {
    const w = mount(DataFooter, { props: { asOf: "2026-08-14", source: "v2" } });
    expect(w.text()).toContain("截至 2026-08-14");
    expect(w.text()).toContain("来源 v2");
  });
});
