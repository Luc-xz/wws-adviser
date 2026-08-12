# WWS Adviser 设计稿审核报告

> **审核日期：** 2026-08-12
> **审核范围：** docs/design-review/ 全部产物（桌面 23 HTML + 移动 35 HTML + 2 manifest + COMPONENT_STATES.md）
> **审核依据：** [UI_DESIGN_SPECIFICATION.md](../UI_DESIGN_SPECIFICATION.md) §4.3 / §7.3 / §7.4 / §8 / §9 / §18
> **审核方法：** 覆盖度统计 + 12 个代表性 HTML 文件的内容级硬规则抽查（色彩/数字时间/组件三维度）

---

## 总体结论

| 维度 | 结论 | 说明 |
|---|---|---|
| 页面覆盖度（§4.3/§18.4） | ✅ **达标** | 必交清单 100%，详见 §1 |
| 色彩硬规则（§7.3） | ⚠️ **部分达标，偏不达标** | 系统性违规，详见 §2 |
| 数字时间硬规则（§7.4/§8） | ⚠️ **部分达标** | 7/12 文件漏开 tabular-nums，详见 §3 |
| 组件硬规则（§9） | ⚠️ **部分达标** | PAUSE/DataStatusBar 4 态严重缺失，详见 §4 |

**核心判断：页面级"有没有"已达标，但内容级"对不对"存在系统性硬规则违规。** 这些稿子是 Stitch AI 生成的，AI 对金融语义色（行情红绿专用、PAUSE 隐藏数量等）理解不足，产生了多类可复现的违规。需要在进入前端实现前，要么修复 Stitch 稿，要么在 COMPONENT_STATES.md 的组件 props 中以代码强制约束（推荐后者，见 §6）。

---

## 1. 页面覆盖度（✅ 达标）

| 清单 | 要求 | 现有 | 状态 |
|---|---|---|---|
| §18.4 移动必交 27 项 | 27 | 27 | ✅ |
| §18.4 桌面必交 13 项 | 13 | 13 | ✅ |
| §4.3 移动全 31 页 | 31 | 28（缺 CHAT-03/SYS-01/SYS-02，均 P1） | ✅ |
| §4.3 桌面全 31 页 | 31 | 16（其余为响应式/P1，可从移动端推导） | ✅ |
| §18.3 组件 Variant | 10 类 | 规范完整（COMPONENT_STATES.md） | ✅（前端实现） |
| §18.4 状态变体 | 必交 | 规范完整（COMPONENT_STATES.md） | ✅（前端实现） |

---

## 2. 色彩硬规则审核（§7.3）—— ⚠️ 部分达标，偏不达标

### 2.1 正向：token 层规范
全部 12 文件把颜色语义化为 Tailwind token（`market-up:#D92D20`、`market-down:#079455`、`risk-critical:#C11574`、`risk-warning:#DC6803`、`primary:#3157D5`），token 定义本身正确。

### 2.2 系统性违规

**违规 A：下跌绿 #079455 被广泛误用作"系统正常/在线/成功"**（根因：设计稿未定义 success/online token）
- `HOME-01-desktop.html:456-457` 任务完成 `check_circle` 用 market-down 绿
- `HOME-01-desktop.html:477-496` 数据源健康度信号条全用 market-down 绿
- `HOME-01-desktop.html:184-187` / `PORT-01-desktop.html:269` "交易中"状态绿点
- `DATA-01-desktop.html:339-367` 数据源 ACTIVE/在线用 market-down 绿
- `PORT-01-desktop.html:395` **正盈利 +11,000 用 market-down 绿（A 股约定反向，严重）**

**违规 B：上涨红 #D92D20 被误用作通知/资金类型**
- `PORT-01-desktop.html:274` 通知未读红点
- `TX-01-mobile.html:237-255` "分红"徽章/入账金额
- `ACC-01-mobile.html:200-203` 现金差异 +¥1,200

**违规 C：Critical 风险与上涨红直接混淆**
- `PORT-01-desktop.html:372-374` Critical 风险行用 `text-market-up`（上涨红）+ 浅红背景，而非 `risk-critical` 洋红 —— **§7.3 明令禁止的混用**

**违规 D：行动色体系缺失，同一行动多种颜色**
- "减少"行动：PORT-01-desktop（橙✓）/ HOME-01-mobile:208（error 红✗）/ PORT-02-mobile:166（market-down 绿✗）—— 三文件三种颜色
- 设计 token 中**完全没有** action-reduce/watch/add/exit/pause 族
- §9.3 六动作变体仅能验证到"减少"和"条件式增加"2 种

