# 基准卡：DATA-01 数据状态中心

## 1. 参考稿

- 移动：`stitch/mobile/DATA-01-mobile.html`（最终版）
- 桌面：`stitch/DATA-01-desktop.html`（响应式自适应；ACTIVE/在线绿违例见 §5）

## 2. 布局结构（从稿人工提取）

```
1. 顶栏（返回 + 标题 + 刷新）
2. 系统总状态卡（System Normal + 汇总徽标）
3. 数据源卡片列表（行情/日历/净值/公告：状态 · 延迟 · 最近同步时间）
4. 数据质量区（quality_status 徽标行；Phase 3.3 起 + conflicts 入口/列表）
5. 净值区（须显示净值日期，非仅数值）
```

- 栅格/分栏：移动单列卡片堆叠；桌面双列网格
- 滚动行为：整页滚动
- 桌面差异：数据源卡 2 列 grid，质量区右侧

## 3. 关键尺寸

| 位置 | 稿实测 | 落点 token |
| --- | --- | --- |
| 数据源卡 | 16px 内边距 | `p-4` |
| 状态徽标 | 12px 圆角 6px | `text-caption rounded-sm` |
| 延迟/时间行 | 12px | `text-caption` |
| 区块间距 | 24px | `space-y-6` |

## 4. 组件清单

| 组件 | 需覆盖 variant |
| --- | --- |
| DataStatusBar（页内汇总形态） | 4 态 |
| 状态徽标 | online/degraded/offline/unknown + 质量态（OK/DELAYED/MISSING/CONFLICT…） |
| conflicts 列表行（Phase 3.3） | UNRESOLVED / RESOLVED（含消解按钮） |

## 5. 稿内违例覆盖注记（disregarded）

| 稿位置 | 违例内容 | 覆盖依据 |
| --- | --- | --- |
| DATA-01-desktop:339-367 | 数据源 ACTIVE/在线用下跌绿 | §3.3 → `online` teal（ADR-0009） |
| DATA-01-mobile:254 | 基金净值无净值日期；空值用 `-` | §8.1 净值必须带日期；空值统一 `—` |

## 6. 走查项打勾区

- [ ] 三截图并排贴 PR
- [ ] tabular-nums / 空值 `—` / 时间戳格式统一
- [ ] conflicts（若存在）可见且可消解（SET-02 落点，Phase 3.3）
- [ ] 默认/加载/空/异常四态
- [ ] 门禁全绿；深色 dark: 核验

---

## 勘误增补：视觉语言字段（2026-09-11 W3-C）

> V1 建卡时未收录视觉语言三要素，致 V3/V4 实现'结构对齐但观感不像'（见 11_LAUNCH_QUALITY_PLAN §0/W3-C）。W3 起以下字段为建卡必填，本卡按已上线的 W3 视觉基线（material-symbols-rounded 图标系 / 卡片 rounded-2xl / 彩色 icon 容器 / 系统字体栈）回填勘误。

| 字段 | 本页基线 |
| --- | --- |
| 图标体系 | material-symbols-rounded（构建期内联）；导航/卡头图标与原型稿一一对位 |
| 圆角档位 | 卡片 rounded-2xl（16px）；按钮/输入 rounded-md/lg；禁用其他档位 |
| 色彩容器 | 摘要/入口卡 icon 容器：语义色 10% 底 + 同色 icon（primary/market/risk 族） |
| 字体 | 系统栈（SF/Segoe + 苹方/雅黑）+ antialias（Q2-A 决策，弃 Inter） |

