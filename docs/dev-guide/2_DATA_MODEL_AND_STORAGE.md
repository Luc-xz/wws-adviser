# 2. 领域模型与数据库 / 存储设计

> 关联：技术架构 §7 §9 · PRD §11 | 索引：[0_DEVELOPMENT_GUIDE_INDEX.md](./0_DEVELOPMENT_GUIDE_INDEX.md)

## 1. 目的

把技术架构 §7 的存储分工与 §7.6 的关系模型落为**可设计的表骨架与存储规则**。本文给设计规则与关键表骨架，不穷举字段——完整字段在编码时由 ORM 定义并随迁移演进，但**必须遵守本文的精度、主键、审计与索引规则**。

## 2. 存储分工（强制）

| 存储 | 保存 | 禁止保存 |
| --- | --- | --- |
| SQLite（`app.db`，WAL） | 用户、账户、交易、持仓快照、最新行情索引、文档元数据、证据、设置、任务、建议、报告元数据、审计、模型调用审计、运行统计 | 大量历史分钟行情、文档二进制、密钥明文 |
| Parquet | 日线、净值、可选分钟线、回测数据集 | 高频随机更新的业务状态 |
| 文件对象目录 | 公告/财报/新闻原文、解析文本 | 业务关系与状态机 |
| 报告目录 | `report.json`/`.md`/`.html`/`manifest.json` | 唯一业务状态（状态以 SQLite 为准） |
| 进程缓存 | 短期行情、交易日历、热点查询 | 任何不可恢复事实 |

> 越界写入（如把文档正文塞 SQLite、把业务状态写 Parquet）需 ADR。

## 3. SQLite 连接与运行约束

启动时对每个连接执行（技术架构 §7.2）：

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;
PRAGMA synchronous = NORMAL;
```

运行约束：

- `uvicorn --workers 1`；`main.py` enforce（见 [1_REPO_STRUCTURE.md](./1_REPO_STRUCTURE.md) §7）。
- 短事务；网络/模型调用不持事务。
- 写事务在 `service` 边界提交。
- 只通过 SQLAlchemy Session 访问；裸 SQL 仅限 FTS5、批量维护、迁移。
- 启动只**校验**迁移版本，不静默升级（生产升级走发布流程）。

## 4. 全局列与主键约定

- 主键：`id CHAR(26)`（ULID），字符串，全局唯一，时间有序。
- 时间：`created_at`/`updated_at` 存 UTC ISO 8601 字符串（`TEXT`），展示转 `Asia/Shanghai`。
- 业务日期：`business_date DATE`（`YYYY-MM-DD`）。
- 乐观锁/可复现：高风险表加 `version INTEGER`。
- 软删除：`deleted_at TEXT NULL`；删除走软删 + 审计。
- 外键：`ON DELETE RESTRICT` 默认（防误删事实）；明细可 `CASCADE`。

## 5. 精度规则（强制，技术架构 §7.3）

| 数据 | SQLite 存储 | scale | API 传输 |
| --- | --- | --- | --- |
| 金额 | 定标整数（`INTEGER`，分）或无损十进制字符串 | 2 | 字符串 `"1485.20"` |
| 股票/ETF 价格 | 定标整数或字符串 | 4 | 字符串 `"12.3450"` |
| 基金净值 | 字符串 | 6 | 字符串 `"1.234567"` |
| 数量 | 字符串 | 6 | 字符串 `"100.000000"` |
| 比例 | 字符串 | 小数 | `"0.0825"` 表 8.25% |

- 领域层一律 `decimal.Decimal`；ORM 用 `String` 或 `Integer`（定标），**不用 `Float`**。
- 推荐：金额/价格用定标整数 + 显式 scale 列，避免字符串排序与聚合问题；基金净值与数量用字符串（scale 大、聚合少）。
- 字段定义需注明 scale，迁移变更 scale 需提供数据迁移脚本与回滚。
- 前端**不得**用浮点重算账本（见 [7_FRONTEND_AND_PWA.md](./7_FRONTEND_AND_PWA.md)）。

## 6. 关键表骨架

关系遵循技术架构 §7.6 的 ER 图。以下给每张表的**职责 + 关键列 + 索引**骨架（`...` 表示按需扩展的非关键列）。

### 6.1 identity

```text
users(id PK, username, password_hash, created_at, updated_at, version)
sessions(id PK, user_id FK, token_hash, issued_at, expires_at, revoked_at, user_agent_hash)
  UNIQUE(token_hash)  INDEX(user_id)
