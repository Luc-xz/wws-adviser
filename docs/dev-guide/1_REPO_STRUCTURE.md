# 1. 仓库结构与模块契约

> 关联：技术架构 §4 §5 §6 | 索引：[0_DEVELOPMENT_GUIDE_INDEX.md](./0_DEVELOPMENT_GUIDE_INDEX.md)

## 1. 目的

把技术架构 §5 的目录骨架落为**可执行的模块契约**：每个后端模块长什么样、模块间怎么依赖、前后端怎么协作、单体边界靠什么 enforce。建任何新模块前读本文。

## 2. 顶层仓库结构

沿用技术架构 §5，以下为开发约定补充（**不重复罗列全部文件**，只标注约定）：

```text
wws-adviser/
├── backend/                 # Python 3.12+ 单体后端
│   ├── pyproject.toml       # uv 管理，锁 uv.lock
│   ├── alembic.ini
│   ├── migrations/versions/ # 每个迁移独立文件，命名 <rev>_<topic>.py
│   ├── src/wws_adviser/
│   └── tests/{unit,integration,contract,fixtures}/
├── frontend/                # Vue 3 + TS PWA
├── deploy/                  # Dockerfile / compose / env.example / healthcheck.sh
├── scripts/                 # 一次性运维脚本（迁移校验、备份演练、回放）
├── docs/                    # 三份基线 + dev-guide/ + adr/
├── data/                    # 运行数据，gitignore
├── Makefile                 # 统一入口：make test/lint/migrate/dev
└── README.md
```

约定：

- `data/`、`backend/.venv/`、`frontend/node_modules/`、`frontend/dist/`、`*.db`、`*.db-wal` 一律 gitignore。
- `docs/` 下不再放临时笔记；架构决策进 `docs/adr/`，开发执行细节进 `docs/dev-guide/`。

## 3. 后端四层与依赖方向

| 层 | 包路径 | 依赖方向 | 可引用 |
| --- | --- | --- | --- |
| 接口层 | `wws_adviser.api` | → 应用层 | FastAPI、Pydantic、应用服务 |
| 应用层 | `<module>.service` | → 领域层、`ports` | 领域、端口、SQLAlchemy Session（仅注入，不散落） |
| 领域层 | `<module>.domain` | 仅标准库 + typing | Decimal、enum、dataclass；**禁** FastAPI/SQLAlchemy/SDK |
| 基础设施层 | `wws_adviser.infrastructure` | 实现 `ports` | SQLAlchemy、HTTPX、Polars、模型 SDK、文件系统 |

**硬规则（lint 强制）：**

1. `domain.py`不得 import `fastapi`、`sqlalchemy`、`httpx`、任何模型 SDK、任何 `infrastructure.*`。用 `ruff` 的 `flake8-tidy-imports` 或自定义 `banned-api` 规则 enforce。
2. `modules/*` 之间不直接 import 对方的 `repository`/`infrastructure`；跨模块协作走 `service` 或 `ports`。
3. `api` 层不直接调用 `repository`，必须经 `service`。
4. `ports/` 里只放 Protocol 与 DTO，不放实现。

> 这四条是“模块化单体”不退化为大泥球的护栏，必须在 CI 中以静态检查守住。

## 4. 后端模块标准文件清单

每个 `modules/<name>/` 默认包含以下文件，**复杂度未到不要拆子目录**：

| 文件 | 职责 | 必需 |
| --- | --- | --- |
| `domain.py` | 实体、值对象、枚举、纯计算函数、状态机 | 是 |
| `schemas.py` | Pydantic 入参/出参 DTO（API 与内部共用边界） | 是 |
| `service.py` | 用例编排、事务边界、降级决策、调用端口 | 是 |
| `repository.py` | SQLAlchemy 仓储，仅应用层调用 | 是（有持久化时） |
| `api.py` | FastAPI router，仅做参数解析→调 service→组装响应 | 有 HTTP 时 |
| `models.py` | SQLAlchemy ORM 表定义 | 有持久化时 |
| `tests/test_<module>_unit.py` | 领域纯函数与状态机单测 | 是 |

模块清单与职责严格对齐技术架构 §6（identity / portfolio / instruments / market_data / documents / analytics / advice / reports / research / model_gateway / notifications / jobs / audit），不新增模块除非提 ADR。

### 4.1 命名约定

- 包/模块：`snake_case`。
- 类：`PascalCase`；服务类后缀 `Service`，仓储 `Repository`，端口 Protocol 不加后缀（如 `QuoteProvider`）。
- 领域纯函数：动词开头，`compute_*`、`rebuild_*`、`evaluate_*`。
- 枚举值：`SCREAMING_SNAKE`。
- DTO 字段：`snake_case`，与 API JSON 一致（见 [3_API_CONTRACT.md](./3_API_CONTRACT.md)）。

### 4.2 service 边界规则

