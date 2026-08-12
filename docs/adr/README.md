# 架构决策记录（ADR）索引

> 关联：[技术架构 §23](../TECHNICAL_ARCHITECTURE.md) · [开发指南索引 §4.2](../dev-guide/0_DEVELOPMENT_GUIDE_INDEX.md)

## 1. 这是什么

本目录记录 WWS Adviser 的架构决策记录（Architecture Decision Record）。每条 ADR 是一份**不可变**的决策快照：为什么在某时点选了某方案、放弃了什么、何时应当推翻。

适用范围（来自开发指南索引 §4.2）：**偏离上游三份基线文档（PRD / 技术架构 / UI 规范）的关键决策，必须先在本目录立 ADR，再改代码或文档**。对齐上游、无分叉的实现选择不需要 ADR。

## 2. 格式

每份 ADR 至少包含以下六段（技术架构 §23 要求）：

| 段落 | 内容 |
| --- | --- |
| 状态 | `Proposed` / `Accepted` / `Superseded by ADR-NNNN` / `Deprecated` |
| 上下文 | 触发该决策的问题、约束、相关事实与引用 |
| 决策 | 选择了什么，足够具体到能指导实现 |
| 备选方案 | 考虑过但放弃的方案，及放弃理由 |
| 正负影响 | 该决策带来的好处与代价 |
| 迁移条件 | 什么信号出现时应当推翻本决策、如何迁移 |

新建 ADR 复制 [`0000-template.md`](./0000-template.md)，编号递增，文件名 `NNNN-kebab-title.md`。

## 3. 决策清单

技术架构 §23 列出的 8 条既有决策散落在基线文档中，已生效（状态 Accepted）。本目录先把它们登记入索引，待某条决策发生演进或被引用时再补独立文件展开。本次（2026-08-12）新增 ADR-0009。

| ADR | 标题 | 状态 | 决策来源 | 独立文件 |
| --- | --- | --- | --- | --- |
| [0001](./0001-modular-monolith.md) | 模块化单体而非微服务 | Accepted | 技术架构 §3.3 / §6 | 待补 |
| [0002](./0002-pwa-not-native.md) | PWA 而非原生 App | Accepted | 技术架构 §14 / PRD §20 | 待补 |
| [0003](./0003-sqlite-wal-single-worker.md) | SQLite WAL 单 worker 运行约束 | Accepted | 技术架构 §7.2 / §15 · [REPO §7](../dev-guide/1_REPO_STRUCTURE.md) | 待补 |
| [0004](./0004-biz-data-vs-parquet-split.md) | 业务数据与 Parquet/内容寻址文件的存储分工 | Accepted | 技术架构 §7.1 / §7.4 | 待补 |
| [0005](./0005-persistent-jobs-apscheduler.md) | 持久任务表 + APScheduler 的任务架构 | Accepted | 技术架构 §12 / §6.12 | 待补 |
| [0006](./0006-model-explains-deterministic.md) | 模型仅解释确定性结果，结构化输出 + 后置校验 | Accepted | 技术架构 §10.1 / §9.4 | 待补 |
| [0007](./0007-fts5-no-vector-mvp.md) | MVP 使用 FTS5，不引入向量数据库 | Accepted | 技术架构 §10.5 / §21.3 | 待补 |
| [0008](./0008-same-origin-cookie-private-cache.md) | 同源部署、会话 Cookie 与 PWA 私有缓存策略 | Accepted | 技术架构 §15.3 / §14.3 | 待补 |
| [0009](./0009-action-and-online-color-tokens.md) | 新增 `action.*` 色彩 token 族与 `status.online` 语义 token | Accepted | [UI §7.1/§7.3](../UI_DESIGN_SPECIFICATION.md) · [REVIEW_REPORT §2.2](../design-review/REVIEW_REPORT.md) | 本文 |

## 4. 维护约定

- ADR 一经 Accepted **不就地修改**；若决策被推翻，新建 ADR 并把旧 ADR 状态改为 `Superseded by ADR-NNNN`，保留原文。
- 编号单调递增、不复用。
- 决策内容若已在上游基线文档中稳定表述，独立 ADR 文件可仅做"指向 + 状态"，不重复抄录，避免文档与代码漂移（见开发指南索引 §4.1「上游为准」）。
