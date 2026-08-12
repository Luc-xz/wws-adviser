# 3. API 契约设计

> 关联：技术架构 §13 · PRD §8 | 索引：[0_DEVELOPMENT_GUIDE_INDEX.md](./0_DEVELOPMENT_GUIDE_INDEX.md)

## 1. 目的

把技术架构 §13 的 API 约定落为**端点契约与错误码规范**。OpenAPI 是接口事实源，前端类型由其生成（见 [7_FRONTEND_AND_PWA.md](./7_FRONTEND_AND_PWA.md)）。写新端点前先在本文登记端点表，再写 router。

## 2. 通用约定（强制）

- 根路径：`/api/v1`。
- JSON UTF-8、`snake_case`。前端不得擅自转 `camelCase`（生成层保持）。
- 时间：带时区 ISO 8601（`Asia/Shanghai` 或 UTC，字段注明）；业务日期 `YYYY-MM-DD`。
- 十进制：字符串传输（见 [2_DATA_MODEL_AND_STORAGE.md](./2_DATA_MODEL_AND_STORAGE.md) §5）。
- 写操作支持 `Idempotency-Key` 请求头；**导入与创建长任务强制要求**，缺失返回 `400 missing_idempotency_key`。
- 列表：游标分页（`cursor`/`limit`/`next_cursor`），禁用大 offset。
- 错误：RFC 9457 Problem Details（见 §5）。
- 每响应含 `X-Request-ID`；客户端可回传以便关联。
- 认证：会话 Cookie（`HttpOnly; Secure; SameSite=Lax/Strict`）；SSE 与敏感操作同源。
- 路径不含动词，动作由方法表达；状态机转换用 `POST /<resource>/<id>/<transition>`（如 `POST /advice/:id/publish`）。

## 3. API 分组与端点表

> 列：`方法 路径 | 用途 | 幂等 | 认证 | 关键请求/响应字段`。`…` 表示次要字段省略。错误码见 §5。

### 3.1 auth

| 方法 路径 | 用途 | 幂等 | 关键字段 |
| --- | --- | --- | --- |
| `POST /auth/login` | 登录 | 需 Idempotency-Key | req: `username,password`; set cookie |
| `POST /auth/logout` | 登出 | — | 撤销当前会话 |
| `GET /auth/session` | 当前会话 | — | resp: `user_id_hash, expires_at` |
| `POST /auth/password` | 改密码 | 需重新认证 | 撤销其他会话 |
| `POST /auth/passkey/*` (P1) | Passkey 注册/登录 | — | 不影响主键/权限 |

### 3.2 accounts

| 方法 路径 | 用途 | 关键字段 |
| --- | --- | --- |
| `GET /accounts` | 账户列表 | resp: `cash, total_assets, reconciled` |
| `POST /accounts` | 创建账户 | req: `name, currency, initial_cash` |
| `PATCH /accounts/:id` | 编辑/停用 | |
| `POST /accounts/:id/reconcile` | 对账确认 | req: `reason`; 写审计 |

### 3.3 transactions

| 方法 路径 | 用途 | 幂等 | 关键字段 |
| --- | --- | --- | --- |
| `GET /transactions` | 流水列表 | — | 游标分页；按 `account,instrument,kind,date` 过滤 |
| `POST /transactions` | 手工录入 | 需 Idempotency-Key | req: `instrument_id,kind,direction,quantity,price,fee,trade_at` |
| `POST /transactions/import` | CSV 导入预览 | 需 Idempotency-Key | req: 文件; resp: `preview rows, errors, duplicates` |
| `POST /transactions/import/confirm` | 确认导入 | 需 Idempotency-Key | req: `fingerprint[]`; 触发重算 |
| `PATCH /transactions/:id` | 编辑 | — | 触发受影响日期起重建 |
| `DELETE /transactions/:id` | 软删除 | — | 写审计 + 重建 |

### 3.4 positions

| 方法 路径 | 用途 | 关键字段 |
| --- | --- | --- |
| `GET /positions` | 当前持仓 | resp: `instrument, quantity, available, avg_cost, market_value, weight, freshness` |
| `GET /positions/history` | 历史持仓 | 按 `business_date` 游标 |

### 3.5 instruments

| 方法 路径 | 用途 |
| --- | --- |
| `GET /instruments` | 搜索（`q, market, kind, industry`） |
| `GET /instruments/:id` | 详情（`lot_size, price_scale, status`） |
| `POST /instruments/:id/watchlist` / `DELETE` | 自选管理 |

### 3.6 market

| 方法 路径 | 用途 | 关键字段 |
| --- | --- | --- |
| `GET /market/state` | 市场状态 | resp: `phase, is_trading_day, next_event_at` |
| `GET /market/quotes` | 行情快照（一批） | resp: `price, change_pct, market_time, freshness, quality_status` |
| `GET /market/bars/:instrument_id` | 日线 | query: `start,end,adjustment` |
| `GET /market/nav/:instrument_id` | 净值 | resp: `nav, nav_date, published_at` |
| `GET /market/quality` | 数据质量状态 | 各源最后成功/新鲜度 |

