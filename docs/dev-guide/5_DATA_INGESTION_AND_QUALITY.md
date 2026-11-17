# 5. 数据采集与质量（端口、流水线、新鲜度、多源冲突、契约测试）

> 文档版本：v1.2  
> 文档状态：开发基线  
> 更新日期：2026-11-16（v1.2 增补 §13 市场环境采集；v1.1 2026-11-13 §12 采集可观测性；v1.0 2026-07-18）  
> 关联：技术架构 §8 §16 · PRD §8.2 §9.4 §9.5 · [ADR-0014](../adr/0014-market-environment-data-domain.md) · 索引：[0_DEVELOPMENT_GUIDE_INDEX.md](./0_DEVELOPMENT_GUIDE_INDEX.md)

## 1. 目的

把技术架构 §8 的采集架构与 PRD §8.2/§9.4/§9.5 落为**端口契约 + 流水线阶段 + 新鲜度/冲突规则 + 契约测试方法**。MVP 数据源已确认为 **AKShare**（§11.2），端口契约设计保持供应商无关，便于后续升级到 Tushare 等付费源（见索引 §2）。

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
  → update data health（source_health + ingest_items，§12）
```

阶段契约：

| 阶段 | 输入 | 输出 | 落库 |
| --- | --- | --- | --- |
| parse | Raw* | 统一 schema 对象 | 不落库（内存） |
| validate | 统一对象 | 校验结果 + 违规字段 | 违规写 `quality_status=PARSE_FAILED` 或 `MISSING` |
| dedup/compare | 校验通过对象 | 去重/比对记录 | 写 `market_records`/`nav_records` 原子行；冲突写 `data_conflicts` |
| publish | 比对结果 | 已发布对象 | Parquet 原子写（`part.parquet.tmp`→`rename`，见 [2_DATA_MODEL_AND_STORAGE.md](./2_DATA_MODEL_AND_STORAGE.md) §8） |
| health | 发布状态 | 质量摘要 | 写 `source_health`（类别级 upsert）+ `ingest_items`（条目明细），见 §12 |

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
| 盘中行情 | `INTRADAY_FRESHNESS_THRESHOLD` | 180 秒 | `quality_status=DELAYED` → 禁即时交易数量 → PAUSE_ADVICE |
| 日线 | `DAILY_COMPLETE` | 最近已结束交易日完整 | 报告标 `不完整` 并降低建议等级 |
| 公告 | `ANNOUNCE_COVERAGE` | 开市前任务覆盖至报告截止 | 显示检索截止时间 |
| 新闻 | —— | 展示发布时间与抓取时间 | 不以陈旧新闻解释即时波动 |
| ETF 净值/IIV | `NAV_PUBLISHED` | 最新官方披露净值 | 明确净值日期，不标实时；未发布生成 `PARTIAL` 报告 |
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

契约测试是**绑定端口而非具体供应商**的手段（即便 MVP 已定 AKShare，升级到 Tushare 时端口契约测试仍是回归保障）：

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

## 11. 已确认、运行配置与待确认项

### 11.1 已确认 / 运行配置（2026-08-11 复核）

| 事项 | 确认值/策略 | 性质 |
| --- | --- | --- |
| 盘中新鲜度阈值 | **180 秒** | 已确认（`INTRADAY_FRESHNESS_THRESHOLD` 可配） |
| 时钟偏差阈值 | `CLOCK_SKEW_THRESHOLD`，运行配置 | `TODO(clock-skew)`，初值待运行观测 |
| 字段级冲突容差表 | `FIELD_TOLERANCE[field]`，按字段分类运行配置 | `TODO(field-tolerance)`，选型后按字段（价格/状态/公司行动/财务）分别定 |
| 熔断窗口/连续失败阈值 | 按 `<source>` 运行配置 | 选型后填充 |
| 源健康降级阈值 | `source_health_degraded_after`（连续失败 ≥ 此值 → degraded），默认 2 | 运行配置（§12） |
| 源健康不可用阈值 | `source_health_unavailable_after`（连续失败 ≥ 此值 → unavailable），默认 5 | 运行配置（§12） |
| 采集条目保留 | `ingest_item_retention_days`，默认 90 天（data_maintenance 收尾清理） | 运行配置（§12） |
| 日线/净值 SQLite vs Parquet 分布 | SQLite 索引+元数据，Parquet 全量 | 运行配置，实现时按查询性能定，留 ADR（[2](./2_DATA_MODEL_AND_STORAGE.md) §13） |

> 标的范围已确认仅 A 股 + 场内 ETF（PRD §20），无需覆盖场外公募基金净值 T+1 披露源；Instruments 端口与占位适配器对应简化。

### 11.2 数据源供应商（已确认 2026-08-12）

**MVP 数据源：AKShare（免费开源）**，`TODO(data-source-selection)` 关闭。

| 端口 | MVP 实现 | 升级路径 |
| --- | --- | --- |
| QuoteProvider（实时行情） | AKShare 实时接口（`stock_zh_a_spot_em` 等，~500ms） | Tushare `realtime_quote`（500元/年=5000分，500次/分） |
| BarProvider（历史日线） | AKShare 历史日线 | Tushare 日线（**免费**）+ Baostock 双备份 |
| DocumentProvider（公告/新闻/财报） | AKShare 公告/新闻/财务爬取接口 | Tushare `fina_indicator`+`anns`+`news`（部分需单独授权） |

**实现约束与风险**：
- **合规**：AKShare 数据来自第三方财经网站爬取，定位「研究学习工具」，商用需另行获取授权。MVP 个人使用可接受，对外服务前须升级到有授权的源（Tushare/米筐）。
- **稳定性**：非交易所直连，偶发接口失效；务必**本地缓存 + 失败降级**（源不可用时报告标注 `PARTIAL`，见技术架构 §11.4）。
- **限频**：底层源（新浪/东财）会反爬，高频调用存在 IP 封锁风险；建议控制调用间隔 + 国内 VPS 部署（数据源服务器在国内）。
- **升级触发条件**：稳定性不满足 SLA（开市前报告 09:00 前完成）/ 对外服务 / 需要分钟线或更全公告数据时，升级到 Tushare Pro（200–500 元/年起，日线免费）。
- **端口设计不变**：升级仅替换适配器实现，端口契约与内部流水线不变（§2）。

## 12. 采集可观测性（采集监控面板，v1.1 2026-11-13 增补）

> 背景：技术架构 §16.3 规划的「SQLite 轻量运行统计」一直未落地；DATA-01 只有结果态
> （质量/冲突/审计），无过程态。本节定义采集运行的数据面：
> **批次（job_runs）→ 条目（ingest_items）→ 落库数据（market_records/documents）** 三级下钻。
> UI 落点：DATA-01「采集运行」分区（UI 规范 §10.5 增补）+ SET-08 汇总卡。

### 12.1 数据模型

**`source_health`（源健康，按数据类别 upsert）**——§3 流水线 health 阶段的落库实现：

| 字段 | 说明 |
| --- | --- |
| `category` PK | `quote / bar / nav / calendar / document / news`（类别级，非物理源级；市场环境域新增三类别见 §13.3） |
| `last_success_at / last_failure_at` | 最近成功/失败时间 |
| `consecutive_failures` | 连续失败计数（成功清零） |
| `last_error_code / last_error_message` | 最近错误（异常类型名 + 截断消息） |
| `updated_at` | — |

派生状态（读取侧计算，不落库）：`ok`（连败=0）/ `degraded`（1 ≤ 连败 < 阈值）/
`unavailable`（连败 ≥ 阈值）/ `no_data`（无行）。阈值见 §11.1。
物理源级「最近成功」从落库记录推导（`market_records`/`documents` 的 `source + MAX(fetched_at)`）；
适配器内主备切换过程不上浮（留结构化日志）；v1 不做真实熔断器。

**`ingest_items`（采集条目明细，append-only）**——回答「这一批对每个对象采了什么、成没成、为什么」：

| 字段 | 说明 |
| --- | --- |
| `run_id` | 关联 `job_runs.id`（FK，ondelete CASCADE）；无运行上下文的服务调用可空 |
| `category` | 同 `source_health` |
| `action` | `ingested / updated / skipped / synced / no_data / failed` |
| `status` | `OK / PARTIAL / SKIPPED / FAILED`（面板徽标用） |
| `target_ref` | `instrument:{id}` / `document:{id}` / `calendar:CN` |
| `display_name` | 写入时去规范化（标的+日期区间 / 公告标题），列表零 join 直出 |
| `rows_written / source / duration_ms` | 采到多少行、最终源、单条目耗时 |
| `error_code / error_message` | 失败原因 |
| `data_ref` | 指向落库数据的引用（`market:{instrument_id}:{from}-{to}` / `doc:{id}`），前端凭它调既有读端点 |
| `created_at` | — |

不复制 payload：K 线/公告正文永远单源在 `market_records`/`documents`，无双写一致性问题。
保留策略见 §11.1（`ingest_item_retention_days`，data_maintenance 收尾清理）。

### 12.2 RunContext 与手动补采 job 化

- `ingest_*` 服务函数增加可选 `run_id` 参数（RunContext）：调度路径由执行器传 `job.id`，
  条目随批次落库；失败记录先 `db.rollback()` 再写 `source_health`（避免把半程未审计数据连带提交）。
- 健康写入点在 service 层（modules），不进 infrastructure 适配器（四层依赖方向，
  [1_REPO_STRUCTURE.md](./1_REPO_STRUCTURE.md) §4）。
- 手动 `POST /market/{bars,nav}/{id}/refresh`、`POST /documents/refresh` 先建
  `job_type=ingest_manual` 的 job_runs 行（直接 RUNNING、`lease_until=NULL` 不入执行器
  领取范围、`attempt=1/max_attempts=1`），同步执行后 complete/fail——手动补采与定时采集
  共用同一套批次视角。执行中途崩溃留下的 RUNNING 行视为「卡住」如实展示，不自动改写。

### 12.3 查询面（API 见 [3_API_CONTRACT.md](./3_API_CONTRACT.md) §3.13/§3.17）

- 批次列表 + 聚合：`GET /jobs`、`GET /jobs/stats`（成功率/耗时/按类型连续失败，SET-08 共用）。
- 批次下钻：`GET /jobs/{id}/items`；跨批次检索：`GET /collections/items`。
- 源健康 + 数据覆盖：`GET /collections/health`（六类别健康 + 各数据集最新业务日期/近 7 天行数；
  `news` 恒为 `no_data` + `configured=false`——FR-DATA-005 仅 stub 实现，面板如实暴露缺口）。
- `job_runs.result_ref`（`bars://3/1` 等）保留为兼容摘要；明细以 `ingest_items` 为准。

