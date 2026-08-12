# WWS Adviser · 组件状态变体实现清单

> **定位：** UI 规范 §9/§10/§14/§18 要求的「状态变体」无法用 Stitch 静态稿完整表达（一次生成验证：Stitch 对基于已有页面的状态变体生成不产出）。本文把这些散落要求**聚合成前端 `shared/ui` 组件可直接消费的状态清单**——每个组件列出 props、触发条件、视觉差异，供 Vue 组件实现阶段按图索骥。
>
> **上游依据：** [UI_DESIGN_SPECIFICATION.md](../UI_DESIGN_SPECIFICATION.md) §9 组件规范、§10 页面状态、§14 全局状态、§18.3 必交 Variant
> **下游消费：** [`7_FRONTEND_AND_PWA.md`](../dev-guide/7_FRONTEND_AND_PWA.md) §9 `shared/ui` 组件实现
> **配套静态稿：** Stitch 覆盖到页面级默认态（见 [stitch/index.md](./stitch/index.md)）；状态变体由组件 props 驱动，无需每个状态一张稿

---

## 1. 为什么不用 Stitch 生成状态变体

| 维度 | Stitch 静态稿 | Vue 组件状态 |
|---|---|---|
| 表达方式 | 每状态一张 HTML/PNG | 单组件 + props/状态机 |
| 维护成本 | 状态组合爆炸（6 动作 × 4 状态 = 24 张） | 改一处即全局生效 |
| 可交互性 | 无（静态截图） | 真实条件渲染、动效 |
| §18.4 达标 | 已达标（页面默认态全覆盖） | 补齐状态变体 |

结论：状态变体的最佳载体是**前端组件**，Stitch 静态稿止步于页面默认态即可。

---

## 2. Data Status Bar（§9.1）

**文件落点：** `frontend/src/shared/ui/DataStatusBar.vue`

### Props

```ts
interface DataStatusBarProps {
  state: 'fresh' | 'delayed' | 'conflict' | 'offline'
  marketPhase: 'pre-open' | 'trading' | 'closed' | 'non-trading'
  updatedAt: string        // ISO 时间，展示层转 Asia/Shanghai
  delaySeconds?: number    // state=delayed 时显示
  issueCount?: number      // state=conflict 时显示
  source?: string          // 数据源名
}
```

### 状态变体（4 态，§9.1 + §18.3 必交）

| state | 触发条件 | 背景 | 圆点 | 文案模板 | 行动 |
|---|---|---|---|---|---|
| `fresh` | 行情 < 90s 且源健康 | 中性 surface | 绿点 | `交易中 · 更新于 10:32:15 · 来源 主行情源 A` | 点击进 DATA-01 |
| `delayed` | 行情 > 90s 未更新 | 琥珀 #DC6803 弱底 | 琥珀点 | `行情延迟 2 分 18 秒` | 点击进 DATA-01 |
| `conflict` | 多源误差超容差 | 洋红 #C11574 弱底 | 洋红点 | `部分数据不可用 · 2 项` | 点击进 DATA-01 |
| `offline` | 网络断开（§14.4） | 灰底 | 灰斜线图标 | `离线 · 显示缓存内容（08-11 16:30）` | 点击查看缓存说明 |

**硬规则：** 高度移动 40px / 桌面紧凑 Pill；点击进 DATA-01，**不能只弹 Toast**（§9.1）；时间精确到秒（盘中）或到分（盘后）。

---

## 3. Advice Card（§9.3）—— 产品最重要组件

**文件落点：** `frontend/src/shared/ui/AdviceCard.vue`

这是规范 §9.3 明确要求"必须在 Figma 中提供完整 Variant"的组件，状态组合最多。

### Props

```ts
type AdviceAction = 'hold' | 'watch' | 'conditional-add' | 'reduce' | 'exit-watch' | 'pause'
type AdviceState  = 'default' | 'expanded' | 'expired' | 'degraded' | 'triggered' | 'recorded' | 'skeleton'

interface AdviceCardProps {
  action: AdviceAction
  state?: AdviceState          // default = 'default'
  instrument: { code: string; name: string }
  riskLevel: 'info' | 'warning' | 'critical'
  currentWeight?: number       // pause 时不显示
  targetRange?: [number, number] // pause 时不显示
  summary: string              // 一句话条件式，≤3 行
  trigger?: string             // 触发条件
  validUntil?: string          // 有效期
  quotedAt?: string            // 行情时间
  evidenceCount?: number
  degradeReason?: string       // state=degraded/pause 时
}
```

