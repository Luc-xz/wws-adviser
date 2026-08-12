import { describe, it } from "vitest";

// ENFORCEMENT_CONTRACT §4 + §7：组件设计规则断言（TC-* 契约）。
// 波 4 组件未建，整组 skip；Phase 1 组件实现时逐条转红灯→绿灯。
describe.skip("设计硬规则（Phase 1 组件实现后启用）", () => {
  it("TC-ADV-02 AdviceCard pause 态不渲染 targetRange/数量/醒目按钮", () => {});
  it("TC-ADV-03 AdviceCard expired 态透明度≤60% + 红 Badge", () => {});
  it("TC-ADV-01 AdviceCard 6 动作色用 action-*，非 market-*", () => {});
  it("TC-DSB-01 DataStatusBar 4 态全覆盖，点击进 DATA-01 非 Toast", () => {});
  it("TC-DSB-02 DataStatusBar fresh 态用 status-online(teal) 非 market-down", () => {});
  it("TC-RA-01 RiskAlert critical 含 impact+action，非空错误码", () => {});
  it("TC-NUM-01 负数用 U+2212 而非 ASCII -", () => {});
  it("TC-NUM-02 空值用 em-dash —", () => {});
});
