# WWS Adviser

A 股 + 场内 ETF 的个人投资顾问：持仓对账、确定性风险分析、开市前/收市后报告、盘中条件式建议。架构为模块化单体（FastAPI + SQLite + Vue PWA），模型仅解释确定性结果，无权写入交易数量。

## 状态

Phase 0 — 工程基础骨架（进行中）。文档基线已齐备，详见 `docs/`。

## 快速开始

需要 `uv`（含 Python）、`node`、`pnpm`。

```bash
make install      # uv sync（后端）；前端依赖在 Phase 0 波4 加入
make dev          # uvicorn --workers 1 --reload
make lint         # ruff + mypy
make test         # pytest（unit + integration）
make migrate-check # 空库 alembic upgrade head 校验
```

Makefile target 名固定，CI 与文档引用一致（见 `docs/dev-guide/1_REPO_STRUCTURE.md` §10）。

## 仓库结构

```
backend/    Python 3.12+ FastAPI 单体（uv 管理）
frontend/   Vue 3 + TS PWA（pnpm，Phase 0 波4 建立）
deploy/     Dockerfile / compose / env.example
scripts/    一次性运维脚本
docs/       三份基线（PRD/技术架构/UI 规范）+ dev-guide/ + adr/ + design-review/
data/       运行数据（gitignore）
```

四层依赖方向、模块契约、单 worker 约束见 `docs/dev-guide/1_REPO_STRUCTURE.md`。

## 文档导航

- 上游基线：`docs/PRODUCT_REQUIREMENTS.md` · `docs/TECHNICAL_ARCHITECTURE.md` · `docs/UI_DESIGN_SPECIFICATION.md`
- 开发指南：`docs/dev-guide/0_DEVELOPMENT_GUIDE_INDEX.md`（入口）
- 里程碑：`docs/dev-guide/10_MILESTONE_PLAN.md`（Phase 0–3 工作项与退出条件）
- 决策记录：`docs/adr/`
