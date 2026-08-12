# ADR-0012：Frontend / PWA 工程默认决策

> 状态：Accepted
> 日期：2026-08-12
> 关联：[7_FRONTEND](../dev-guide/7_FRONTEND_AND_PWA.md) · [ENFORCEMENT_CONTRACT](../design-review/ENFORCEMENT_CONTRACT.md) · [UI §5/§7/§10.1](../UI_DESIGN_SPECIFICATION.md) · [技术架构 §14](../TECHNICAL_ARCHITECTURE.md)

## 上下文

波 4 从零建 frontend（Vue3 PWA）+ 登录 + 五导航 + OpenAPI 类型生成。文档定了工具链与设计契约，但具体版本组合、PWA 模式、页面深度、OpenAPI 生成方式多为"实现时定"。

## 决策

| 项 | 决策 | 理由 |
|---|---|---|
| 工具链版本 | vite 5 + vitest 2（非 6/3） | vitest 2 的 peer 是 vite 5；装 vite 6 导致双 vite 版本类型冲突（实测） |
| PWA 模式 | vite-plugin-pwa `generateSW` | 简单；`injectManifest` 留待需自定义 SW 时 |
| icon | 单 SVG（`purpose: any`） | 占位；Chrome 接受；PNG 192/512 留设计稿 |
| 五导航深度 | 路由 + 占位页面 | AC-08 只要求可安装+登录；业务页面 Phase 1/3 |
| OpenAPI 生成 | 后端 `export_openapi.py` 导出静态 `openapi.json` + 前端 `openapi-typescript` | CI 友好，不依赖后端运行 |
| 开发联调 | vite proxy `/api`,`/health` → `:8000` | 同源避免 CORS |
| request_id | `crypto.randomUUID()`（v4） | 浏览器原生；文档建议 v7 但 v4 唯一性足够，免装包 |
| ESLint | vue recommended + `@typescript-eslint/parser`（script 块）；TS 类型由 vue-tsc | 分工：eslint 管模板规则，vue-tsc 管类型 |
| 组件设计规则测试 | `describe.skip` 骨架（8 条 TC-*） | 6 核心组件 Phase 1 建，届时转红灯→绿灯 |
| session 探测 | App `onMounted` → `fetchSession` | cookie 有效直接进入，否则路由 guard 跳登录 |

## 备选方案

- **vite 6 + vitest 3**：放弃（vitest 3 当时稳定性未验证；vite 5 + vitest 2 成熟组合，实测无冲突）。
- **前端直连后端 :8000**：放弃（CORS 配置复杂；vite proxy 同源最简）。
- **完整五导航业务页面**：放弃（AC-08 不要求；HOME-01/PORT-01 等真实业务留 Phase 1/3，波 4 仅占位）。
- **request_id 用 uuid v7**：放弃（需额外包；v4 唯一性已满足关联用途）。

## 正负影响

**正向：**
- PWA 可安装（manifest+SW）+ 登录连后端（Argon2id+session+CSRF），AC-08 满足。
- OpenAPI 类型生成流打通，前端 `api/generated/types.ts` 类型安全，禁止手改。
- 前后端闭环验证：HomeOverview 调 `/api/v1/market-data/quotes` 显示 stub 行情。
- UnoCSS token 用 teal `online`（ADR-0009），ENFORCEMENT_CONTRACT 落地。

**负向 / 代价：**
- 单 SVG icon：Chrome 接受 `any`，iOS PWA 可能要求 PNG → 真实 PNG icon 后续补。
- 组件/业务页面占位，完整体验待 Phase 1/3。
- 完整浏览器登录 e2e 未自动化（后端 API 波 2 已测 + 前端 build/vue-tsc 验证逻辑；浏览器手动 e2e 待后续）。

## 迁移条件

- iOS PWA 安装：补 PNG 192/512 icon（maskable + any）。
- 自定义 SW（离线报告缓存精细化、Web Push）：vite-plugin-pwa 切 `injectManifest`。
- request_id 升 v7：装 `uuid` 包或 polyfill，改 `client.ts`。
- 前端 e2e 自动化：Phase 1 引入 Playwright（9_TEST_AND_CI §18.1 E2E 矩阵）。
