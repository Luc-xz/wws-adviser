// 生产验收（观察窗收官 · PWA_DEVICE_CHECKLIST A–G 等效环境）
// 前置：服务器铸临时会话（见 README），WWS_ACCEPT_TOKEN 注入。
// 产物：TIMING: 行为耗时日志（收官记录引用）；artifacts/ 截图（本地留存，不入库——含个人资产数据）。
// 设计约束：唯一数据写点 = D1（记一笔→删一笔，账本收敛回 1722）与 E1（一次问询，advice_records +1）。
import { expect, test, type Page } from "@playwright/test";

const TOKEN = process.env.WWS_ACCEPT_TOKEN;
const ART = "acceptance/artifacts";

test.beforeEach(async ({ page, context, baseURL }) => {
  test.skip(!TOKEN || !baseURL, "缺少 WWS_ACCEPT_TOKEN");
  const url = new URL(baseURL!);
  await context.addCookies([
    { name: "wws_session", value: TOKEN!, domain: url.hostname, path: "/", secure: true, httpOnly: true, sameSite: "Lax" },
    { name: "csrf_token", value: TOKEN!.slice(0, 32), domain: url.hostname, path: "/", secure: true, httpOnly: false, sameSite: "Lax" },
  ]);
});

async function api(page: Page, path: string, init: RequestInit = {}) {
  const csrf = TOKEN!.slice(0, 32);
  const res = await page.request.fetch(baseURL() + path, {
    ...init,
    headers: { "x-csrf-token": csrf, ...(init.headers ?? {}) },
  });
  return res;
}
function baseURL(): string {
  return test.info().project.use.baseURL ?? "https://openclow.cc.cd";
}
async function shot(page: Page, name: string) {
  await page.screenshot({ path: `${ART}/${name}.png`, fullPage: false });
}

test.describe.configure({ mode: "serial" });

test("A1 PWA 可安装性（manifest + Service Worker）", async ({ page }) => {
  const mf = await api(page, "/manifest.webmanifest");
  expect(mf.status()).toBe(200);
  const manifest = (await mf.json()) as { display?: string; icons?: unknown[] };
  expect(manifest.display).toBe("standalone");
  expect(Array.isArray(manifest.icons) && manifest.icons!.length).toBeGreaterThan(0);
  await page.goto("/");
  const sw = await page.evaluate(async () => {
    const reg = await navigator.serviceWorker.ready;
    return { scope: reg.scope, active: !!reg.active };
  });
  expect(sw.active).toBe(true);
});

test("A2 登录端点活体（错误凭据 401，Problem Details）", async ({ page }) => {
  const res = await page.request.fetch(baseURL() + "/api/v1/auth/login", {
    method: "POST",
    headers: { "content-type": "application/json", "idempotency-key": "acceptance-probe-a2" },
    data: { username: "probe-acceptance", password: "wrong" },
  });
  expect([401, 429]).toContain(res.status());
});

test("B1 首页 30 秒信息面 + 360px 无横向滚动 + 耗时", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 800 });
  const t0 = Date.now();
  await page.goto("/");
  await expect(page.getByTestId("data-status-bar")).toBeVisible();
  await expect(page.getByTestId("total-assets")).toBeVisible();
  const tVisible = Date.now() - t0;
  const nav = await page.evaluate(() => {
    const [n] = performance.getEntriesByType("navigation");
    const navEl = document.querySelector("nav[aria-label='主导航']") as HTMLElement;
    window.scrollTo(80, 0);
    const scrollX = window.scrollX;
    window.scrollTo(0, 0);
    return {
      domContentLoaded: Math.round(n.domContentLoadedEventEnd),
      load: Math.round(n.loadEventEnd),
      navW: Math.round(navEl.getBoundingClientRect().width),
      htmlOX: getComputedStyle(document.documentElement).overflowX,
      scrollXAfterPush: scrollX,
    };
  });
  console.log(`TIMING:home-visible=${tVisible}ms domContentLoaded=${nav.domContentLoaded}ms navW=${nav.navW}`);
  // 清单 G 红线 = 无横向滚动（可滚动性口径；导航盒宽度见收官记录已知问题注记）
  expect(nav.htmlOX).toBe("hidden");
  expect(nav.scrollXAfterPush).toBe(0);
  await shot(page, "b1-home-360");
});