```

- `password_hash` = Argon2id；`token_hash` = 会话令牌哈希（明文不落库）。
- 改密码撤销其他会话：`UPDATE sessions SET revoked_at=now WHERE user_id=? AND id<>current`。

### 6.2 portfolio

```text
accounts(id PK, name, currency, initial_cash, current_cash, total_assets,
         reconciled BOOL, reconciled_at, ...)
  每用户单账户（MVP 唯一约束 user_id=const）
transactions(id PK, account_id FK, instrument_id FK, kind, direction, quantity, price,
             fee, tax, trade_at, external_ref, fingerprint, note, deleted_at,
             created_at, updated_at, version)
  UNIQUE(external_ref)      UNIQUE(fingerprint)      INDEX(account_id, trade_at)
  INDEX(instrument_id, trade_at)
pending_transactions(id PK, account_id FK, instrument_id FK, kind, requested_at,
                     confirm_status, confirmed_at, ...)
position_snapshots(id PK, account_id FK, instrument_id FK, business_date,
                   quantity, available_qty, avg_cost, realized_pnl, unrealized_pnl,
                   market_value, weight, cost_method_version, snapshot_algo_version, ...)
  UNIQUE(account_id, instrument_id, business_date)
  INDEX(account_id, business_date)
reconciliation_adjustments(id PK, account_id FK, instrument_id FK, business_date,
                           before_qty, after_qty, reason, audit_event_id, ...)
```

- `fingerprint` = 标的+方向+数量+价格+日期+费用的稳定哈希，防重复导入。
- `cost_method_version` / `snapshot_algo_version`：算法版本，重建时记录（技术架构 §9.1）。
- 历史交易变更 → 从受影响日期起重建受影响 `position_snapshots`，不手改。

### 6.3 instruments

```text
instruments(id PK, code, market, kind, name, industry, sector, lot_size,
            price_scale, qty_scale, tradable BOOL, status, ...)
  UNIQUE(market, code)   INDEX(name)   INDEX(industry)
instrument_aliases(instrument_id FK, alias_type, alias_value, source)
watchlist(id PK, instrument_id FK, added_at, note)
```

- 内部用稳定 `instrument_id`，代码不作永久主键。
- `price_scale`/`qty_scale` 校验传输与存储精度。

### 6.4 market_data

```text
trading_calendar(date PK, market, is_trading_day, session_schedule_json)
market_records(id PK, instrument_id FK, business_date, open, high, low, close,
               volume, amount, source, source_url, market_time, fetched_at,
               received_at, source_delay_class, quality_status, content_hash,
               adjustment_type, ...)
  UNIQUE(instrument_id, business_date, source, adjustment_type)
  INDEX(instrument_id, business_date DESC)
nav_records(id PK, instrument_id FK, nav_date, nav, published_at, source, quality_status, ...)
  UNIQUE(instrument_id, nav_date, source)
intraday_quotes(id PK, instrument_id FK, market_time, fetched_at, price, change_pct,
                volume, amount, bid_ask_json, quality_status, source, ...)
  INDEX(instrument_id, market_time DESC)
```

- 日线/净值**主存 Parquet**，`market_records`/`nav_records` 在 SQLite 仅存**最新索引 + 元数据**用于查询路由；Parquet 存完整历史（见 §8）。
  - 设计取舍：若查询复杂度高，可改为 SQLite 存最近 N 日 + Parquet 存全量，由 repository 透明合并。决策留 ADR。
- `quality_status ∈ {OK, DELAYED, MISSING, CONFLICT, PARSE_FAILED, SOURCE_UNAVAILABLE}`。
- 新鲜度字段齐全（见 [5_DATA_INGESTION_AND_QUALITY.md](./5_DATA_INGESTION_AND_QUALITY.md)）。

### 6.5 documents

```text
documents(id PK, kind, title, issuer, published_at, source, source_url,
          content_sha256, local_path, text_path, trust_level, fetched_at, quality_status, ...)
  UNIQUE(content_sha256)   INDEX(kind, published_at)   INDEX(instrument_id... via links)
document_links(document_id FK, instrument_id FK, link_type)
  INDEX(instrument_id)
evidence(id PK, document_id FK, source_record_id, slice_ref, claim_text, cited_at,
         trust_level, content_hash, ...)
  INDEX(document_id)   INDEX(instrument_id via links)
