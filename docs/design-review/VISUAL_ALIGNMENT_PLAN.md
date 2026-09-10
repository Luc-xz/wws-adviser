# WWS Adviser 前端视觉对齐与补页批次计划（执行中）

> **文档状态：** V1–V5 已交付（2026-09-09，分支 `visual-alignment`）；批次审计 + 三缺口回填完成（11 张新页基准卡、空账户 HOME 404 修复、§8.3 里程碑回填）；仅余 PWA 真机验证（与 §7 上线门槛合流）
> **背景：** Phase 3 验收期用户直观反馈"前端和设计稿很不一样"。核实结论：前端语义层（色彩/数字/风险/PAUSE 硬规则）由代码强制、全部正确；但**视觉层从未以还原设计稿为验收目标**，且 UI §4.3 的 31 页中仅实现 8 个路由。
> **上游：** [UI_DESIGN_SPECIFICATION.md](../UI_DESIGN_SPECIFICATION.md)（§4.3 页面清单 / §5 外壳 / §7 tokens / §18 交付清单）
> **配套：** [REVIEW_REPORT.md](./REVIEW_REPORT.md)（稿的问题在哪）· [ENFORCEMENT_CONTRACT.md](./ENFORCEMENT_CONTRACT.md)（代码怎么强制做对）· [COMPONENT_STATES.md](./COMPONENT_STATES.md)（组件状态清单）· [ADR-0009](../adr/0009-action-and-online-color-tokens.md)（token 决策）
> **排期落点：** §7 上线门槛的 PWA 真机验证项**之前**完成主体（波 V1–V4），走查收口（波 V5）与真机验证合流执行。

---

## 1. 问题陈述与定位

### 1.1 现状两条差距

| 差距 | 事实 | 根因 |
| --- | --- | --- |
| **视觉不对齐** | 已实现 8 页按 UI 规范 + ENFORCEMENT_CONTRACT"自绘"，布局密度、区块排布、观感与 Stitch 稿差异大 | 2026-08-12 评审决策：Stitch 稿系统性违规（REVIEW_REPORT §2–§4），走"代码强制"而非"逐张修稿"路线——语义对齐了，视觉基准悬空 |
| **页面覆盖缺口** | 8 路由 vs UI §4.3 共 31 页；P0 页面缺 ONB-01 / HOME-02 / PORT-02 / TX-01·02·03 / ACC-01 / CHAT-02 / SET-01~08 子页 | 各 Phase 按 AC 最小集交付前端；TX-02/TX-03 为 §8.0 声明的显式留白 |

### 1.2 本批次定位

**把"设计基准"补起来，并以它为唯一视觉验收口径，同时一次性补齐 P0 缺页**——新页面直接按基准实现，避免"先裸实现、再二次对齐"的双倍返工。这既是视觉还原批次，也是前端 P0 页面的收官批次。

**明确不做的事（非目标）：**

- 不改语义硬规则：ENFORCEMENT_CONTRACT 的 token 唯一色值来源、ESLint `no-market-color-misuse`、Vitest 契约断言全部维持，本计划只做视觉层加法；
- 不动后端 API 契约（个别页面需要的 settings 子资源缺口见 §5 波 V4，走正常后端工作项）；
- 不引入新框架/组件库/Storybook（继续 UnoCSS + 手写组件，单人项目成本不划算）；
- 不做逐像素还原：AI 稿本身布局质量参差（§10 风险），取**布局结构、信息密度、层级、组件排布**的对齐；
- P1 页面（CHAT-03 / SYS-01 / SYS-02）不进本批次。

---

## 2. 设计基准制度（本批次核心机制）

### 2.1 基准的构成（三层合成）

```
视觉基准（每页一张「基准卡」）
├─ 布局 / 密度 / 层级   ← Stitch 稿（docs/design-review/stitch/，桌面 23 + 移动 35 份）
├─ 色值 / 字体档位       ← UI §7.1–§7.7 + ADR-0009（唯一权威，稿内色值违例不作数）
└─ 硬规则走查项          ← REVIEW_REPORT §6 整改清单 + ENFORCEMENT_CONTRACT（tabular-nums、
                            负号 U+2212、空值 em-dash、footer 句式、组件 variant 等）
```