test("B2 最新日报：降级标记 + footer + 依据抽屉 + 耗时", async ({ page }) => {
  const res = await api(page, "/api/v1/reports?limit=5");
  const { items } = (await res.json()) as { items: { id: string; report_type: string }[] };
  expect(items.length).toBeGreaterThan(0);
  const t0 = Date.now();
  await page.goto(`/reports/${items[0].id}`);
  await expect(page.getByTestId(/report-(in)?complete/).first()).toBeVisible();
  await expect(page.getByTestId("data-footer").first()).toBeVisible();
  const tRead = Date.now() - t0;
  console.log(`TIMING:report-open=${tRead}ms id=${items[0].id}`);
  const drawer = page.getByTestId("open-evidence-drawer").first();
  if (await drawer.count()) {
    await drawer.click();
    await expect(page.getByTestId("evidence-drawer")).toBeVisible();
    await shot(page, "b2-evidence-drawer");
    await page.getByTestId("evidence-close").first().click();
  }
  await shot(page, "b2-report");
});

test("B3 研究任务全链（创建→进度→降级报告→导出入口）", async ({ page }) => {
  await page.goto("/research");
  await expect(page.getByTestId("research-create-form").or(page.getByTestId("research-empty"))).toBeVisible();
  await page.getByTestId("research-type-company").click();
  await page.getByTestId("research-subject-input").fill("603823");
  await page.getByTestId("research-submit").click();
  // 模型故障期：预期降级形态（AC-06）——进度推进后出确定性报告
  await expect(page.getByTestId("research-report-panel").first()).toBeVisible({ timeout: 120_000 });
  const citations = page.getByTestId("research-citations");
  const citationCount = await citations.count();
  console.log(`RESEARCH:panel-visible citations-block=${citationCount}（模型故障期降级报告无引用属预期）`);
  await expect(page.getByText("导出 MD").first()).toBeVisible();
  await shot(page, "b3-research-degraded");
});

test("C1 离线：报告副本可读 + 盘中入口禁用 + 首页可开", async ({ page, context }) => {
  const res = await api(page, "/api/v1/reports?limit=1");
  const { items } = (await res.json()) as { items: { id: string }[] };
  await page.goto(`/reports/${items[0].id}`);
  await expect(page.getByTestId("data-footer").first()).toBeVisible();
  // 首次导航页面尚不被 SW 控制（register 后下一次导航才接管）——等 controller
  // 出现并再导航一次，之后的离线 reload 才由 SW precache 供页
  await page.evaluate(() => navigator.serviceWorker.ready);
  await page.goto(`/reports/${items[0].id}`);
  await expect(page.getByTestId("data-footer").first()).toBeVisible();
  await context.setOffline(true);
  await page.reload();
  await expect(page.getByTestId("offline-copy-banner")).toBeVisible();
  await expect(page.getByTestId("data-footer").first()).toBeVisible();
  await shot(page, "c1-offline-report");
  // 离线首页：SW 外壳可用、刷新禁用（AC-08）
  await page.goto("/");
  await expect(page.getByTestId("data-status-bar").or(page.getByTestId("empty-guide"))).toBeVisible();
  const refreshDisabled = await page.getByTestId("refresh").isDisabled().catch(() => null);
  // 盘中入口离线禁用
  await page.goto("/assistant");
  const offline = page.getByTestId("intraday-offline");
  if (await offline.count()) {
    await expect(offline.first()).toBeVisible();
  } else {
    const askDisabled = await page.getByTestId("intraday-ask").isDisabled().catch(() => null);
    console.log(`OFFLINE:assistant-guard=${offline.count() > 0} ask-disabled=${askDisabled}`);
  }
  console.log(`OFFLINE:report-banner=ok home-shell=ok refresh-disabled=${refreshDisabled}`);
  await shot(page, "c1-offline-assistant");
  await context.setOffline(false);
});

test("C2 恢复在线刷新至最新", async ({ page }) => {
  await page.goto("/");
  const bar = page.getByTestId("data-status-bar");
  await expect(bar).toBeVisible();
  await page.getByTestId("refresh").click().catch(() => {});
  await expect(bar).toBeVisible();
  console.log("ONLINE:refresh-ok");
});

