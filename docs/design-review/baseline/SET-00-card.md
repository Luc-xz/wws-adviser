# 基准卡：SET-00 设置首页

> 本批次动作：V 对齐 + 子页入口（SET-01~08 子页在波 V4 各自建卡）。

## 1. 参考稿

- 移动：`stitch/mobile/SET-00-mobile.html`（最终版）
- 桌面：`stitch/SET-00-desktop.html`（响应式自适应）

## 2. 布局结构（从稿人工提取）

```
1. 顶栏（标题「设置」+ 头像）
2. 账户区（用户名 + 会话状态摘要）
3. 设置分组列表（icon + 标题 + 当前值摘要 + chevron）：
   投资与风险 / 凯利参数 / 数据源 / 模型 / 通知与隐私 / 任务时间 / 安全 / 备份 / 系统
4. 外观（深色模式开关）
5. 通知（Web Push 开启按钮——Phase 3.5 已接）
6. 登出（全宽次级按钮，含清私有缓存语义）
```

- 栅格/分栏：移动分组列表单列；桌面双列分组卡
- 滚动行为：整页滚动
- 桌面差异：分组卡 2 列；登出移至账户区

## 3. 关键尺寸

| 位置 | 稿实测 | 落点 token |
| --- | --- | --- |
| 分组行高 | ~56px | `py-3`（行内 icon 20px） |
| 行标题 | 14px/500 | `text-body font-medium` |
| 行摘要值 | 13px | `text-label text-gray-500` |
| 分组卡 | 14px 圆角 | `rounded-lg` |
| chevron | 图标 20px 线性 1.75 | `i-carbon-chevron-right text-xl` |

## 4. 组件清单

| 组件 | 需覆盖 variant |
| --- | --- |
| 设置行（SettingsRow） | 有摘要值 / 无值 / 危险动作（登出全部） |
| 开关 | 深色模式 / 隐私模式 |
| Push 开启按钮 | idle/enabling/enabled/denied/unsupported |

## 5. 稿内违例覆盖注记（disregarded）

| 稿位置 | 违例内容 | 覆盖依据 |
| --- | --- | --- |
| SET-02-desktop | 3 处 tabular-nums 未覆盖（子页卡承接） | §2.2 |
| 稿未含 Push/Passkey 区块 | 稿早于 Phase 3.5 | 以代码现状为准（本卡 §2 第 5 项） |

## 6. 走查项打勾区

- [ ] 三截图并排贴 PR
- [ ] 子页入口与 §3 差距矩阵路由一一对应（V4 完成后全通）
- [ ] 登出确认（清缓存提示）+ 深色开关即时生效
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