### 12.4 边界（v1 不做）

- 历史批次（`ingest_items` 上线前）只有聚合计数，明细区空态「早于明细记录功能上线」，不回填。
- 不做 per-fetch 网络日志表、Prometheus（技术架构 §16.3 明言不部署）、真实熔断状态机。
- 任务级自动重试（`RETRY_WAIT`/`max_attempts` 实际生效）与采集失败通知（技术架构 §16.4）
  为独立工作项，不随本节交付。

## 13. 市场环境采集（指数 / 板块资金流 / 外围市场，v1.2 2026-11-16 增补）

> 决策依据：[ADR-0014](../adr/0014-market-environment-data-domain.md)。市场环境是**研究
> 上下文数据域**（整体市场环境研究：A 股大盘指数、活跃板块、板块主力净流入/流出、两市
> 成交量、美股指数（含盘前/盘后参考）、日韩港股指数），独立于投资标的域——不进
> instruments/portfolio，不参与凯利/建议计算，其质量状态不触发 PAUSE_ADVICE。

### 13.1 端口定义（ports/market_env.py）

```python
class IndexQuoteProvider(Protocol):
    async def fetch_index_quotes(self, refs: list[IndexRef]) -> list[RawIndexQuote]: ...
    # RawIndexQuote 含 pre_market_price/change、post_market_price/change（美股专用，
    # A股/亚市指数置空）；amount/volume 支撑两市成交量汇总

class IndexBarProvider(Protocol):
    async def fetch_index_bars(self, ref: IndexRef, start: date, end: date) -> RawDataset: ...

class SectorFlowProvider(Protocol):
    async def fetch_sector_flows(self, kind: SectorKind) -> list[RawSectorFlow]: ...
    # RawSectorFlow: board_code/name/kind/change_pct/turnover/net_main_inflow/
    # leader —— 板块涨幅榜（活跃板块）与主力净流入/流出榜同源覆盖
```