---

## 3. 数字时间硬规则审核（§7.4/§8）—— ⚠️ 部分达标

### 3.1 tabular-nums（§7.4）—— 5/12 开启，7/12 缺失

| 开启 ✓ | 缺失 ✗ |
|---|---|
| PORT-01-desktop（13处，标杆）、PORT-02-desktop（15处）、HOME-01-desktop（6处）、HOME-01-mobile（6处）、SET-02-desktop（3处） | TX-01-desktop、REP-01-desktop、PORT-02-mobile、CHAT-01-mobile、REP-01-mobile、ACC-01-mobile、DATA-01-mobile |

### 3.2 时间/来源常驻（§8.3）—— 严重不一致

正向标杆：`HOME-01-mobile.html:208` 建议卡 footer `截至 10:32:15 · 有效至 10:42`（唯一完整命中 §8.3 句式）

缺失：
- `HOME-01-desktop.html:255-290` 今日建议行动区**无任何 footer**
- `TX-01-desktop.html` 全页无时间/来源
- `CHAT-01-mobile.html:231` 建议卡有有效期但**缺来源**
- `DATA-01-mobile.html:254` 基金净值**未显示净值日期**（§8.1 硬要求）

### 3.3 空值与负号（§8.2）
- 空值：仅 `TX-01-desktop.html:281` 用对 `—`；`DATA-01-mobile.html:254` 用错 `-`
- **负号：全部 12 文件用 ASCII `-` 而非数学负号 `−`（U+2212）** —— 系统性轻微违规

### 3.4 数字精度（§8.1）—— 基本合理
- 金额 2 位 ✓、A 股价格 2 位 ✓、港股按 tick ✓、仓位 1 位 ✓
- 瑕疵：`PORT-01-desktop.html:286-298` 摘要金额无小数（`¥328,540`）
- 瑕疵：`REP-01-desktop.html:193` 日期用 `2024年10月17日` 非 ISO

---

## 4. 组件硬规则审核（§9）—— ⚠️ 部分达标

### 4.1 AdviceCard（§9.3）—— 变体覆盖严重不足
- 仅 3/6 动作变体出现（减少✓/保持1次/条件式增加2次）；**观察、退出观察、PAUSE 全缺**
- **PAUSE 变体在全部样稿中零实现** —— §9.3 "必须提供完整 Variant"未达标，PAUSE"不显示数量"硬规则无法验证
- 违反 §9.8：`HOME-01-desktop.html:273,518` "立即执行"/"快速下单"、`HOME-02-mobile.html:174,212` "执行调整" —— 系统不提供立即买入/卖出
- 标杆：`HOME-01-mobile.html:208` 唯一完整呈现 6 层信息层级的 REDUCE 卡

### 4.2 DataStatusBar（§9.1）—— 最严重不达标
- **4 态只设计了 1 态**（正常态）；延迟/冲突/离线三态零实现
- 持仓页（PORT-02）、报告页（REP-01/REP-03）顶部**完全没有 DataStatusBar**
- 无 Chevron、无跳转 DATA-01 入口 —— DATA-01 成孤岛

### 4.3 RiskAlert（§9.4）—— 部分达标
- 正向：未发现"仅显示错误代码"违规；`REP-01-mobile.html:198-212` Critical 含影响说明
- 违规：`HOME-01-desktop.html:407-413` Critical 同时缺"影响什么"+"如何处理"

### 4.4 EvidenceDrawer（§9.6）—— 桌面达标，移动全缺
- 标杆：`REP-03-desktop.html:374-414` 完整右抽屉（事实来源/模型引用 Tab + L1/L2 等级）
- 移动端 Bottom Sheet（80-92%）形态**零实现**
- 事实/模型区分仅 REP-03-desktop 一处

### 4.5 Fact/Calculation/Judgment 标签（§9.7）—— 桌面达标，移动不达标
- 标杆：`REP-03-desktop.html:267-274` 4 标签全、配色对、配 [1][2] 引用
- `REP-03-mobile.html` 缺 [计算]/[未证实]，且 [判断] 用蓝色而非琥珀（§9.7 违规）
- 标签语言不一致：REP-01-mobile 英文 vs REP-03 中文

---

## 5. 正面标杆（可直接复用为模板）

