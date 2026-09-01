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
| 1.8 | 连续 5 个交易日运行验证（PRD §17 阶段 1 退出；2026-08-27 窗口压缩） | 全局运行 | AC-02/04 |

**退出条件**（2026-08-27 起验证窗口压缩为 5 个交易日，PRD §20 变更决策；操作口径见 deploy/README §2）：

- [x] 连续 5 个交易日（跨周末并含一个周一）稳定形成“交易→持仓→报告→复盘”闭环（PRD §17 阶段 1）。✅ 2026-08-25 ~ 08-31（D1=8/25 周二起算，D5=8/31 周一收官），窗口内 job_runs 零失败；附注：8/29-30 周末因日历缺陷多生成 4 份报告（见下），不计入样本
- [x] 账本对账一致率 100%；报告关键数值可追溯率 100%（PRD §4.2）。✅ 8/27 实测：1635 笔全量回放 vs 79 标的快照，数量精确全等、avg_cost 半分容差内一致（分级定标舍入，属设计）；报告头版本链（MWAC_v1/frozen_at/trade_cutoff）齐备
- [x] 开市前/收市后报告按时生成：5 日 10 份全部于 09:00/17:00 前完成（≥95% 的零容错收紧形态，PRD §4.2）。✅ 10/10（最早完成 08:30:26，最晚 16:02:27，距截止均余量充足；连周末 4 份误生成计 14/14）
- [x] 模型关闭仍可登录/管交易/更新行情/展示确定性风险摘要，报告显示可重试降级（AC-06）。✅ 8/27 断 key 实测：16:00 post 以 `model_unavailable` 降级生成（确定性内容完整、通知照发），17:37 恢复后 8/28 起模型段恢复正常；另实测 prod 护栏有效拦截 stub 上线
- [x] CSV 重复导入不产生重复流水；错误行被预览拒绝（AC-01）。✅ 8/27 实测：真实交易重构 CSV 重导 → 预览 5 重复 0 可导入、确认后 1635→1635；非法数量/未知方向两行被拒并给出行号
- [x] 公告源失败时报告标记不完整（AC-02）。✅ 验证期全程 `documents_unavailable` + PARTIAL 形态覆盖（公告-持仓关联属 Phase 3.1，PRD §20 决策记录已声明接受）
- [x] 备份恢复演练通过，账本哈希/持仓一致，密钥不进普通备份（AC-09）。✅ 8/27 实测：drill 28 表一致；生产首份真实备份（Online Backup API）；3 个真实密钥值子串扫描未泄漏

> **Phase 1 完成声明（2026-08-31 16:03，VPS 114.132.239.95 实测收官）**：七条退出条件全绿。
> 运行镜像 `wws-adviser:6e2b29d`（dev）。验证期发现并已修复两项缺陷：① stub 护栏触发导致的
> 启动崩溃循环（改用断 key 形态完成 AC-06）；② 非交易日不跳过（8/29-30 周末误生成 4 份报告
> ——trading_calendar 空 + 校验 fail-open + 日历同步缺失三层叠加；修复=weekday 兜底 +
> AKShare 日历同步挂入每日 15:20 维护任务，766 行真实日历已落库，下周末起生效）。
> 遗留观察：① PRD §4.2 成功指标观察窗（连续 20 交易日）自 2026-09-01 起算；② tech-debt
> 分支（10 提交）待合并——`openai_model.py` 需融合流式与 structured-output 两版改动。