### 2.2 基准卡（新增交付物）

每页一张 `docs/design-review/baseline/<PAGE-ID>-card.md`，字段固定：

1. **参考稿**：HTML/PNG 文件路径 + 版本注记（多版本稿注明取哪版，如 HOME-01 取最终版不取 v1）；
2. **布局结构**：区块顺序、栅格/分栏、滚动行为（从稿人工提取，非截图）；
3. **关键尺寸**：间距/圆角/字号档位（映射到 §2.3 版式 token，禁止散落 magic number）；
4. **组件清单**：用到的 shared/ui 组件 + 必须覆盖的 variant（对照 COMPONENT_STATES）；
5. **稿内违例覆盖注记**：该页稿子违反硬规则处（按 REVIEW_REPORT 索引），标注"以代码强制为准"——例如 PORT-01 稿中 Critical 用上涨红、正盈利用绿，基准卡注明 disregarded；
6. **走查项打勾区**：§6 验收口径清单的逐项落点。

### 2.3 版式 token 化（工程前置）

当前 `uno.config.ts` 只有 colors。本批次扩展 theme：`spacing` 档位（4/8/12/16/24/32）、`fontSize` 档位（UI §7.4 + tabular-nums 默认开启面）、`borderRadius`（稿实测 8 为主）。基准卡与组件只引用 token，杜绝视觉层 magic number。

### 2.4 对 Stitch 稿本身的处理

维持 2026-08-12 决策：**不逐张修 58 份 HTML**，仅两类例外：

- 修 REVIEW_REPORT §6 点名的 3 处演示硬伤（PORT-01-desktop Critical 色错 / 正盈利绿错 / HOME-01-desktop"立即执行/快速下单"按钮）——这些稿还承担对外演示职责；
- 基准卡覆盖注记承担其余全部违规的"修正层"（成本最低且不会回退）。

---

## 3. 差距矩阵（31 页全景盘点）

状态图例：✅ 已实现（视觉待对齐=V） · 🆕 本批次新建 · ⬜ P1 出窗不做

