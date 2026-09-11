// E2E 公共助手：登录 + 常用跳转。
import { expect, type Page } from "@playwright/test";

export async function login(page: Page): Promise<void> {
  await page.goto("/login");
  await page.locator("input").nth(0).fill("alice");
  await page.locator("input").nth(1).fill("pw12345");
  await page.getByRole("button", { name: /登录|进入/ }).click();
  await expect(page).not.toHaveURL(/login/);
}
