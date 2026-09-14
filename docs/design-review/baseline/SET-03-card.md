# 基准卡：SET-03 模型与任务路由

> 补卡（审计回填 2026-09-09）：V4 已实现页的追溯基准卡。密钥只存 env 引用名、
> 绝不回显明文（8_SECURITY §5）。UI 规范 §18.2 点名本页需单独深色设计。

## 1. 参考稿

- 移动：`stitch/mobile/SET-03-mobile.html`（最终版）
- 桌面：`stitch/SET-03-desktop-v2.html`（取 v2）

## 2. 布局结构

```
1. PageHeader（title「模型与任务路由」+ subtitle「密钥只存 env 引用名，绝不回显明文（8_SECURITY §5）」）
2. 参数表单卡（Base URL / 模型名 / 温度（0~1） / 最大输出 tokens / 超时（秒） / 重试次数）
3. 保存条（保存 + 成功提示）
```

- 栅格/分栏：单列表单
- 滚动行为：整页滚动
- 桌面差异：无（响应式同构）

## 3. 关键尺寸

| 位置 | 稿实测 | 落点 token |
| --- | --- | --- |
| 字段标签 | — | `text-label text-gray-500` |
| 数值输入 | — | `num`（tabular-nums） |
| 卡片 | — | `p-4` + `rounded-lg` |
| 密钥占位 | — | env 引用名（如 `WWSE_MODEL_KEY`），placeholder 不含明文 |

## 4. 组件清单

| 组件 | 需覆盖 variant |
| --- | --- |
| 参数字段 | URL / 文本 / 数值 |
| 密钥显示 | env 引用名（脱敏恒态） |
| 保存 | idle / submitting / 成功提示 |

## 5. 稿内违例覆盖注记（disregarded）

| 稿位置 | 违例内容 | 覆盖依据 |
| --- | --- | --- |
| 稿密钥输入框回显 | 明文/掩码输入 | 8_SECURITY §5：只存 env 引用名 |
| 稿英文文案 | 英文占位 | 中文文案规范 |

## 6. 走查项打勾区

- [ ] 三截图并排贴 PR
- [x] 深色 dark: 单独核验（UI §18.2 点名页，V5 扫描清零）
- [x] 默认 / 加载 / 空 / 异常四态
- [x] 门禁全绿

---

## 勘误增补：视觉语言字段（2026-09-11 W3-C）

> V1 建卡时未收录视觉语言三要素，致 V3/V4 实现'结构对齐但观感不像'（见 11_LAUNCH_QUALITY_PLAN §0/W3-C）。W3 起以下字段为建卡必填，本卡按已上线的 W3 视觉基线（material-symbols-rounded 图标系 / 卡片 rounded-2xl / 彩色 icon 容器 / 系统字体栈）回填勘误。

| 字段 | 本页基线 |
| --- | --- |
| 图标体系 | material-symbols-rounded（构建期内联）；导航/卡头图标与原型稿一一对位 |
| 圆角档位 | 卡片 rounded-2xl（16px）；按钮/输入 rounded-md/lg；禁用其他档位 |
| 色彩容器 | 摘要/入口卡 icon 容器：语义色 10% 底 + 同色 icon（primary/market/risk 族） |
| 字体 | 系统栈（SF/Segoe + 苹方/雅黑）+ antialias（Q2-A 决策，弃 Inter） |

