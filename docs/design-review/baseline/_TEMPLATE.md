# 基准卡：<PAGE-ID> <页面名>

> 模板使用说明（VISUAL_ALIGNMENT_PLAN §2.2）：每页一张，随页面 PR 评审。
> 三层合成：布局/密度/层级取 Stitch 稿；色值/字体档位取 UI §7 + ADR-0009（唯一权威）；
> 硬规则走查项取 REVIEW_REPORT §6 + ENFORCEMENT_CONTRACT。

## 1. 参考稿

- 移动：`stitch/<PAGE-ID>-mobile.html`（版本注记：取最终版 / 取 vN，理由）
- 桌面：`stitch/<PAGE-ID>-desktop.html` 或「响应式自适应」

## 2. 布局结构（从稿人工提取）

```
区块顺序（自上而下）：
1. ...
2. ...
```

- 栅格/分栏：
- 滚动行为：
- 桌面差异：

## 3. 关键尺寸（映射 §2.3 版式 token，禁止 magic number）

| 位置 | 稿实测 | 落点 token |
| --- | --- | --- |
| 页面区块间距 | — | `p-6`（space.6 24px） |
| 卡片内边距 | — | `p-4`（space.4 16px） |
| 卡片圆角 | — | `rounded-lg`（14px） |
| 页面主标题 | — | `text-h1 lg:text-h1-d` |

## 4. 组件清单（对照 COMPONENT_STATES）

| 组件 | 需覆盖 variant |
| --- | --- |
| 例：DataStatusBar | 4 态（normal/degraded/offline/unknown） |

## 5. 稿内违例覆盖注记（disregarded——以代码强制为准）

| 稿位置 | 违例内容 | 覆盖依据（REVIEW_REPORT 索引） |
| --- | --- | --- |
| 例：PORT-01-desktop:372 | Critical 用上涨红 | §3.1 严重风险≠上涨红 → `risk-critical` 洋红 |

## 6. 走查项打勾区（§6 验收口径）

- [ ] 三截图（桌面 1440 / 移动 375 / 深色）与本卡并排贴 PR
- [ ] tabular-nums 开启面 / 负号 `−`(U+2212) / 空值 `—`
- [ ] footer 句式（`截至 · 来源 · 有效至`）
- [ ] 组件 variant 完整（本卡 §4 全部可达）
- [ ] 默认 / 加载 / 空 / 异常四态；空态无假 ¥0
- [ ] 门禁全绿（eslint 含 no-market-color-misuse + vue-tsc + vitest + build）
- [ ] 深色 dark: 变体核验（稿无深色，按 token 映射 + 对比度抽检）
