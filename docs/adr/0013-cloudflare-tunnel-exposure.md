# ADR-0013：公网暴露采用 Cloudflare Tunnel（替代原定 Nginx + 443 方案）

- 状态：已采纳（2026-09-15 核对回填）
- 日期：2026-09-11 上线 / 2026-09-15 安全核对
- 关联：[8_SECURITY_AND_DEPLOYMENT.md §11](../dev-guide/8_SECURITY_AND_DEPLOYMENT.md) · [10_MILESTONE_PLAN.md §7](../dev-guide/10_MILESTONE_PLAN.md)

## 背景

原部署设计（§9.2 / §12.2）为「VPS 开 443 + Nginx 终结 HTTPS + certbot 证书」。
2026-09-11 实际上线改用 **Cloudflare Tunnel（token 模式，systemd 常驻 cloudflared）**。

## 决策

公网暴露走 Cloudflare Tunnel：容器仅绑 `127.0.0.1:8000`，cloudflared 经出站连接
（QUIC）注册到 CF 边缘，TLS 在边缘终结；VPS **零公网入站端口**（ufw 仅 22）。

## 理由

1. 国内 VPS 备案/80-443 入站治理成本高，Tunnel 完全绕开；
2. 自动 HTTPS（边缘证书 + HTTP/2/3），无需 certbot 续期运维；
3. 零入站 = 攻击面只有 CF 边缘；源站 IP 不暴露；
4. DDoS/WAF/NEL 报告等边缘能力免费档可用。

## 代价与对策

| 代价 | 对策 |
| --- | --- |
| 链路多一跳（边缘→VPS） | 实测 SSE/行情延迟可接受（盘中建议链路已验证） |
| 依赖 CF 可用性 | 个人工具可接受；cloudflared systemd + update.timer 常驻 |
| token 出现在进程列表（token 模式固有） | token 仅限隧道注册权限，rotate 在 Zero Trust 控制台 |
| 应用不自知 TLS（边缘终结） | 会话/CSRF Cookie `secure=settings.is_prod` 按生产环境置位；HSTS/安全头由应用补齐（2026-09-15 已加中间件） |

## §11 清单核对结果（2026-09-15，域名 openclow.cc.cd 实测）

| 项 | 结果 |
| --- | --- |
| HTTPS/身份/会话/CSRF | ✅ 边缘 TLS+HTTP/2；未授权 API 401；Cookie httponly+secure(prod)+samesite=lax；CSRF double-submit 中间件 |
| 密钥不入库/日志 | ✅ DB 全表扫描 0 命中；SQLite 仅存 env 引用名 |
| 安全头 | ✅（本次新增中间件）CSP/HSTS/nosniff/Referrer-Policy/X-Frame-Options + 集成测试 |
| 注入测试覆盖 | ✅ 提示注入（untrusted_context）/XSS（renderMd 先转义）有测试；路径穿越本次补测；CSV 注入：无 CSV 导出面（导出为 md）→ 不适用 |
| readiness fail 语义 | ✅ 迁移头比对（b1ed09a）+ 备份恢复演练（9/10）实证 |
| 单 worker | ✅ worker_guard（tested） |
| 备份恢复演练 | ✅ 2026-09-10 隔离容器全流程通过 |
| 数据源条款 | ✅ 见 dev-guide §8.5 复核记录（AKShare MIT；东财公告接口按只读低频使用） |
| 镜像安全 | ✅ USER wws 非 root + 只读根 FS（本次 compose 增 read_only/tmpfs）+ tag=commit + pip-audit 零已知漏洞（2026-09-15） |
| health 端点 | ✅ live/ready 正常；模型失败不 fail liveness（9/11–9/14 模型持续失败期间服务无恙，实证） |