### 3.1 行动变体（6 动作，§9.3 硬规则 + §7.3 行动色不混用行情色）

| action | 标签色 | 图标（Material Symbols） | 语义 | 数量区显示 |
|---|---|---|---|---|
| `hold` 保持 | Slate 中性 | `pause_circle` | 当前处于目标区间 | 显示 |
| `watch` 观察 | Amber #DC6803 | `eye` | 等待条件，不暗示立即交易 | 显示 |
| `conditional-add` 条件式增加 | Indigo #3157D5 | `add_circle` | **禁用上涨红/立即买入** | 显示 |
| `reduce` 减少 | Orange #DC6803 同系？见注 | `south_east` | **与行情下跌绿 #079455 严格区分** | 显示 |
| `exit-watch` 退出观察 | Magenta #C11574 | `logout` / `shield` | 投资假设失效 | 显示 |
| `pause` 暂停建议 | Gray | `shield_off` | 数据不足/异常 | **不显示** |

> 注：§9.3 表格中 reduce=Orange、watch=Amber，两者色值接近，实现时 reduce 用更深的橙 `#C2410C` 与 watch 的 `#DC6803` 区分；以 §7.3 行动色硬规则为准——**减少/观察/条件式增加/退出观察/暂停 五色必须彼此可辨**。

### 3.2 状态变体（8 态，§9.3 + §18.3 必交 4 态）

| state | 视觉差异 | 触发条件 | §18.3 必交 |
|---|---|---|---|
| `default` | 白底 1px 边框，完整 6 级信息 | 正常发布 | ✅ |
| `expanded` | 展开证据/计算过程（手风琴） | 用户点"查看依据" | ✅ |
| `expired` | 顶部贴"已过期"红 Badge，整卡 60% 透明度灰化，有效期标红 | `validUntil` 已过 | ✅ |
| `degraded` | 琥珀边框 + 顶部"数据延迟"标，隐藏目标数量（PAUSE 化） | 行情延迟/单源失败 | ✅ |
| `triggered` | 触发条件已满足（绿色对勾标"已触发"） | 实时监控命中 | — |
| `recorded` | 灰色"已记录操作"标，操作按钮消失 | 用户已记录 | — |
| `skeleton` | 卡片轮廓 + 灰条占位（§14.1） | 首次加载 | — |

**§9.3 硬规则：** `pause` 时**不显示目标交易数量和醒目行动按钮**，只显示原因（`degradeReason`）+ 可用事实。这是产品红线，前端必须有断言测试。

### 3.3 固定信息层级（6 级，不可调序）

```
① 标的代码/名称 + 行动标签 + 风险级别
② 当前仓位 → 目标仓位区间（pause 隐藏）
③ 一句话条件式摘要（≤3 行）
④ 触发条件 / "为什么现在关注"
⑤ 行情时间 · 有效期 · 数据状态
⑥ [查看 N 条依据] [记录操作]
```

---

## 4. Risk Alert（§9.4 + §18.3）

**文件落点：** `frontend/src/shared/ui/RiskAlert.vue`

### Props

```ts
interface RiskAlertProps {
  level: 'info' | 'warning' | 'critical'
  variant?: 'compact' | 'full'   // §18.3 必交两形态
  title: string
  impact?: string                // critical 必填："影响什么"
  action?: string                // critical 必填："如何处理"
}
```

| level | 触发 | 颜色 | 位置规则 |
|---|---|---|---|
| `info` | 需要知道但不要求立即处理 | 蓝 | 内联 |
| `warning` | 当日应查看 | 琥珀 #DC6803 | 区块顶部 |
| `critical` | 硬限制/重大公告/账本或数据严重异常 | 洋红 #C11574 | **固定在页面重要内容之前** |

