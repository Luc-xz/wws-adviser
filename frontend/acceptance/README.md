# 生产验收套件（观察窗收官 · PWA_DEVICE_CHECKLIST 等效环境）

对生产 HTTPS 站点执行 `deploy/PWA_DEVICE_CHECKLIST.md` A–G 中可等效自动化的事项；
真机专属项（Passkey 生物识别弹窗、Web Push 真机送达、添加到主屏幕实机安装）仍需持机执行。

## 会话铸造与吊销（免污染登录）

不知道用户口令时，在服务器临时铸一枚会话（8 小时），验收完由 Z1 登出自动吊销：

```bash
ssh ubuntu@114.132.239.95 'docker exec -i deploy-wws-1 python -' <<'EOF'
import sqlite3, secrets, datetime, hashlib
tok = secrets.token_urlsafe(32)
now = datetime.datetime.now(datetime.timezone.utc)
sid = "01TEST" + secrets.token_hex(10)[:20]
c = sqlite3.connect("/data/app.db", timeout=10)
uid = c.execute("select id from users limit 1").fetchone()[0]
c.execute("insert into sessions (id,user_id,token_hash,issued_at,expires_at,revoked_at,user_agent_hash)"
          " values (?,?,?,?,?,NULL,?)",
          (sid, uid, hashlib.sha256(tok.encode()).hexdigest(),
           now.isoformat(), (now+datetime.timedelta(hours=8)).isoformat(), ""))
c.commit(); print("TOKEN", tok)
EOF
```

兜底吊销（Z1 未跑时）：`update sessions set revoked_at=... where id like '01TEST%'`。

## 运行

```bash
cd frontend
WWS_ACCEPT_TOKEN=<token> pnpm exec playwright test -c acceptance/playwright.acceptance.ts
```

- 数据写点仅两处：D1 记一笔即删（账本收敛）、E1 一次问询（advice_records +1，作为降级形态运行证据）。
- `artifacts/` 截图含个人资产数据——已 gitignore，仅本地留存。
- `TIMING:` 前缀日志为 PRD §4.2 耗时指标测量记录。