### 3.7 documents / evidence

| 方法 路径 | 用途 |
| --- | --- |
| `GET /documents` | 公告/财报/新闻列表（过滤 `kind,instrument_id,since,trust_level`） |
| `GET /documents/:id` | 详情 + 原文/归档链接 |
| `GET /documents/search` | FTS5 检索（`q`，元数据过滤） |
| `GET /evidence/:id` | 单条证据 + 定位信息 |

### 3.8 analytics

| 方法 路径 | 用途 | 关键字段 |
| --- | --- | --- |
| `GET /analytics/summary` | 组合摘要 | `total_assets, cash_ratio, pnl_today, pnl_total, concentration, volatility, max_drawdown` |
| `GET /analytics/risk` | 风险暴露 | 触发的软/硬限制清单 |
| `GET /analytics/attribution` | 收益归因 | 按标的/行业/现金贡献 |
| `GET /analytics/signals/:instrument_id` | 信号与凯利输入 | `signal_class, calibration_state, p_low/p_mid/p_high, n_eff, n_eff_oos, b, reason_chain` |

### 3.9 advice

| 方法 路径 | 用途 | 关键字段 |
| --- | --- | --- |
| `GET /advice` | 今日建议列表 | 每条：`action, current_weight, target_weight_range, triggers, invalidations, valid_until, evidence_ids, degradation_reasons` |
| `GET /advice/:id` | 建议详情 | 含 `reason_chain`（凯利拒绝/折扣） |
| `GET /advice/:id/evaluation` | 建议评价 | 按动作类型口径（见 [4_ANALYTICS_AND_RISK.md](./4_ANALYTICS_AND_RISK.md)） |
| `POST /advice/:id/acknowledge` | 用户确认已读/已记录行动 | 写审计 |

### 3.10 assistant（盘中/通用问询）

| 方法 路径 | 用途 | 关键字段 / SLA |
| --- | --- | --- |
| `POST /assistant/intraday` | 盘中快速问询 | P50≤5s P95≤12s; 见技术架构 §13.3 示例 |
| `POST /assistant/query` | 通用问询 | 同样返回条件式结构; 数据不合格返回 PAUSE_ADVICE |

约定：盘中/通用响应**必须**含 `market_time, freshness, valid_until, triggers, invalidations, evidence_ids, degradation_reasons`；数据不合格 → `action=PAUSE_ADVICE` 且 `target_weight_range` 与交易数量为空。

### 3.11 reports

| 方法 路径 | 用途 | 关键字段 |
| --- | --- | --- |
| `GET /reports` | 列表（按 `type,business_date`） | 游标 |
| `GET /reports/:id` | 元数据 + 结构化 JSON | `status, version, sources_count` |
| `GET /reports/:id/render?format=md\|html` | 渲染产物 | |
| `POST /reports/generate` | 手动触发 | 需 Idempotency-Key; 返回 `job_run_id` |
| `GET /reports/:id/export?format=csv\|pdf` | 导出 | CSV 注入转义（见 [8_SECURITY_AND_DEPLOYMENT.md](./8_SECURITY_AND_DEPLOYMENT.md)） |

### 3.12 research

| 方法 路径 | 用途 | 关键字段 |
| --- | --- | --- |
| `POST /research` | 创建研究任务 | req: `scope(company\|industry), target, depth`; 返回 `job_run_id`; 需 Idempotency-Key |
| `GET /research/jobs/:id` | 任务详情 + 进度 | |
| `GET /research/reports/:id` | 研究报告结构化内容 | 含引用、事实/计算/判断标签 |

### 3.13 jobs

| 方法 路径 | 用途 |
| --- | --- |
| `GET /jobs/:id` | 状态/进度/错误 |
| `POST /jobs/:id/retry` | 手动重试（受 max_attempts 约束） |
| `POST /jobs/:id/cancel` | 取消 |

### 3.14 settings

`GET/PATCH` 于：`/settings/risk` `/settings/data-sources` `/settings/models` `/settings/notifications` `/settings/schedule` `/settings/security` `/settings/retention`。敏感值只存环境变量引用，API 返回掩码。修改写审计。

### 3.15 backups

| 方法 路径 | 用途 |
| --- | --- |
| `POST /backups` | 触发手动备份（需 Idempotency-Key） |
| `GET /backups` | 备份列表 + 校验状态 |
| `POST /backups/restore/prepare` | 恢复准备（校验版本/哈希） |
| `POST /backups/restore/confirm` | 二次确认执行恢复 |

### 3.16 events (SSE)

| 方法 路径 | 用途 |
| --- | --- |
| `GET /events` | 认证 SSE 流；事件仅 `job_id,status,progress`，不发完整持仓 |

## 4. 分页与游标规范

- 请求：`?limit=50&cursor=<opaque>`；`limit` 上限由模块定（如 200）。
- 响应：`{ items, next_cursor, has_more }`；`next_cursor=null` 表示到底。
- 游标为基础排序键的 base64 编码（如 `(business_date, id)`）；不暴露 offset。
- 列表默认按 `business_date DESC, id DESC`，端点表可覆盖。