| 页面 | 路由 | 移动稿 | 桌面稿 | 现状 | 本批次动作 | 后端就绪度 |
| --- | --- | --- | --- | --- | --- | --- |
| AUTH-01 登录 | `/login` | ✓ | ✓ | ✅ | V 对齐 | 就绪 |
| ONB-01 首次配置向导 | `/onboarding` | ✓ | — | 无 | 🆕 新建 | accounts API 就绪 |
| HOME-01 首页总览 | `/` | ✓ | ✓ | ✅ | V 对齐 | 就绪 |
| HOME-02 今日行动与风险 | `/advice` | ✓ | 响应式 | 无（并入 HOME） | 🆕 新建（从 HOME 拆出建议区） | advice API 就绪 |
| DATA-01 数据状态中心 | `/data-status` | ✓ | 响应式 | ✅ | V 对齐 | 就绪（+conflicts 列表） |
| PORT-01 持仓与自选 | `/portfolio` | ✓ | ✓ | ✅（三 Tab 含流水/自选/ECharts） | V 对齐 | 就绪 |
| PORT-02 标的/持仓详情 | `/instruments/:id` | ✓(7 变体) | ✓ | 无 | 🆕 新建 | bars/documents/positions 就绪 |
| TX-01 交易流水 | `/transactions` | ✓ | ✓ | Tab 内雏形 | 🆕 独立页（与 PORT Tab 关系见 §10-Q2） | transactions API 就绪 |
| TX-02 新建/编辑交易 | `/transactions/new` | ✓ | 响应式 | 无 | 🆕 新建（§8.0 留白承接） | records API 就绪 |
| TX-03 CSV 导入向导 | `/transactions/import` | ✓ | ✓ | 无 | 🆕 新建（§8.0 留白承接） | jgd 三步闭环就绪（012360b） |
| ACC-01 账户与对账 | `/account` | ✓ | 响应式 | 无 | 🆕 新建 | reconcile API 就绪（be0c497） |
| CHAT-01 助手首页 | `/assistant` | ✓ | ✓ | ✅ | V 对齐 | 就绪 |
| CHAT-02 建议详情 | `/advice/:id` | ✓ | 响应式 | 无 | 🆕 新建 | advice_records 查询就绪 |
| CHAT-03 历史问询 | `/assistant/history` | 列表 | 响应式 | 无 | ⬜ P1 | — |
| LIB-01 研究与报告库 | `/research` | ✓ | ✓ | ✅（含新建/进度合并实现） | V 对齐 | 就绪 |
| RES-01/02 新建研究/任务进度 | （并入 LIB-01） | ✓ | 响应式 | ✅ 合并实现 | 保持合并（§10-Q1 同类决策） | 就绪 |
| REP-01/02/03 三类报告 | `/reports/:id` | ✓ | ✓ | ✅（一页承载三形态） | V 对齐（拆分决策见 §10-Q1） | 就绪（含导出） |
| SET-00 设置首页 | `/settings` | ✓ | 响应式 | ✅（风险阈值+登出） | V 对齐 + 子页入口 | 就绪 |
| SET-01 风险与约束 | `/settings/risk` | ✓ | ✓ | SET-00 内雏形 | 🆕 拆独立页 | `/settings/risk` 就绪 |
| SET-02 数据源与质量 | `/settings/data-sources` | ✓ | ✓ | 无 | 🆕 新建（含 conflicts 消解 UI——Phase 3.3 的 SET-02 落点） | conflicts API 就绪 |
| SET-03 模型与任务路由 | `/settings/models` | ✓ | 响应式 | 无 | 🆕 新建 | `/settings/models` 就绪 |
| SET-04 通知与隐私 | `/settings/notifications` | ✓(4 变体) | 响应式 | 无 | 🆕 新建（含 Push 订阅/隐私模式） | notifications+push API 就绪 |
| SET-05 任务时间 | `/settings/schedule` | ✓ | 响应式 | 无 | 🆕 降级形态（只读展示+说明） | **后端缺子资源**（§10-Q3） |
| SET-06 安全与会话 | `/settings/security` | ✓ | 响应式 | 无 | 🆕 含会话列表/登出全部（Passkey 管理已有 API） | 部分（sessions 列表缺） |
| SET-07 存储备份恢复 | `/settings/backups` | ✓ | 响应式 | 无 | 🆕 只读（备份列表+恢复指引） | 部分（无 REST，读 backups 目录需后端补） |
| SET-08 系统状态 | `/settings/system` | ✓ | ✓ | 无 | 🆕 新建（health/dependencies + job_runs 近况） | health 就绪，jobs 查询需核 |
| SYS-01 全局搜索 | Modal | — | — | 无 | ⬜ P1 | — |
| SYS-02 通知中心 | `/notifications` | 列表 | 抽屉 | 无 | ⬜ P1 | — |

**外壳与横切面现状：**

| 项 | 现状 | 本批次动作 |
| --- | --- | --- |
| 移动外壳（UI §5.1 底导航） | 已有 5 项（首页/持仓/助手/研究/设置） | 对齐稿的视觉规格（§5 波 V2） |
| 桌面外壳（UI §5.2） | **未做**（现为移动布局拉宽） | 🆕 波 V2：侧栏/顶栏外壳 + 断点切换 |
| 页面标题区（UI §5.3） | 不统一 | 波 V2 统一组件 |
| 深色模式 | 已有（useDark + surface token + dark: 变体，技术债 7 已清） | 每页走查时核验 dark: 覆盖（稿无深色，按 token 映射人工核） |
| 离线行为 | SW NetworkOnly /api + 离线报告缓存已有 | 不动，仅回归 |

**执行记录（2026-09-09，`visual-alignment` 分支）：**

