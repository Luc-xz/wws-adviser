# 基准卡：HOME-01 首页总览

## 1. 参考稿

- 移动：`stitch/mobile/HOME-01-mobile.html`（最终版；**弃 v1**——v1 密度与信息层级早于定稿）
- 桌面：`stitch/HOME-01-desktop.html`（注意：本稿 6 处违例，覆盖注记见 §5）

## 2. 布局结构（从稿人工提取）

```
1. 顶栏（问候语 + 刷新 + 头像，56px）
2. DataStatusBar（市场状态 + 行情更新时间，点击进 DATA-01）
3. 组合摘要卡（总资产 Display 大数字 + 今日盈亏；现金占比 / 风险等级两列）
4. 风险聚合条（"N 项风险需要处理" → 危险色横条，Critical 前置）
5. 今日行动（建议卡列表；HOME-01-mobile:208 为 6 层信息标杆）
6. 持仓概览（Top5 持仓行，见 PORT-01 行规范）
7. 最新报告入口卡
8. 空账户 → empty-guide（绝不显示假 ¥0）
```

- 栅格/分栏：移动单列；桌面 8/4 两栏（左：行动+持仓；右：风险+任务+数据状态，UI §5.2）
- 滚动行为：整页滚动；桌面两栏独立滚动不常见，保持整页
- 桌面差异：摘要卡数字升 `text-display-d`；右栏收纳风险聚合与数据状态

## 3. 关键尺寸

| 位置 | 稿实测 | 落点 token |
| --- | --- | --- |
| 区块间距 | 24px | `space-y-6` |
| 卡片内边距 | 16px | `p-4` |
| 总资产数字 | 28/32px·700 | `text-display lg:text-display-d font-bold num` |
| 建议卡 footer | 12px | `text-caption`，句式 `截至 · 来源 · 有效至` |
| 卡片圆角 | 14px | `rounded-lg` |

## 4. 组件清单

| 组件 | 需覆盖 variant |
| --- | --- |
| DataStatusBar | 4 态（normal/degraded/offline/unknown） |
| MetricCard | 主数字 + 同环比副行 |
| RiskAlert | Info/Warning/Critical（Critical 固定前置于内容前） |
| AdviceCard（摘要形态） | 6 动作色族；PAUSE 零数量 |
| PositionRow | 正常 / 数据过期角标 |

## 5. 稿内违例覆盖注记（disregarded）

| 稿位置 | 违例内容 | 覆盖依据 |
| --- | --- | --- |
| HOME-01-desktop:456-457 | 任务完成用下跌绿 | §3.2 成功≠行情绿 → `success` |
| HOME-01-desktop:477-496 | 数据源健康度全用下跌绿 | §3.3 在线健康 → `online` teal |
| HOME-01-desktop:184-187 | "交易中"状态绿点 | §3.3 → `online`，非 market-down |
| HOME-01-desktop:255-290 | 今日建议区无 footer | §8.3 footer 句式必填（以 mobile:208 为准） |
| HOME-01-desktop:407-413 | Critical 缺"影响什么/如何处理" | §5（REP-01-mobile:198 为正向形态） |
| HOME-01-desktop:273,518 | "立即执行/快速下单"按钮 | §4.1/§9.8 系统不提供立即买卖——**稿已修**（波 V1） |
| HOME-01-mobile:208 附近 | "减少"卡用 error 红 | §3.1 减少建议 → `action-reduce` 深橙（footer 句式保留为标杆） |

## 6. 走查项打勾区

- [ ] 三截图并排贴 PR
- [ ] tabular-nums / 负号 `−` / 空值 `—` / footer 句式
- [ ] 组件 variant 完整（§4 全部可达）
- [ ] 默认/加载/空/异常四态；空账户 empty-guide
- [ ] 门禁全绿；深色 dark: 核验
- [ ] 离线态：刷新禁用 + 提示（AC-08）
