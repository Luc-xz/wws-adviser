# 5. 数据采集与质量（端口、流水线、新鲜度、多源冲突、契约测试）

> 文档版本：v1.0  
> 文档状态：开发基线  
> 更新日期：2026-07-18  
> 关联：技术架构 §8 §16 · PRD §8.2 §9.4 §9.5 · 索引：[0_DEVELOPMENT_GUIDE_INDEX.md](./0_DEVELOPMENT_GUIDE_INDEX.md)

## 1. 目的

把技术架构 §8 的采集架构与 PRD §8.2/§9.4/§9.5 落为**端口契约 + 流水线阶段 + 新鲜度/冲突规则 + 契约测试方法**。外部供应商未定时一律以端口 + 占位适配器表达，标注 `TODO(data-source-selection)`（见索引 §2）。

## 2. 端口定义（ports/，技术架构 §8.1）

端口只返回**原始对象**，标准化与质量判定由内部流水线统一执行；端口**不**带业务语义方法（如 `get_fresh_quote`）。

```python
# ports/market_data.py
class QuoteProvider(Protocol):
    async def fetch_quotes(self, instruments: list[InstrumentRef]) -> list[RawQuote]: ...

class BarProvider(Protocol):
    async def fetch_daily_bars(self, instrument: InstrumentRef, start: date, end: date) -> RawDataset: ...

class NAVProvider(Protocol):
    async def fetch_nav(self, instrument: InstrumentRef, as_of: date) -> RawNAV: ...

# ports/document_source.py
class DocumentProvider(Protocol):
    async def discover(self, scope: DocumentScope, since: datetime) -> list[DocumentRef]: ...
    async def download(self, ref: DocumentRef) -> RawDocument: ...
```

约定：

- `RawQuote / RawDataset / RawNAV / RawDocument` 是原始 DTO，字段含 `source`、`source_url`、`market_time`、`fetched_at`、`received_at`、`source_delay_class`、原始字段映射；**不**含已判定 `quality_status`。
- 适配器实现放 `infrastructure/market_data/<source>_adapter.py`、`infrastructure/documents/<source>_adapter.py`，构造仅在 `api/dependencies.py`（见 [1_REPO_STRUCTURE.md](./1_REPO_STRUCTURE.md) §5）。
- 占位适配器（`stub_*`）返回合成数据 + `source="stub"`，用于 Phase 0/1 开发与契约测试，禁用于生产。

## 3. 采集流水线（技术架构 §8.2）

```text
plan/request            # 来自调度或盘中请求
  → rate_limit & circuit_breaker check
  → fetch raw response
  → persist raw response summary / file（按内容寻址，见 [2_DATA_MODEL_AND_STORAGE.md](./2_DATA_MODEL_AND_STORAGE.md) §9）
  → parse to unified schema
  → field & market-rule validation
  → dedup & multi-source comparison
  → assign quality_status
  → atomic publish（DB 行 + Parquet/文件）
  → update data health（runtime_stats / market data quality 状态）
```

阶段契约：

| 阶段 | 输入 | 输出 | 落库 |
| --- | --- | --- | --- |
| parse | Raw* | 统一 schema 对象 | 不落库（内存） |
| validate | 统一对象 | 校验结果 + 违规字段 | 违规写 `quality_status=PARSE_FAILED` 或 `MISSING` |
| dedup/compare | 校验通过对象 | 去重/比对记录 | 写 `market_records`/`nav_records` 原子行；冲突写 `data_conflicts` |
| publish | 比对结果 | 已发布对象 | Parquet 原子写（`part.parquet.tmp`→`rename`，见 [2_DATA_MODEL_AND_STORAGE.md](./2_DATA_MODEL_AND_STORAGE.md) §8） |
| health | 发布状态 | 质量摘要 | 写 `runtime_stats` |

## 4. 网络与重试策略（技术架构 §8.3）

- 每供应商独立连接池、并发上限、速率限制、超时（命名常量在 `config` 按源配置）。
- 仅对幂等 GET 自动重试：指数退避 + 抖动，上限由 `config.<source>.max_retries`。
- 不重试：认证失败、解析结构突变（schema 不匹配）、明确 429 限流（进入熔断）。
- 日志记录供应商错误类型；**不**记录 Token/Cookie/完整敏感响应头。
- 连续失败达阈值 → 短期熔断，状态页显示降级；熔断窗口由 `config.<source>.circuit_window_s`。
- User-Agent、调用频率、缓存策略遵循供应商规则（适配器内声明，不跨源共用）。

## 5. 新鲜度判定（技术架构 §8.4，PRD §9.4）