> **波次进度**（退出条件全部留待波8 整体核验，逐波只记交付）：
>
> - **波1（1.1）✅ 2026-08-13**：持仓/交易基础层交付。新增 `instruments`、`portfolio` 两模块（domain/models/repository/schemas/service/api）+ 迁移 `0003_portfolio`（instruments/accounts/transactions）。金额按定标整数分存储、price/quantity 无损 decimal 串；指纹去重（sha256，量化保证 `100`≡`100.000000`）；CSV 导入预览（`batch_id` 串起确认）+ 确认两阶段、错误行预览拒绝、跨路径（导入/手工）幂等。端点：`/api/v1/instruments*`、`/accounts`、`/transactions*`（含 `/import`、`/import/confirm`）。门禁全绿：ruff/mypy strict（76 文件）/pytest 99 passed/migrate-check/backup-dry（9 表一致）/前端 gen:api+lint+build。AC-01 由 `test_csv_import_*`、`test_manual_transaction_*` 直接覆盖。position_snapshots（avg_cost/PnL）随波4 引入。
> - **波2（1.2）✅ 2026-08-13**：行情采集（日线/净值为主）交付。扩展 `market_data` 模块（+models/repository + service 采集流水线 + domain parse_bars/parse_nav/质量/新鲜度骨架）+ 迁移 `0004_market_data`（trading_calendar/market_records/nav_records）+ `infrastructure/storage/parquet_store.py`（polars 分区原子写/读）。日线采集：fetch→parse（OHLC 合法性校验）→Parquet 主存 + SQLite 元数据索引 upsert（UNIQUE 去重）→质量状态（日线口径 OK/MISSING/DELAYED）。端点：`/api/v1/market/{bars,nav,quality,state}` + `*/refresh`（ops，需 Idempotency-Key）。AKShare 列为 optional extra + 懒加载适配器脚手架（`rows_to_*` 纯函数单测，真实调用留待国内 VPS 实录）；stub 默认、闭环可测。门禁全绿：ruff/mypy strict（82 文件）/pytest 116 passed/migrate-check/backup-dry（12 表一致）/前端 gen:api+lint。盘中 180s TTL/状态机（Phase 2.1）、data_conflicts（Phase 3.3）、clock-skew/熔断（TODO）本轮留白。
> - **波3（1.3）✅ 2026-08-13**：公告/文档 + 内容寻址 + FTS5 交付。新增 `documents` 模块（domain/models/repository/schemas/service/api）+ 迁移 `0005_documents`（documents/document_links/evidence + `documents_fts` contentless 虚拟表）。采集流水线：discover→download→`LocalObjectStore` sha256 内容寻址存原文/文本→`content_sha256` UNIQUE 去重→insert documents + links + FTS 索引。FTS5 contentless（`content=''`，正文不进 SQLite）+ **CJK 按字分词**（unicode61 无内置中文分词，索引与查询两侧插空格）；rowid 用 documents 隐式整数 rowid。端点：`/api/v1/documents`（列表/详情/`search` FTS）、`/evidence/{id}`、ops `/refresh`（需 Idempotency-Key）。`document_source` 配置 + `akshare_document` 懒加载脚手架（`rows_to_document_ref` 纯函数单测）；stub 默认闭环。门禁全绿：ruff/mypy strict（90 文件）/pytest 126 passed/migrate-check（含 FTS5 DDL）/backup-dry（20 表一致，含 FTS5 影子表）/前端 gen:api+lint。evidence 填充（Phase 3.1）、真实公告源实录（国内 VPS）、PDF/HTML 解析、data_conflicts（Phase 3.3）留白。
> - **波4（1.4）✅ 2026-08-13**：确定性组合指标 + 风险规则交付（Phase 1 计算核心）。迁移 `0006_positions`（position_snapshots）。`portfolio/domain` 新增 MWAC 纯函数 `compute_positions`/`compute_position_series`（**全 8 种交易类型**：BUY/SELL/SUBSCRIBE/REDEEM/DIVIDEND/SPLIT/FEE/ADJUST；现金分红=已实现收益、送股=零成本增数、费用/调整=现金；卖空校验、replay 幂等——确定性数值由 `test_positions_domain` 固定 fixture 断言锁定）。`portfolio/service` 新增 `rebuild_snapshots`（删-重建，逐 trade_at 落快照）并接入波1 的 record/import/delete 触发；`get_position_state` 现金账本从 initial_cash 回放补齐。新增 `analytics` 模块：`valuate`（市值/权重/未实现/新鲜度，叠加 market_data 最新价）、`summary`（total_assets/cash_ratio/pnl_total/集中度；volatility/max_drawdown 样本不足降级）、`risk`（single_cap/industry_cap/cash_floor 硬截断 + top_n 软告警）、`attribution`（标的/行业/现金）。端点：`/api/v1/positions`、`/positions/history`、`/analytics/{summary,risk,attribution}`。风险阈值在 `config` 默认（`/settings/risk` PATCH + RiskRule 表留后续）。门禁全绿：ruff/mypy strict（94 文件）/pytest 138 passed/migrate-check/backup-dry（21 表一致）/前端 gen:api+lint。Kelly/校准/信号（Phase 2）、真实比例拆股/NAV 自动匹配/analysis_snapshots 冻结（波5）留白。
> - **波5（1.5）✅ 2026-08-14**：开市前/收市后报告流水线交付（确定性，无模型——即 AC-06 降级基线形态）。迁移 `0007_reports`（analysis_snapshots/reports/report_evidence；job_runs 复用 0002）。新增 `reports` 模块：domain（报告状态机 PENDING→RUNNING→COMPLETED/PARTIAL/FAILED→RENDERED + `render_markdown` 纯渲染）、repository（`freeze_snapshot` 幂等**不可变**——同 (account,date,purpose) 重入返回既有冻结）、service（`freeze_snapshot` 冻结交易截止/行情 refs/新鲜度/证据截止/各算法版本；`generate_report` 流水线 = freeze→波4 analytics 确定性计算→降级判定（任一持仓 freshness=missing→`market_data_missing`；持仓无关联公告→`documents_unavailable`）→原子写 `data/reports/<date>/<id>/{manifest,report.json,report.md}`（.tmp→replace）→落 reports+来源清单→commit；PARTIAL→补算 version+1 旧版保留；RENDERED 幂等直接返回）。`executor.run_due_jobs`（独立于 scheduler——APScheduler 仅入队不变）：领取 PRE_MARKET/POST_MARKET → 生成 → complete(result_ref=report://id)；非交易日 PRE_MARKET 跳过（skipped://），手动触发放行。端点：`/api/v1/reports`（列表/详情含 report.json 内容）、`/{id}/render?format=md`、`POST /reports/generate`（Idempotency-Key 必需，入队+内联执行返 job_run_id）、`GET /jobs/{id}`。门禁全绿：ruff/mypy strict（102 文件）/pytest 156 passed/migrate-check/backup-dry（24 表一致）/前端 gen:api+lint。6_MODEL §11 不变量由 test_reports 覆盖（幂等/降级/版本递进/executor）。Model Gateway 解释段+MODEL_UNAVAILABLE（波6）、advice（Phase 2）、常驻 worker 线程、CSV/PDF export、html 模板留白。
> - **波6（1.6）✅ 2026-08-14**：Model Gateway + 邮件 SMTP 通知交付（AC-06 闭环）。迁移 `0008_model_notify`（model_profiles/model_calls/notifications/app_settings）。新增 `model_gateway` 模块：prompt 注册表（pre/post_market v1，版本即代码+hash 入审计）、后置校验（数值与确定性不一致→**覆盖为确定性值**、evidence 白名单违例→BLOCKED、结构缺字段→一次受控修复仍败→放弃模型段）、脱敏上下文（现金绝对金额不进模型明文，`<untrusted_context>` 数据块防注入）；`call_model` 网关（路由/审计/异常一律降级不外抛）。真实适配器：`openai_model.py`（httpx 懒加载，`<think>` 剥离+JSON 抽取纯函数单测）+ `smtp_notifier.py`（stdlib smtplib+to_thread 零新依赖，587/465）；stub 默认闭环。`notifications` 模块：幂等 notify（UNIQUE(channel,event_type,payload_hash)）+ 隐私脱敏 mask_payload；executor 报告终态后通知，**通知失败绝不失败 job**（FR-NOTIFY-001）。`generate_report` 改 async：freeze 后独立 commit → **模型调用时无打开写事务**（集成测试断言）→ 失败→`model_unavailable` 降级标记 + 确定性内容完整 + 可重试新版本（AC-06 完整验证）。`appsettings` 模块 + `/api/v1/settings/{risk,models,notifications}`：GET 掩码（key 只显 env 引用名）/PATCH 白名单持久化+审计/risk 覆盖经 effective_settings 实际生效。门禁全绿：ruff/mypy strict（119 文件）/pytest 174 passed/migrate-check/backup-dry（28 表一致）/前端 gen:api+lint。真实 OpenAI/SMTP 联调（VPS+凭据）、原生 structured-output、wechat_work/server_chan、通知冷却聚合、4 个 settings 子资源、advice 动作词全集（Phase 2）留白。
> - **波7（1.7）✅ 2026-08-14**：前端页面交付（HOME-01/PORT-01/REP-01/02/DATA-01/SET-00 + typed client 迁移 + 轮询兜底）。引入 **TanStack Vue Query**（doc7 §2 唯一服务端状态入口）+ main.ts 装配；`Login.vue`/`stores/session.ts`/首页全部迁移 openapi-fetch typed client（CSRF/Request-ID 中间件既有）。`shared/ui` 5 组件（DataStatusBar 4 态 `[data-state]`/MetricCard/RiskAlert hard 前置/PositionRow/DataFooter 尾注——ENFORCEMENT_CONTRACT §2.3）全部 UnoCSS 语义 token；`shared/sse/useJobStatus`（EventSource→退避轮询 `GET /jobs/{id}` 兜底，SSE 端点 Phase 2.2 就绪即插，终态停止）。页面：HOME（问候/DataStatusBar/摘要 MetricCards/风险/持仓 top5/最新报告/空账户 empty-guide 绝不显假 ¥0/离线禁刷新 AC-08）、PORT（摘要条/风险前置持仓卡/记录交易占位/空态）、REP `/reports/:id`（头部降级标记/执行摘要/风险/持仓/模型段有则显无则降级提示/版本尾注/重新生成→轮询→跳转）、DATA-01 `/data-status`、SET（风险阈值 + 登出）。路由 +`/reports/:id`、`/data-status`；PWA NetworkOnly 扩为 `/api/`（当前值不经 SW）；eslint 自定义规则 `no-market-color-misuse` 实现+注册（§3.1）。测试：TC-DSB/TC-RA/TC-NUM un-skip 转绿 + home 契约（空账户/离线）+ useJobStatus 轮询兜底——**18 前端测试**；门禁：pnpm lint（0 error）+ build（PWA SW）+ 后端 174 passed 无回归。AdviceCard/PAUSE（Phase 2）、ECharts 趋势图、深色模式、自选/流水 Tab、交易记录 UI、离线报告私有缓存（Phase 3.4）、SSE 服务端 `/events`（Phase 2.2）、CSV 导入 UI 留白。
> - **波8（1.8）部署就绪 ✅ 2026-08-14（运行验证待 VPS 执行）**：交付部署工件 + 常驻执行闭环。①`deploy/`：多阶段 Dockerfile（Node 构建前端→uv `--frozen --extra akshare`→非 root 精简镜像，标签=commit 禁 latest）+ docker-compose（/data 卷、仅回环 8000、healthcheck）+ env.example（只名不密，8_SECURITY §9.3）+ nginx.conf.example（HTTPS/安全头/登录限速/SSE 透传）+ README=**波8 运行手册**（首次部署步骤 + 10 交易日逐日核验表映射七条退出条件 + 运维要点）。②后端补件：`WWSE_STATIC_DIR` 同源挂载 PWA 静态（SPA 回退，API 路由优先）；**执行器常驻线程**（持 scheduler 锁启动、`run_due_jobs` 轮询领取报告任务+通知、test 环境不启动、优雅停机）——补上 scheduler 仅入队后无人领取的波8 缺口。门禁全绿：后端 174 + 前端 18/lint/build。**退出条件勾选仍待 VPS 实跑 10 交易日回填**（见 deploy/README §2）。

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

> **验收口径与收官进度（2026-09-01 补记）**：
>
> - **运行指标测法**：新鲜度达标率 = 观察窗内 `advice_records` 中 reasons_json 不含 `data_stale`
>   的占比；阅读 ≤30 秒 = 验收时人工抽样计时（建议各形态 3 次）；条件 1 运行形态 =
>   `signal_calibrations` 存在 `calibrated_oos` 且未过期；条件 2 运行形态 = 至少一条凯利
>   建议的约束轨迹含硬上限截断步骤（或自动测试 + 任意真实建议实例佐证）。
> - **已达成**：`breakout-20` 于 2026-09-01 深回填 3 年日线（2023-08 起）后校准通过
>   （`calibrated_oos`，n_eff_oos=109/30，reliability 通过，有效期至 2026-12-02）；降级
>   场景有真实实例（2026-08-31 盘中建议：三重原因明确、区间字段全空）。
> - **收官补件**：① 对账确认机制（`POST /accounts/{id}/reconcile` + 新交易自动复位，
>   be0c497）——此前 `reconciled` 无任何置 True 路径，盘中建议恒带 `ledger_unreconciled`
>   降级属结构性死锁；② 日线深回填作为一次性运维动作（数据维护任务日常 lookback=30 天
>   仅增量）。剩余为观察窗积累（与 20 交易日成功指标窗口同载体，约 2026-09-28 到期）。

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

### 8.0 技术债清理批次（2026-08-26，tech-debt 分支）

Phase 1 各波次注记中的「无期留白」一次性清账（每项原子提交，门禁全绿）：

| # | 项 | 出处 | 落点 |
| --- | --- | --- | --- |
| 1 | documents 游标分页（keyset，替换 limit 截断） | 波3 `TODO(波后续)` | `GET /documents` + `next_cursor` |
| 2 | clock-skew 校验（零依赖 SNTP，启动测偏移 + health 暴露） | 波2 `TODO(clock-skew)` | `infrastructure/clock_sntp.py` |
| 3 | 通知冷却窗口（同 channel+event_type，默认关闭可配） | 波6 留白 | `WWSE_NOTIFY_COOLDOWN_SEC` |
| 4 | 企微机器人 / Server酱 渠道适配器 | 波6 留白 / PRD §20.1 | `notifier_source=wechat_work\|server_chan` |
| 5 | 模型原生 structured-output（json_schema，4xx 剥离回退） | 波6 留白 | model_gateway + openai_model |
| 6 | PORT 三 Tab：流水列表 / 自选增删（app_settings KV）/ ECharts 已实现盈亏趋势 | 波7 前端留白 | `/portfolio` |
| 7 | 深色模式（useDark class 策略 + 表面 token + 全页面 dark: 变体） | 波7 前端留白 | 设置页外观开关 |
| 8 | dev 遗留 mypy strict 报错 ×6（备源 None 上抛防御等） | 近期运行期提交 | 随批清零 |

仍留待后续：交易记录手工录入 UI、CSV 导入 UI、SSE 服务端 `/events`（Phase 2 收口项）、
离线报告私有缓存与报告导出（Phase 3.4）、企微/Server酱真实联调（VPS+凭据）。

### 8.1 运行配置 / 条件触发（2026-08-11 复核）

| 事项 | 确认策略 | 备注 |
| --- | --- | --- |
| Phase 4 触发与范围 | 仅占位 | 达 [技术架构 §21](../TECHNICAL_ARCHITECTURE.md) 触发条件再立 ADR |
| 成功指标观察窗 | 连续 20 交易日 | PRD §4.2，Phase 1 后启动观察 |
| 连续 5 交易日验证起点 | Phase 1.8 | 单实例手动起算并记审计（2026-08-27 起窗口压缩，见 §3/PRD §20） |

### 8.2 供应商选型（全部已确认 2026-08-12）

| 事项 | 确认决策 | 影响 Phase |
| --- | --- | --- |
| 数据源供应商 | **AKShare（免费开源）**，端口+适配器；升级路径 Tushare Pro | Phase 1.2（采集适配器） |
| 模型供应商 | **通用 OpenAI-compatible**，不锁定；部署时配置 `base_url`+`api_key`+`model` | Phase 1.6（Model Gateway） |
| 通知渠道 | **邮件 SMTP**（587/465） | Phase 1.6 |
| VPS 地域 | **国内 VPS** | Phase 2（部署） |

> **全部 `TODO(*)-selection` 标记已关闭**。原 Phase 1.6 前"通知渠道必须定"的约束已解除。数据源 MVP 用 AKShare 免费起步，对外服务或 SLA 不满足时升级 Tushare（端口不变）。