适配器落 `infrastructure/market_env/`：`tencent_index_quote.py`（主源，批量）、
`sina_index_quote.py`（全球指数兜底 + 美股期货）、`eastmoney_index_bar.py`（指数日 K）、
`eastmoney_sector_flow.py`（行业 `m:90+t:2` + 概念 `m:90+t:3` 板榜，2 请求/轮）。
源选型沿用 config 模式：`market_env_index_source` / `market_env_sector_source`
（`stub` 默认 | 直连实现）。端点均经 niuone 项目生产验证（ADR-0014 上下文）。

### 13.2 数据源与降级链

| 端口 | 主源 | 兜底 | 说明 |
| --- | --- | --- | --- |
| 指数快照（A股+美股+亚市） | 腾讯 `qt.gtimg.cn` 批量（1 请求全代码） | 新浪 `hq.sinajs.cn`（需固定 Referer） | 兜底仅主源失败时启用；v1 不做双源并发比对；腾讯行内**字段位序不稳定**（同一响应 86/88 字段并存），时间与成交额按模式定位（见 `tencent_index_quote.py`） |
| 指数日 K | 东财 `push2his` kline（多域名轮换） | 腾讯 `ifzq.gtimg.cn` | 历史一次性回补 2–3 年 |
| 板块资金流 | 东财 `push2delay clist`（延时源，如实标 `DELAYED`） | —— | 行业+概念各取主力净额**升降序两页**（4 请求/轮，双向榜单全覆盖）；板块代码漂移由 `sector_boards` upsert 吸收 |
| 美股盘前参考 | 新浪全球期货（ES/NQ 代理）+ 东财/腾讯美股盘前字段 | —— | 见 §13.6 开放点 |

