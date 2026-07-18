# WWS Adviser 开发指南（索引与协作约定）

> 文档版本：v1.0  
> 文档状态：开发基线  
> 更新日期：2026-07-18  
> 上游文档：[产品需求](../PRODUCT_REQUIREMENTS.md) · [技术架构](../TECHNICAL_ARCHITECTURE.md) · [UI 设计规范](../UI_DESIGN_SPECIFICATION.md)  
> 适用范围：指导 WWS Adviser 整体开发，从骨架到 MVP 上线

## 1. 本开发指南是什么

本目录是把上游三份基线文档（PRD / 技术架构 / UI 规范）**落为可执行工程规范**的桥梁：上游说“要做什么、为什么、架构边界是什么”，本指南说“怎么落到代码、目录、契约、测试任务和里程碑里”。

本指南**不重复**上游已确定的内容，只补充开发执行所需的细节，并在冲突时以上游为准。若本指南与上游矛盾，停下并提交 ADR，不要私自改某一处。

## 2. 文档集导航

| 文件 | 主题 | 何时读 |
| --- | --- | --- |
| [0_DEVELOPMENT_GUIDE_INDEX.md](./0_DEVELOPMENT_GUIDE_INDEX.md) | 索引、术语、协作约定（本文） | 入项必读 |
| [1_REPO_STRUCTURE.md](./1_REPO_STRUCTURE.md) | 仓库结构、模块契约、分层与依赖方向 | 建任何后端/前端模块前 |
| [2_DATA_MODEL_AND_STORAGE.md](./2_DATA_MODEL_AND_STORAGE.md) | SQLite 表骨架、Parquet/文件布局、Alembic、备份恢复 | 写 ORM/迁移/仓储前 |
| [3_API_CONTRACT.md](./3_API_CONTRACT.md) | API 分组、端点契约、错误码、幂等与分页、OpenAPI 流程 | 写 API 与前端类型前 |
| [4_ANALYTICS_AND_RISK.md](./4_ANALYTICS_AND_RISK.md) | 凯利资格决策流、degenerate 护栏、Advice 状态机、信号校准 | 写 analytics/advice 前 |
| [5_DATA_INGESTION_AND_QUALITY.md](./5_DATA_INGESTION_AND_QUALITY.md) | 数据源端口、采集流水线、新鲜度、多源冲突、契约测试 | 写 market_data/documents 适配器前 |
| [6_MODEL_AND_REPORT_PIPELINE.md](./6_MODEL_AND_REPORT_PIPELINE.md) | Model Gateway、报告流水线、Jobs 状态机、SSE | 写 reports/research/jobs 前 |
| [7_FRONTEND_AND_PWA.md](./7_FRONTEND_AND_PWA.md) | 前端分层、状态边界、缓存规则、SSE、类型生成 | 写 Vue 代码前 |
| [8_SECURITY_AND_DEPLOYMENT.md](./8_SECURITY_AND_DEPLOYMENT.md) | 身份/会话/Web 安全、Docker 构建、env、部署清单 | 上线与安全审查前 |
| [9_TEST_AND_CI.md](./9_TEST_AND_CI.md) | 测试分层、必测不变量、属性测试、CI 门禁 | 写任意测试与提交 PR 前 |
| [10_MILESTONE_PLAN.md](./10_MILESTONE_PLAN.md) | Phase 0–3 工作项、退出条件、验收映射 | 排期与每次 plan-phase 前 |

> 数据源供应商与模型供应商当前**未确定**：本指南凡涉及外部具体供应商处，一律以**端口契约 + 占位适配器**表达，并标注 `TODO(data-source-selection)`，待《数据源选型与质量规范》确定后填充。这是有意约束——避免在选型未定前写死字段映射、限频、认证细节。

## 3. 术语表

