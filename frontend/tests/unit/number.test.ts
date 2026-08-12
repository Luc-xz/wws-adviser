import { describe, expect, it } from "vitest";

import { EMPTY, formatMoney, formatPercent } from "@/shared/format/number";

describe("§8 数字硬规则（ENFORCEMENT_CONTRACT §2.1）", () => {
  it("空值返回 em-dash，非 0 或空", () => {
    expect(formatMoney(null)).toBe(EMPTY);
    expect(formatMoney("")).toBe(EMPTY);
    expect(formatMoney(undefined)).toBe(EMPTY);
    expect(formatPercent(null)).toBe(EMPTY);
  });

  it("负数用 U+2212 而非 ASCII -", () => {
    const out = formatMoney("-1234.5");
    expect(out).toContain("\u2212");
    expect(out).not.toMatch(/^-\d/);
  });

  it("金额千分位 + 精度", () => {
    expect(formatMoney("328540")).toBe("328,540.00");
    expect(formatMoney("100")).toBe("100.00");
  });

  it("涨跌幅带符号", () => {
    expect(formatPercent("1.25")).toBe("+1.25%");
    expect(formatPercent("-1.25")).toBe("\u22121.25%");
    expect(formatPercent("0")).toBe("0.00%");
  });
});
