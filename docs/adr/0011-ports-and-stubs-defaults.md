# ADR-0011：Ports / Stub 适配器实现默认决策

> 状态：Accepted
> 日期：2026-08-12
> 关联：[5_DATA §2/§9](../dev-guide/5_DATA_INGESTION_AND_QUALITY.md) · [6_MODEL §3](../dev-guide/6_MODEL_AND_REPORT_PIPELINE.md) · [技术架构 §7.5/§8.1](../TECHNICAL_ARCHITECTURE.md) · [1_REPO §6](../dev-guide/1_REPO_STRUCTURE.md)

## 上下文

波 3 实现 5 类端口（QuoteProvider/BarProvider/NAVProvider/DocumentProvider/ModelPort/NotifierPort/ObjectStore）+ stub 适配器 + 契约测试骨架 + stub→domain→API 闭环。文档对 4 个行情/文档端口给定签名，对 ModelPort/NotifierPort/ObjectStore 只给契约；Raw DTO 字段、InstrumentRef/DocumentRef、cassette 格式多为"实现时定"。

## 决策

| 项 | 决策 | 理由 |
|---|---|---|
| ModelPort 方法名 | `async call(request: ModelRequest) -> ModelResponse` | 文档伪代码 `model_gateway.call(...)` |
| NotifierPort | `async notify(channel, event_type, payload) -> NotificationResult`；幂等键 `payload_hash=sha256(json)` | UNIQUE(channel,event_type,payload_hash) |
| ObjectStore | `put(content,kind,ext)->rel_path` / `get` / `exists`，sha256 内容寻址 | 技术架构 §7.5 |
| Raw 数值字段 | Decimal（vendor parse 后的数值） | 金融精度 §7.3 |
| source_delay_class | StrEnum `REALTIME/DELAYED/END_OF_DAY` | "实时/延时/日终" |
| InstrumentRef | `code/market/kind` frozen dataclass，定义在 ports/market_data | A 股+ETF 足够；端口契约载体 |
| infrastructure 子目录 | `data_sources/models/notifications/storage`（技术架构 §5） | TA §5 为权威仓库骨架 |
| cassette 格式 | 自定义 JSON（`{port,scenario,recorded_at,sanitized,response}`），非 VCR | 文档明确 .json + 脱敏 |
| stub 禁生产 | 构造时 `assert_not_prod(env)` → raise RuntimeError | 5_DATA §2 |
| 闭环领域 | market_data 最小 slice（`domain.parse_quote` + `service.get_quote` + api），用 `ports.InstrumentRef` | 文档模块清单内；Phase 1 扩展 |
| 闭环证明 | `GET /api/v1/market-data/quotes/{code}` 返回 `source="stub"` | 一条闭环（10_MILESTONE 退出条件 4） |

## 备选方案

- **InstrumentRef 放 instruments/domain**：放弃（ports 需独立契约载体，避免 ports→modules 依赖倒置；Phase 1 建 instruments 模块时再定义完整 Instrument 实体）。
- **Raw 用 vendor 原始 dict**：放弃（系统 DTO 需类型安全；如需保留 vendor 原始可后续加 `raw_payload: dict` 字段）。
- **闭环用独立 demo 模块**：放弃（"demo"不在文档模块清单；market_data 是清单内模块，最小启动为 Phase 1 打基础）。

## 正负影响

**正向：**
- 端口抽象落地，Phase 1 换真实适配器（AKShare/SMTP/OpenAI-compatible）只改 `infrastructure/` + cassette，端口与流水线不变（5_DATA §9 的核心收益）。
- 闭环证明端口可工作，为 Phase 1 instruments/market_data 完整模块（表/repository/CSV 导入）打基础。

**负向 / 代价：**
- Raw 数值字段为设计（文档未列），Phase 1 接 AKShare 可能需调整字段名/类型。
- ObjectStore 只支持文档 sha 寻址；报告路径键（`data/reports/<date>/<id>/`）留 Phase 1.5。

## 迁移条件

- 接 AKShare：仅新增 `infrastructure/data_sources/akshare_*.py` + 真实 cassette，端口签名不变。
- 报告对象存储：ObjectStore 加 `put_report(date, report_id, filename)` 或独立 ReportStore。
- ModelPort 接 OpenAI-compatible：仅新增 `infrastructure/models/openai_adapter.py`，ModelPort/ModelRequest/ModelResponse 不变。
