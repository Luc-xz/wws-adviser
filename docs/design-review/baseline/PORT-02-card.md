# 基准卡：PORT-02 标的/持仓详情

> 补卡（审计回填 2026-09-09）：V4 已实现页的追溯基准卡。入口：PORT-01 持仓行、
> HOME 持仓概览整行导航（PositionRow `to` prop）。稿有多个变体（-cn / -maotai），
> 结构取通用版。

## 1. 参考稿

- 移动：`stitch/mobile/PORT-02-mobile.html`（通用版；-cn/-maotai 为数据变体）
- 桌面：`stitch/PORT-02-desktop.html`（响应式：区块两列化）

## 2. 布局结构

```
1. PageHeader（title「{名称} {代码}」+ subtitle「{市场} · {类型} · 价格精度 {n}」+ 返回）
2. 行情卡（「日线收盘」+ TrendChart 近 30 日趋势；无日线 → 空态「暂无日线（采集后展示）」
   + DataFooter 截至「最近采集」）
3. 持仓明细卡（持有才显示：数量 / 成本 / 市值 / 占比 dl 网格）
4. 相关公告与文档（docs 列表；空态「暂无相关文档」）
```

- 栅格/分栏：移动单列；桌面 dl 网格 `grid-cols-2 sm:grid-cols-4`
- 滚动行为：整页滚动
- 桌面差异：区块标题 `lg:text-h3-d`；明细网格展宽

## 3. 关键尺寸

| 位置 | 稿实测 | 落点 token |
| --- | --- | --- |
| 收盘价数字 | — | `text-h3 font-semibold num` + `data-num` |
| 区块标题 | — | `text-h3 font-semibold lg:text-h3-d` |
| 明细 dl 标签/值 | — | `text-caption text-gray-400` / `text-body font-medium num` |
| 卡片 | — | `p-4` + `rounded-lg` + shadow-sm |

## 4. 组件清单

| 组件 | 需覆盖 variant |
| --- | --- |
| PageHeader | 动态标题（标的加载前后）+ 返回 |
| TrendChart | 有数据 / 无数据（空态文案） |
| 持仓明细 dl | 持有 / 未持有（整卡隐藏） |
| 文档列表 | 有 / 空 |

## 5. 稿内违例覆盖注记（disregarded）

| 稿位置 | 违例内容 | 覆盖依据 |
| --- | --- | --- |
| -maotai 变体行情色 | 涨跌用蓝绿系 | ADR-0009 A 股红涨绿跌（`market-up/down`） |
| 稿英文文案 | 英文占位 | 中文文案规范 |

## 6. 走查项打勾区

- [ ] 三截图并排贴 PR
- [x] footer 句式（`截至 · 来源`，行情卡 DataFooter）
- [x] 默认 / 加载 / 空 / 异常四态（无日线/无持仓/无文档均有态）
- [x] 门禁全绿；深色 dark: 核验（V5 扫描清零）