**§9.4 硬规则：** Critical 必须含 `impact` + `action`，**禁止仅显示错误代码**；`compact` 用于列表项，`full` 用于页内。

---

## 5. Position Card（§9.5 + §18.3）

**文件落点：** `frontend/src/shared/ui/PositionRow.vue`

### 状态变体（§18.3 必交 6 态）

| state | 视觉 | 触发 |
|---|---|---|
| `normal` | 白底 | 默认 |
| `up` | 数值红 #D92D20（A 股红涨） | 当日涨 |
| `down` | 数值绿 #079455（A 股绿跌） | 当日跌 |
| `alert` | 行首洋红风险图标 + 淡红底 | 触发 Critical 风险 |
| `stale` | 行情时间灰化 + "延迟"小标 | 行情过期 |
| `skeleton` | 灰条占位 | 加载中 |

**硬规则：** 移动单行 72–88px；左滑"自选/更多"**不能作为唯一入口**，详情点击始终有效；右侧主指标可切换（市值/仓位/持有收益）。

---

## 6. HOME-01 首页页面状态（§10.3）

**文件落点：** `frontend/src/features/home/pages/HomeOverview.vue`

页面级状态由 `marketPhase` + 数据健康度组合驱动，**不是 6 张独立稿，而是同一组件的条件分支**。

| 页面状态 | marketPhase | 核心差异（vs 盘前默认态） |
|---|---|---|
| 盘前（默认，已有 Stitch 稿） | `pre-open` | 突出开市前报告 + 今日观察 |
| **盘中** | `trading` | DataStatusBar=green+秒级时间；突出盘中风险 + **盘中快捷问询入口**（盘前没有）；AdviceCard 显示实时触发的条件式建议 |
| **收市后** | `closed` | DataStatusBar=灰"已收盘"；**收市后复盘卡置顶**（替代开市前报告位）；盈亏归因摘要；AdviceCard 改"已执行"标 |
| 非交易日 | `non-trading` | 突出研究入口 + 最近周总结，**不伪装实时** |
| **空账户** | — | **不展示 ¥0 假仪表盘**（§10.3 红线）；改为插画 + 导入/录入引导按钮 |
| **离线**（§14.4） | — | 顶部常驻离线条；DataStatusBar=offline；缓存值标"•缓存"；隐藏刷新/盘中问询；缓存报告标"离线副本"且不更新时间 |

> 已尝试用 Stitch 生成盘中/收市后/离线 3 态，未产出（见本文 §1）。前端按上表条件分支实现。

---

## 7. CHAT-01 助手对话状态（§10.12）

**文件落点：** `frontend/src/features/assistant/pages/AssistantChat.vue`

| 状态 | 触发 | 视觉规则 |
|---|---|---|
| 正常（已有 Stitch 稿） | 数据健康 | AdviceCard 完整展示，含有效期 |
| **生成中** | 用户发送后 | **分阶段时间线**：✓获取行情 → ✓检查持仓 → ●运行风险规则(脉动) → ○生成解释；12s 规则：先展示确定性结果；AdviceCard 骨架占位；输入框 Loading |
| **行情过期** | 行情 > 90s | 输入框上方**常驻琥珀提示**"当前无法提供即时交易数量"；历史 AdviceCard 贴"已过期"红 Badge + 60% 灰化；当前回复为 **PAUSE 变体**（不显示数量，§9.3 硬规则） |

**§10.12 硬规则：** AI 核心建议**禁用普通聊天气泡**，必须用 AdviceCard；数据上下文在回答**开头**显示，不藏底部免责声明。

---

## 8. 全局状态（§14 + §18.4 必交）

### 8.1 加载（§14.1）

| 场景 | 规则 |
|---|---|
| 首次加载 | **结构 Skeleton**（保留卡片轮廓+标签，灰化动态数据），**不用全屏 Spinner** |
| 刷新已有数据 | 保留旧内容，顶部/局部刷新指示，**不清空页面** |
| 行情更新 | 只刷新受影响数字和时间 |
| 长任务 | 步骤时间线 + "可离开"提示 |

### 8.2 空状态（§14.2，6 类必设计）

