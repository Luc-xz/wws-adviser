# 多阶段构建（技术架构 §17.1 / 8_SECURITY §8）：
#   1) Node 构建前端静态 → 2) uv 锁定安装后端 → 3) 精简运行镜像（同源 /api + PWA 静态）
# 构建上下文为仓库根：docker build -f deploy/Dockerfile -t wws-adviser:$(git rev-parse --short HEAD) .

# —— 1. 前端构建 ——
FROM node:22-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN corepack enable pnpm && pnpm install --frozen-lockfile
COPY frontend/ ./
# openapi.json 由仓库外生成流程提供（make gen-api）；CI 缺省时跳过类型重生成
RUN pnpm build

# —— 2. 后端依赖（锁定） ——
FROM python:3.12-slim AS backend-deps
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
# akshare 为 optional extra：生产启用真实数据源时加 --extra akshare（构建参数）
ARG WITH_AKSHARE=1
RUN uv sync --frozen --no-dev $([ "$WITH_AKSHARE" = "1" ] && echo --extra akshare)

# —— 3. 运行镜像 ——
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
