# 基准卡：SET-02 数据源与质量

> 补卡（审计回填 2026-09-09）：V4 已实现页的追溯基准卡。Phase 3.3 多源交叉验证
> 冲突消解闭环落在本页（conflicts 区 + 逐冲突 pick 源 + resolve）。

## 1. 参考稿

- 移动：`stitch/mobile/SET-02-mobile.html`（最终版）
- 桌面：`stitch/SET-02-desktop-v2.html`（取 v2）

## 2. 布局结构

```
1. PageHeader（title「数据源与质量」+ subtitle「多源冲突消解（SET-02）· 采集源质量一览」）
2. 冲突消解区（§标题「数据冲突」）：
   ├ 加载中（「加载中…」）
   ├ 空态（conflicts-empty：无冲突）
   └ 冲突行（标的 + 字段 + 候选源值对比 + 每源 pick 按钮 + resolve 确认）
3. 采集源质量区（各源 fresh/latency/状态一览）
```

- 栅格/分栏：移动单列；桌面冲突行内候选值横向对比
- 滚动行为：整页滚动
- 桌面差异：候选源值并排展示（移动纵向堆叠）

## 3. 关键尺寸

| 位置 | 稿实测 | 落点 token |
| --- | --- | --- |
| 区块标题 | — | `text-h3 font-semibold lg:text-h3-d` |
| 冲突行卡 | — | `p-4` + `rounded-lg` |
| pick 按钮 | — | 次级描边；选中 `bg-primary/10 text-primary` |
| 状态徽标 | — | `text-caption` 语义色 |

## 4. 组件清单

| 组件 | 需覆盖 variant |
| --- | --- |
| 冲突行 | 单候选 / 多候选；已 pick / 未 pick |
| resolve 确认 | idle / submitting / 失败 |
| 质量行 | OK / 降级 / 过期 |
| 空态 | 无冲突（正向确认文案，非错误） |

## 5. 稿内违例覆盖注记（disregarded）

| 稿位置 | 违例内容 | 覆盖依据 |
| --- | --- | --- |
| 稿无冲突消解区 | 稿早于 Phase 3.3 | 以 data_conflicts API 契约为准 |
| 稿英文文案 | 英文占位 | 中文文案规范 |

## 6. 走查项打勾区

- [ ] 三截图并排贴 PR
- [x] 默认 / 加载 / 空 / 异常四态
- [x] 门禁全绿；深色 dark: 核验（V5 扫描清零）
