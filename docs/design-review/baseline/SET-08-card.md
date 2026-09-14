# 基准卡：SET-08 系统状态

> 补卡（审计回填 2026-09-09）：V4 已实现页的追溯基准卡。健康探针：
> 进程存活（/health/live）+ 就绪（/health/ready，DB/迁移）+ 数据源与模型依赖。

## 1. 参考稿

- 移动：`stitch/mobile/SET-08-mobile.html`（最终版）
- 桌面：`stitch/SET-08-desktop-v2.html`（取 v2）

## 2. 布局结构

```
1. PageHeader（title「系统状态」+ subtitle「进程存活 / 就绪 / 数据源与模型依赖」）
2. 探针行（存活：正常/异常/检测中；就绪：正常/异常（DB/迁移）/检测中——三态即时探测）
3. 依赖一览区（§标题 + 数据源与模型依赖状态列表）
```

- 栅格/分栏：移动探针行纵向；桌面并排
- 滚动行为：整页滚动
- 桌面差异：探针行横向双列

## 3. 关键尺寸

| 位置 | 稿实测 | 落点 token |
| --- | --- | --- |
| 探针行 | — | 行式卡 `p-4` + `rounded-lg` |
| 状态值 | — | `text-body font-medium` + 语义色（success / risk-critical / gray） |
| 区块标题 | — | `text-h3 font-semibold lg:text-h3-d` |

## 4. 组件清单

| 组件 | 需覆盖 variant |
| --- | --- |
| 探针行 | ok / fail / 检测中（pending） |
| 依赖行 | 正常 / 降级 / 异常 |

## 5. 稿内违例覆盖注记（disregarded）

| 稿位置 | 违例内容 | 覆盖依据 |
| --- | --- | --- |
| 稿英文文案 | 英文占位 | 中文文案规范 |
| 稿探针为静态徽标墙 | 与真实探针 API 不符 | 以 /health/* 契约为准（三态即时探测） |

## 6. 走查项打勾区

- [ ] 三截图并排贴 PR
- [x] 默认 / 加载（检测中）/ 空 / 异常四态（fail 态文案含 DB/迁移定位）
- [x] 门禁全绿；深色 dark: 核验（V5 扫描清零）

---

## 勘误增补：视觉语言字段（2026-09-11 W3-C）

> V1 建卡时未收录视觉语言三要素，致 V3/V4 实现'结构对齐但观感不像'（见 11_LAUNCH_QUALITY_PLAN §0/W3-C）。W3 起以下字段为建卡必填，本卡按已上线的 W3 视觉基线（material-symbols-rounded 图标系 / 卡片 rounded-2xl / 彩色 icon 容器 / 系统字体栈）回填勘误。

| 字段 | 本页基线 |
| --- | --- |
| 图标体系 | material-symbols-rounded（构建期内联）；导航/卡头图标与原型稿一一对位 |
| 圆角档位 | 卡片 rounded-2xl（16px）；按钮/输入 rounded-md/lg；禁用其他档位 |
| 色彩容器 | 摘要/入口卡 icon 容器：语义色 10% 底 + 同色 icon（primary/market/risk 族） |
| 字体 | 系统栈（SF/Segoe + 苹方/雅黑）+ antialias（Q2-A 决策，弃 Inter） |