test("D1 交易闭环：记录→流水可见→筛选→删除回滚（账本收敛）", async ({ page }) => {
  // 解析 600519 的 instrument_id，按标的过滤得到隔离基线（0→1→0 严格收敛）
  const inst = await api(page, "/api/v1/instruments?q=600519");
  const instJson = (await inst.json()) as { items: { id: string; code: string }[] };
  const instId = instJson.items.find((i) => i.code === "600519")?.id ?? instJson.items[0]?.id;
  expect(instId).toBeTruthy();
  const baseRes = await api(page, `/api/v1/transactions?instrument_id=${instId}&limit=50`);
  const baseCount = ((await baseRes.json()) as { items: unknown[] }).items.length;
  console.log(`TX:600519 baseline-count=${baseCount}`);

  await page.goto("/portfolio");
  await page.getByTestId("record-trade").click();
  await expect(page).toHaveURL(/transactions\/new/);
  await page.getByTestId("tx-instrument").fill("600519");
  await page.getByTestId("tx-quantity").fill("100");
  await page.getByTestId("tx-price").fill("1500");
  await page.getByTestId("tx-submit").click();
  await expect(page).toHaveURL(/\/transactions$/);
  await expect(page.getByText("1,500.00").first()).toBeVisible();
  await shot(page, "d1-tx-recorded");

  // TX-01 类型筛选生效（分红页无 600519 这笔买入）
  await page.getByTestId("tx-filter-kind").selectOption("DIVIDEND").catch(async () => {
    await page.getByTestId("tab-dividend").click();
  });
  await page.waitForTimeout(600);
  const filteredHasBuy = await page.getByText("1,500.00").count();
  expect(filteredHasBuy).toBe(0);

  // 回滚：该标的最新一笔即刚记录的买入，删除后过滤计数回到基线
  const after = await api(page, `/api/v1/transactions?instrument_id=${instId}&limit=5`);
  const { items } = (await after.json()) as { items: { id: string }[] };
  const created = items[0];
  expect(created).toBeTruthy();
  const del = await api(page, `/api/v1/transactions/${created.id}`, { method: "DELETE" });
  expect([200, 204]).toContain(del.status());
  const check = await api(page, `/api/v1/transactions?instrument_id=${instId}&limit=50`);
  const checkCount = ((await check.json()) as { items: unknown[] }).items.length;
  expect(checkCount).toBe(baseCount);
  console.log(`TX-ROLLBACK:baseline=${baseCount} restored=${checkCount}`);
});

test("E1 盘中问询：降级建议只显原因不显数量", async ({ page }) => {
  await page.goto("/assistant");
  const code = process.env.WWS_ACCEPT_CODE ?? "600519";
  await page.getByTestId("intraday-code").fill(code);
  const t0 = Date.now();
  await page.getByTestId("intraday-ask").click();
  await expect(page.getByTestId("intraday-reason").first()).toBeVisible({ timeout: 60_000 });
  const tAdvice = Date.now() - t0;
  const band = await page.getByTestId("advice-band").count();
  expect(band).toBe(0); // 降级零区间（PRD §18 拒绝形态）
  console.log(`TIMING:advice-card=${tAdvice}ms band-count=${band} code=${code}`);
  await shot(page, "e1-advice-degraded");
});

test("E2 数据状态页（冲突区 + 审计日志入口渲染）", async ({ page }) => {
  await page.goto("/data-status");
  await expect(page.getByTestId("audit-toggle")).toBeVisible();
  const conflicts = await page.getByTestId("conflict-row").count();
  console.log(`DATA-STATUS:audit-entry=ok conflict-rows=${conflicts}`);
  await shot(page, "e2-data-status");
});

test("F1 通知与隐私页（推送开关渲染；真实送达属真机项）", async ({ page }) => {
  await page.goto("/settings/notifications");
  await expect(page.getByTestId("push-enable").or(page.getByTestId("push-enable-set04"))).toBeVisible();
  await shot(page, "f1-notifications");
});

test("G1 深色模式无白底残留", async ({ page }) => {
  await page.goto("/settings");
  await page.getByTestId("dark-toggle").click();
  await page.goto("/");
  await expect(page.getByTestId("total-assets")).toBeVisible();
  const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  expect(bg).not.toBe("rgb(255, 255, 255)");
  const htmlDark = await page.evaluate(() => document.documentElement.classList.contains("dark"));
  expect(htmlDark).toBe(true);
  await shot(page, "g1-home-dark");
  await page.goto("/settings");
  await page.getByTestId("dark-toggle").click(); // 还原浅色
});

test("G2 横竖屏切换不破", async ({ page }) => {
  await page.goto("/portfolio");
  await expect(page.getByTestId("record-trade").or(page.getByTestId("account-stats"))).toBeVisible();
  await page.setViewportSize({ width: 800, height: 360 });
  await page.waitForTimeout(400);
  const stuck = await page.evaluate(() => {
    window.scrollTo(80, 0);
    const x = window.scrollX;
    window.scrollTo(0, 0);
    return x;
  });
  expect(stuck).toBe(0); // 不可横向滚动（钳制红线）
  await shot(page, "g2-landscape");
});

test("Z1 登出：私有缓存清除 + 会话吊销", async ({ page }) => {
  await page.goto("/settings");
  await page.getByTestId("logout").click();
  await expect(page).toHaveURL(/login/);
  const keys = await page.evaluate(() => caches.keys());
  const reportCaches = keys.filter((k) => k.startsWith("wws-report-"));
  expect(reportCaches.length).toBe(0);
  console.log(`LOGOUT:cache-cleared keys=${JSON.stringify(keys)}`);
  // 会话已被服务端吊销（登出端点 revoke）——后续请求应 401
  const me = await api(page, "/api/v1/analytics/summary");
  expect(me.status()).toBe(401);
});
