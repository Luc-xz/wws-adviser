// E4 报告离线：打开报告（写入私有缓存）→ 断网重载 → 离线副本横幅可见（AC-08）。
// E5 登出清缓存：登出后 Cache Storage 的 wws-report-* 全部清除（doc7 §3 规则 3）。
import { expect, test } from "@playwright/test";
import { login } from "./helpers";

async function openSeededReport(page: import("@playwright/test").Page): Promise<string | null> {
  await login(page);
  const res = await page.evaluate(async () => {
    const r = await fetch("/api/v1/reports", { credentials: "include" });
    if (!r.ok) return null;
    const body = (await r.json()) as { items?: { id: string }[] };
    return body.items?.[0]?.id ?? null;
  });
  return res;
}

test.describe("E4 报告离线", () => {
  test("断网后重载报告显示离线副本横幅", async ({ page }) => {
    const reportId = await openSeededReport(page);
    test.skip(!reportId, "种子未产出日报（非交易日运行），跳过离线链路");
    if (!reportId) return;

    await page.goto(`/reports/${reportId}`);
    await expect(page.getByTestId("report-complete").or(page.getByTestId("report-incomplete"))).toBeVisible();
    // 等私有缓存写入（useReport writeThrough）
    await page.waitForTimeout(1_500);

    await page.context().setOffline(true);
    await page.reload();
    await expect(page.getByText(/离线副本/)).toBeVisible({ timeout: 15_000 });
    await page.context().setOffline(false);
  });
});

test.describe("E5 登出清缓存", () => {
  test("登出后 wws-report-* 私有缓存清空", async ({ page }) => {
    const reportId = await openSeededReport(page);
    if (reportId) {
      await page.goto(`/reports/${reportId}`);
      await page.waitForTimeout(1_500); // 等缓存写入
    }

    await page.goto("/settings");
    await page.getByTestId("logout").click();
    await expect(page).toHaveURL(/login/);

    const reportCaches = await page.evaluate(async () => {
      if (!("caches" in window)) return [];
      const keys = await caches.keys();
      return keys.filter((k) => k.startsWith("wws-report-"));
    });
    expect(reportCaches).toEqual([]);
  });
});
