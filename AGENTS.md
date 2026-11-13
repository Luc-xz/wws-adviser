# WWS Adviser — Agent 协作入口

本文件是所有 coding agent 会话的路由器：告诉你在哪类改动前读什么、哪些决策不可
静默推翻、收尾时必须披露什么。它不重复细节——细节在被指向的文档里。

## 0. 项目事实速览

- 单用户个人投资助手：A 股 + 场内 ETF 的持仓账本 → 晨/晚报 → 盘中建议 → 深度研究。
- 后端 `backend/`：Python 3.12 · FastAPI · SQLAlchemy 2 · Alembic · APScheduler（uv 管理）。
- 前端 `frontend/`：Vue 3.5 · TypeScript · Vite · Pinia · UnoCSS · PWA（pnpm 管理）。
- 部署：单容器 Docker + Cloudflare Tunnel，国内 VPS（ADR-0013）。
- 文档驱动开发：**上游三基线（PRD / 技术架构 / UI 规范）是唯一事实源**，
  `docs/dev-guide/` 是执行展开，`docs/adr/` 是决策快照，`docs/design-review/baseline/`
  是视觉验收基准卡。

## 1. 改动前路由

| 场景 | 必读 |
| --- | --- |
| **任何代码改动前** | [LESSONS.md](./LESSONS.md)——本仓库教训库，历史上返工过什么、规则是什么 |
| 后端模块 / 分层 | [1_REPO_STRUCTURE](docs/dev-guide/1_REPO_STRUCTURE.md)（分层与依赖方向是硬约束） |
| 改 schema / 迁移 | [2_DATA_MODEL_AND_STORAGE](docs/dev-guide/2_DATA_MODEL_AND_STORAGE.md)，先写 Alembic 迁移 + 备份兼容检查 |
| 加 / 改 API | [3_API_CONTRACT](docs/dev-guide/3_API_CONTRACT.md)，OpenAPI 是接口事实源（`make gen-api`） |
| 凯利 / 风险 / 信号 | [4_ANALYTICS_AND_RISK](docs/dev-guide/4_ANALYTICS_AND_RISK.md)，凯利是纯领域函数，模型 Gateway 无权写 `p` |
| 数据源 / 采集 | [5_DATA_INGESTION_AND_QUALITY](docs/dev-guide/5_DATA_INGESTION_AND_QUALITY.md)，先端口 + 契约 cassette 再适配器 |
| 报告 / Jobs / SSE | [6_MODEL_AND_REPORT_PIPELINE](docs/dev-guide/6_MODEL_AND_REPORT_PIPELINE.md) |
| 前端 / PWA | [7_FRONTEND_AND_PWA](docs/dev-guide/7_FRONTEND_AND_PWA.md)；**UI 改动另见 §1.1** |
| 安全 / 部署 | [8_SECURITY_AND_DEPLOYMENT](docs/dev-guide/8_SECURITY_AND_DEPLOYMENT.md) |
| 写测试 / 提 PR | [9_TEST_AND_CI](docs/dev-guide/9_TEST_AND_CI.md) + [PR 模板](.github/PULL_REQUEST_TEMPLATE.md) |
| 排期 / 批次 | [10_MILESTONE_PLAN](docs/dev-guide/10_MILESTONE_PLAN.md)（§7 上线门槛、§8 批次记录）· [11_LAUNCH_QUALITY_PLAN](docs/dev-guide/11_LAUNCH_QUALITY_PLAN.md) |
| 生产验收 | [frontend/acceptance/README.md](frontend/acceptance/README.md) + [PWA_DEVICE_CHECKLIST](deploy/PWA_DEVICE_CHECKLIST.md)（会话铸造/吊销手册在前者） |
| 偏离上游基线 | **先立 ADR 再动手**：[docs/adr/](docs/adr/README.md) |

### 1.1 UI 改动专项

- 新页面**基准卡先于代码**建卡（`docs/design-review/baseline/_TEMPLATE.md`），走查以
  「原型 PNG vs 实现截图」双图对照为凭，不以卡文本为凭（防自证闭环，见 LESSONS）。
- 数值字段必须过 `formatMoney` / `formatPercent`（ESLint `no-raw-number-interpolation`
  已强制）；行情色仅 `data-context="quote"`。
- 提 PR 按 PR 模板：入口可达性路径 + 桌面 1440 / 移动 375 / 深色三截图对照基准卡。

## 2. 决策保护——不可静默推翻

这是本仓库最重要的纪律。以下内容**不得在任何"顺手"的改动中变更**：

1. **上游三基线为准**。业务规则、风险约束、凯利定义、UI 安全规则冲突时，停下来：
   提交 ADR 说明分叉，或向用户提出，**不要私自改某一边**（0_INDEX §1/§4）。
2. **ADR 一经 Accepted 不就地修改**。要推翻：新建 ADR，旧 ADR 状态改
   `Superseded by ADR-NNNN`，保留原文（ADR README §4）。
3. **已确认决策表**（0_INDEX §7.1：标的范围、新鲜度 180s、凯利折扣、AKShare、
   OpenAI-compatible、SMTP 通知等）变更必须走 ADR，不得在代码或文档中静默改值。
4. **已披露的遗留口径不得"顺手"抹掉**。当前活口径：模型段自 2026-09-01 降级运行
   是唯一 P0 活缺陷（10 号 §8.6）；§6-Q1 信号覆盖决策挂起中。它们的状态变更
   （修复/决策落定）必须更新 10/11 号文档对应条目并在提交说明中写明，不得只改代码。

## 3. 验证与诚实披露

门禁命令（对应 CI 与 PR 模板）：

```
make lint          # ruff + mypy
make test          # 单元 + 集成
make test-e2e      # Playwright 六链路（涉及 UI 交互时本地门禁必跑）
make migrate-check # 改 schema 后：空库可建
cd frontend && pnpm lint && pnpm test && pnpm build
```

**提交与收尾三问**（写进提交 body 或任务汇报，缺一不可）：

1. **跑了什么**——命令与结果（全绿 / 部分通过的原因）。
2. **手动破坏性验证了什么**——把修复反过来关掉，测试/页面确实变红/变坏。
3. **没跑 / 没试什么**——如实列出，绝不省略。没跑的检查就写"未跑"，
   不许默认带过、更不许暗示跑过。

## 4. 教训库与复盘机制（LESSONS.md）

- **改代码前读 [LESSONS.md](./LESSONS.md)**：每条 = 规则 + 原因 + 证据（提交号/文档节）+ Seen 计数。
- **复盘节奏**：每个批次收口或里程碑收官时，从 LESSONS.md 头部 `reviewed-through`
  游标起复盘 `git log`（返工、验证太薄、不该合的），更新条目与新教训，推进游标。
- **晋升**：同一教训 Seen 3 次 → 规则正文移入
  [0_INDEX §5 协作工作流](docs/dev-guide/0_DEVELOPMENT_GUIDE_INDEX.md) 或
  [9_TEST_AND_CI](docs/dev-guide/9_TEST_AND_CI.md)，LESSONS 留索引行。
- **正面记录**：做对了什么（可复制的成功模式）记入 LESSONS「Done right」节，不只记错。

## 5. 提交纪律

- Conventional commits，中文长描述；**大提交（跨多文件/多关注点）body 必须含 §3 三问**。
- 文档与代码同批提交：改了文档化行为，同一个提交（或同批 PR）更新对应文档，
  不留"文档回头再补"。
- 原子提交：一个提交一个目的，不夹带无关重构。
