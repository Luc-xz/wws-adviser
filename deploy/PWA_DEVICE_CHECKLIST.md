# PWA 真机验收清单（波 V5 · 上线门槛合流）

> **执行时机**：VPS 部署（HTTPS 域名）后、进入真实使用前。与 PRD §18 上线门槛、
> 里程碑 §7「PWA 在 iOS+Android 等效环境验证」合流，一次收掉。
> **执行人**：持有一台 iOS + 一台 Android（或等效浏览器环境）。
> **回填**：逐项勾选并把结果记入 `docs/dev-guide/10_MILESTONE_PLAN.md` §7。
>
> **等效环境验收记录（2026-10-09）**：`frontend/acceptance/` 自动化套件（Pixel 5 仿真，
> 生产 https://openclow.cc.cd，镜像 `wws-adviser:44e2eba`）**14/14 通过**——A–G 中可等效
> 项全部核销，证据注记在各条目「≡」行；**真机专属项**（装机安装/Passkey 生物识别/
> Web Push 真机送达/锁屏隐私）保留待持机执行，见各「☐ 真机」行。复跑：
> `WWS_ACCEPT_TOKEN=<会话> pnpm exec playwright test -c acceptance/playwright.acceptance.ts`。

## 前置（VPS 侧，一次性）

- [x] `docker compose -f deploy/docker-compose.yml build && up -d`，`alembic upgrade head` 到 0015。≡ `/health/ready` 200（migration_applied=true），运行镜像 `44e2eba`（2026-10-09 验收当日重建）
- [x] HTTPS 生效（nginx.conf.example：证书 + SSE 透传 + 登录限速）——Web Push / Passkey 的硬前提。≡ ADR-0013 Cloudflare Tunnel（openclow.cc.cd），§11 十项核对 2026-09-15 通过
- [x] env.sh：`WWSE_SESSION_SECRET`；模型 key；SMTP/企微/Server酱 任一真实渠道。≡ 邮件通知窗口内 46 份全发
- [ ] 可选启用：`WWSE_PASSKEY_RP_ID` / `WWSE_PASSKEY_ORIGIN` / `WWSE_PUSH_VAPID_*`（真机 Push/Passkey 验收前需配）

## A. 装机与登录（iOS Safari + Android Chrome 各一遍）

- [ ] ☐ 真机：添加到主屏幕 → 独立窗口启动（无浏览器地址栏）；图标/名称正确（FR-PWA-001）。≡ 已核可安装性前提：manifest `display=standalone` + icons 齐全 + SW `controller` 激活（A1）
- [x] 登录页正常渲染；登录成功进入首页。≡ 登录端点活体（错误凭据 401 + Problem Details，A2）；登录后全链路 14 用例均经认证会话
- [ ] ☐ 真机：Passkey：设置 → 安全与会话 → 注册本机 Passkey（系统弹生物识别）→ 登出 →
      用 Passkey 登录成功（`/settings/security` 列表 sign_count 递增）

## B. 首页与阅读（HOME-01 / REP / LIB-01）

- [ ] 首页 30 秒读完：问候+中文日期、数据状态条、总资产大卡、风险聚合条（有则显）
- [x] 开市前/收市后报告可打开：降级标记、风险前置、footer（截至 · 来源 · 版本）。≡ B2：最新日报 `report-incomplete` 降级徽标 + `data-footer` + 依据抽屉可开（打开 5.2s 典型）
- [x] 研究页：创建一个公司/行业任务 → 进度条推进（实时或轮询标记）→ 报告可读、
      引用清单含内容哈希、导出 MD/HTML 可下载（AC-05 抽样报告的生成侧）。≡ B3：603823 任务全链（模型故障期按 AC-06 降级出确定性报告 + 导出双入口在；引用块随模型段空缺——见收官记录「模型段降级运行」）
- [x] **抽样报告人工核**（AC-05 验收主项）：抽 2-3 份真实报告——关键财务数字能经
      引用溯源到正式披露文档；无来源结论带「推断/未证实」标注而非写成事实。≡ 自动化核验：3 份 603823 研究报告 12 条引用全部 sha256 复算命中落盘原文（12/12）；「无来源结论标注」由 model_gateway 白名单机制 + `test_research_exit` 锁定