- **波 V1 ✅**（7dd1b96）：版式 token（fontSize 12 档 + radius 覆盖 preset）；基准卡模板 + 既有 8 页基准卡；演示稿硬伤核验（3 处已于 08-12 修）+ 补漏 REP-01-desktop「立即执行」。
- **波 V2 ✅**（9a69167）：AppShellDesktop（侧栏 224px + 顶栏 64px + @iconify-json/carbon）；移动底导航按 §5.1；PageHeader；路由 meta.title + document.title 同步；tabular-nums :root 全局。实机双视口走查通过。
- **波 V3 ✅**（b8330dc）：8 页对齐（HOME 摘要大卡/风险聚合条/日期修复；PORT 下划线 Tab/4 指标摘要；REP 补 DataStatusBar；DATA conflicts 区块；CHAT/LIB/SET/AUTH token 化）。顺修三真 bug：路由守卫会话竞态（PWA 重开被踢登录）、日期 toLocaleDateString 格式、Tab UA 默认按钮样式暴露（计算样式实证）。
- **波 V4 ✅**（afce597）：11 新路由（TX-01/02/03、ACC-01、PORT-02、SET-01/02/03/04/06/08）全交付；SET-02 conflicts 消解 UI 闭环（Phase 3.3 落点）；SET-06 Passkey 真注册流程；PORT-02 接 PositionRow 整行跳转。
- **波 V5 ◐ 本地部分完成（2026-09-09）**：桌面全路由巡检（14 条：标题/渲染/API 错误文案扫描全绿，含不存在 id 的异常态不白屏）；深色全页核验（真实持久化 key 扫白底残留——修复 11 处漏 dark: 的卡/空态 + Home 刷新按钮，复扫清零，截图留档）；真机装机验证移交 `deploy/PWA_DEVICE_CHECKLIST.md` 清单（A–G 七组，与 §7 上线门槛合流执行）。
- **批次审计 + 三缺口回填（2026-09-09）**：按 §7 六条退出条件文档侧逐项核验 + 稿侧 5 页实拍比对（HOME/DATA/SET/CHAT 移动 375 + PORT 桌面 1440，浏览器实拍 vs Stitch PNG 结构 diff）。当日闭环：①审计发现的空账户 HOME bug——`analytics/summary` 404 落入数据模板渲染全 `—` 假数据卡，修复为 404→null 空标记走导入引导（同 TX-01 口径，+TC-GS-02，14375a7）；②V1 任务 5 欠账补齐——11 张 V4 新页基准卡（TX-01/02/03、ACC-01、PORT-02、SET-01/02/03/04/06/08，追溯卡口径：结构/四态以实现为准、稿作密度参照）；③§8.3 里程碑卡执行回填。稿侧比对主要差异均为「规范/路由优先于 Stitch 占位稿」的有意偏离（稿底导航/品牌占位与 PRD 路由不符、CHAT 对话形态依赖 CHAT-02 后端、稿英文文案），逐页记入各卡 §5 违例覆盖注记。
- **偏差记录**：~~HOME-02/CHAT-02 归 P2——`advice_records` 查询 API 后端未开放~~ **已收口（2026-09-10，dev）**：后端 `GET /api/v1/advice` 列表/详情/评价三端点 + 前端 /advice 与 /advice/:id 两页 + 基准卡 2 张交付（27 页达成 22→24；路由 19→21），偏差仅余稿侧 P2 项（当前仓位双带、触发条件文本、实际操作记录——未持久化列/写端点，见两卡 §5）。SET-05/07 维持 P2 裁剪线（后端缺 settings 子资源/REST）。

---

## 4. 批次总量与裁剪线

- **全量**：8 页视觉对齐 + 约 15 个新路由 ≈ 17 个页面工作单元，单人估 **12–18 个工作日**。
- **P0 核心线（不可裁）**：UI §18.4 移动必交 27 页对应的全部页面 + 桌面外壳 + 走查收口。
- **可裁剪（P2 标注，进度压力时延后）**：ONB-01（现有登录直进可用）、SET-05/07（后端本就缺资源，先降级只读甚至延后）。裁剪决策在波 V4 中途检查点做，不提前砍。

---

## 5. 波次拆分

> 每波独立提交、门禁全绿（eslint 含自定义规则 + vue-tsc + vitest + gen:api + build）；页面级工作逐页原子 PR，PR 描述贴"桌面 1440 + 移动 375 + 深色"三截图 vs 基准卡并排比对。

### 波 V1 · 基准固化（1.5–2 天）

