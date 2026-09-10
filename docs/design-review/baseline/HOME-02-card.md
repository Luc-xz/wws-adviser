# 基准卡：HOME-02 今日行动与风险

> 补卡（2026-09-10）：`advice_records` 查询 API 交付后追溯基准卡；结构/四态以实现为准，
> 稿（UI §10.4）作语义参照。V4 批次因后端缺口未交付本页，本次收口（路由 19→21）。

## 1. 参考稿

- 移动：`stitch/mobile/HOME-02-mobile.html`（最终版；Tab 双区语义取稿）
- 桌面：响应式自适应（列表区 max-w 收窄，同 TX-01 口径）

## 2. 布局结构

```
1. PageHeader（title「今日行动与风险」+ back）
2. Tab 栏（今日行动 / 风险；风险 Tab 带未处理数徽标——hard 洋红 / soft 警告黄）
3. ── 今日行动 Tab ──
   3a. 筛选行（动作下拉：全部/提升/降低/维持/暂停 + 标的代码输入，变更即重载）
   3b. 错误条（error 时）
   3c. 空态卡（「当前没有需要处理的行动」+ 最近检查时间 + 盘中问询/研究次入口；
       不使用庆祝动画）
   3d. 当日建议列表（行：动作徽标 ACTION_META + 有效角标 + 代码 + 原因首条摘要 +
       时间；整行 → /advice/:id；有效期内的排前）
   3e. 历史折叠（非当日记录；「历史记录（N）」默认折叠，展开后行尾标 已评价/已失效/已过期）
   3f. 加载更多（hasMore 时；keyset 游标）
4. ── 风险 Tab ──
   4a. 空态卡（「当前没有触发的风险项」）
   4b. RiskAlert 明细列表（hard 前置；rule/level/actual/limit/code/industry）
```

- 栅格/分栏：单列；Tab 栏满宽（品牌色下划线激活态，同 PORT-01 基准）
- 滚动行为：整页滚动；建议记录 keyset 游标分页
- 桌面差异：同宽单列，无表格化改造
- 入口：HOME-01 风险聚合条（risk-summary-bar）→ 本页（原 /portfolio）

## 3. 关键尺寸

| 位置 | 稿实测 | 落点 token |
| --- | --- | --- |
| 页面主标题 | — | PageHeader `text-h1 lg:text-h1-d` |
| Tab 高度 | — | `py-2.5` + `border-b-2`（激活 `border-primary text-primary`） |
| 列表行内边距 | — | `px-4 py-3`（space.4/3） |
| 卡片圆角 | — | `rounded-lg`（14px） |
| 行内数字/代码 | — | `num` + `data-num`（tabular-nums） |

## 4. 组件清单

| 组件 | 需覆盖 variant |
| --- | --- |
| PageHeader | back 返回 |
| Tab 栏 | 两 Tab + 风险计数徽标（hard/soft 两色） |
| 建议行 | 4 动作徽标（buy/reduce/hold/suspend）+ 有效角标 + 原因摘要/区间摘要 |
| 历史折叠 | 收起 / 展开（chevron 旋转） |
| 加载更多 | idle / loading |
| RiskAlert | hard / soft（复用 HOME-01 同组件） |
| 空态 | 今日行动空（含次入口）/ 风险空 |

## 5. 稿内违例覆盖注记（disregarded）

| 稿位置 | 违例内容 | 覆盖依据 |
| --- | --- | --- |
| 稿 §10.4 | Critical 关联建议排序 / 行业筛选 / 记录实际操作 | 后端无建议-风险关联与 acknowledge 写端点；P2 裁剪线语义，列为偏差非阻断（偏差记录见计划文档） |
| 稿 §10.4 | 风险分组五类（硬限制/数据账本/公告/暴露/观察） | analytics/risk 现返回 soft/hard 两级；按 hard 前置渲染，分组细化待 API 扩展 |
| 稿 §10.4 | 已确认/已处理风险保留当日历史 | 风险为计算态非持久对象，无「已处理」生命周期；空态即无风险 |

## 6. 走查项打勾区

- [ ] 三截图（桌面 1440 / 移动 375 / 深色）并排贴 PR
- [x] tabular-nums（`data-num`）/ 空值 `—`
- [x] 默认 / 加载 / 空 / 异常四态；空态无假数据（建议 5 测试覆盖）
- [x] 降级行不显示任何仓位数字（列表契约，测试锁定）
- [x] 门禁全绿（eslint + vue-tsc + vitest + build）；深色 dark: 变体核验
