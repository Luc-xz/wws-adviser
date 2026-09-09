# 基准卡：LIB-01 研究与报告库

> RES-01/02（新建研究/任务进度）维持并入本页（计划 §10-Q1 决策）；基准卡按"卡内分区"对齐稿区块。

## 1. 参考稿

- 移动：`stitch/mobile/LIB-01-mobile.html`（最终版）
- 桌面：`stitch/LIB-01-desktop.html`
- 关联稿：`stitch/mobile/RES-01-mobile.html`（新建研究表单分区）、`RES-02-mobile.html`（任务进度分区）——并卡实现时对照其区块

## 2. 布局结构（从稿人工提取）

```
1. 顶栏（标题「研究」+ 头像/刷新）
2. Tab：报告 / 研究任务
3. 报告 Tab：类型过滤（全部/开市前/收市后/公司/行业）→ 报告行（日期+类型+最新徽标）
4. 研究任务 Tab：新建研究表单（类型/标的/深度，含 peer_codes）→ 任务行列表
5. 任务行展开：进度条（SSE 实时/轮询标记）+ 状态徽标 + 取消
6. 报告阅读面板（选中任务/报告）：标题 + 认知层级标签渲染 + 引用清单 + 导出
7. 离线副本横幅（Phase 3.4：缓存时间）
```

- 栅格/分栏：移动单列（列表→面板推入）；桌面左列表右阅读双栏
- 滚动行为：列表区滚动，阅读面板独立滚动
- 桌面差异：左 5 右 7 分栏；引用清单可固定右缘

## 3. 关键尺寸

| 位置 | 稿实测 | 落点 token |
| --- | --- | --- |
| Tab 过滤 pill | 6px 圆角 | `rounded-sm text-caption` |
| 进度条 | 高 6px 圆角 full | `h-1.5 rounded-full` |
| 报告正文 | 14px/1.55 | `text-body`（renderMd 输出） |
| 引用清单行 | 12px | `text-caption` |
| 区块间距 | 24px | `space-y-6` |

## 4. 组件清单

| 组件 | 需覆盖 variant |
| --- | --- |
| 任务状态徽标 | PENDING/RUNNING/COMPLETED/FAILED/CANCELLED |
| 进度条（useResearchTaskStatus） | sse / polling 双源标记 |
| 认知层级标签（renderMd） | 事实/推断/判断/未证实（§9.7：判断琥珀、未证实灰禁与事实混排） |
| 引用清单行 | 已验证 / 未验证（含 hash 短码） |
| 导出入口 | md / html |

## 5. 稿内违例覆盖注记（disregarded）

| 稿位置 | 违例内容 | 覆盖依据 |
| --- | --- | --- |
| — | 移动稿 tabular-nums 未全覆盖 | §2.2 |
| — | RES 系列稿英文标签（Draft/Processing） | §4.5 标签语言统一中文（Phase 2 收口决策沿用） |

## 6. 走查项打勾区

- [ ] 三截图并排贴 PR
- [ ] 认知层级标签：4 类可达且配色合规（§9.7）
- [ ] 引用可追溯展示（Evidence → 文档 → hash）
- [ ] 四态（无任务 empty-guide / 任务失败 error_code 人话映射）
- [ ] 门禁全绿；深色 dark: 核验；离线横幅显示