| # | 任务 | 落点 |
| --- | --- | --- |
| 1 | 版式 token 化（spacing/fontSize/radius 档位） | `frontend/uno.config.ts` |
| 2 | 基准卡模板定稿 | `docs/design-review/baseline/_TEMPLATE.md` |
| 3 | 既有 8 页基准卡（含稿内违例覆盖注记） | `docs/design-review/baseline/*.md` ×8 |
| 4 | 修 3 处演示稿硬伤（REVIEW_REPORT §6 末清单） | `stitch/PORT-01-desktop.html`、`stitch/HOME-01-desktop.html` |
| 5 | 新页基准卡随波 V4 各页先行补齐（不集中做） | 同目录 |

### 波 V2 · 外壳与全局版式（2–3 天）

| # | 任务 | 落点 |
| --- | --- | --- |
| 1 | 桌面外壳：UI §5.2 侧栏 + 顶栏，断点切换（稿 2560 设计，实现按 1280+/1440 适配） | `App.vue` + `shared/ui/AppShellDesktop.vue` |
| 2 | 移动底导航对齐稿规格（尺寸/激活态/图标） | `App.vue` |
| 3 | 页面标题区统一（UI §5.3：标题+副标题+主操作位） | `shared/ui/PageHeader.vue` |
| 4 | 全局版式走查（字号档位/间距 token 应用面 + tabular-nums 全局默认开启） | `styles/` |

### 波 V3 · 既有 8 页视觉对齐（4–6 天，逐页 0.5–1 天）

顺序（风险与价值兼顾）：HOME-01 → PORT-01 → REP-01/02/03 → DATA-01 → CHAT-01 → LIB-01 → SET-00 → AUTH-01。每页动作：对照基准卡重排区块/密度/层级 → 补齐组件 variant（DataStatusBar 4 态、AdviceCard 6 动作、PAUSE 零数量——语义已有，视觉补全）→ 三截图走查。

### 波 V4 · P0 缺页补齐（6–9 天，按后端就绪度排序）

| 序 | 页面 | 依赖后端 | 说明 |
| --- | --- | --- | --- |
| 1 | TX-02 新建/编辑交易 | 全就绪 | 8 种交易类型表单（SUBSCRIBE/REDEEM 等 UI §10 对应页） |
| 2 | TX-03 CSV 导入向导 | jgd 三步闭环（012360b） | 状态导出→增量转换→校验回显→导入 |
| 3 | TX-01 交易流水 | 全就绪 | 与 PORT 流水 Tab 的取舍见 §10-Q2 |
| 4 | ACC-01 账户与对账 | reconcile（be0c497） | 差异列表 + 确认对账交互 |
| 5 | PORT-02 标的详情 | 全就绪 | 行情图 + 持仓明细 + 相关公告（documents）+ 建议 |
| 6 | HOME-02 / CHAT-02 | 全就绪 | 建议列表页 + 建议详情（6 层信息 + footer 句式，以 HOME-01-mobile:208 标杆卡为基准） |
| 7 | SET-01/02/03/04/08 | 大多就绪 | SET-02 含 conflicts 消解（Phase 3.3 SET-02 落点闭环） |
| 8 | SET-06 安全与会话 | 部分 | sessions 列表 API 缺 → 先做 Passkey 管理 + 登出全部 |
| 9 | ONB-01 / SET-05 / SET-07（P2 可裁） | 部分/缺 | 见 §4 裁剪线；中途检查点决策 |

### 波 V5 · 走查收口 + 真机合流（1–2 天 + 真机）

1. 全页走查清单终核（§6）；2. 深色全页核验；3. PWA 真机装机验证 iOS+Android（与 §7 上线门槛该项合流执行，一次收掉）；4. 里程碑回填。

---

## 6. 每页验收口径（DoD，写进每页 PR 模板）

1. **三截图比对**：桌面 1440 / 移动 375 / 深色，与基准卡（或稿 PNG）并排贴 PR；
2. **硬规则走查全绿**：tabular-nums 开启面、负号 `−`(U+2212)、空值 `—`、建议卡 footer 句式（`截至 · 来源 · 有效至`，HOME-01-mobile:208 标杆）、金额/价格精度（UI §8.1）；
3. **组件 variant 完整**：该页用到的组件按 COMPONENT_STATES 全 variant 可达（DataStatusBar 4 态、AdviceCard 6 动作、EvidenceDrawer 移动 Bottom Sheet）；
4. **状态完备**（UI §4.3"完整设计"要求）：默认 / 加载 / 空 / 异常四态不缺，空态绝不显示假 ¥0（既有契约）；
5. **门禁全绿无回退**：eslint（含 `no-market-color-misuse`）+ vue-tsc + vitest + gen:api + build；
6. **深色核验**：dark: 变体人工核（稿无深色，按 token 映射 + 对比度抽检）。

