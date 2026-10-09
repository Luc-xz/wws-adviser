// 生产验收配置（PWA_DEVICE_CHECKLIST A–G 等效环境执行）
// 与本地门禁 e2e/ 目录隔离：不启本地服务，直连生产 HTTPS。
// 用法：
//   WWS_ACCEPT_TOKEN=<会话 token> pnpm exec playwright test -c acceptance/playwright.acceptance.ts
// 会话铸造/吊销见 acceptance/README.md（token 永不入库）。
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: ".",
  timeout: 90_000,
  expect: { timeout: 25_000 }, // 公网隧道延迟抖动，放宽默认断言等待
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.WWS_ACCEPT_BASE ?? "https://openclow.cc.cd",
    trace: "retain-on-failure",
    screenshot: "off",
  },
  projects: [{ name: "mobile", use: { ...devices["Pixel 5"] } }],
});