| 场景 | 文案基调 |
|---|---|
| 尚无账户/持仓 | 引导导入/录入，**不展示 ¥0 假仪表盘** |
| 有账户无交易 | 平静 |
| 尚无自选 | 平静 |
| 尚无报告/研究 | "首份开市前报告将在交易日 08:45 生成" |
| 无匹配搜索 | 平静 |
| 当前没有风险/建议 | **"没有风险"用平静文字，不使用庆祝动画**——只代表规则未触发 |

### 8.3 异常状态（§14.3，9 类必设计）

每个异常必须四要素：**发生了什么 / 哪些仍可信 / 哪些暂停 / 用户下一步**。

- 完全离线、单一数据源失败、多源冲突、行情过期、模型不可用、报告部分完成、任务失败可重试、数据库/存储只读、未登录/会话过期

### 8.4 会话过期（§14.5）

- 保留未提交的**非敏感**表单草稿（如 TX-02 普通交易）
- 交易、恢复等**敏感表单不在浏览器长期存储**
- 弹出重新登录模态；重新认证后回原页面并重新校验数据

---

## 9. Evidence Drawer（§9.6 + §18.3）

**文件落点：** `frontend/src/shared/ui/EvidenceDrawer.vue`

§18.3 必交 4 来源变体：

| 来源类型 | 可信等级标 | 视觉 |
|---|---|---|
| `official` 官方公告/财报 | L1 绿 | 绿色 Badge |
| `professional` 授权行情/专业供应商 | L2 蓝 | 蓝色 Badge |
| `news` 可信新闻 | L3 琥珀 | 琥珀 Badge |
| `unverified` 未证实 | — | **洋红虚线边框 + 警示**，禁止与 `事实` 标签混排 |

**形态：** 移动 80–92% Bottom Sheet；桌面 360–420px 右抽屉。明确区分"事实来源"与"模型引用"。

---

## 10. 前端实现优先级建议

按 §18.3 必交 + MVP 阻塞程度排序：

| 优先级 | 组件 | 必交状态数 | 阻塞页面 |
|---|---|---|---|
| P0 | DataStatusBar | 4 | HOME-01/PORT-01/CHAT-01/REP 全部 |
| P0 | AdviceCard（含 PAUSE 硬规则） | 6动作×4状态 | HOME-01/HOME-02/CHAT-01/PORT-02 |
| P0 | RiskAlert（Critical 固定） | 3×2 | 全页面 |
| P0 | 全局 加载/空/异常/会话过期 | 4 | 全页面 |
| P1 | PositionRow | 6 | PORT-01/HOME-01 |
| P1 | EvidenceDrawer | 4 | REP-03/CHAT-02 |
| P2 | Fact/Calculation/Judgment 标签 | 4 | REP-03 |

---

## 11. 验收清单（对照 §18.3 必交 Variant）

实现完成后，下列断言必须通过（建议写 vitest 单测）：

- [ ] DataStatusBar 4 态均有，点击进 DATA-01 非 Toast
- [ ] AdviceCard 6 动作色彼此可辨，且**不与行情红绿混用**
- [ ] AdviceCard `pause` 态**断言不渲染** `targetRange`/数量/醒目按钮
- [ ] AdviceCard `expired` 态透明度 ≤ 60% 且贴红 Badge
- [ ] RiskAlert `critical` 含 `impact` + `action`，非空错误代码
- [ ] HOME-01 空账户态**断言不渲染** ¥0 数值
- [ ] HOME-01 离线态断言刷新按钮 `disabled`
- [ ] CHAT-01 生成中态显示分阶段时间线（4 步）
- [ ] CHAT-01 行情过期态：当前回复为 PAUSE 变体，无交易数量
- [ ] 全局加载态**无全屏 Spinner**，用 Skeleton
- [ ] 空风险态文案平静，**无庆祝动画**
- [ ] EvidenceDrawer `unverified` 态洋红虚线边框

---

*本文是 UI 规范的工程化提炼，冲突时以 [UI_DESIGN_SPECIFICATION.md](../UI_DESIGN_SPECIFICATION.md) 上游为准。*
