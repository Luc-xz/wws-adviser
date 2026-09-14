# 基准卡：ACC-01 账户与对账

> 补卡（审计回填 2026-09-09）：V4 已实现页的追溯基准卡。对账是盘中建议前置
> （`ledger_unreconciled` 解除条件），POST reconcile 无请求体（幂等确认）。

## 1. 参考稿

- 移动：`stitch/mobile/ACC-01-mobile.html`（最终版）
- 桌面：`stitch/ACC-01-desktop.html`（响应式：账户卡展宽）

## 2. 布局结构

```
1. PageHeader（title「账户与对账」+ subtitle「对账确认是盘中建议的前置条件（ledger_unreconciled 解除）」）
2. 空态卡（无账户：「暂无账户——通过 CLI 或交易记录创建」）
3. 账户卡列表（行：账户名/类型 + 状态徽标 account-status-* + 「标记已对账」按钮 reconcile-*）
4. 对账错误条（reconcile-error，失败可重试）
```

- 栅格/分栏：单列账户卡
- 滚动行为：整页滚动
- 桌面差异：账户卡横向信息排布（徽标与按钮同行右侧）

## 3. 关键尺寸

| 位置 | 稿实测 | 落点 token |
| --- | --- | --- |
| 账户卡内边距 | — | `p-4` |
| 圆角 | — | `rounded-lg` |
| 状态徽标 | — | `text-caption` + 语义色（success / warning / gray） |
| 对账按钮 | — | 次级按钮（描边） |

## 4. 组件清单

| 组件 | 需覆盖 variant |
| --- | --- |
| PageHeader | 有副标题（业务前置说明） |
| 账户行 | 已对账 / 未对账（徽标双色） |
| 对账按钮 | idle / submitting / 失败重试 |
| 空态卡 | 无账户引导（CLI/交易创建） |

## 5. 稿内违例覆盖注记（disregarded）

| 稿位置 | 违例内容 | 覆盖依据 |
| --- | --- | --- |
| 稿英文文案 | 英文占位 | 中文文案规范 |
| 稿对账为复选清单形态 | 与后端单账户逐个确认 API 不符 | 以 reconcile API 契约为准 |

## 6. 走查项打勾区

- [ ] 三截图并排贴 PR
- [x] 默认 / 加载 / 空 / 异常四态（对账失败可重试）
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

