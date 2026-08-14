# Phase 1 部署与波8 运行手册

> 对应工作项 1.8（连续 10 个交易日闭环验证，PRD §17 阶段 1 退出）。
> 依据：8_SECURITY_AND_DEPLOYMENT.md §8/§9/§11、技术架构 §17、10_MILESTONE_PLAN.md Phase 1 退出条件。
> 形态（已确认 2026-08-12）：国内 VPS 单容器 + 宿主 Nginx HTTPS；AKShare（免费）+ 国内 OpenAI-compatible 模型直连 + SMTP 587/465。

## 1. 首次部署

```bash
# 1) 服务器准备（国内 VPS，Debian/Ubuntu）
sudo apt update && sudo apt install -y docker.io docker-compose-plugin nginx git
sudo usermod -aG docker $USER && newgrp docker

# 2) 拉取代码与构建（标签=commit，禁 latest）
git clone <repo> && cd wws-adviser
export WWS_TAG=$(git rev-parse --short HEAD)
docker compose -f deploy/docker-compose.yml build   # 默认 --extra akshare

# 3) 配置环境（只填名称不含密钥的样例 → 填值；env.sh 严禁提交）
cp deploy/env.example deploy/env.sh && vim deploy/env.sh
#   必填：WWSE_SESSION_SECRET（openssl rand -hex 32）
#   数据源：akshare 无需 key；模型 base_url/name + WWSE_MODEL_API_KEY；SMTP host/user/key/from/to

# 4) 启动（仅回环 8000，宿主 Nginx 反代）
docker compose -f deploy/docker-compose.yml up -d
docker compose -f deploy/docker-compose.yml exec wws alembic upgrade head   # 首次建库（发布流程内）
docker compose -f deploy/docker-compose.yml exec wws \
  python -m wws_adviser.cli admin create-user --username <你的用户名>       # 首个用户（无公开注册）

# 5) Nginx + HTTPS
sudo cp deploy/nginx.conf.example /etc/nginx/sites-available/wws.conf  # 改域名
sudo ln -s /etc/nginx/sites-available/wws.conf /etc/nginx/sites-enabled/ && sudo nginx -t
sudo apt install -y certbot python3-certbot-nginx && sudo certbot --nginx -d wws.example.com
sudo systemctl reload nginx

# 6) 健康验证
curl -fsS https://wws.example.com/health/live  &&  curl -fsS https://wws.example.com/health/ready
# 手机浏览器打开 https://… → 安装 PWA → 登录（AC-08）
```

## 2. 波8：连续 10 个交易日验证（PRD §17 退出条件）

**起算**：部署完成且首个交易日数据闭环形成日起，单实例手动起算并记审计（10_MILESTONE §8.1）。

**每日节奏**（scheduler 08:30/16:00 自动入队，执行器线程领取生成，SMTP 通知结果）：

| 时点 | 动作 | 通过标准 |
| --- | --- | --- |
| 开盘前 | 收到开市前报告邮件 → PWA 查看 | 09:00 前生成；内容含摘要/风险/持仓/解读或降级标记 |
| 盘中任意 | 记录交易（curl/后续 UI）、查看持仓 | 交易入账、快照重建、无重复 |
| 收盘后 | 收到收市后复盘邮件 → 查看 | 17:00 前生成；盈亏/归因正确 |
| 每日一次 | `curl /health/ready` + 数据状态页 | ready 200；质量状态可解释 |
| 每周一次 | 备份演练 `docker compose exec wws python scripts/backup_drill.py` | 表一致 |

**10 日核验表**（对应 Phase 1 七条退出条件，10_MILESTONE_PLAN.md §3；全绿后回填勾选）：

1. **闭环稳定** — 10 个交易日「交易→持仓→报告→复盘」无中断：逐日记录 ✅/❌ 于下表。
2. **对账一致/数值可追溯** — 任一日抽查：`GET /positions` 数值 = 交易回放（MWAC 测试基线口径）；报告头含各版本与冻结引用。
3. **报告按时率 ≥95%** — 10 日 ≥19/20 份（pre+post）在 09:00/17:00 前完成；从 `job_runs`/邮件时间统计。
4. **模型关闭降级（AC-06）** — 任选一日停模型（改 `WWSE_MODEL_SOURCE=stub` 或断 key）→ 登录/交易/行情/风险摘要正常，报告出 `model_unavailable` 降级并可重试成功。
5. **CSV 幂等（AC-01）** — 重复导入同一 CSV：0 新增、预览标 duplicate；错误行被拒。
6. **公告源失败标记（AC-02）** — 任选一日断公告源 → 报告 `documents_unavailable` + PARTIAL。
7. **备份恢复（AC-09）** — backup_drill 通过；检查备份归档不含 `WWSE_*_KEY` 值。

**逐日记录**（粘贴于运维笔记，日期/两份报告状态/异常）：

```
D1  2026-__-__  pre:✅ post:✅  异常:-
D2  ...
```

## 3. 运维要点

- **升级**：部署前自动一致性备份 → `alembic` 迁移检查（不静默升级）→ 切容器；健康失败回退镜像（8_SECURITY §10）。
- **日志**：容器 json-file 50m×5；结构化 JSON 含 request_id/job_id（脱敏）。
- **排障**：`docker compose logs wws`；`GET /health/dependencies`（认证后）看数据源/模型状态。
- **风险阈值**：登录后 `PATCH /api/v1/settings/risk`（写审计，即时生效）。
- **回退**：镜像按 commit 标签回滚；DB 迁移不可逆时按恢复手册（2_DATA §11.2），不自动降级。

## 4. 已知边界（Phase 1）

- akshare 适配器为脚手架：首次上线需在 VPS 实测 `WWSE_MARKET_DATA_SOURCE=akshare` 拉取日线/公告并核对（本仓库测试以 stub 闭环 + 契约 cassette 覆盖解析层）。
- 模型/SMTP 真实联调首次在 VPS 进行；失败自动降级（报告仍出确定性内容）。
- 交易记录 UI/CSV 导入界面为后续波次；波8 期间交易录入可经 API（curl）完成。
