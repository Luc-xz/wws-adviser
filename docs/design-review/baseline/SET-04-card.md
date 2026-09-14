# 基准卡：SET-04 通知与隐私

> 补卡（审计回填 2026-09-09）：V4 已实现页的追溯基准卡。Web Push 已接后端
> （usePushManager，Phase 3.5）；FR-NOTIFY-003 锁屏脱敏开关。

## 1. 参考稿

- 移动：`stitch/mobile/SET-04-mobile-v2.html`（取 v2）
- 桌面：响应式自适应

## 2. 布局结构

```
1. PageHeader（title「通知与隐私」+ subtitle「渠道状态 · 锁屏脱敏 · 浏览器推送」）
2. 渠道状态卡（各通知渠道开闭一览）
3. 隐私卡（§「锁屏脱敏」+ privacy-toggle 开关 + 保存 privacy-save）
4. Web Push 卡（§「浏览器推送」+ push-enable-set04 按钮）
```

- 栅格/分栏：单列分组卡
- 滚动行为：整页滚动
- 桌面差异：无（响应式同构）

## 3. 关键尺寸

| 位置 | 稿实测 | 落点 token |
| --- | --- | --- |
| 分组卡 | — | `p-4` + `rounded-lg` + shadow-sm |
| 区块标题 | — | `text-h3 font-semibold` |
| 开关 | — | 全局 toggle 基类 |
| Push 按钮 | — | idle / enabling / enabled / denied / unsupported 五态 |

## 4. 组件清单

| 组件 | 需覆盖 variant |
| --- | --- |
| 渠道行 | 开 / 关 |
| privacy-toggle | on / off（FR-NOTIFY-003 说明文案随动） |
| push-enable-set04 | idle / enabling / enabled / denied / unsupported |

## 5. 稿内违例覆盖注记（disregarded）

| 稿位置 | 违例内容 | 覆盖依据 |
| --- | --- | --- |
| v1 稿 Push 形态 | 与 Phase 3.5 实装不符 | 取 v2；以 push API 契约为准 |
| 稿英文文案 | 英文占位 | 中文文案规范 |

## 6. 走查项打勾区

- [ ] 三截图并排贴 PR
- [x] 默认 / 加载 / 空 / 异常四态（denied/unsupported 有专属态）
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

