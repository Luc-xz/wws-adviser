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
