# ADR-0010：Identity/Audit/Jobs 实现默认决策

> 状态：Accepted
> 日期：2026-08-12
> 关联：[8_SECURITY §3](../dev-guide/8_SECURITY_AND_DEPLOYMENT.md) · [3_API_CONTRACT §3.1/§6](../dev-guide/3_API_CONTRACT.md) · [6_MODEL §8](../dev-guide/6_MODEL_AND_REPORT_PIPELINE.md) · [2_DATA §6](../dev-guide/2_DATA_MODEL_AND_STORAGE.md)

## 上下文

波 2 实现 Identity/Audit/Jobs 三模块。上游文档明确了"要什么"（Argon2id、session 只存哈希、任务 7 态状态机、UNIQUE 幂等等），但大量数值参数与机制留"实现时定"。本 ADR 记录这些决策，作为波 2 产物的溯源。

## 决策

| 项 | 决策 | 理由 |
|---|---|---|
| Argon2id 参数 | `argon2-cffi.PasswordHasher()` 库默认（time/memory/parallelism 由库审慎维护） | OWASP 推荐库；库默认接近 OWASP 基线，避免手工调参漂移 |
| 会话令牌 | `secrets.token_urlsafe(32)`（256bit）；DB 存 `sha256(token)` 十六进制 | 高熵随机 + 只存哈希（8_SECURITY §3）|
| 会话有效期 | 14 天（`WWSE_SESSION_TTL_DAYS`）| "有限有效期"；个人工具合理默认 |
| REAUTH | 改密端点用"旧密码验证"作为近期认证代理；`WWSE_REAUTH_WINDOW_MIN=15` 备用 | 文档未定机制；旧密码验证是最简 reauth |
| 登录限流 | 进程内 `dict[ip→deque[失败时间戳]]` 滑动窗口，5/300s/IP，仅失败计数（成功不重置）| 3_API_CONTRACT §9 已确认；单 worker 保证进程内一致 |
| lease TTL | 5 分钟（`WWSE_JOB_LEASE_TTL_SEC`）| 文档未定；报告任务量级合理 |
| max_attempts | 3（`WWSE_JOB_MAX_ATTEMPTS`），按 job_type 可配（波 2 全用默认）| 6_MODEL §12 "实现时定" |
| claim 并发 | 条件 `UPDATE ... WHERE id=:id AND (PENDING/RETRY_WAIT OR (RUNNING AND lease<now))`，`rowcount=1` 才成功 | 单进程 + CAS 保证"同一 job_run 不并发"；不依赖 SELECT FOR UPDATE（SQLite 不支持）|
| 过期 lease 重领 | claim_next 条件含 `lease<now` 的 RUNNING，直接重置 RUNNING+新 lease（不回 PENDING）| 文档 GAP；最简路径，attempt 递增可审计 |
| 首个用户 | CLI `python -m wws_adviser.cli admin create-user`，无公开注册 | 8_SECURITY §3；用户选 CLI（最安全，无 HTTP 攻击面）|
| 执行器形式 | 仅提供 claim/reclaim/complete 服务方法 + 集成测试验证闭环；不跑持续后台循环 | 用户选；Phase 0 退出条件用测试满足；循环留 Phase 1 |
| CSRF | double-submit（`csrf_token` cookie + `X-CSRF-Token` header）+ SameSite=Lax；login 豁免 | 8_SECURITY §4；写操作统一校验，login 建立认证前豁免 |
| audit JSON 列 | SQLite TEXT 存 JSON 字符串 | SQLite 无原生 JSON 类型 |

## 备选方案

- **Argon2id 手工 m/t/p**：放弃，库默认更可信且随版本更新。
- **executor 持续循环**：放弃（Phase 0 无真实业务可跑，徒增复杂度，Phase 1 接报告时再加）。
- **session 短 TTL（1 天）**：放弃，个人工具 14 天更友好。
- **过期 lease 回 PENDING 再 claim**：放弃，多一次状态跳转且 PENDING 与"已领过"语义混淆；直接 RUNNING+attempt++ 更直接。

## 正负影响

**正向：**
- 全部未定项落地可执行；ADR 提供溯源。
- 单进程 CAS 模型简单可靠，Phase 4 迁移 PG 时加 `with_for_update(skip_locked)` 即可。

**负向 / 代价：**
- Argon2id 库默认可能随版本变化 → 升级时需回归测试哈希往返。
- 过期 lease 不回 PENDING 而是 RUNNING，attempt 语义为"领取次数"（含重领），需文档说明。

## 迁移条件

- Argon2id 若需固定参数：在 config 暴露 m/t/p，并加密码重哈希迁移脚本。
- 迁移 PostgreSQL 时：claim_next 加 `with_for_update(skip_locked=True)`，Repository 接口不变。
- executor 持续循环：Phase 1 报告流水线接入时，在 lifespan 启动 claim 循环线程，复用本波 service.claim_next。
