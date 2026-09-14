# 基准卡：TX-03 CSV 导入向导

> 补卡（审计回填 2026-09-09）：V4 已实现页的追溯基准卡。三步闭环：
> 选择文件 → 校验回显 → 完成；指纹幂等去重（重复导入安全）。

## 1. 参考稿

- 移动：`stitch/mobile/TX-03-mobile.html`（最终版）
- 桌面：`stitch/TX-03-desktop-v2.html`（取 v2）

## 2. 布局结构

```
1. PageHeader（title「CSV 导入」+ subtitle「预览校验 → 勾选确认 → 指纹幂等去重」）
2. 步骤条（STEPS = [选择文件, 校验回显, 完成]；当前步 primary/10 底）
3. Step1：文件选择（FormData 上传 → preview 接口）+ 错误条
4. Step2：预览表（前 N 行回显）
   ├ 错误区（errors：不可导入行，阻断确认）
   ├ 重复区（duplicates：指纹命中，默认跳过）
   └ 确认按钮（仅无 errors 可用）
5. Step3：完成卡（导入计数摘要 + 返回流水入口）
```

- 栅格/分栏：单列；预览表横向滚动
- 滚动行为：整页滚动
- 桌面差异：预览表展宽，其余同构

## 3. 关键尺寸

| 位置 | 稿实测 | 落点 token |
| --- | --- | --- |
| 步骤条 | — | 胶囊 + `text-label`；当前步 `bg-primary/10 text-primary` |
| 卡片内边距 | — | `p-4` |
| 圆角 | — | `rounded-lg` |
| 预览表数字列 | — | `num` + `data-num` |

## 4. 组件清单

| 组件 | 需覆盖 variant |
| --- | --- |
| 步骤条 | 1/2/3 当前态 |
| 文件选择 | idle / 上传中 / 失败 |
| 预览表 | 正常 / 空（「无有效行」） |
| 错误与重复区 | 仅 errors / 仅 duplicates / 两者 / 都无 |
| 确认 | disabled（有 errors）/ idle / submitting |

## 5. 稿内违例覆盖注记（disregarded）

| 稿位置 | 违例内容 | 覆盖依据 |
| --- | --- | --- |
| 稿英文文案 | 英文占位 | 中文文案规范 |
| 稿无重复区 | 稿早于指纹去重设计 | 以导入 API 契约为准（duplicates 回显） |

## 6. 走查项打勾区

- [ ] 三截图并排贴 PR
- [x] 默认 / 加载 / 空 / 异常四态（上传失败、无有效行、确认失败均有态）
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

