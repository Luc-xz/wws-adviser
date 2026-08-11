# 8. 安全与部署（身份/会话、Web 安全、密钥、Docker、env、部署与恢复清单）

> 文档版本：v1.0  
> 文档状态：开发基线  
> 更新日期：2026-07-19  
> 关联：技术架构 §15 §16 §17 · PRD §8.11 §12.3–§12.5 §13.1 · 索引：[0_DEVELOPMENT_GUIDE_INDEX.md](./0_DEVELOPMENT_GUIDE_INDEX.md)

## 1. 目的

把技术架构 §15（信任边界 / 身份会话 / Web 安全 / 密钥 / 供应链）、§16（健康检查 / 日志 / 指标 / 告警 / 备份 / 恢复 / 保留）、§17（镜像 / NAS+Tailscale / 云端 / 配置）落为**可执行的硬规则与上线清单**。上线与安全审查前读本文。核心约束：

- 即使单用户部署也**必须**启用身份验证（PRD §12.3）。
- 密钥**不**进入 SQLite 明文、日志、API 响应、报告、默认备份、前端（技术架构 §15.4）。
- 数据库不可写时 readiness 必须 fail，禁止产生半条交易（PRD §12.2）。

## 2. 信任边界（技术架构 §15.1，PRD §12.3）

不可信输入：公网请求、CSV、外部网页/PDF、模型输出、通知回调、数据源响应。**所有输入在进入领域层前完成类型/长度/格式/业务校验**（[3_API_CONTRACT.md](./3_API_CONTRACT.md) §5 `VALIDATION_ERROR` 422）。

| 输入 | 最小化/校验责任 |
| --- | --- |
| CSV 导入 | 行数上限（[3_API_CONTRACT.md](./3_API_CONTRACT.md) §9），指纹去重（[2_DATA_MODEL_AND_STORAGE.md](./2_DATA_MODEL_AND_STORAGE.md) §6.2） |
| 文档/网页/新闻 | 长度/类型/来源过滤后入模型上下文（[6_MODEL_AND_REPORT_PIPELINE.md](./6_MODEL_AND_REPORT_PIPELINE.md) §4.2） |
| 模型输出 | schema + 数值 + 引用白名单 + 动作词后置校验（[6_MODEL_AND_REPORT_PIPELINE.md](./6_MODEL_AND_REPORT_PIPELINE.md) §5） |
| 文件上传 | 大小/扩展名/实际 MIME 限制，随机/哈希路径（技术架构 §15.3） |
| 路径 | 路径只由服务端生成，拒绝用户相对路径（[2_DATA_MODEL_AND_STORAGE.md](./2_DATA_MODEL_AND_STORAGE.md) §9） |

## 3. 身份与会话（技术架构 §15.2，PRD §12.3）

- 首个用户通过本地 CLI 或一次性初始化流程创建，**无公开注册入口**。
- 密码 `Argon2id`，支持长密码；P1 增加 Passkey（不影响主键/权限，[3_API_CONTRACT.md](./3_API_CONTRACT.md) §3.1）。
- 会话令牌高熵随机；DB **只存令牌哈希**（`sessions.token_hash`，明文不落库，[2_DATA_MODEL_AND_STORAGE.md](./2_DATA_MODEL_AND_STORAGE.md) §6.1）。
- Cookie：`HttpOnly; Secure; SameSite=Lax`（同源 PWA）；研究/敏感操作可提 `Strict`。
- 改密码撤销其他会话：`UPDATE sessions SET revoked_at=now WHERE user_id=? AND id<>current`。
- 登录失败：进程内限速 + 写审计；公网入口由反代叠加限速（[3_API_CONTRACT.md](./3_API_CONTRACT.md) §9 5 次/5 分钟/IP）。
- 高风险操作要求 `REAUTH_REQUIRED`（近期认证或二次确认）：恢复、删除、密码改、撤销全部会话（UI §16.2）。
- 不采集/保存券商登录凭据（PRD §12.3）。

