# 10. 里程碑计划（Phase 0–3 工作项、退出条件、验收映射）

> 文档版本：v1.0  
> 文档状态：开发基线  
> 更新日期：2026-07-19  
> 关联：技术架构 §24 §25 · PRD §4.2 §16 §17 §18 · 索引：[0_DEVELOPMENT_GUIDE_INDEX.md](./0_DEVELOPMENT_GUIDE_INDEX.md)

## 1. 目的

把 PRD §17 迭代计划与技术架构 §24 实施顺序落为**可被 `gsd:plan-phase` 直接消费的阶段卡片**：每个 Phase 一组工作项、退出条件（硬门槛）、对应验收场景（AC）与成功指标。本文是排期入口；某 Phase 开始前先读本文对应卡片，再读 1–8 的子文档契约。

约定：

- **退出条件是硬门槛**：未全绿不进下一 Phase（PRD §17 退出条件、§18 上线门槛、技术架构 §25）。
- 工作项可拆为 `gsd:plan-phase` 任务，每任务原子提交（索引 §6）。
- 外部供应商已全部确认（§8.2）：数据源 AKShare（MVP）、模型通用 OpenAI-compatible、通知邮件 SMTP、VPS 国内。各 Phase 按端口 + 适配器交付，不阻塞退出。

## 2. Phase 0：工程基础骨架

**对应**：PRD §17 阶段 0 · 技术架构 §24 Phase 0 · 验收 AC-08（PWA 可安装子集）、AC-09（备份骨架子集）。

| # | 工作项 | 主文档 |
| --- | --- | --- |
| 0.1 | 前后端目录、锁文件（`uv.lock`/`pnpm-lock`）、Makefile、ruff/mypy/eslint/vitest 基线与 CI | [1_REPO_STRUCTURE.md](./1_REPO_STRUCTURE.md) |
| 0.2 | FastAPI 生命周期、`core/config`、结构化日志、错误模型（Problem Details）、`/health/live` `/health/ready` `/health/dependencies` | [3_API_CONTRACT.md](./3_API_CONTRACT.md) · [8_SECURITY_AND_DEPLOYMENT.md](./8_SECURITY_AND_DEPLOYMENT.md) §6 |
| 0.3 | SQLite（WAL + 外键 + busy timeout）、Alembic 空库可建、备份骨架、单 worker enforce + scheduler 文件锁 | [2_DATA_MODEL_AND_STORAGE.md](./2_DATA_MODEL_AND_STORAGE.md) · [1_REPO_STRUCTURE.md](./1_REPO_STRUCTURE.md) §7 |
| 0.4 | Vue PWA 外壳、登录、五导航（首页/持仓/助手/研究/设置）、OpenAPI 类型生成流 | [7_FRONTEND_AND_PWA.md](./7_FRONTEND_AND_PWA.md) §6 |
| 0.5 | Identity（Argon2id、会话哈希、Cookie 安全属性）、Audit（只追加）、Jobs（持久任务表 + APScheduler 入队）基础 | [8_SECURITY_AND_DEPLOYMENT.md](./8_SECURITY_AND_DEPLOYMENT.md) §3 · [6_MODEL_AND_REPORT_PIPELINE.md](./6_MODEL_AND_REPORT_PIPELINE.md) §7 |
| 0.6 | 数据源/模型/通知端口 Protocol + 占位适配器（`stub_*`）+ 契约测试 cassette 骨架 | [5_DATA_INGESTION_AND_QUALITY.md](./5_DATA_INGESTION_AND_QUALITY.md) §9 · [6](./6_MODEL_AND_REPORT_PIPELINE.md) §3 |

**退出条件**：

- [x] 手机可安装 PWA 并安全登录（AC-08 安装子集）。✅ 波4（06172ef）：PWA manifest+SW build 生成 + AUTH-01 登录连后端 `/api/v1/auth/login`
- [x] 服务持久化数据，`/health/ready` 在 DB 可写时绿，不可写时 fail。✅ 波1（b2c0876）：`/health/ready` 检查 DB 可写 + 迁移已应用，不可写/未迁移返 503
- [x] 基础任务可入队、领取、租约到期可重领（[6](./6_MODEL_AND_REPORT_PIPELINE.md) §7）。✅ 波2（ebaab7f）：job_runs + UNIQUE 幂等 + 条件 UPDATE CAS 领取 + lease 过期重领（测试覆盖）
- [x] 端口 + 占位适配器可跑通一条 stub 数据→领域→API 闭环。✅ 波3（8b407b8）：`GET /api/v1/market-data/quotes/{code}` 经 stub QuoteProvider→parse_quote→API，前端 HomeOverview 亦调通
- [x] CI 静态 + 单元 + 迁移门禁全绿（[9_TEST_AND_CI.md](./9_TEST_AND_CI.md) §7）。✅ 波1–5：ruff+mypy strict / pytest（66 测试）/ migrate-check 本地全绿；波5 CI yaml 含前后端门禁（CI 绿需 push 触发）
- [x] 备份骨架能产出一致性副本（不进模型/通知，AC-09 子集）。✅ 波1+5：`core/backup.py` Online Backup API + `scripts/backup_drill.py` 演练（backup→restore→表一致）