---

## 7. 退出条件（批次硬门槛）

- [ ] UI §18.4 移动必交 27 页全部实现且逐页走查通过（截图留档 PR）。
- [ ] 既有 8 页 + 新建页全部有基准卡，稿内违例全部有覆盖注记（不依赖"记得"）。
- [ ] 桌面外壳落地，"完整设计"桌面页至少 13 张必交页在桌面断点可用。
- [ ] 深色模式全页核验通过；ESLint/Vitest 契约零豁免。
- [ ] PWA 真机验证（iOS+Android 等效环境）与上线门槛该项同步回填。
- [ ] 里程碑计划 §8.3 批次卡回填完成声明。

---

## 8. 排期落点

```
现在 ──► 波V1 基准 ──► 波V2 外壳 ──► 波V3 对齐 ──► 波V4 补页 ──► 波V5 走查+真机 ──► §7 上线门槛其余项
         (2d)          (3d)          (5d)           (8d)           (2d+真机)
```

- 主体（V1–V4）须在上线门槛 PWA 真机项**之前**完成；与 20 交易日观察窗、Phase 2 出窗持续项**完全并行无冲突**（纯前端）。
- 总量 12–18 个工作日（单人，含裁剪余量）；若压缩，按 §4 P2 裁剪线减 3–4 天。

---

## 9. 工程保障

- **不新增工具链**：截图走查人工执行、PR 留档；不引入 Storybook/Chromatic/视觉回归（开放问题 §10-Q4 可选）。
- **既有契约不放松**：ENFORCEMENT_CONTRACT 全部断言维持；新增页面同步接入 typed client（openapi-fetch）与 TanStack Query，遵守 doc7 §2 状态边界。
- **基准卡进仓库**：`docs/design-review/baseline/` 随代码评审，防"还原后漂移无凭据"。

---

## 10. 风险与开放问题

| # | 风险/问题 | 对策/决策点 |
| --- | --- | --- |
| R1 | AI 稿布局质量参差（不合理留白/拥挤/伪交互） | 基准卡人工判读权：稿明显不合理处以 UI 规范为准并在卡上记录，不盲从 |
| R2 | 稿无深色、无响应式断点细节 | 深色走 token 映射 + 对比度抽检；断点按 UI §3.3 推导 |
| R3 | 工作量超预期（18 天上限） | §4 P2 裁剪线 + 波 V4 中途检查点 |
| Q1 | REP-01/02/03 一页承载 vs 稿三页分立；RES-01/02 并入 LIB-01 | 建议维持合并（信息架构更贴单人使用），基准卡按"卡内分区"对齐稿区块。如需拆分在波 V3 前决策 |
| Q2 | TX-01 独立页与 PORT 流水 Tab 功能重叠 | 建议：PORT Tab 保留持仓视角摘要，TX-01 为全量流水+筛选。若嫌重复，TX-01 可改跳转壳 |
| Q3 | SET-05/07 后端无 settings 子资源（Phase 1 波6 留白"4 个子资源"） | 降级只读或延后（P2）；若要完整，另立后端工作项，不阻塞本批次 |
| Q4 | 无视觉回归工具，还原后可能漂移 | 单人+PR 截图留档已够；真需要时后续补 Playwright screenshot，不进本批次 |

---

## 11. 与既有留白/文档的关系

- §8.0 技术债批次"仍留待后续"中的**交易记录手工录入 UI（TX-02）、CSV 导入 UI（TX-03）** → 本批次波 V4 承接清账；企微/Server酱真实联调仍留（需凭据）。
- SET-02 数据源页同时收口 **Phase 3.3 的 SET-02 消解 UI 落点**（conflicts 端点已鉴权，a8421c3）。
- 本计划不改 REVIEW_REPORT / ENFORCEMENT_CONTRACT 任何结论；基准卡体系是两者之间的"视觉执行层"。