反爬基线（同 §4）：每源固定 UA/Referer、限频、有界重试；东财多域名轮换
（push2 / push2delay / 82.push2 + http 降级）为适配器公共模式。

### 13.3 类别与可观测性

- `Category` 枚举新增：`index_quote` / `index_bar` / `sector_flow`；`source_health`
  与 `ingest_items` 直接复用（§12），DATA-01 采集面板类别驱动自动覆盖。
- 采集条目 `target_ref` 口径：`index:{code}`（单指数）/ `index:batch`（整批快照）/
  `sector:{kind}`；`data_ref`：`index-quotes:{date}` / `index-bars:{code}:{from}-{to}` /
  `sector-flows:{kind}:{date}`。
- `quality_status` 六态照用（§7）。

### 13.4 新鲜度阈值（研究级，宽于盘中行情）

| 数据 | 阈值常量 | 默认 | 说明 |
| --- | --- | --- | --- |
| 指数快照 | `INDEX_QUOTE_FRESHNESS_THRESHOLD` | 900 秒 | 盘中 5 分钟采样，容一轮失败 |
| 板块资金流 | `SECTOR_FLOW_FRESHNESS_THRESHOLD` | 3600 秒 | 盘中 30 分钟采样 |
| 指数日 K | `DAILY_COMPLETE`（同 §5 表） | 最近已结束交易日 | — |
| 外围指数 | 按当地交易日历判定 market_time | — | 美股时段随冬/夏令时漂移，用 TZ 数据库算，不硬编码时差 |

### 13.5 调度（APScheduler 只入队不变）

| JobType | cron | 内容 |
| --- | --- | --- |
| `market_env_intraday` | 交易日 09:15–15:00 每 5 分钟 | 指数快照 + 板块资金流（执行器查 `trading_calendar` 过滤非交易日） |
| `market_env_eod` | 15:25 | 指数日 K + 板块终态快照 |
| `overseas_morning` | 08:10 | 隔夜美股（含盘前/盘后）+ 亚市指数 + 美股期货 |

日请求量约 70–100 次（研究型频率，防风控优先，见 ADR-0014 备选方案 D 的放弃理由）。

### 13.6 边界与开放点（v1 不做 / 待实测）

- **批次 A 线上实录事实（2026-11-16，开发机）**：腾讯 `qt.gtimg.cn` 与新浪
  `hq.sinajs.cn` 直连可实录（cassette 为真实响应）；东财 `push2his` 可用但**风控为
  分钟级滚动**（同会话先成功后被重置）；`push2*/clist` 在开发机网络全域名连接层重置
  （HTTP 000，含 http/数字镜像）——板块资金流适配器按 niuone 生产格式钉住，
  **VPS 线上验证为遗留项**。
- 美股「盘前/盘后」字段口径：实现期先录 cassette 实测东财/腾讯美股响应字段（盘前价/
  盘前涨跌幅/盘后价），确认后再定 `RawIndexQuote` 字段映射；呈现按「指数期货（盘前
  参考）+ 指数收盘与盘后」双轨，不承诺个股级盘前盘后。
- **双轨实测结论（2026-11-16，批次 B）**：① 东财 push2 美股指数 `f276/f277`（盘前/
  盘后位）对指数恒为 `"-"`——指数无盘前盘后撮合，字段保留但不采信；② 新浪 `hf_ES/
  hf_NQ/hf_YM` 美股指数期货可用（cassette `sina_futures_ok.json` 实录，涨跌幅以
  最新/昨结自算）——**盘前参考以期货为准**，注册表新增 `futures_us` 组三项；
  「盘后」= 收盘后指数快照本身（overseas_morning 任务隔夜采集）。
- 不做：板块成分股映射、指数分钟线量能 profile（晨报需要「量能对比昨日」时作端口扩展）、
  双源并发比对写 `data_conflicts`（留扩展）。
- 契约测试沿用 §9 方法（cassette 三场景：happy / schema 突变→`PARSE_FAILED` / 降级路径）。