> **Phase 0 完成声明（2026-08-12）**：六个退出条件全部满足，工程基础骨架就绪，可进入 Phase 1（持仓—报告闭环）。

## 3. Phase 1：持仓—报告闭环（MVP 核心）

**对应**：PRD §17 阶段 1 · 技术架构 §24 Phase 1 · 验收 AC-01/02/04/06/08/09 · 成功指标 PRD §4.2。

| # | 工作项 | 主文档 | 关联 AC |
| --- | --- | --- | --- |
| 1.1 | Instrument/Portfolio/transactions + CSV 导入（指纹去重、错误行预览拒绝、幂等键） | [2_DATA_MODEL_AND_STORAGE.md](./2_DATA_MODEL_AND_STORAGE.md) §6 · [3_API_CONTRACT.md](./3_API_CONTRACT.md) §3 | AC-01 |
| 1.2 | Market Data 日线/净值/快照 + 质量状态 + 新鲜度门禁骨架（日线为主） | [5_DATA_INGESTION_AND_QUALITY.md](./5_DATA_INGESTION_AND_QUALITY.md) | AC-02 |
| 1.3 | Documents 公告/少量新闻 + 内容寻址 + FTS5 | [2_DATA_MODEL_AND_STORAGE.md](./2_DATA_MODEL_AND_STORAGE.md) §7 | AC-02 |
| 1.4 | 确定性组合指标（成本/盈亏/归因）+ 风险规则（硬上限截断骨架） | [4_ANALYTICS_AND_RISK.md](./4_ANALYTICS_AND_RISK.md) | AC-04 |
| 1.5 | 开市前/收市后报告流水线（`analysis_snapshot` 冻结、可复现、降级路径） | [6_MODEL_AND_REPORT_PIPELINE.md](./6_MODEL_AND_REPORT_PIPELINE.md) §4 §8 | AC-02/04 |
| 1.6 | Model Gateway（结构化输出 + 后置校验 + 一次受控修复）+ 邮件 SMTP 通知渠道（已确认） | [6](./6_MODEL_AND_REPORT_PIPELINE.md) §3 §5 §10 | AC-06 |
| 1.7 | 首页/持仓页/开市前报告/收市后复盘移动端页面 + SSE/轮询兜底 | [7_FRONTEND_AND_PWA.md](./7_FRONTEND_AND_PWA.md) | AC-08 |
| 1.8 | 连续 10 个交易日运行验证（PRD §17 阶段 1 退出） | 全局运行 | AC-02/04 |

**退出条件**：

- [ ] 连续 10 个交易日稳定形成“交易—持仓—报告—复盘”闭环（PRD §17 阶段 1）。
- [ ] 账本对账一致率 100%；报告关键数值可追溯率 100%（PRD §4.2）。
- [ ] 开市前/收市后报告按时生成率 ≥95%（PRD §4.2）。
- [ ] 模型关闭仍可登录/管交易/更新行情/展示确定性风险摘要，报告显示可重试降级（AC-06）。
- [ ] CSV 重复导入不产生重复流水；错误行被预览拒绝（AC-01）。
- [ ] 公告源失败时报告标记不完整（AC-02）。
- [ ] 备份恢复演练通过，账本哈希/持仓一致，密钥不进普通备份（AC-09）。