## 4. Web 安全（技术架构 §15.3，PRD §12.3）

- 前后端**同源**部署，生产默认关闭任意 CORS。
- 写操作 SameSite 之外叠加 CSRF：`X-CSRF-Token` 双提交或严格 Origin 校验（[3_API_CONTRACT.md](./3_API_CONTRACT.md) §6）。
- 安全头：CSP、HSTS、`X-Content-Type-Options`、`Referrer-Policy`。
- 富文本/Markdown 输出用允许列表清洗，链接加安全属性；HTML 白名单禁脚本与事件属性。
- CSV 导出对 `= + - @` 开头单元格做公式注入转义（[3_API_CONTRACT.md](./3_API_CONTRACT.md) §3.11）。
- 文件上传限制大小/扩展名/实际 MIME，随机/哈希路径。

## 5. 密钥与隐私（技术架构 §15.4，PRD §12.3 §12.4）

- 模型/数据源密钥由 env 或 Docker Secret 注入；SQLite 只存**引用名 + 掩码**（`model_profiles.key_ref`，[2_DATA_MODEL_AND_STORAGE.md](./2_DATA_MODEL_AND_STORAGE.md) §6.7）。
- 密钥**不**进入：API 响应、普通日志、报告、默认备份、错误追踪、前端本地存储。
- 发送给外部模型的持仓金额可按设置脱敏；默认只发送分析所需最少字段（PRD §12.3）。设置页明确显示会发送哪些内容（UI §16.3）。
- 通知默认隐私模式，锁屏不显示股票名称/金额/盈亏/动作（PRD §8.9 FR-NOTIFY-003，[6_MODEL_AND_REPORT_PIPELINE.md](./6_MODEL_AND_REPORT_PIPELINE.md) §10）。
- `/data` 只允许应用用户访问；可选宿主机磁盘加密。
- 审计事件敏感值存**摘要/脱敏差异**，不存明文（[2_DATA_MODEL_AND_STORAGE.md](./2_DATA_MODEL_AND_STORAGE.md) §6.7）。
- 日志脱敏：不记录 Token/Cookie/完整敏感响应头/完整敏感持仓提示词（[5_DATA_INGESTION_AND_QUALITY.md](./5_DATA_INGESTION_AND_QUALITY.md) §4；技术架构 §10.1）。

## 6. 健康检查、日志、指标、告警（技术架构 §16.1–§16.4）

### 6.1 健康检查

| 端点 | 用途 | 失败影响 |
| --- | --- | --- |
| `/health/live` | 进程存活，不访问外部 | liveness |
| `/health/ready` | DB + 迁移版本 + 数据目录可写 | readiness；DB 不可写/迁移不匹配 → fail |
| `/health/dependencies` | 数据源/模型/通知最近状态 | 仅认证用户见详情 |

模型/新闻源失败**不**让 liveness 失败（技术架构 §16.1）。DB 不可写或迁移不匹配 → readiness 失败 → 反代摘流。

### 6.2 结构化日志（技术架构 §16.2，PRD §12.4）

JSON 至少含：`timestamp, level, service_version, request_id, job_id, report_id, user_id_hash, module, event, duration_ms, status, error_code`，外加数据源/模型名（不含密钥/完整敏感请求）。按大小+日期轮转，默认 14~30 天。诊断包先自动脱敏。

### 6.3 指标与状态页（技术架构 §16.3，UI `SET-08` `DATA-01`）

MVP 不部署 Prometheus；`runtime_stats`（[2_DATA_MODEL_AND_STORAGE.md](./2_DATA_MODEL_AND_STORAGE.md) §6.7）维护轻量统计在设置页/数据状态中心展示：任务成功率/耗时/连续失败、各源最后成功与新鲜度、模型调用次数/Token/费用/错误率/P95、SQLite/WAL/Parquet/文档占用、备份最后成功与最近恢复演练时间。

