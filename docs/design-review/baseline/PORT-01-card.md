# 基准卡：PORT-01 持仓与自选

> 桌面稿为全稿库正向标杆（13 处 tabular-nums 全覆盖，REVIEW_REPORT §7.1）——
> 但含 2 处演示硬伤（波 V1 已修，见 §5 前 2 行）。

## 1. 参考稿

- 移动：`stitch/mobile/PORT-01-mobile.html`（最终版）
- 桌面：`stitch/PORT-01-desktop.html`（标杆版；**弃 v2**——v2 为中途迭代）

## 2. 布局结构（从稿人工提取）

```
1. 顶栏（标题 + 头像/刷新）
2. 摘要条（总市值 + 涨跌箭头% + 现金占比 + 最大集中度，四指标横排/两列）
3. Tab 切换：当前持仓 / 自选 / 流水
4. 持仓列表（PositionRow：名称代码 · 现值 · 成本 · 盈亏额% · 权重条）
5. 自选 Tab：增删管理（app_settings KV）
6. 流水 Tab：近期记录摘要（全量流水在 TX-01，Q2 决策：本 Tab 保留持仓视角摘要）
7. ECharts 已实现盈亏趋势（Tab 内或摘要下）
```

- 栅格/分栏：移动单列；桌面持仓表全宽（等宽数字标杆 :380-399）
- 滚动行为：列表滚动；Tab 切换不回滚顶部
- 桌面差异：表格列完整展示（代码/名称/现值/成本/盈亏/权重/新鲜度角标）

## 3. 关键尺寸

| 位置 | 稿实测 | 落点 token |
| --- | --- | --- |
| 摘要条指标 | 16px 数值 | `text-body-lg num font-medium` |
| 持仓行高 | ~56px | `py-3` |
| 行内数字 | 14px 等宽 | `text-body num` |
| Tab 激活态 | 品牌色下划线 2px | `border-b-2 border-primary` |
| 区块间距 | 24px | `space-y-6` |

## 4. 组件清单

| 组件 | 需覆盖 variant |
| --- | --- |
| MetricCard（摘要条形态） | 4 指标 |
| PositionRow | 正常 / 数据过期角标 / 负盈亏（`−` U+2212） |
| Tab 切换 | 3 Tab（持仓/自选/流水） |
| TrendChart | 空（样本不足）/ 有数据 |

## 5. 稿内违例覆盖注记（disregarded）

| 稿位置 | 违例内容 | 覆盖依据 |
| --- | --- | --- |
| PORT-01-desktop:372-374 | Critical 风险行用上涨红 | §3.1 → `risk-critical` 洋红——**稿已修**（波 V1） |
| PORT-01-desktop:395 | 正盈利 +11,000 用下跌绿 | §3.1 A 股红涨 → `market-up`——**稿已修**（波 V1） |
| PORT-01-desktop:274 | 通知未读红点用行情红 | 通知 ≠ 行情 → `risk-warning`/`primary` |
| PORT-01-desktop:286-298 | 摘要金额无小数 | §8.1 金额精度（缺陷级，实现按 formatMoney） |

## 6. 走查项打勾区

- [ ] 三截图并排贴 PR
- [ ] tabular-nums（表全覆盖，向 :380-399 看齐）/ 负号 `−` / 空值 `—`
- [ ] 盈亏颜色：红涨绿跌 + 正负号并存（不能只靠颜色）
- [ ] 组件 variant 完整；四态（空账户 empty-guide）
- [ ] 门禁全绿；深色 dark: 核验