## 5. 错误码（RFC 9457 Problem Details）

响应体：

```json
{
  "type": "https://wws-adviser/errors/data-stale",
  "title": "数据过期",
  "status": 409,
  "detail": "行情 market_time 已超 90s 阈值",
  "instance": "/api/v1/assistant/intraday",
  "request_id": "01J...",
  "code": "DATA_STALE",
  "reasons": ["market_time_age>threshold"]
}
```

`code` 供前端分支，`type` URI 文档化。统一错误码枚举（持续扩充）：

| code | HTTP | 含义 | 典型场景 |
| --- | --- | --- | --- |
| `UNAUTHENTICATED` | 401 | 未登录 | 会话缺失/过期 |
| `REAUTH_REQUIRED` | 401 | 需重新认证 | 高风险操作 |
| `FORBIDDEN` | 403 | 无权限 | 单用户下基本不触发，预留 |
| `VALIDATION_ERROR` | 422 | 请求校验失败 | 字段/格式/范围 |
| `MISSING_IDEMPOTENCY_KEY` | 400 | 缺幂等键 | 导入/长任务创建 |
| `IDEMPOTENCY_CONFLICT` | 409 | 同键不同体 | Idempotency-Key 复用 |
| `NOT_FOUND` | 404 | 资源不存在 | |
| `CONFLICT` | 409 | 业务冲突 | 重复导入、状态非法转换 |
| `DATA_STALE` | 409 | 数据过期 | 行情超阈值 → PAUSE_ADVICE |
| `DATA_MISSING` | 409 | 关键数据缺失 | |
| `DATA_CONFLICT` | 409 | 多源冲突未消解 | 见数据质量 |
| `LEDGER_UNRECONCILED` | 409 | 账本未对账 | 禁精确调仓 |
| `MARKET_ABNORMAL` | 409 | 市场状态异常 | |
| `CALIBRATION_REJECTED` | 409 | 凯利资格被拒 | 见 §4 文档 |
| `MODEL_UNAVAILABLE` | 503 | 模型不可用 | 降级而非 5xx 崩溃 |
| `RATE_LIMITED` | 429 | 限流 | 登录限速等 |
| `DB_NOT_WRITABLE` | 503 | 数据库不可写 | 禁提交交易 |
| ` INTERNAL_ERROR` | 500 | 兜底 | 关联 request_id |

> 降级类（`DATA_STALE` 等）**优先返回 200 + `action=PAUSE_ADVICE` 的业务体**，仅当无法形成业务体时才用 Problem Details。盘中建议按技术架构 §13.3：数据不合格仍 200 返回 PAUSE_ADVICE 结构，便于前端统一渲染行动卡。

## 6. 认证与 CSRF

- 会话 Cookie：`HttpOnly; Secure; SameSite=Lax`（同源 PWA）；研究/敏感操作可提 `Strict`。
- 写操作除 SameSite 外，叠加 CSRF Token（`X-CSRF-Token` 双提交）或 Origin 校验。
- 高风险（恢复、删除、密码改）要求 `REAUTH_REQUIRED`（近期认证或二次确认）。
- 详见 [8_SECURITY_AND_DEPLOYMENT.md](./8_SECURITY_AND_DEPLOYMENT.md)。

## 7. OpenAPI 生成与前端类型流

1. FastAPI router 全部带 `response_model`、`tags`、`operation_id`（前端函数名依据）。
2. CI 运行 `openapi.json` 导出并 diff：路径/字段变更须在 PR 说明。
3. `frontend` 用 `openapi-typescript` 生成 `src/api/generated/types.ts`，`openapi-fetch` 生成客户端。
4. 前端**禁止**手写覆盖 generated；如需包装写 `src/api/wrapped/`。
5. 十进制字段 generated 为 `string`，前端不做数值运算。

## 8. 版本与兼容

- `/api/v1` 前缀；破坏性变更升 `/v2` 并保留 v1 一段过渡期（个人单用户可短）。
- 新增可选字段不算破坏；删除/改语义/改类型算破坏，需 PR 标注与迁移说明。
- 报告 schema 与提示词模板版本随响应返回（`schema_version`, `prompt_version`）。

## 9. 已确认与运行配置项

> 2026-08-11 复核：以下事项确认沿用默认值，归入 MVP 基线。标注「运行配置」者为可配参数，初值如下，上线后按实际调整。

| 事项 | 确认值 | 性质 |
| --- | --- | --- |
| SSE 事件 schema 字段集 | `{event, job_id, status, progress, ts}` | 已确认 |
| 导入预览最大行数 | 5000，超出分批 | 已确认 |
| 限流阈值（登录） | 5 次/5 分钟/IP，进程内 + Nginx 反代双层 | 已确认 |
| OpenAPI diff 强度 | 路径+方法+响应码+必填字段 | 运行配置（CI 守门） |