### 6.4 告警（技术架构 §16.4）

通过已配置通知渠道（[6_MODEL_AND_REPORT_PIPELINE.md](./6_MODEL_AND_REPORT_PIPELINE.md) §10）发送：开市前/收市后任务错过或失败、盘中关键行情源持续过期、SQLite 不可写/磁盘不足/备份失败、持仓重建不一致、模型费用超日/月预算。相同错误冷却窗口聚合。

## 7. 备份与恢复（技术架构 §16.5–§16.7，PRD §8.11，[2_DATA_MODEL_AND_STORAGE.md](./2_DATA_MODEL_AND_STORAGE.md) §11）

### 7.1 备份

不能在 WAL 写入期间直接复制 `app.db`。流程（技术架构 §16.5）：

1. 获取 `backups` 任务锁（`job_runs` + 文件锁）。
2. SQLite Online Backup API（`sqlite3.Connection.backup()`）生成一致性副本。
3. 遍历 documents/parquet/reports 清单 + SHA-256。
4. 打包：db 副本 + 配置非敏感部分 + 清单。
5. 可选客户端加密后异地复制。
6. 校验归档可读，写 `runtime_stats` 备份状态/时间。
7. **密钥不进入**普通备份。

保留：最近 7 日备份、4 周备份、6 月备份；每日增量文件同步 + 定期全量。

### 7.2 恢复（维护模式）

停调度与任务领取 → 校验归档版本/哈希 → **先备份当前状态** → 替换文件 → `alembic` 迁移检查 → DB 一致性检查 → 持仓重建验证 → 重新开放。**二次确认**（API 与 UI 都强制，UI §16.2，恢复额外交付确认文字 + `REAUTH_REQUIRED`）。

### 7.3 演练与保留

`scripts/restore_drill.py`（[2_DATA_MODEL_AND_STORAGE.md](./2_DATA_MODEL_AND_STORAGE.md) §11.3）：备份→注入交易→恢复→校验账本哈希与持仓一致；CI 每周或手动触发；恢复演练至少每季度一次。

RPO ≤ 24h（交易录入后允许立即手动备份）；RTO ≤ 2h（有有效本地备份时）。交易/持仓快照/建议/报告元数据/审计长期保留；盘中细粒度 90 天；日志 30 天；新闻正文按容量/授权清理但**元数据与引用哈希保留**（[5_DATA_INGESTION_AND_QUALITY.md](./5_DATA_INGESTION_AND_QUALITY.md) §10）。

## 8. 镜像构建（技术架构 §17.1，PRD §13.1）

多阶段 Dockerfile：

1. Node 阶段构建前端静态资源。
2. Python 阶段安装锁定依赖（`uv sync --frozen`）。
3. 精简运行镜像复制后端、迁移、前端产物。
4. FastAPI 同源提供 `/api` 与 PWA 静态文件。

运行命令（单 worker，[1_REPO_STRUCTURE.md](./1_REPO_STRUCTURE.md) §7）：

```text
uvicorn wws_adviser.main:app --host 0.0.0.0 --port 8000 --workers 1
```

运行时：非 root 用户、只读根文件系统（除 `/data` 与必要 `/tmp`）；镜像标签含 Git commit，**禁**用不可追溯的 `latest` 部署（技术架构 §15.5）。Python 与 Node 依赖均用锁文件；CI 执行依赖漏洞 + 许可证 + 密钥扫描（[9_TEST_AND_CI.md](./9_TEST_AND_CI.md)）。

## 9. 部署形态（技术架构 §17.2 §17.3，PRD §12.3 §13.1）

### 9.1 推荐：家庭设备/NAS + Tailscale

- 不直接开放公网端口；通过 Tailscale DNS/HTTPS 访问。
- 应用自身仍启用登录，**不**把私有网络当唯一认证。
- 宿主机配置自动启动、磁盘监控、异地加密备份。
- 单容器 + `/data` 持久化卷。

### 9.2 可选：轻量云服务器