documents_fts USING FTS5(title, body_text, content='documents', content_rowid='id')
```

- 原文按 `content_sha256` 内容寻址（见 §9）。
- FTS5 为 `documents` 的外部内容表，重建可由原文重生成。

### 6.6 analytics / advice

```text
analysis_snapshots(id PK, account_id FK, business_date, frozen_at,
                   portfolio_version, trade_cutoff_at, market_record_refs_json,
                   freshness_refs_json, evidence_cutoff_at, risk_ruleset_version,
                   signals_version, calendar_version, anomalies_json,
                   degradation_flags_json, ...)
  UNIQUE(account_id, business_date, snapshot_purpose)
signals(id PK, signal_class L1|L2|L3, rule_version, training_window_json,
        applicable_scope_json, cost_assumption_json, p_low, p_mid, p_high,
        n_eff, n_eff_oos, b_avg_win, b_avg_loss, calibration_state, calibration_expires_at,
        reliability_ece, platt_version, oos_metrics_json, ...)
  INDEX(signal_class, calibration_state)
advice(id PK, analysis_snapshot_id FK, instrument_id FK, action, current_weight,
       target_weight_range_json, triggers_json, invalidations_json, valid_until,
       reason_chain_json, degradation_reasons_json, state, evidence_ids_json, ...)
  INDEX(analysis_snapshot_id)  INDEX(instrument_id)
advice_evaluations(advice_id FK, evaluation_window_json, evaluated_at,
                   primary_metric, secondary_metric_json, outcome_json, ...)
```

- `p_*` 字段**只在 signals 仓储内由回测/校准服务写入**；`model_gateway` 无写权限（见 [4_ANALYTICS_AND_RISK.md](./4_ANALYTICS_AND_RISK.md)）。
- `reason_chain_json` 是凯利拒绝/折扣的可审计原因链。
- `advice.state` 走状态机（见 [4_ANALYTICS_AND_RISK.md](./4_ANALYTICS_AND_RISK.md)）。

### 6.7 reports / research / jobs / model / notifications / audit

```text
reports(id PK, report_type, business_date, status, version, manifest_path,
        content_json_path, content_md_path, content_html_path, analysis_snapshot_id FK,
        sources_count, generated_at, ...)
  UNIQUE(report_type, business_date, version)
report_evidence(report_id FK, evidence_id FK, citation_ref)
  INDEX(report_id)
research_jobs(id PK, scope_kind company|industry, target, depth, status, job_run_id FK, ...)
job_runs(id PK, job_type, business_date, scope_key, idempotency_key, config_version,
         status, attempt, max_attempts, lease_until, progress, error_code,
         next_retry_at, started_at, completed_at, result_ref, ...)
  UNIQUE(job_type, business_date, scope_key, config_version)  -- 幂等防线
  INDEX(status, lease_until)   INDEX(idempotency_key)
model_profiles(id PK, name, base_url, model_name, key_ref, temperature, max_tokens,
               timeout, retry, task_routes_json, ...)
model_calls(id PK, job_run_id FK, model_profile_id FK, task_type, prompt_template,
            prompt_version, prompt_hash, input_evidence_ids_json, started_at, ended_at,
            prompt_tokens, completion_tokens, estimated_cost, status, error_code, ...)
  INDEX(job_run_id)   INDEX(model_profile_id, started_at)
notifications(id PK, channel, event_type, payload_hash, status, attempts, sent_at, error_code, ...)
  UNIQUE(channel, event_type, payload_hash)  -- 通知幂等
audit_events(id PK, actor, action, target_type, target_id, before_summary_json,
             after_summary_json, request_id, job_id, occurred_at)
  INDEX(target_type, target_id, occurred_at)   -- 只追加
runtime_stats(key PK, value_json, updated_at)   -- 轻量运行统计（技术架构 §16.3）
data_conflicts(id PK, instrument_id FK, field, source_a, source_b, value_a, value_b,
               resolved_by, resolved_at, status, ...)
  INDEX(instrument_id, status)
