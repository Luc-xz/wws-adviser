# 多阶段构建（技术架构 §17.1 / 8_SECURITY §8）：
#   1) uv 锁定安装后端 → 2) 导出 OpenAPI → 3) Node 构建前端静态 → 4) 精简运行镜像（同源 /api + PWA 静态）
# 构建上下文为仓库根：docker build -f deploy/Dockerfile -t wws-adviser:$(git rev-parse --short HEAD) .

# —— 1. 后端依赖（锁定） ——
FROM python:3.12-slim AS backend-deps
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
# akshare 为 optional extra：生产启用真实数据源时加 --extra akshare（构建参数）
ARG WITH_AKSHARE=1
RUN uv sync --frozen --no-dev $([ "$WITH_AKSHARE" = "1" ] && echo --extra akshare)

# —— 2. OpenAPI 导出 ——
# openapi.json 与 src/api/generated/ 均被 gitignore：在镜像内生成（与 CI 的 make gen-api 同源），
# 全新 clone 也能构建。脚本写出到 parents[2]/frontend/openapi.json = /app/frontend/openapi.json
FROM backend-deps AS openapi-export
COPY backend/src ./src
COPY backend/scripts ./scripts
RUN .venv/bin/python scripts/export_openapi.py

# —— 3. 前端构建 ——
FROM node:22-alpine AS frontend
WORKDIR /app/frontend
# pnpm-workspace.yaml 必须在 install 前就位：pnpm≥10.3 strictDepBuilds 默认拒绝未审核的
# 依赖构建脚本（esbuild/vue-demi），缺了 allowBuilds 白名单会以 ERR_PNPM_IGNORED_BUILDS 失败
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN corepack enable pnpm && pnpm install --frozen-lockfile
COPY frontend/ ./
# 用镜像内导出的 openapi.json 覆盖上下文里的本地副本（.dockerignore 已排除，双保险），保证与后端同源
COPY --from=openapi-export /app/frontend/openapi.json ./openapi.json
RUN pnpm gen:api && pnpm build

# —— 4. 运行镜像 ——
FROM python:3.12-slim AS runtime
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
# 非 root（8_SECURITY §8）
RUN useradd -m -u 1000 wws && mkdir -p /data && chown wws:wws /data
WORKDIR /app/backend
COPY --from=backend-deps /app/backend/.venv ./.venv
COPY backend/pyproject.toml backend/alembic.ini ./
COPY backend/src ./src
COPY backend/migrations ./migrations
COPY backend/scripts ./scripts
COPY --from=frontend /app/frontend/dist /app/static
ENV PATH="/app/backend/.venv/bin:$PATH" \
    WWSE_DATA_DIR=/data \
    WWSE_STATIC_DIR=/app/static
USER wws
EXPOSE 8000
# 单 worker（1_REPO §7 enforce）；启动只校验迁移版本，升级走发布流程（2_DATA §10）
CMD ["uvicorn", "wws_adviser.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
