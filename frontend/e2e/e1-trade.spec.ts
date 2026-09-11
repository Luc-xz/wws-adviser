// E1 核心链路：登录 → 持仓页"记录交易" → 表单（6 位代码直填）→ 保存 → 流水可见。
// 这是对 2026-09-11 "记录交易点击无效"事故的永久防回归（W1-1）。
import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test.describe("E1 记录交易链路", () => {
  test("持仓页入口 → 表单 → 保存 → 流水可见", async ({ page }) => {
    await login(page);

    await page.goto("/portfolio");
    await expect(page.getByTestId("record-trade")).toBeVisible();
    await page.getByTestId("record-trade").click();
    await expect(page).toHaveURL(/transactions\/new/);

    // 表单：6 位代码直填（W4 可用性修复：代码 → ID 自动解析）
    await page.getByTestId("tx-instrument").fill("600519");
    await page.getByTestId("tx-quantity").fill("10");
    await page.getByTestId("tx-price").fill("1600");
    await page.getByTestId("tx-submit").click();

    // 成功回流水页，新记录可见（数量/价格已格式化）
    await expect(page).toHaveURL(/\/transactions$/);
    await expect(page.getByText("贵州茅台").first()).toBeVisible();
    await expect(page.getByText("1,600.00").first()).toBeVisible();
    // 不应有提交错误
    await expect(page.getByTestId("tx-error")).toHaveCount(0);
  });

  test("不存在的代码给出明确错误（不静默）", async ({ page }) => {
    await login(page);
    await page.goto("/transactions/new");
    await page.getByTestId("tx-instrument").fill("999999");
    await page.getByTestId("tx-quantity").fill("10");
    await page.getByTestId("tx-price").fill("10");
    await page.getByTestId("tx-submit").click();
    await expect(page.getByTestId("tx-error")).toContainText("999999");
  });
});
