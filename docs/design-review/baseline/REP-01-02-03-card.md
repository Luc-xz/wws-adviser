# 基准卡：REP-01/02/03 三类报告（一页承载）

> 三形态维持一页承载（计划 §10-Q1 决策：信息架构贴单人使用）；基准卡按形态分区对齐三张稿。
> 桌面阅读布局：3/9 或 2/8/2（左目录/正文/右证据抽屉，UI §5.2）。

## 1. 参考稿

- 移动：`stitch/mobile/REP-01-mobile.html`（开市前，最终版）· `REP-02-mobile.html`（收市后）· `REP-03-mobile.html`（深度研究）
- 桌面：`stitch/REP-01-desktop.html` 等（REP-03-desktop 的证据右抽屉 :374-414 为正向标杆）

## 2. 布局结构（从稿人工提取）

```
REP-01 开市前：
1. 二级顶栏（返回 + 标题 + 分享/导出）
2. 报告头（日期 + 状态徽标 最终版/PARTIAL）
3. 组合风险评分卡（分数 + 等级 + 一句话归因）
4. 重大事项监控列表
5. 持仓风险明细 → DataFooter（截至 · 来源 · 版本）

REP-02 收市后：
1. 同二级顶栏
2. 当日盈亏摘要（盈亏额 + 收益率 + 基准差，三指标）
3. 盈亏贡献 Top/Bottom（正贡献红/负贡献绿 + 正负号）
4. 行为偏差区 → footer

REP-03 深度研究：
1. 研究头（主题 + 副题 + 数据截止）
2. 核心结论摘要 + 评级/目标价（研究报告形态）
3. 正文分区（认知层级标签逐段）+ 确定性指标表（模型不得修改）
4. 引用清单（含来源等级）+ 证据抽屉（桌面右栏；移动 Bottom Sheet 80~92%）
5. 导出（md / html）
```

- 栅格/分栏：移动单列；桌面 2/8/2（目录 | 正文 | 证据）
- 滚动行为：正文滚动；目录 sticky；证据抽屉独立
- 桌面差异：目录树左栏 + 引用常驻右缘

## 3. 关键尺寸

| 位置 | 稿实测 | 落点 token |
| --- | --- | --- |
| 报告大标题 | 24/28px·700 | `text-h1 lg:text-h1-d font-bold` |
| 盈亏大数字 | 28/32px | `text-display lg:text-display-d num` |
| 分区标题 | 17/18px·600 | `text-h3 lg:text-h3-d font-semibold` |
| 正文 | 14px | `text-body` |
| DataFooter | 12px | `text-caption` |

## 4. 组件清单

| 组件 | 需覆盖 variant |
| --- | --- |
| DataStatusBar（页头） | 4 态（稿 REP-01/03 缺失——**必须补**，REVIEW_REPORT §5 孤岛项） |
| MetricCard（摘要） | 盈亏/收益率/基准差 |
| RiskAlert | 三级（Critical 含影响+处理两行） |
| 认知层级标签 | 4 类（以 REP-03-desktop:267-274 为标杆） |
| EvidenceDrawer | 桌面右抽屉 360-420px / 移动 Bottom Sheet |
| 降级标记 | PARTIAL + degradation_flags 人话映射 |

## 5. 稿内违例覆盖注记（disregarded）

| 稿位置 | 违例内容 | 覆盖依据 |
| --- | --- | --- |
| REP-01/03 稿顶部 | 无 DataStatusBar | §5（DATA-01 孤岛问题）——实现必须补 |
| REP-03-mobile | 缺 [计算]/[未证实] 标签；[判断] 用蓝 | §9.7 → 判断琥珀；4 标签全 |
| REP-01-mobile 标签 | 英文（Final/Partial） | §4.5 语言统一中文 |
| REP-01-desktop:193 | 日期非 ISO | §8.1 → ISO `YYYY-MM-DD` |

## 6. 走查项打勾区

- [ ] 三截图并排贴 PR（三形态各一组）
- [ ] tabular-nums / 负号 `−` / 空值 `—` / footer 句式
- [ ] 认知标签 4 类 + 引用定位 + 证据抽屉
- [ ] 降级形态（模型不可用 → 确定性内容完整 + 提示）
- [ ] 门禁全绿；深色 dark: 核验；离线副本横幅
