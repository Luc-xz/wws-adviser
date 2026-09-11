// E2 研究链路：语料前置提示 → 创建任务 → 列表可见。
// E6 依据抽屉：完成态研究报告 → 打开 EvidenceDrawer → 切片原文可读（AC-05）。
import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test.describe("E2 研究链路", () => {
  test("输入代码显示语料提示；创建任务入列", async ({ page }) => {
    await login(page);
    await page.goto("/research");

    await page.getByTestId("research-type-company").check();
    await page.getByTestId("research-subject-input").fill("600519");
    // 种子已含 600519 语料 → 提示语料条数（非低量警示）
    await expect(page.getByTestId("corpus-hint")).toContainText("语料", {
      timeout: 15_000,
    });

    await page.getByTestId("research-submit").click();
    // 任务入列（列表出现新任务行）
    await expect(page.getByTestId("research-task-row").first()).toBeVisible();
  });
});

test.describe("E6 依据抽屉", () => {
  test("完成态报告 → 打开抽屉 → 切片详情可读", async ({ page }) => {
    await login(page);
    await page.goto("/research");

    // 种子的完成态任务排在列表最前（created_at 最新）
    const doneRow = page
      .getByTestId("research-task-row")
      .filter({ hasText: "已完成" })
      .first();
    await doneRow.click();
    await expect(page.getByTestId("research-report-panel")).toBeVisible();
    await expect(page.getByTestId("research-citations")).toBeVisible();

    await page.getByTestId("open-evidence-drawer").click();
    await expect(page.getByTestId("evidence-drawer")).toBeVisible();

    const first = page.locator('[data-testid^="evidence-item-"]').first();
    await first.click();
    await expect(page.getByTestId("evidence-detail")).toBeVisible();
    // 追溯链内容：原文标题/切片原文/内容哈希三段至少出现其一关键词
    await expect(page.getByTestId("evidence-detail")).toContainText("原文");

    await page.getByTestId("evidence-close").click();
    await expect(page.getByTestId("evidence-drawer")).toBeHidden();
  });
});