> **波次进度**（退出条件全部留待波8 整体核验，逐波只记交付）：
>
> - **波1（1.1）✅ 2026-08-13**：持仓/交易基础层交付。新增 `instruments`、`portfolio` 两模块（domain/models/repository/schemas/service/api）+ 迁移 `0003_portfolio`（instruments/accounts/transactions）。金额按定标整数分存储、price/quantity 无损 decimal 串；指纹去重（sha256，量化保证 `100`≡`100.000000`）；CSV 导入预览（`batch_id` 串起确认）+ 确认两阶段、错误行预览拒绝、跨路径（导入/手工）幂等。端点：`/api/v1/instruments*`、`/accounts`、`/transactions*`（含 `/import`、`/import/confirm`）。门禁全绿：ruff/mypy strict（76 文件）/pytest 99 passed/migrate-check/backup-dry（9 表一致）/前端 gen:api+lint+build。AC-01 由 `test_csv_import_*`、`test_manual_transaction_*` 直接覆盖。position_snapshots（avg_cost/PnL）随波4 引入。
> - **波2（1.2）✅ 2026-08-13**：行情采集（日线/净值为主）交付。扩展 `market_data` 模块（+models/repository + service 采集流水线 + domain parse_bars/parse_nav/质量/新鲜度骨架）+ 迁移 `0004_market_data`（trading_calendar/market_records/nav_records）+ `infrastructure/storage/parquet_store.py`（polars 分区原子写/读）。日线采集：fetch→parse（OHLC 合法性校验）→Parquet 主存 + SQLite 元数据索引 upsert（UNIQUE 去重）→质量状态（日线口径 OK/MISSING/DELAYED）。端点：`/api/v1/market/{bars,nav,quality,state}` + `*/refresh`（ops，需 Idempotency-Key）。AKShare 列为 optional extra + 懒加载适配器脚手架（`rows_to_*` 纯函数单测，真实调用留待国内 VPS 实录）；stub 默认、闭环可测。门禁全绿：ruff/mypy strict（82 文件）/pytest 116 passed/migrate-check/backup-dry（12 表一致）/前端 gen:api+lint。盘中 180s TTL/状态机（Phase 2.1）、data_conflicts（Phase 3.3）、clock-skew/熔断（TODO）本轮留白。
> - **波3（1.3）✅ 2026-08-13**：公告/文档 + 内容寻址 + FTS5 交付。新增 `documents` 模块（domain/models/repository/schemas/service/api）+ 迁移 `0005_documents`（documents/document_links/evidence + `documents_fts` contentless 虚拟表）。采集流水线：discover→download→`LocalObjectStore` sha256 内容寻址存原文/文本→`content_sha256` UNIQUE 去重→insert documents + links + FTS 索引。FTS5 contentless（`content=''`，正文不进 SQLite）+ **CJK 按字分词**（unicode61 无内置中文分词，索引与查询两侧插空格）；rowid 用 documents 隐式整数 rowid。端点：`/api/v1/documents`（列表/详情/`search` FTS）、`/evidence/{id}`、ops `/refresh`（需 Idempotency-Key）。`document_source` 配置 + `akshare_document` 懒加载脚手架（`rows_to_document_ref` 纯函数单测）；stub 默认闭环。门禁全绿：ruff/mypy strict（90 文件）/pytest 126 passed/migrate-check（含 FTS5 DDL）/backup-dry（20 表一致，含 FTS5 影子表）/前端 gen:api+lint。evidence 填充（Phase 3.1）、真实公告源实录（国内 VPS）、PDF/HTML 解析、data_conflicts（Phase 3.3）留白。
> - **波4（1.4）✅ 2026-08-13**：确定性组合指标 + 风险规则交付（Phase 1 计算核心）。迁移 `0006_positions`（position_snapshots）。`portfolio/domain` 新增 MWAC 纯函数 `compute_positions`/`compute_position_series`（**全 8 种交易类型**：BUY/SELL/SUBSCRIBE/REDEEM/DIVIDEND/SPLIT/FEE/ADJUST；现金分红=已实现收益、送股=零成本增数、费用/调整=现金；卖空校验、replay 幂等——确定性数值由 `test_positions_domain` 固定 fixture 断言锁定）。`portfolio/service` 新增 `rebuild_snapshots`（删-重建，逐 trade_at 落快照）并接入波1 的 record/import/delete 触发；`get_position_state` 现金账本从 initial_cash 回放补齐。新增 `analytics` 模块：`valuate`（市值/权重/未实现/新鲜度，叠加 market_data 最新价）、`summary`（total_assets/cash_ratio/pnl_total/集中度；volatility/max_drawdown 样本不足降级）、`risk`（single_cap/industry_cap/cash_floor 硬截断 + top_n 软告警）、`attribution`（标的/行业/现金）。端点：`/api/v1/positions`、`/positions/history`、`/analytics/{summary,risk,attribution}`。风险阈值在 `config` 默认（`/settings/risk` PATCH + RiskRule 表留后续）。门禁全绿：ruff/mypy strict（94 文件）/pytest 138 passed/migrate-check/backup-dry（21 表一致）/前端 gen:api+lint。Kelly/校准/信号（Phase 2）、真实比例拆股/NAV 自动匹配/analysis_snapshots 冻结（波5）留白。
> - **波5（1.5）✅ 2026-08-14**：开市前/收市后报告流水线交付（确定性，无模型——即 AC-06 降级基线形态）。迁移 `0007_reports`（analysis_snapshots/reports/report_evidence；job_runs 复用 0002）。新增 `reports` 模块：domain（报告状态机 PENDING→RUNNING→COMPLETED/PARTIAL/FAILED→RENDERED + `render_markdown` 纯渲染）、repository（`freeze_snapshot` 幂等**不可变**——同 (account,date,purpose) 重入返回既有冻结）、service（`freeze_snapshot` 冻结交易截止/行情 refs/新鲜度/证据截止/各算法版本；`generate_report` 流水线 = freeze→波4 analytics 确定性计算→降级判定（任一持仓 freshness=missing→`market_data_missing`；持仓无关联公告→`documents_unavailable`）→原子写 `data/reports/<date>/<id>/{manifest,report.json,report.md}`（.tmp→replace）→落 reports+来源清单→commit；PARTIAL→补算 version+1 旧版保留；RENDERED 幂等直接返回）。`executor.run_due_jobs`（独立于 scheduler——APScheduler 仅入队不变）：领取 PRE_MARKET/POST_MARKET → 生成 → complete(result_ref=report://id)；非交易日 PRE_MARKET 跳过（skipped://），手动触发放行。端点：`/api/v1/reports`（列表/详情含 report.json 内容）、`/{id}/render?format=md`、`POST /reports/generate`（Idempotency-Key 必需，入队+内联执行返 job_run_id）、`GET /jobs/{id}`。门禁全绿：ruff/mypy strict（102 文件）/pytest 156 passed/migrate-check/backup-dry（24 表一致）/前端 gen:api+lint。6_MODEL §11 不变量由 test_reports 覆盖（幂等/降级/版本递进/executor）。Model Gateway 解释段+MODEL_UNAVAILABLE（波6）、advice（Phase 2）、常驻 worker 线程、CSV/PDF export、html 模板留白。

## 4. Phase 2：盘中与凯利

**对应**：PRD §17 阶段 2 · 技术架构 §24 Phase 2 · 验收 AC-03/07 · 风险/降级自动测试门槛 PRD §18。

| # | 工作项 | 主文档 | 关联 AC |
| --- | --- | --- | --- |
| 2.1 | 盘中行情 TTL + 市场状态机 + 新鲜度门禁（90s 阈值） | [5_DATA_INGESTION_AND_QUALITY.md](./5_DATA_INGESTION_AND_QUALITY.md) §8 | AC-03 |
| 2.2 | 盘中快速问询 + SSE + 10 分钟有效期 + 失效条件 | [6](./6_MODEL_AND_REPORT_PIPELINE.md) §9 · [7](./7_FRONTEND_AND_PWA.md) §11 | AC-03 |
| 2.3 | 回测 + 概率校准（Platt/滚动）+ 信号版本 + 校准状态机 | [4_ANALYTICS_AND_RISK.md](./4_ANALYTICS_AND_RISK.md) §4 §5 | AC-07 |
| 2.4 | 分数凯利纯函数 + 约束轨迹 + Advice 状态机 + 原因链 | [4_ANALYTICS_AND_RISK.md](./4_ANALYTICS_AND_RISK.md) §6 §7 | AC-07 |
| 2.5 | 建议评价回灌 + 行为偏差分析 + 降级安全测试 | [4](./4_ANALYTICS_AND_RISK.md) §8 §9 | AC-03/07 |

**退出条件**：

- [ ] 凯利输入通过样本外校准；模型 Gateway 无权写 `p`（AC-07、技术架构 §25）。
- [ ] 硬风险上限始终截断理论值；移除校准标记后不再给凯利新增仓位（AC-07）。
- [ ] 行情过期/账本未对账/模型冲突时可靠进入降级，拒绝时不输出具体区间（PRD §18、技术架构 §25）。
- [ ] 盘中快照新鲜度达标率 ≥95%；用户快速建议阅读 ≤30 秒（PRD §4.2）。
- [ ] AC-03 全路径：过期行情 → 停止给具体交易数量。

## 5. Phase 3：深度研究与体验增强

**对应**：PRD §17 阶段 3 · 技术架构 §24 Phase 3 · 验收 AC-05、AC-08 增强。

| # | 工作项 | 主文档 | 关联 AC |
| --- | --- | --- | --- |
| 3.1 | 研究任务分解 + 文档解析 + 证据切片 + 引用白名单 | [6](./6_MODEL_AND_REPORT_PIPELINE.md) §4 · [2_DATA_MODEL_AND_STORAGE.md](./2_DATA_MODEL_AND_STORAGE.md) §7 | AC-05 |
| 3.2 | 公司/行业模板 + 估值情景（DCF/可比）+ 长期跟踪指标 | [6](./6_MODEL_AND_REPORT_PIPELINE.md) §4 | AC-05 |
| 3.3 | 多数据源交叉验证 + 事实/计算/判断/未证实标签 | [5_DATA_INGESTION_AND_QUALITY.md](./5_DATA_INGESTION_AND_QUALITY.md) §6 · AC-05 | AC-05 |
| 3.4 | 离线报告缓存（SW 私有缓存，按 user+report+version 隔离）+ 报告导出 | [7_FRONTEND_AND_PWA.md](./7_FRONTEND_AND_PWA.md) §5 | AC-08 |
| 3.5 | Web Push + Passkey（P1）+ 隐私通知模式 | [8_SECURITY_AND_DEPLOYMENT.md](./8_SECURITY_AND_DEPLOYMENT.md) §3 · [6](./6_MODEL_AND_REPORT_PIPELINE.md) §10 | AC-08 |

**退出条件**：

- [ ] 抽样研究报告关键事实均可追溯，无来源结论标“未证实”（AC-05、PRD §17 阶段 3）。
- [ ] 移动端阅读与异步任务体验稳定（SSE + 轮询兜底，[7](./7_FRONTEND_AND_PWA.md) §11）。
- [ ] 离线可打开最近报告并显示缓存时间；盘中/建议入口离线不可用（AC-08）。
- [ ] 退出登录清除私有缓存；PWA 装机验证 iOS+Android 等效环境（PRD §18）。

## 6. Phase 4：按需扩展（非 MVP）

PRD §17 阶段 4、技术架构 §21 扩展触发条件。**不预设规模提前增复杂度**，仅触发时升级（SQLite→PG、独立 worker、时序存储、向量索引、原生 App）。每次扩展经 ADR，Repository 接口不变（技术架构 §21.1）。本文不展开，作为占位。

## 7. 上线门槛核对（PRD §18 + 技术架构 §25，进入个人真实使用前）

Phase 3 完成后逐项核：

- [ ] 持仓计算测试覆盖买/卖/费用/分红/拆分/申赎/调整（Phase 1）。
- [ ] 风险规则、凯利、降级逻辑有自动测试（Phase 2）。
- [ ] 报告关键数字可溯至数据记录或确定性计算（Phase 1/3）。
- [ ] 交易时段行情过期可靠阻止具体交易数量（Phase 2）。
- [ ] 模型不可用/异常不破坏业务数据（Phase 1）。
- [ ] PWA 在 iOS+Android 等效环境验证（Phase 0/3）。
- [ ] 备份恢复演练完成（Phase 0 骨架 → Phase 1 全量）。
- [ ] 公网部署 HTTPS/身份/会话/密钥检查（[8_SECURITY_AND_DEPLOYMENT.md](./8_SECURITY_AND_DEPLOYMENT.md) §11）。
- [ ] 数据源使用符合授权与服务条款（供应商确定后复核）。
- [ ] 技术架构 §25 MVP 架构验收清单 16 项全绿。

## 8. 运行配置与待确认项

### 8.1 运行配置 / 条件触发（2026-08-11 复核）

| 事项 | 确认策略 | 备注 |
| --- | --- | --- |
| Phase 4 触发与范围 | 仅占位 | 达 [技术架构 §21](../TECHNICAL_ARCHITECTURE.md) 触发条件再立 ADR |
| 成功指标观察窗 | 连续 20 交易日 | PRD §4.2，Phase 1 后启动观察 |
| 连续 10 交易日验证起点 | Phase 1.8 | 单实例手动起算并记审计 |

### 8.2 供应商选型（全部已确认 2026-08-12）

| 事项 | 确认决策 | 影响 Phase |
| --- | --- | --- |
| 数据源供应商 | **AKShare（免费开源）**，端口+适配器；升级路径 Tushare Pro | Phase 1.2（采集适配器） |
| 模型供应商 | **通用 OpenAI-compatible**，不锁定；部署时配置 `base_url`+`api_key`+`model` | Phase 1.6（Model Gateway） |
| 通知渠道 | **邮件 SMTP**（587/465） | Phase 1.6 |
| VPS 地域 | **国内 VPS** | Phase 2（部署） |

> **全部 `TODO(*)-selection` 标记已关闭**。原 Phase 1.6 前"通知渠道必须定"的约束已解除。数据源 MVP 用 AKShare 免费起步，对外服务或 SLA 不满足时升级 Tushare（端口不变）。