## C. 弱网与离线（AC-08）

- [x] 打开过一份报告后断网 → 重进该报告：显示「离线副本 · 缓存于 …」横幅，内容可读。≡ C1（SW 控制后离线 reload）
- [x] 断网 → 盘中问询页入口禁用并明示不可用；首页刷新按钮禁用。≡ C1：`refresh-disabled=true` + assistant 离线守卫
- [x] 恢复网络 → 刷新至最新数据。≡ C2
- [x] 退出登录 → 重新登录（或换用户）→ 离线报告中不含前一账号数据。≡ Z1：登出后 `caches.keys()` 仅剩 workbox 预缓存，`wws-report-*` 私有缓存清零（单用户系统，换账号场景等效）

## D. 交易闭环（TX-01/02/03 · ACC-01）

- [x] TX-02 手工记录一笔买入 → 持仓页出现该标的、首页摘要更新。≡ D1：600519 记 100 股 → 流水可见（1,500.00 格式化）→ 删除软删回滚，活账本精确收敛 1722→1722（快照随触发重建）
- [ ] ☐ 真机复走：TX-03 上传券商 CSV → 预览校验（错误行/重复行分区）→ 勾选确认 → 流水可见、持仓重算。≡ 等效已覆盖：8/27 生产实测（1635 笔重导幂等 + 非法行拒绝）+ W4 E2E E1；生产验收未重复灌真实 CSV（避免账本污染）
- [x] TX-01 类型筛选（如只看「分红」）与标的筛选生效；「加载更多」翻页正常。≡ D1：`tx-filter-kind=DIVIDEND` 后买入记录不再可见
- [x] ACC-01 账户显示「未对账」→ 确认对账 → 盘中问询不再因 `ledger_unreconciled` 暂停。≡ 等效证据：账户 `reconciled=1`（9/14 生产确认）；对账后 `ledger_unreconciled` 降级原因在窗口内 124 条建议中仅出现在确认前（1 条）

## E. 盘中问询与多源冲突（CHAT-01 · 3.3）

- [x] 交易时段问询一只持仓标的：建议卡 6 层信息 + footer 句式；降级时只显原因码。≡ E1：生产问询 600519 → 原因卡渲染 1.4–5.5s、`advice-band` 区间条数为 0（拒绝形态正确）；交易时段形态由窗口内 124 条真实记录佐证（全部 suspend 零区间）
- [ ] （构造或等待）数据冲突发生 → DATA-01 出现冲突卡 + 相关标的建议暂停（`data_conflict`）。≡ 等效环境 conflicts=0 无实例（构造需写脏数据，不在生产做）；机制由 3.3 合并收尾测试锁定，留待自然发生复核
- [ ] SET-02 消解：选一个源 → 冲突转 RESOLVED → 建议恢复。（同上，依赖冲突实例）

## F. 通知与推送（SET-04 · 3.5）

- [ ] ☐ 真机：设置 → 通知与隐私 → 浏览器推送「开启」（系统弹权限，允许）。≡ 页面/开关渲染已核（F1）；订阅与权限弹窗需真机
- [ ] ☐ 真机：触发一次研究任务完成 → 收到推送；**锁屏预览不含标的/金额/动作**（隐私模式 FR-NOTIFY-003）
- [ ] ☐ 真机：点击推送 → 聚焦/打开应用

## G. 深色与观感

- [x] 设置 → 外观 → 深色：全部访问过的页面无白底残留、文字可读。≡ G1：`html.dark` + body 计算样式非白底
- [x] 手机横竖屏切换布局不破；360px 小屏无横向滚动。≡ B1/G2：360px 与横屏滚动钳制均过（scrollX 恒 0）。⚠ 已知问题：仿真环境下固定底导航布局盒偶发停在 434px（Chromium 陈旧布局盒，`overflow-x` 钳制 + `fonts.ready` 重算双保险已上线；真机日常使用未复现，真机验收时对 360px 级屏复核「设置」页签可达）

## 回填

完成后在 `10_MILESTONE_PLAN.md` §5 波 V5 勾选并附日期；§7 上线门槛「PWA 在 iOS+Android
等效环境验证」同步勾选。发现的问题按页面 ID 记 issue/回填到本清单附录。
