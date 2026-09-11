// E3 盘中问询：对话流形态 + 降级原因人话透出（W2-3 / Q1 落地）。
import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test.describe("E3 盘中问询对话流", () => {
  test("问询 600519 → 建议卡含动作徽章与原因（降级时附设计行为说明）", async ({
    page,
  }) => {
    await login(page);
    await page.goto("/assistant");

    await expect(page.getByTestId("chat-empty")).toBeVisible();
    await page.getByTestId("intraday-code").fill("600519");
    await page.getByTestId("intraday-ask").click();

    // 用户气泡 + 助手建议卡
    await expect(page.getByText("盘中怎么操作？")).toBeVisible();
    await expect(
      page.locator('[data-testid^="intraday-action-"]').first(),
    ).toBeVisible({ timeout: 20_000 });

    // 降级原因可见（种子环境无校准/无行情，必为降级形态）
    const reasons = page.locator('[data-testid="intraday-reason"]');
    await expect(reasons.first()).toBeVisible();

    // suspend + no_calibrated_signal → 设计行为说明块
    const suspendBadge = page.getByTestId("intraday-action-suspend");
    if (await suspendBadge.isVisible()) {
      await expect(page.getByTestId("intraday-suspend-note")).toBeVisible();
      await expect(page.getByTestId("intraday-suspend-note")).toContainText(
        "设计行为",
      );
    }
  });

  test("离线时入口禁用（AC-08，重载式断言——不依赖事件时序）", async ({ page }) => {
    await login(page);
    await page.goto("/assistant");
    // 等 SW 激活（离线重载依赖预缓存壳；未激活时 reload 会网络级失败）
    await page.evaluate(() => navigator.serviceWorker.ready);
    await page.context().setOffline(true);
    // SW 预缓存壳可离线加载；navigator.onLine 初始即 false
    await page.reload();
    await expect(page.getByTestId("intraday-offline")).toBeVisible();
    await expect(page.getByTestId("intraday-ask")).toBeDisabled();
    await page.context().setOffline(false);
  });
});
