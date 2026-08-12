# 9. 测试与 CI（分层、必测不变量、属性测试、契约、CI 门禁）

> 文档版本：v1.0  
> 文档状态：开发基线  
> 更新日期：2026-07-19  
> 关联：技术架构 §18 §19 · PRD §16 §18 · 索引：[0_DEVELOPMENT_GUIDE_INDEX.md](./0_DEVELOPMENT_GUIDE_INDEX.md)

## 1. 目的

把技术架构 §18（测试架构）与 §19（CI/CD 与发布）落为**测试分层职责、可执行不变量、夹具与契约方法、CI 门禁**。本文是各子文档“必测不变量”段的汇聚点：4–8 各自声明本领域不变量，本文负责把它们装配进分层与 CI，**不重述**具体不变量文本。写任意测试或提 PR 前读本文。

核心约束：

- 不变量测试是“硬护栏”，CI 红则不合并；性能预算与金丝是“软信号”，不阻断合并但记 issue。
- 测试绑**端口契约**而非具体供应商（[5_DATA_INGESTION_AND_QUALITY.md](./5_DATA_INGESTION_AND_QUALITY.md) §9）——即便 MVP 数据源已定 AKShare，端口契约测试仍是切换/升级供应商时的回归保障。
- 时间相关测试**冻结** `Asia/Shanghai` 时钟，禁止依赖墙上时间。

## 2. 测试分层（技术架构 §18.1）

| 类型 | 重点 | 工具 | 位置 | CI 阻断 |
| --- | --- | --- | --- | --- |
| 单元 | 账本、费用、公司行动、风险、凯利、时间、状态机 | pytest | `tests/unit/<module>/` | 是 |
| 属性 | 任意交易序列不变量、凯利上限不破 | Hypothesis | `tests/property/` | 是 |
| 领域纯函数 | `domain.py` 输入→输出，无 IO | pytest | `tests/unit/<module>/domain/` | 是 |
| 集成 | SQLite 事务、迁移、Parquet、任务租约、报告落盘 | pytest + 临时 DB | `tests/integration/` | 是 |
| 数据源契约 | cassette 喂 parse，断言 schema/单位/突变降级 | pytest + VCR-like | `tests/contract/cassettes/<port>/` | 是 |
| 模型契约 | 结构化输出、超时、错误、引用白名单、降级 | pytest + mock `ModelPort` | `tests/contract/model/` | 是 |
| API | 认证、幂等、校验、Problem Details、权限、CSRF | pytest + httpx ASGI transport | `tests/api/` | 是 |
| E2E | 手机关键路径、PWA、离线、CSV 导入、任务进度 | Playwright | `e2e/` | 是（移动关键路径子集） |
| 安全 | CSRF、XSS、CSV 注入、路径穿越、密钥泄漏 | pytest + 专项 | `tests/security/` | 是 |
| 金丝/回放 | 固定 business_date 重放，比较关键数值与结构 | pytest + 固定夹具 | `tests/replay/` | 否（diff 记 issue） |

> 领域层单测**禁**触 DB/网络（[1_REPO_STRUCTURE.md](./1_REPO_STRUCTURE.md) §3）；集成测试不调用真实外部服务，一律走 cassette 或 stub 适配器。

## 3. 必测不变量（汇聚，技术架构 §18.2）

各不变量的权威定义分布在领域文档，本文只索引 + 补充测试装配方式，**不复制文本**：