| 术语 | 含义 |
| --- | --- |
| 单体（Modular Monolith） | 一个可部署进程内按领域模块隔离的代码组织方式 |
| 端口（Port） | 应用层定义的 Protocol/接口，描述需要的能力 |
| 适配器（Adapter） | 基础设施层对端口的实现（SQLite、HTTP 数据源、模型 SDK 等） |
| 确定性计算 | 由程序在版本化输入上可重复得到的数值结果，不依赖模型或网络 |
| analysis_snapshot | 一次报告/建议冻结的不可变输入集合，保证可复现 |
| evidence | 从文档/数据记录中抽取的可定位引用，带 ID 和出处 |
| 原因链（reason chain） | 凯利拒绝/折扣时的可审计原因类别序列，写入 Advice |
| 新鲜度（freshness） | 行情是否在阈值内、字段完整、源健康、时钟健康 |
| 校准状态机 | 信号概率校准的 `UNCALIBRATED→CALIBRATING→CALIBRATED(oos)→STALE→DECAYED` 流转 |
| 幂等键 | `Idempotency-Key` / 业务复合键，保证同一请求不产生两条副作用 |
| 租约（lease） | 任务执行器领取任务后持有的时限锁，崩溃后到期可恢复 |
| 降级（degraded） | 数据/模型/账本不达标时进入的安全输出模式（PAUSE_ADVICE 等） |
| L1–L4 信号 | 按可校准性分层的信号类型，见 [4_ANALYTICS_AND_RISK.md](./4_ANALYTICS_AND_RISK.md) |
| business_date | `Asia/Shanghai` 下的交易日 `YYYY-MM-DD` |

## 4. 读写与版本约定

1. **上游为准**：业务规则、风险约束、凯利定义、UI 安全规则以上游三份文档为准。本指南只展开执行细节。
2. **ADR 起始**：偏离上游关键决策须在 `docs/adr/` 新增 ADR（格式见技术文档 §23）。本指南实施过程中产生的决策也记 ADR。
3. **版本号**：每份子文档头部维护 `文档版本 / 状态 / 更新日期 / 变更说明`，与技术文档一致。
4. **TODO 标记**：未确定项统一用 `TODO(<topic>)`，便于全局检索。已知大块待定区见 §2 注释与各文档末尾“待确认项”。
5. **不写实现值**：算法阈值常量、错误码、状态枚举在本指南中**定义为命名常量与允许范围**，但具体业务校准数值留到运行配置与测试夹具，避免文档与代码漂移。

## 5. 协作工作流

- **建模块前**：读 1_REPO_STRUCTURE 确认分层与文件清单，读对应子文档确认契约。
- **改 schema 前**：读 2_DATA_MODEL_AND_STORAGE，先写 Alembic 迁移并补备份兼容性检查。
- **加端点前**：读 3_API_CONTRACT，OpenAPI 是接口事实源，前端类型由其生成，手工 DTO 视为临时物。
- **写凯利/风险前**：读 4_ANALYTICS_AND_RISK，凯利是纯领域函数，模型 Gateway 无权写 `p`。
- **接外部源前**：读 5_DATA_INGESTION_AND_QUALITY，先写端口与契约测试 cassette，再写适配器。
- **提 PR 前**：读 9_TEST_AND_CI，确保 CI 门禁全绿、必测不变量覆盖。
- **排期前**：读 10_MILESTONE_PLAN，每个 Phase 的退出条件是硬门槛。

## 6. 与 GSD 流程的衔接

本指南可直接被 `gsd:plan-phase` / `gsd:execute-phase` 消费：[10_MILESTONE_PLAN.md](./10_MILESTONE_PLAN.md) 的每个 Phase 卡片即是一个可规划阶段，其工作项可拆为任务。建议工作流：

1. 选定一个 Phase / 子模块。
2. 用 `gsd:plan-phase` 基于该卡片产出 PLAN.md。
3. 用 `gsd:execute-phase` 执行，每个任务原子提交。
4. 达到退出条件后用 `gsd:verify-work` 验证对应验收清单。

## 7. 待确认项汇总（跨文档）

| 事项 | 当前默认 | 归属文档 |
| --- | --- | --- |
| 数据源供应商（行情/公告/新闻） | 未定，端口契约+占位 | 5_DATA_INGESTION_AND_QUALITY |
| 模型供应商 | OpenAI-compatible，未定具体 | 6_MODEL_AND_REPORT_PIPELINE |
| 初始通知渠道 | 待选企业微信/Server 酱/邮件一种 | 6 / 8 |
| 凯利折扣 | 默认 0.20，范围 0.10–0.25 | 4_ANALYTICS_AND_RISK |
| 盘中新鲜度阈值 | 90 秒 | 5_DATA_INGESTION_AND_QUALITY |
| 校准有效期 | 60 交易日 | 4_ANALYTICS_AND_RISK |
| `n_eff` 门禁 | <30 拒绝；30≤n<100 半折扣 | 4_ANALYTICS_AND_RISK |
| 部署形态 | 单容器，优先 NAS+Tailscale | 8_SECURITY_AND_DEPLOYMENT |
