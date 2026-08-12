# WWS Adviser — 统一入口（target 名固定，CI 与文档引用一致）
# 见 docs/dev-guide/1_REPO_STRUCTURE.md §10

BACKEND := uv run --directory backend

.PHONY: install lint test test-unit test-integration test-contract migrate migrate-check dev backup-dry replay

install:                   ## uv sync（后端依赖）
	cd backend && uv sync

lint:                      ## ruff + mypy
	$(BACKEND) ruff check src tests
	$(BACKEND) mypy src

test: test-unit test-integration  ## 全部测试

test-unit:                 ## 单元测试
	$(BACKEND) pytest tests/unit -q

test-integration:          ## 集成测试
	$(BACKEND) pytest tests/integration -q

test-contract:             ## 契约测试（波3 起填充）
	$(BACKEND) pytest tests/contract -q

migrate:                   ## alembic upgrade head（用配置的数据目录）
	$(BACKEND) alembic upgrade head

migrate-check:             ## 空库可建校验（CI 用临时空库）
	WWSE_DATA_DIR=$$(mktemp -d) $(BACKEND) alembic upgrade head

dev:                       ## 本地开发：单 worker + 热重载
	$(BACKEND) uvicorn wws_adviser.main:app --reload --workers 1 --host 0.0.0.0 --port 8000

backup-dry:                ## 备份演练（波5）
	@echo "TODO 波5: scripts/backup_dry_run.py"

gen-api:                   ## 导出后端 OpenAPI + 前端类型生成
	cd backend && uv run python scripts/export_openapi.py
	cd frontend && pnpm gen:api

replay:                    ## 金丝雀报告回放（波5）
	@echo "TODO 波5: scripts/replay_canary.py"