| 不变量 | 权威位置 | 测试装配 |
| --- | --- | --- |
| 交易重放后现金/持仓与快照一致；删改历史会失效重建 | [2_DATA_MODEL_AND_STORAGE.md](./2_DATA_MODEL_AND_STORAGE.md) §6 | 属性测试：随机交易序列 + 快照散列比对 |
| 金额/数量全链路无浮点结算误差 | [2_DATA_MODEL_AND_STORAGE.md](./2_DATA_MODEL_AND_STORAGE.md) §5 | 属性测试：Decimal 端到端，断言尾数恒等 |
| 相同幂等键不产生两条交易/任务/报告/通知 | [3_API_CONTRACT.md](./3_API_CONTRACT.md) §6 · [6](./6_MODEL_AND_REPORT_PIPELINE.md) §11 | API 测试：并发双发同键断言单条 |
| 行情过期时不产具体交易数量 | [4_ANALYTICS_AND_RISK.md](./4_ANALYTICS_AND_RISK.md) · [5](./5_DATA_INGESTION_AND_QUALITY.md) §8 | 集成测试：冻结时钟构造过期 → 断言 `PAUSE_ADVICE` |
| 硬风险上限始终截断凯利理论值 | [4_ANALYTICS_AND_RISK.md](./4_ANALYTICS_AND_RISK.md) §6 | 属性测试：随机 `p,b` 输入，输出 ≤ 上限链 |
| 模型冲突数值不覆盖确定性字段 | [6_MODEL_AND_REPORT_PIPELINE.md](./6_MODEL_AND_REPORT_PIPELINE.md) §11 | 模型契约测试：注入冲突 → 断言 BLOCKED |
| 凯利拒绝/折扣保留可审计原因链，拒绝不输出区间 | [4_ANALYTICS_AND_RISK.md](./4_ANALYTICS_AND_RISK.md) §7 | 单元测试：遍历拒绝类目断言 `reason_chain` + 区间为空 |
| 备份恢复后账本哈希/持仓/报告引用一致 | [2_DATA_MODEL_AND_STORAGE.md](./2_DATA_MODEL_AND_STORAGE.md) §11 | `scripts/restore_drill.py` 跑全流程 |
| 退出登录后私有 PWA 缓存清除 | [7_FRONTEND_AND_PWA.md](./7_FRONTEND_AND_PWA.md) §13 | E2E：登录→缓存报告→登出→断言 SW 缓存空 |
| 模板不得要求模型重算凯利/持仓/概率 | [6_MODEL_AND_REPORT_PIPELINE.md](./6_MODEL_AND_REPORT_PIPELINE.md) §11 | grep/模板测试断言关键词缺失 |
| `workers>1` 生产拒绝启动 | [1_REPO_STRUCTURE.md](./1_REPO_STRUCTURE.md) §7 | 启动自检测试 |

## 4. 属性测试要点

- **账本守恒**：生成任意合法交易序列（买/卖/费用/分红/拆分/申赎），断言 `Σ quantity` 与 `Σ cash` 在重放后与快照恒等，删改任意历史交易后所有下游快照失效并重建。
- **凯利上限**：随机 `p ∈ (0,1)`、`b`、`n_eff`、约束集，断言输出 `target_weight_range` 的上界 ≤ `min(kelly_theoretical, per_symbol_cap, industry_cap, portfolio_cap)`，且 `KELLY_DISCOUNT ∈ [0.10,0.25]`。
- **十进制不漂移**：随机 string 数值经 API→领域→存储→API 往返，前端展示值不超展示精度；领域算术全程 Decimal。
- **幂等**：随机重复/乱序提交同幂等键，副作用数恒为 1。
- Hypothesis 用 `@settings(max_examples=200, deadline=None)`；时间相关 strategy 注入冻结 clock，不读 `datetime.now()`。

## 5. 测试数据与夹具（技术架构 §18.3）

- 合成账本**不含真实个人持仓**；CSV 夹具覆盖买卖、费用、分红、拆分、申赎、调整、错误行（被预览拒绝）。
- 外部响应录制后移除 Cookie/Token/个人标识/受限正文，存 `tests/contract/cassettes/`；cassette 命名 `<port>/<scenario>.json`。
- 时钟夹具 `frozen_clock(business_date, market_state)` 覆盖：连续竞价、集合竞价、午休、节假日、临时休市、跨日。
- 基金/财务样本覆盖披露延迟、复权、分红、拆分、申赎确认延迟（[2_DATA_MODEL_AND_STORAGE.md](./2_DATA_MODEL_AND_STORAGE.md) §6.4）。
- 模型夹具：`FakeModelPort` 返回预置结构化输出 + 可注入超时/冲突/引用越界，覆盖降级路径。

## 6. 契约测试与金丝（技术架构 §18.1）

- **数据源契约**：绑端口（[5_DATA_INGESTION_AND_QUALITY.md](./5_DATA_INGESTION_AND_QUALITY.md) §9）。cassette → parse → schema 断言；突变 cassette（删字段/改类型/越界）→ 断言 `quality_status=PARSE_FAILED` 不抛异常；新鲜度测试冻结时钟断言 `fresh` 与降级。
- **模型契约**：结构化输出 schema（[6_MODEL_AND_REPORT_PIPELINE.md](./6_MODEL_AND_REPORT_PIPELINE.md) §5）、超时、错误、引用白名单、动作词后置校验、冲突→BLOCKED/降级。
- **金丝/回放**：固定 business_date 重放开市前/收市后报告，比较关键数值与段落结构；diff 仅记 issue 不阻断（[6](./6_MODEL_AND_REPORT_PIPELINE.md) §8 复现性）。

