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

---

## 增补：分区 tab 与「采集运行」（采集监控面板波2，2026-11-13）

> 依据：5_DATA §12（v1.1）/ 3_API §3.13/§3.17。页首新增分段 tab：**数据质量**（原 V1–V4 全部内容不动）
> / **采集运行**（过程态新增）。深链 `?tab=runs` 直达。无新参考稿——结构沿用本卡既有
> 卡片语言（rounded-2xl 白卡 + caption 副行 + 徽标），按"先建卡再写代码"回填。

### 布局（采集运行 tab，移动单列 / 桌面同页栅格）

```
0. 分段 tab（圆角胶囊容器，双按钮，aria-selected）
1. 近 7 日任务（三格 mini 卡：任务数 / 成功率 / 平均耗时；连续失败警示行）
2. 数据源健康（六类别卡：类别名 + 最近成功相对时间·连败·覆盖徽标行 + 健康徽标）
3. 任务运行近况（批次行：类型+业务日期+状态徽标+摘要+耗时 ▼；展开=条目明细）
   3a. 展开区：筛选 chips（全部/仅失败）+ 条目计数行
   3b. 条目行：display_name + 徽标 + 行数/源/耗时/错误 + FAILED 日线「手动补采」
```

### 组件与状态

| 元素 | variant / 约束 |
| --- | --- |
| 分段 tab | 胶囊容器 `rounded-full bg-gray-100`；选中 `bg-white shadow-sm text-primary`（深色 `dark:bg-gray-700`） |
| 任务状态徽标 | 7 态（COMPLETED→success / PARTIAL→risk-warning / FAILED→error / RUNNING→**online** / 其余→gray；9 态文案对齐 UI §8.4） |
| 源健康徽标 | ok→**online teal**（ADR-0009）/ degraded→risk-warning / unavailable→error / no_data→gray；禁行情涨跌色 |
| 条目状态徽标 | OK→success / SKIPPED→gray / PARTIAL→risk-warning / FAILED→error |
| 数值 | 一律过 `formatCount` / `formatDuration` / `formatRate`（shared/format，ENFORCEMENT_CONTRACT §2） |
| 相对时间 | `formatRelativeTime`（刚刚/N分钟前/N小时前/昨天 HH:mm/YYYY-MM-DD；未来时间不伪装） |

### 四态与边界

- 加载：Skeleton（metric/row/text 按区块形态）；
- 空：任务列表空文案"定时任务 15:20 后与手动补采在此展示"；条目空=「早于明细记录功能上线」占位（5_DATA §12.4，不回填）；
- 异常：查询失败沿 Vue Query 默认重试 + 上方区块各自空态；补采失败 inline `text-error` 文案（不弹 Toast）；
- 特殊：`news` 类别恒 `no_data + 未配置真实数据源`——如实暴露 FR-DATA-005 缺口，不做假健康。

### 走查增补

- [ ] tab 切换不丢质量 tab 已有交互（conflicts/审计折叠）
- [ ] FAILED 条目「手动补采」闭环：点击→按钮禁用→列表刷新出新批次（ingest_manual）
- [ ] 深色：胶囊 tab / 徽标 / 条目底 `dark:bg-gray-700/50` 核验