- 容器前放 Caddy/Nginx 或云 LB 处理 HTTPS；仅开放 443，应用端口不直接公网暴露。
- 反代配置登录限速、请求体大小限制、安全头。
- `/data` 持久磁盘 + 异地备份。
- 选择离目标数据源网络稳定的区域，评估向外部模型发送数据的隐私影响。

### 9.3 配置（env 分类，技术架构 §17.4，[1_REPO_STRUCTURE.md](./1_REPO_STRUCTURE.md) §5）

| 类别 | 内容 | 存储 |
| --- | --- | --- |
| 启动必需 | 数据目录、会话密钥、运行环境（`WWSE_ENV`）、`WWSE_EXPECTED_WORKERS` | env |
| 外部凭据 | 数据源/模型 API Key | env / Docker Secret；SQLite 仅存引用名 |
| 可调默认值 | 日志等级、任务并发、超时、新鲜度阈值、凯利折扣范围 | env 默认 + SQLite settings（非敏感，写审计） |

`env.example` 只含名称与说明，**不含**可用密钥。普通业务设置保 SQLite 并审计（[3_API_CONTRACT.md](./3_API_CONTRACT.md) §3.14）；敏感值只存 env 引用，API 返回掩码。

## 10. 升级与回退（技术架构 §19.2，PRD §12.5）

- 语义化或日期版本；镜像标签含 Git commit；发布说明列 schema/配置/数据源/模型提示词变化。
- 部署前自动创建一致性备份。
- 先运行**迁移检查**（不静默升级，[2_DATA_MODEL_AND_STORAGE.md](./2_DATA_MODEL_AND_STORAGE.md) §10），再切换容器。
- 健康检查失败回退应用版本；迁移不可逆时按恢复手册处理，**不自动降级数据库**。
- SQLite→PostgreSQL 升级经 Repository 接口不变 + 一次性迁移工具校验行数/账本哈希/快照重算（技术架构 §21.1）。

## 11. 上线安全清单（PRD §18 上线门槛 + 技术架构 §25）

- [ ] 公网部署完成 HTTPS、身份验证、会话 Cookie 安全属性、CSRF 防护。
- [ ] 密钥不进入 SQLite 明文/日志/前端/默认备份/报告。
- [ ] 安全头（CSP/HSTS/X-Content-Type-Options/Referrer-Policy）生效。
- [ ] CSV 注入、路径穿越、提示词注入、XSS 有自动测试覆盖（[9_TEST_AND_CI.md](./9_TEST_AND_CI.md)）。
- [ ] DB 不可写/迁移不匹配时 readiness fail 且不产生半条交易。
- [ ] 单 worker 在生产明确拒绝多 worker（[1_REPO_STRUCTURE.md](./1_REPO_STRUCTURE.md) §7）。
- [ ] 完成一次备份恢复演练（`scripts/restore_drill.py`）。
- [ ] 数据源使用方式符合授权与服务条款（PRD §18）。
- [ ] 镜像非 root、只读根 FS、标签含 commit、依赖扫描通过。
- [ ] `\`/health/ready\`` 与 `\`/health/live\`` 正常；模型/源失败不让 liveness fail。

## 12. 待确认项

| 事项 | 当前默认 | 备注 |
| --- | --- | --- |
| 通知渠道首选 | 待选企业微信/Server 酱/邮件一种 | `TODO(notifier-selection)`，**Phase 1.6 前定** |
| 备份异地加密 | 客户端可选加密，异地启用 | 密钥与备份分离 |
| CSRF 策略 | 双提交 Token + SameSite | 高敏感操作额外 Origin 校验 |

> **已确认（2026-08-11）**：部署形态为**云端 VPS（单容器）**；反向代理 / HTTPS 选定 **Nginx** + 证书（certbot 或同等方案）。原“NAS 部署评估磁盘加密”随部署变更取消，改为 VPS 宿主机磁盘加密按云厂商能力评估。