## 7. CI 门禁（技术架构 §19.1）

每次合并到 `dev`/`main` 至少执行，全绿方合并：

1. **静态**：Python `ruff`（含 §8 的 import/`banned-api` 规则）+ `mypy --strict` 领域层；TypeScript `eslint` + `vue-tsc` 类型检查；前端 `prettier`/`oxlint`。
2. **测试**：单元 + 集成 + API + 属性 + 数据源/模型契约 + 安全。
3. **前端构建**：`vite build` + 移动关键路径 E2E 子集（[7_FRONTEND_AND_PWA.md](./7_FRONTEND_AND_PWA.md) §13）。
4. **迁移**：Alembic 从空库 `upgrade head` + 从上一 tag 升级（`downgrade -1` 可逆性可选留 ADR，[2_DATA_MODEL_AND_STORAGE.md](./2_DATA_MODEL_AND_STORAGE.md) §10）。
5. **供应链**：依赖漏洞（`pip-audit`/`npm audit`）+ 许可证扫描 + 密钥扫描（gitleaks）。
6. **容器**：Docker 多阶段构建 + `/health/live` `/health/ready` 健康检查（[8_SECURITY_AND_DEPLOYMENT.md](./8_SECURITY_AND_DEPLOYMENT.md) §6.1）。
7. **lint 跨模块护栏**：`domain.py` 无框架 import、`model_gateway` 不 import calibration 写接口、OpenAPI generated 无手改 diff（grep 断言）。

> 非阻断但需记录：金丝 diff、前端 JS 预算（≤250KB 指导值，技术架构 §20）、P95 性能采样。

## 8. 分支与发布（技术架构 §19.2 §19.3，[8_SECURITY_AND_DEPLOYMENT.md](./8_SECURITY_AND_DEPLOYMENT.md) §10）

- 分支：`main`（发布基线）/`dev`（集成）/`feat-*`。PR 必过 CI + 至少一人评审。
- 语义化或日期版本；镜像标签含 Git commit，禁 `latest`（[8](./8_SECURITY_AND_DEPLOYMENT.md) §8）。
- 发布说明列 schema/配置/数据源适配器/模型提示词变化（技术架构 §19.3 独立版本化项）。
- 部署前自动一致性备份 → 迁移检查 → 切容器 → 健康检查失败回退应用版本；迁移不可逆按恢复手册，不自动降级 DB。

## 9. 测试不变量与 PR 自检

每个 PR 描述含“不变量覆盖”段：本改动触及哪些 §3 不变量、对应测试文件。无不变量覆盖的领域改动需说明理由。CI 红的 PR 不合并；金丝 diff 记 issue 不阻塞。

## 10. 运行配置项（2026-08-11 复核）

> 以下事项确认采用「运行配置 / ADR」策略。

| 事项 | 确认策略 | 备注 |
| --- | --- | --- |
| 金丝回放业务日期集 | 固定 3 个代表性交易日 | 覆盖正常/午休/数据源部分缺失 |
| `downgrade -1` 可逆性 | 建议保留，复杂迁移留 ADR | [2_DATA_MODEL_AND_STORAGE.md](./2_DATA_MODEL_AND_STORAGE.md) §10 |
| 性能采样在 CI 跑 | 不阻断，定期手动 | 触发扩展迁移时复核（技术架构 §21） |

> **已确认（2026-08-11）**：
> - **E2E 浏览器矩阵**：Playwright 桌面等效环境，模拟 iOS Safari + Android Chrome 的 user-agent + viewport（PRD §18），无需真机/模拟器。
> - **依赖许可证策略**：**宽松白名单**——允许 MIT / Apache-2.0 / BSD-2/3-Clause / ISC；拒绝 GPL / AGPL 等 copyleft（避免传染，适合闭源个人项目）。LGPL/MPL 弱 copyleft 需个案评估。CI 用 `pip-licenses` + 许可证检查脚本守门。
