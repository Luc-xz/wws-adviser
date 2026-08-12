# ADR-0009：新增 `action.*` 色彩 token 族与 `status.online` 语义 token

> 状态：Accepted
> 日期：2026-08-12
> 关联：[UI §7.1 / §7.3](../UI_DESIGN_SPECIFICATION.md) · [REVIEW_REPORT §2.2](../design-review/REVIEW_REPORT.md) · [COMPONENT_STATES §3.1](../design-review/COMPONENT_STATES.md) · [ENFORCEMENT_CONTRACT](../design-review/ENFORCEMENT_CONTRACT.md)

## 上下文

设计稿审核（[REVIEW_REPORT.md](../design-review/REVIEW_REPORT.md) §2.2）发现两类系统性色彩违规，根因都指向 token 缺失：

- **违规 A**：下跌绿 `color.market.down`（#079455）被广泛误用作"任务完成 / 数据源 ACTIVE / 连接正常 / 正盈利"（如 `PORT-01-desktop.html:395` 把 +11,000 正盈利涂成下跌绿，与 A 股"红涨绿跌"约定反向）。根因：UI 规范**没有定义"在线/健康/成功"的独立语义 token**，导致一切"绿色 = 正常"的直觉全部落到了唯一的绿 token（下跌绿）上。
- **违规 D**：行动色未入 token。UI §7.3 硬规则已规定"减少=橙、观察=琥珀、条件式增加=靛蓝、退出观察=洋红、暂停=灰"，但 §7.1 token 表无对应 token，结果同一"减少"行动在不同稿中出现橙、error 红、下跌绿三种颜色（`PORT-01-desktop` / `HOME-01-mobile:208` / `PORT-02-mobile:166`）。

`color.status.success`（#067647）虽已存在，但其语义是"任务成功"，无法承担"连接在线/数据源健康"这一**持续态**语义，且与下跌绿仍同属绿色族、易混。

## 决策

1. **§7.1 新增 `color.action.*` 六 token**（行动建议专用，见 [UI §7.1](../UI_DESIGN_SPECIFICATION.md) 表）：
   - `hold`=#475467（中性 slate）、`watch`=#DC6803（琥珀）、`conditionalAdd`=#3157D5（靛蓝）、`reduce`=#C2410C（**深橙，刻意深于 watch 以求可辨**）、`exitWatch`=#C11574（洋红）、`pause`=#667085（灰）。
2. **§7.1 新增 `color.status.online`=#0D9488（teal）**：用于"数据源在线 / 连接健康 / 同步正常"等**持续态**，与 `color.market.down`（#079455，下跌专用）严格区分，也区别于一次性的 `status.success`。
3. **§7.3 硬规则强化**：行动建议必须用 `action.*`、禁用 `market.*`；在线/健康必须用 `status.online`、禁用 `market.down`。规则原文已更新进 UI §7.3。
4. **§7.2 深色**：为 `action.*` 与 `status.online` 给出初定深色值并标注"待对比度验证"；`status.success`/`status.info` 的深色值是已知缺口，留给 Phase 0.4 前端落地时按真实机型补齐。

## 备选方案

- **A. 逐张修复 Stitch 静态稿**：放弃。23+35 张 HTML 成本高、易回退，且不解决 token 缺失这一根因——下次生成仍会重犯。评审报告 §6 同样推荐"以前端代码强制约束而非逐张修稿"。
- **B. 仅保留 §7.3 口头硬规则、不引入 token**：放弃。没有 token，前端无法在组件 props 与 vitest 断言层 enforce，违规会随实现重现。
- **C. 复用 `status.success` 兼任"在线"语义**：放弃。"任务成功"是终态事件，"在线健康"是持续态，混用会再次产生违规 A 的歧义。

## 正负影响

**正向：**
- 行动色与在线色可在前端组件 + vitest 断言层强制（见 [ENFORCEMENT_CONTRACT.md](../design-review/ENFORCEMENT_CONTRACT.md)），违规在 CI 阶段被拦截。
- 修复 A 股约定反向违规（正盈利涂绿、下跌涂红），消除金融语义色歧义。
- Stitch 稿的既有违规无需逐张改——前端按 token 渲染即自动纠正。

**负向 / 代价：**
- token 表新增 7 项，设计稿与组件需对齐映射。
- 深色 `action.*`/`online` 值为初定，Phase 0.4 需在真实机型做对比度验证，可能小幅调整色值（token 名稳定）。

## 迁移条件

- 若未来 UI §7.3 提及的"设置页可扩展配色"落地（用户可选涨跌色约定），`action.*` token 名保持不变，仅替换色值映射。
- 若出现新的行动类型（如"加仓 / 清仓"拆分），新增 `action.*` 条目，不改动既有 token 语义。
