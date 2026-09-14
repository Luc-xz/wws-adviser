# 基准卡：TX-01 交易流水

> 补卡（审计回填 2026-09-09）：V4 已实现页的追溯基准卡；结构/四态以实现为准，稿作密度参照。
> 本页语义决策见计划 §10-Q2：全量流水独立页，PORT 流水 Tab 只留持仓视角摘要。

## 1. 参考稿

- 移动：`stitch/mobile/TX-01-mobile.html`（最终版）
- 桌面：`stitch/TX-01-desktop.html`（响应式：列表区 max-w 收窄）

## 2. 布局结构

```
1. PageHeader（title「交易流水」+ subtitle「全量记录 · 指纹去重 · 类型与标的筛选」
   + 右上主按钮「记一笔」→ /transactions/new）
2. 筛选行（类型下拉 TX_KINDS 全集 + 标的下拉，变更即重载）
3. 错误条（error 时，text-risk-critical）
4. 空态卡（loaded 且无行：「暂无交易记录」→ 引导导入/手工）
5. 流水列表（行：类型徽标 KIND_NAMES + 标的 + 方向 + 数量×价格 + 费税角标 + 时间）
6. 加载更多（hasMore 时；footer 计数「共 N 条（可继续加载）」）
```

- 栅格/分栏：单列列表；桌面列表卡居中
- 滚动行为：整页滚动；keyset 游标分页（`cursor` + `has_more`，非页码）
- 桌面差异：筛选行与列表同宽排布，无表格化改造

## 3. 关键尺寸

| 位置 | 稿实测 | 落点 token |
| --- | --- | --- |
| 页面主标题 | — | PageHeader `text-h1 lg:text-h1-d` |
| 区块标题 | — | `text-h3 font-semibold` |
| 列表行内边距 | — | `p-4`（space.4） |
| 卡片圆角 | — | `rounded-lg`（14px） |
| 行内数字 | — | `num` + `data-num`（tabular-nums） |

## 4. 组件清单

| 组件 | 需覆盖 variant |
| --- | --- |
| PageHeader | 有副标题 + 右上动作 |
| 筛选下拉 | 全类型 / 单类型；标的联动 |
| 流水行 | 8 种类型徽标；费税>0 角标；方向（买入/卖出） |
| 加载更多 | idle / loading（「加载中…」） |
| 404 空态 | 无账户 → 空列表非错误（TX-01 决策，HOME 同口径） |

## 5. 稿内违例覆盖注记（disregarded）

| 稿位置 | 违例内容 | 覆盖依据 |
| --- | --- | --- |
| 稿分页器 | 页码分页 | 实现 keyset 游标（后端 API 语义），UI 以「加载更多」承接 |
| 稿英文文案 | 英文占位 | 中文文案规范（UI §7 + 模板三层合成） |

## 6. 走查项打勾区

- [ ] 三截图（桌面 1440 / 移动 375 / 深色）并排贴 PR
- [x] tabular-nums（`data-num`）/ 空值 `—`
- [x] 默认 / 加载 / 空 / 异常四态；空态无假数据
- [x] 404 = 无账户 → 空态
- [x] 门禁全绿（eslint + vue-tsc + vitest + build）；深色 dark: 核验（V5 扫描清零）

---

## 勘误增补：视觉语言字段（2026-09-11 W3-C）

> V1 建卡时未收录视觉语言三要素，致 V3/V4 实现'结构对齐但观感不像'（见 11_LAUNCH_QUALITY_PLAN §0/W3-C）。W3 起以下字段为建卡必填，本卡按已上线的 W3 视觉基线（material-symbols-rounded 图标系 / 卡片 rounded-2xl / 彩色 icon 容器 / 系统字体栈）回填勘误。

| 字段 | 本页基线 |
| --- | --- |
| 图标体系 | material-symbols-rounded（构建期内联）；导航/卡头图标与原型稿一一对位 |
| 圆角档位 | 卡片 rounded-2xl（16px）；按钮/输入 rounded-md/lg；禁用其他档位 |
| 色彩容器 | 摘要/入口卡 icon 容器：语义色 10% 底 + 同色 icon（primary/market/risk 族） |
| 字体 | 系统栈（SF/Segoe + 苹方/雅黑）+ antialias（Q2-A 决策，弃 Inter） |