freshness 是**服务端**生成的状态，前端只展示，模型不得修改。所需字段齐全（[2_DATA_MODEL_AND_STORAGE.md](./2_DATA_MODEL_AND_STORAGE.md) §6.4）：

| 字段 | 含义 |
| --- | --- |
| `market_time` | 行情代表的市场时间 |
| `fetched_at` | 系统抓取完成时间 |
| `received_at` | 系统收到响应时间 |
| `source_delay_class` | 实时 / 延时 / 日终 |
| `market_state` | 当前市场状态（来自交易日历 + 实时状态） |

交易时段判定（伪代码）：

```text
age = now_asia_shanghai - market_time
fresh = age <= INTRADAY_FRESHNESS_THRESHOLD        # 默认 90s（命名常量）
      AND required_fields_present(quote)
      AND source_status_healthy(source)
      AND local_clock_healthy()                    # 与 NTP 偏差在阈值内
```

阈值表（PRD §9.4，命名常量，范围可配，§9）：

| 数据 | 阈值常量 | 默认 | 超时处理 |
| --- | --- | --- | --- |
| 盘中行情 | `INTRADAY_FRESHNESS_THRESHOLD` | 90 秒 | `quality_status=DELAYED` → 禁即时交易数量 → PAUSE_ADVICE |
| 日线 | `DAILY_COMPLETE` | 最近已结束交易日完整 | 报告标 `不完整` 并降低建议等级 |
| 公告 | `ANNOUNCE_COVERAGE` | 开市前任务覆盖至报告截止 | 显示检索截止时间 |
| 新闻 | —— | 展示发布时间与抓取时间 | 不以陈旧新闻解释即时波动 |
| 基金净值 | `NAV_PUBLISHED` | 最新官方披露净值 | 明确净值日期，不标实时；未披露生成 `PARTIAL` 报告 |
| 财报 | `REPORT_PERIOD` | 最新正式披露期 | 不用预告替代正式值 |

时钟健康：

- 启动与定时任务校验本机时钟与可信 NTP/数据源时间戳偏差；超 `CLOCK_SKEW_THRESHOLD` 视为不健康，freshness 强制为非 fresh。
- 盘中非交易时段（午休/集合竞价/收盘后）的“当前价”显示最后成交时间或净值日期，不假装实时（PRD §9.1）。

## 6. 多源冲突消解（技术架构 §8.5，PRD §9.5）

可信等级（PRD §9.5）：`L1 交易所/监管/官方披露 > L2 授权行情/专业供应商 > L3 可信新闻/协会 > L4 聚合转载 > L5 社交媒体`。

字段级比对规则：

1. **保留每个来源原始值，不覆盖删除**（`market_records.UNIQUE(instrument_id, business_date, source, adjustment_type)`）。
2. 对价格、交易状态、公司行动、正式财务数据执行**字段级比对**。
3. 误差在 `FIELD_TOLERANCE[field]` 内 → 选高等级源，记录 `comparison=pass`；不污染。
4. 超误差 → 写 `data_conflicts`（[2_DATA_MODEL_AND_STORAGE.md](./2_DATA_MODEL_AND_STORAGE.md) §6.7），相关指标标记 `quality_status=CONFLICT`，advice 降级。
5. 同等级冲突且无法消解 → 展示差异或暂停相关结论（PRD §9.5），advice 不给即时交易数量。

`data_conflicts` 处理：

| `status` | 含义 | 谁可解 |
| --- | --- | --- |
| `OPEN` | 待消解 | 自动规则或人工（设置页 SET-02） |
| `RESOLVED` | 已选源并记录原因 | `resolved_by`/`resolved_at` 落库 |
| `UNRESOLVED` | 无法消解，持续降级 | advice 持续 PAUSE 直到数据恢复 |

## 7. 数据质量状态机（PRD §8.2 FR-DATA-006）

`quality_status ∈ {OK, DELAYED, MISSING, CONFLICT, PARSE_FAILED, SOURCE_UNAVAILABLE}`。

| 状态 | 触发 | 对 advice 的影响 |
| --- | --- | --- |
| `OK` | fresh + 字段齐 + 无冲突 | 正常 |
| `DELAYED` | `age > threshold` | `data_stale` → PAUSE_ADVICE |
| `MISSING` | 关键字段缺失或未到 | `data_missing` → PAUSE_ADVICE |
| `CONFLICT` | 多源超误差 | `data_conflict` → PAUSE_ADVICE |
| `PARSE_FAILED` | schema 不匹配 | `data_missing` → PAUSE_ADVICE |
| `SOURCE_UNAVAILABLE` | 熔断/认证失败 | `data_missing`（源级）→ PAUSE_ADVICE |