| 标杆 | 文件:行 | 价值 |
|---|---|---|
| 完整 REDUCE AdviceCard | HOME-01-mobile.html:208 | 唯一呈现 §9.3 全部 6 层信息 |
| 持仓表 tabular-nums 全覆盖 | PORT-01-desktop.html:380-399 | 等宽数字最佳实践 |
| 建议卡 footer 句式 | HOME-01-mobile.html:208 | `截至 · 来源 · 有效至` 模板 |
| 完整 EvidenceDrawer | REP-03-desktop.html:374-414 | 事实/模型 Tab + 来源等级 |
| 4 标签段落写法 | REP-03-desktop.html:267-274 | Fact/Calculation/Judgment/未证实 |
| Critical RiskAlert | REP-01-mobile.html:198-212 | 含影响说明 |
| 空值 em-dash | TX-01-desktop.html:281-282 | `—` 正确用法 |

---

## 6. 整改建议

> **修复状态（2026-08-12 更新）：** 本节属于**设计 token 层**的 P0/P1 项已落地——新增 `color.action.*` 六 token 与 `color.status.online`，并强化 UI §7.3 硬规则，决策记录见 [ADR-0009](../adr/0009-action-and-online-color-tokens.md)；前端组件层的强制断言已规格化为 [COMPONENT_TEST_CONTRACTS.md](./COMPONENT_TEST_CONTRACTS.md)，Phase 0.4 起 translate 为 vitest 红灯测试。下方"按 §11 验收清单"表保留为前端实现 Checklist。§2.2 对违规的描述为审核时点快照，保留作问题记录，不就地改写。

### 推荐路径：以前端组件代码强制约束（而非逐张修 Stitch 稿）

理由：Stitch 稿是 AI 生成的静态快照，逐张修复 23+35 张 HTML 成本高且易回退。更好的做法是在 [`COMPONENT_STATES.md`](./COMPONENT_STATES.md) 的组件 props 基础上，用前端代码 + vitest 断言强制约束硬规则，让违规在 CI 阶段被拦截。

> ✅ **本路径已落地为可执行契约：** 见 [`ENFORCEMENT_CONTRACT.md`](./ENFORCEMENT_CONTRACT.md) —— 含 token 完整定义（补 success/online/action-* 族）、formatMoney/formatPercent 函数实现、ESLint 自定义规则、12 条 vitest 断言代码、落地文件清单。前端骨架建起后按其 §5 移入即可生效。

### 按 §11 验收清单补充断言（优先级排序）

| 优先级 | 整改项 | 对应违规 | 落点 |
|---|---|---|---|
| P0 | 新增 `success`/`online` token，替换所有误用的 market-down 绿 | §2.2 违规 A | 设计 token 层 |
| P0 | Critical 风险强制用 risk-critical 洋红，禁用 market-up | §2.2 违规 C | RiskAlert.vue |
| P0 | PAUSE 变体实现 + 断言不渲染 targetRange/数量/醒目按钮 | §4.1 | AdviceCard.vue |
| P0 | DataStatusBar 4 态实现 + 持仓/报告页接入 + 跳 DATA-01 | §4.2 | DataStatusBar.vue |
| P0 | 移除"立即执行/快速下单/执行调整"按钮文案 | §4.1 §9.8 | AdviceCard.vue |
| P1 | 行动色 action-* token 族（6 动作各自独立色） | §2.2 违规 D | 设计 token 层 |
| P1 | 全局 tabular-nums（交易/对账/报告/个股表） | §3.1 | 全局 CSS |
| P1 | 时间来源 footer 常驻（建议卡/报告/交易） | §3.2 | 各组件 |
| P1 | 负号统一用 `−`（U+2212） | §3.3 | 数字格式化工具 |
| P2 | 移动端 EvidenceDrawer Bottom Sheet | §4.4 | EvidenceDrawer.vue |
| P2 | REP-03-mobile 补 [计算]/[未证实] 标签 + 修 [判断] 配色 | §4.5 | REP-03 页 |
| P2 | 标签语言统一（中/英选一） | §4.5 | 研究 report 体系 |

### 如需修复 Stitch 稿本身

最高优先级修 3 处硬伤（影响演示效果）：
1. `PORT-01-desktop.html:372-374` Critical 行改用 risk-critical 洋红
2. `PORT-01-desktop.html:395` +11000 正盈利改用 market-up 红（A 股红涨）
3. `HOME-01-desktop.html:273,518` 删除"立即执行/快速下单"按钮

---

*本报告与 [COMPONENT_STATES.md](./COMPONENT_STATES.md) 配套：前者记录"问题在哪"，后者给出"前端怎么强制做对"。*
