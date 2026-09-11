// W4 E2E（11_LAUNCH_QUALITY_PLAN 波次 W4，Q3 决策：本地门禁必跑）
// 环境：backend/scripts/e2e_server.py（种子 + uvicorn:8000）+ vite dev:5174（/api 代理）
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false, // 单实例后端共享状态，串行执行
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:5174",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: [
    {
      command: "uv run python scripts/e2e_server.py --port 8000",
      url: "http://127.0.0.1:8000/health/live",
      cwd: "../backend",
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: "pnpm build && pnpm exec vite preview --port 5174 --strictPort",
      url: "http://localhost:5174",
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