数据质量状态页 API：`GET /market/quality`（[3_API_CONTRACT.md](./3_API_CONTRACT.md) §3.6）、UI `DATA-01` 数据状态中心（[7_FRONTEND_AND_PWA.md](./7_FRONTEND_AND_PWA.md)）。

## 8. 交易日历与市场状态（PRD §8.2 FR-DATA-001，§9.1）

- `trading_calendar`（[2_DATA_MODEL_AND_STORAGE.md](./2_DATA_MODEL_AND_STORAGE.md) §6.4）按 `Asia/Shanghai` 维护，每个交易日含 `is_trading_day` + `session_schedule_json`（集合竞价/连续竞价/午休/收盘集合竞价/临时休市）。
- 市场状态来源：交易日历 + 数据源实时状态（停牌/临停）。`GET /market/state` 返回 `phase, is_trading_day, next_event_at`。
- 时钟：业务时间统一 `Asia/Shanghai` 存储/展示；DB 同时存 UTC ISO 8601（[2_DATA_MODEL_AND_STORAGE.md](./2_DATA_MODEL_AND_STORAGE.md) §4）。
- 非交易日不自动生成开市前/收市后报告，除非用户手动触发（PRD §8.4 FR-REP-003）。
- 临时休市/官方调整通过日历版本更新写入，记 `calendar_version`（进 `analysis_snapshot`，见 [4_ANALYTICS_AND_RISK.md](./4_ANALYTICS_AND_RISK.md) §2 快照引用）。

## 9. 契约测试方法（对应技术架构 §18.1 数据源契约测试）

外部供应商未定，契约测试是**绑定端口而非具体供应商**的手段：

1. **cassette 录制**：对每个端口方法，录制脱敏固定响应（移除 Cookie/Token/个人标识/受限正文），存 `tests/contract/cassettes/<port>/<scenario>.json`。
2. **解析器测试**：用 cassette 喂适配器的 parse 阶段，断言统一 schema 字段、单位、scale（[2_DATA_MODEL_AND_STORAGE.md](./2_DATA_MODEL_AND_STORAGE.md) §5）。
3. **schema 突变测试**：故意改动 cassette（删字段/改类型/越界值），断言 parse → `quality_status=PARSE_FAILED`，不抛不透明异常。
4. **新鲜度测试**：冻结 `Asia/Shanghai` 时钟，构造不同 `market_time` 与 `market_state`，断言 `fresh` 判定与超时降级路径。
5. **冲突测试**：构造两源同字段不同值，断言 `data_conflicts` 写入与 advice 降级（`data_conflict`）。
6. **占位适配器测试**：`stub_*` 返回的合成数据须满足统一 schema，便于 Phase 0/1 上下游联调。

> 契约测试在选型确定后**只换 cassette 与适配器实现**，端口与流水线不变——这是端口抽象的回报。

## 10. 文档与行情的写入边界

- 行情日线/净值主存 Parquet，SQLite 存最新索引 + 元数据（路由查询），见 [2_DATA_MODEL_AND_STORAGE.md](./2_DATA_MODEL_AND_STORAGE.md) §6.4 §8。
- 文档原文按 `content_sha256` 内容寻址（[2_DATA_MODEL_AND_STORAGE.md](./2_DATA_MODEL_AND_STORAGE.md) §9）；`documents_fts` 为外部内容表，可由原文 `REBUILD`。
- 新闻正文可按容量/授权清理，**元数据与引用哈希必须保留**（evidence 可定位，[2_DATA_MODEL_AND_STORAGE.md](./2_DATA_MODEL_AND_STORAGE.md) §12）。

## 11. 待确认项

| 事项 | 当前默认 | 备注 |
| --- | --- | --- |
| 数据源供应商（行情/公告/新闻） | 未定，端口 + 占位适配器 | `TODO(data-source-selection)`，《数据源选型与质量规范》 |
| 盘中新鲜度阈值 | 90 秒 | `INTRADAY_FRESHNESS_THRESHOLD` 可配 |
| 时钟偏差阈值 | `CLOCK_SKEW_THRESHOLD` TODO | 留运行配置 |
| 字段级冲突容差表 | `FIELD_TOLERANCE[field]` TODO | 按字段（价格/状态/公司行动/财务）分别定 |
| 熔断窗口/连续失败阈值 | 按 `<source>` 配置 | 选型后填充 |
| 日线/净值 SQLite vs Parquet 分布 | SQLite 索引+元数据，Parquet 全量 | 见 [2_DATA_MODEL_AND_STORAGE.md](./2_DATA_MODEL_AND_STORAGE.md) §13 |