- `service` 方法是事务边界：进入开 session，返回前 commit/rollback。
- **网络请求与模型调用不得持有 DB 事务**（技术架构 §7.2）。模式：先在事务内读快照版本号，事务外做网络/模型，再开新事务写结果。
- `service` 不抛裸异常给 API；抛领域异常或 `OperationError`，由 `api/errors.py` 统一翻译为 Problem Details。
- `service` 不构造 HTTP 响应；返回 dataclass/DTO，由 `api.py` 包 Problem Details 与 header。

## 5. 入口与生命周期

`wws_adviser/main.py` 负责：

1. 加载 `core.config.Settings`（Pydantic Settings，见 [8_SECURITY_AND_DEPLOYMENT.md](./8_SECURITY_AND_DEPLOYMENT.md) env 分类）。
2. 初始化结构化日志（`core.logging`）。
3. 启动时：校验单 worker（环境变量 `WEB_CONCURRENCY!=1` 时告警/拒绝，见 §7）、校验数据目录可写、运行 Alembic 版本校验（不静默升级）、获取 scheduler 文件锁。
4. 装配依赖（`api/dependencies.py` 提供 session、当前用户、端口实现注入）。
5. 挂载 routers、静态文件、健康检查、SSE。
6. lifespan：启动 scheduler 与 job executor，优雅关闭停止领取新任务、等待短任务、释放租约。

`api/dependencies.py` 是唯一允许构造基础设施对象的地方；service 通过依赖注入接收端口，不在内部 `import` 具体适配器。

## 6. ports 目录

```text
ports/
├── market_data.py      # QuoteProvider / BarProvider / NAVProvider
├── document_source.py  # DocumentProvider（discover/download）
├── model.py            # ModelPort（结构化调用 + 审计回调）
├── notifier.py         # NotifierPort
└── object_store.py     # 文档/报告对象存储抽象（本地 FS 实现）
```

- 每个 Port 是 `typing.Protocol`，方法返回**原始对象**（`RawQuote` 等），标准化由内部流水线统一执行（见 [5_DATA_INGESTION_AND_QUALITY.md](./5_DATA_INGESTION_AND_QUALITY.md)）。
- Port 不带业务语义方法（如 `get_fresh_quote` 是 service 的职责，不是 Port 的）。

## 7. 单 worker 与单调度实例的 enforce

技术架构要求 `workers=1` 且只有一个调度实例。开发落地：

- `core/config.py` 读取 `WWSE_EXPECTED_WORKERS`（默认 1）。
- `main.py` 启动钩子：若检测到多 worker（uvicorn `--workers`>1 或 `WEB_CONCURRENCY`>1），生产环境（`WWSE_ENV=prod`）**直接拒绝启动**；非生产告警但继续。
- scheduler 文件锁 `/data/locks/scheduler.lock`：`fcntl.flock` 非阻塞获取，失败则不启动调度线程（仍可服务 API，便于调试），并日志告警。**文件锁不是唯一正确性来源**，最终防线是 DB 唯一约束（见 [6_MODEL_AND_REPORT_PIPELINE.md](./6_MODEL_AND_REPORT_PIPELINE.md)）。
- 加一条启动自检测试：模拟 `workers=2` 配置断言拒绝。

## 8. 审计与不可变主键的全局约定

- 所有关键表主键用 ULID（字符串，26 位，时间有序），便于跨 SQLite/PG 迁移且无需中心化 ID 服务。
- 所有关键表含 `created_at`、`updated_at`（UTC ISO 8601 字符串）、必要 `version`（乐观锁/可复现）。
- 审计事件（`audit` 模块）只追加，更新走“新事件 + 旧值摘要”，不 in-place 覆盖敏感字段（见 [8_SECURITY_AND_DEPLOYMENT.md](./8_SECURITY_AND_DEPLOYMENT.md)）。

## 9. 前端目录与后端的契约点

前端结构见 [7_FRONTEND_AND_PWA.md](./7_FRONTEND_AND_PWA.md)。此处只列**与后端协作的边界**：

- API 类型由 OpenAPI 生成到 `frontend/src/api/generated/`，**禁止手写覆盖**。
- 路由与 UI 规范页面 ID（如 `PORT-01`）对齐 [UI 规范 §4.3](../UI_DESIGN_SPECIFICATION.md)；前端 `features/` 目录用相同 slug（`portfolio`、`assistant`、`research`、`settings`、`home`）。
- 十进制值前端一律以字符串接收，仅在展示层格式化，不参与结算（技术架构 §7.3）。

## 10. Makefile 统一入口（建议）

```makefile
make install      # uv sync + pnpm install
make lint         # ruff + mypy + eslint + vue-tsc
make test         # pytest + vitest
make test-unit / test-integration / test-contract
make migrate      # alembic upgrade head
make migrate-check # alembic 校验（不写）
make dev          # 后端 uvicorn + 前端 vite 并行
make backup-dry   # 跑一次备份演练（见 2_DATA_MODEL_AND_STORAGE）
make replay       # 金丝雀报告回放（见 9_TEST_AND_CI）
```

具体命令在实现时填充，但入口名固定，便于 CI 与文档引用一致。