```

- `audit_events` 敏感值存**摘要/脱敏差异**，不存明文。
- `runtime_stats` 用于状态页（任务成功率、源新鲜度、模型费用等）。

## 7. 索引设计原则

- 高频查询路径必须有索引：`business_date DESC`、`(account_id, business_date)`、`status+lease`（任务领取）。
- FTS5 表与外部内容表分离，定期 `REBUILD`。
- 索引在迁移中显式创建，命名 `ix_<table>_<cols>`。
- 避免在 SQLite 上建过多宽索引；个人量级下查询计划以 EXPLAIN 验证即可。

## 8. Parquet 布局与写入规则

布局与技术架构 §7.4 一致：

```text
data/market/
├── daily/market=<SSE|SZSE>/instrument=<id>/year=<YYYY>/part.parquet
├── nav/instrument=<id>/year=<YYYY>/part.parquet
└── intraday/date=<YYYY-MM-DD>/instrument=<id>/part.parquet
```

写入规则：

1. 先写同目录 `part.parquet.tmp`，校验行数与 schema 后原子 `rename`。
2. 每个 parquet 文件元数据含：`schema_version`、`source`、`adjustment_type`、`generated_at`、`n_rows`。
3. 同一分区单 writer（任务 scope_key 锁）。
4. 小批次先内存/SQLite 暂存，任务合并写入，避免碎片。
5. 定期校验：交易日连续性、主键去重、OHLC 合法（`low≤open,close≤high` 等）。
6. 读取经 Polars；跨分区分析按需用 DuckDB（不常驻）。

## 9. 文档与报告文件布局

```text
data/documents/{kind}/{sha256[0:2]}/{sha256}.{ext}
data/documents/text/{sha256[0:2]}/{sha256}.txt
data/reports/<business_date>/<report_id>/{manifest,report.json,report.md,report.html}
data/backups/<YYYY-MM-DD>/...        # 见 §11
data/locks/scheduler.lock            # 单调度实例
```

- 路径**只由服务端生成**，拒绝用户提供的相对路径（路径穿越防护，见 [8_SECURITY_AND_DEPLOYMENT.md](./8_SECURITY_AND_DEPLOYMENT.md)）。
- DB 存相对 `/data` 的路径，便于容器迁移。
- 报告先存 `report.json`，再渲染 md/html；状态以 SQLite `reports` 为准。

## 10. Alembic 迁移规则

- 每个迁移：`<rev>_<topic>.py`，含 `upgrade()` 与 `downgrade()`。
- **先检查备份兼容性**：破坏性迁移在 docstring 注明影响与回滚边界。
- 启动只 `alembic current` 校验，不 `upgrade head`（生产升级走发布流程，见 [8_SECURITY_AND_DEPLOYMENT.md](./8_SECURITY_AND_DEPLOYMENT.md)）。
- CI 必测：从空库 `upgrade head` 与从上一版本升级两条路径（见 [9_TEST_AND_CI.md](./9_TEST_AND_CI.md)）。
- 不在迁移里做大规模数据回填；回填走独立脚本并在维护窗口执行。
- FTS5 表迁移：用 `REBUILD` 重建，不丢原文。

## 11. 备份与恢复

### 11.1 备份（技术架构 §16.5）

不能在 WAL 写入期间直接复制 `app.db`。流程：

1. 获取 `backups` 任务锁（`job_runs` + 文件锁）。
2. SQLite Online Backup API（`sqlite3.Connection.backup()`）生成一致性副本 `app.db.bak`。
3. 遍历生成 documents/parquet/reports 清单 + SHA-256。
4. 打包：db 副本 + 配置非敏感部分 + 清单。
5. 可选加密（客户端）复制异地。
6. 校验归档可读，写 `runtime_stats` 备份状态与时间。
7. 密钥**不进入**普通备份。

保留策略：最近 7 日备份、4 周备份、6 月备份；增量文件同步 + 定期全量。

### 11.2 恢复（技术架构 §16.6）

维护模式：停调度与任务领取 → 校验归档版本/哈希 → **先备份当前状态** → 替换文件 → `alembic` 迁移检查 → DB 一致性检查 → 持仓重建验证 → 重新开放。恢复需二次确认（API 与 UI 都强制）。

### 11.3 演练

`scripts/restore_drill.py`：自动跑一次“备份→注入若干交易→恢复→校验账本哈希与持仓一致”，CI 每周或手动触发。

## 12. 数据保留与清理

- 交易、持仓快照、建议、报告元数据、审计：长期保留，除非用户显式清理。
- 日线/净值：长期保留。
- 盘中细粒度（intraday parquet）：默认保留 90 天，可配置；清理任务记审计。
- 日志：默认 30 天轮转。
- 新闻正文：按容量与授权清理，**元数据与引用哈希保留**（保证 evidence 可定位）。

## 13. 待确认项

| 事项 | 当前默认 | 备注 |
| --- | --- | --- |
| 日线/净值在 SQLite vs Parquet 的分布 | SQLite 存索引+元数据，Parquet 存全量 | 实现时按查询性能定，留 ADR |
| ULID 生成库 | 选稳定 Python ULID 库，运行时生成（非 DB 默认） | 避免依赖 SQLite 扩展 |
| 金额存储 | 定标整数（分） | 净值/数量用字符串 |
| 备份加密 | 客户端可选加密，异地启用 | 密钥与备份分离管理 |
