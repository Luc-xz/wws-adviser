# 7. 前端与 PWA（分层、状态/缓存边界、OpenAPI 类型、SSE、十进制）

> 文档版本：v1.0  
> 文档状态：开发基线  
> 更新日期：2026-07-19  
> 关联：技术架构 §14 · PRD §8.10 §12.1 §12.6 · UI 规范 §4 §7 §8 §9 §14 · 索引：[0_DEVELOPMENT_GUIDE_INDEX.md](./0_DEVELOPMENT_GUIDE_INDEX.md)

## 1. 目的

把技术架构 §14（前端栈 / 状态边界 / 缓存 / 移动 / SSE）与 UI 规范落为**前端分层契约、状态与缓存硬规则、类型生成流、十进制处理与可访问性约束**。写任何 Vue 代码前读本文。核心约束：

- 前端**不得**自行计算最终成本、盈亏、风险或凯利仓位（技术架构 §14.2；与 [4_ANALYTICS_AND_RISK.md](./4_ANALYTICS_AND_RISK.md) §2 写权限一致）。
- 十进制字段以**字符串**接收，仅在展示层格式化，不参与结算（[2_DATA_MODEL_AND_STORAGE.md](./2_DATA_MODEL_AND_STORAGE.md) §5；[1_REPO_STRUCTURE.md](./1_REPO_STRUCTURE.md) §9）。
- OpenAPI 是接口事实源，generated 类型**禁止手写覆盖**（[3_API_CONTRACT.md](./3_API_CONTRACT.md) §7）。

## 2. 技术栈（技术架构 §14.1，PRD §13.1）

| 类别 | 选型 | 用途/约束 |
| --- | --- | --- |
| 框架 | Vue 3 Composition API + `<script setup>` + TypeScript | |
| 构建 | Vite | `vite-plugin-pwa`/Workbox 生成 Manifest + SW |
| 路由 | Vue Router | 五个一级入口（UI §4.1） |
| 客户端 UI 状态 | Pinia | 主题、展开项、草稿、筛选；**不持久化敏感离线数据** |
| 服务端状态 | TanStack Vue Query | 缓存、重试、失效；唯一与服务端事实交互的入口 |
| 样式 | UnoCSS 或等效原子化 | 用语义 Token（UI §7），禁止无语义临时色值 |
| 图表 | Apache ECharts | 按页面**懒加载**，仅组合/研究页 |
| API 类型 | `openapi-typescript` + `openapi-fetch` | generated，禁止手写覆盖 |
| 校验 | 与后端共享 schema 派生（如 zod from OpenAPI） | 表单校验与后端一致 |

## 3. 目录结构（与后端协作的边界，[1_REPO_STRUCTURE.md](./1_REPO_STRUCTURE.md) §9）

```text
frontend/
├── src/
│   ├── api/
│   │   ├── generated/        # openapi-typescript 产物，禁止手改
│   │   ├── wrapped/          # 可选薄包装（重试/错误归一），不重写类型
│   │   └── client.ts         # openapi-fetch 客户端 + X-Request-ID/X-CSRF
│   ├── features/<slug>/      # slug = portfolio | assistant | research | settings | home
│   │   ├── components/       # 业务组件
│   │   ├── composables/      # useQuery/useMutation 封装
│   │   ├── pages/            # 对齐 UI 页面 ID（PORT-01 等）
│   │   └── types.ts          # 仅本地纯客户端类型
│   ├── shared/
│   │   ├── ui/               # 通用组件（DataStatusBar / AdviceCard / EvidenceDrawer…）
│   │   ├── format/           # 金额/价格/百分比/时间格式化（字符串输入）
│   │   ├── decimals/         # Decimal.js 展示运算（仅展示，不结算）
│   │   └── sse/              # EventSource 封装 + 轮询兜底
│   ├── stores/               # Pinia（session、ui、theme）
│   ├── router/               # 路由 + 守卫
│   ├── app/                  # 入口、Provider、错误边界
│   └── styles/               # Token、UnoCSS 配置
├── public/                   # manifest、图标
└── tests/                    # vitest
```

约定：

- `features/<slug>` 与 UI §4.3 页面 slug 一一对应；路由路径用 UI §4.3 建议值。
- 通用组件来自 `shared/ui`；与 UI §9 组件规范一一映射（`DataStatusBar`、`MetricCard`、`AdviceCard`、`RiskAlert`、`PositionRow`、`EvidenceDrawer`、`FactCalcJudgment`…）。
- 页面文件命名带页面 ID 注释（如 `// PORT-01 持仓与自选`），便于追溯 UI 规范。

## 4. 状态边界（技术架构 §14.2，PRD §8.10）

| 类别 | 内容 | 存储 |
| --- | --- | --- |
| 服务端事实 | 账户、交易、持仓、行情、报告、建议、任务状态 | TanStack Query 缓存（与服务端为准） |
| 客户端 UI 状态 | 主题、展开项、草稿问题、筛选条件 | Pinia / 内存 |
| 敏感离线数据 | 受控 SW 缓存的已完成报告 | SW 私有缓存（按 `user_id + report_id + version` 隔离） |

硬规则：

1. 前端**不得**计算最终成本/盈亏/风险/凯利仓位；只展示服务端返回值（技术架构 §14.2）。
2. 敏感离线数据**不进入** Pinia 长期持久化（技术架构 §14.2）。
3. 退出登录、密码重置或“清除本机数据”时清除所有私有缓存（PRD §8.10、技术架构 §14.3）。
4. 会话过期（[UI §14.5](../UI_DESIGN_SPECIFICATION.md)）→ 跳登录，不清缓存报告除非显式登出。

## 5. 缓存规则（技术架构 §14.3，PRD §8.10）

| 资源 | 策略 |
| --- | --- |
| 带哈希静态资源 | Cache First，长期缓存 |
| 应用入口 HTML | Network First，短超时后回退 |
| 最近查看的**已完成**报告 | Network First，失败回退私有缓存，限制数量 |
| 当前持仓、资产、风险 | **不**由 SW 离线缓存为“当前值” |
| 盘中行情和建议 | **Network Only** |
| 登录、设置、交易写入 | **Network Only** |

报告离线缓存按 `user_id + report_id + version` 隔离；离线报告顶部固定显示生成时间与“离线副本”标记（UI §8.2、§8.4）。盘中行情/建议入口在离线时显示不可用（PRD §16 AC-08）。

## 6. OpenAPI 类型生成流（技术架构 §14.1，[3_API_CONTRACT.md](./3_API_CONTRACT.md) §7）

1. 后端 router 全部带 `response_model`、`tags`、`operation_id`（前端函数名依据）。
2. CI 导出 `openapi.json` 并 diff（路径/方法/响应码/必填字段）；变更须在 PR 说明。
3. 前端 `openapi-typescript` 生成 `src/api/generated/types.ts`；`openapi-fetch` 生成客户端。
4. **禁止**手写覆盖 generated；如需包装写 `src/api/wrapped/`。
5. 十进制字段 generated 为 `string`，前端不做数值运算。
6. 客户端每次请求自动注入 `X-Request-ID`（UUIDv7）；遇 `REAUTH_REQUIRED` 跳重新认证流程。

## 7. 十进制与数字展示（[2_DATA_MODEL_AND_STORAGE.md](./2_DATA_MODEL_AND_STORAGE.md) §5，UI §8.1 §8.2）

- 金额/价格/净值/数量/比例 API 一律 `string`；前端用 `decimal.js` **仅做展示运算**（如单位换算、千分位），不参与结算。
- 格式化集中在 `shared/format`：人民币千分位、价格按 `price_scale`、净值按 6 位、涨跌幅始终带正负号、仓位默认一位小数。
- 空数据用 `—`，不用 `0` 代替未知（UI §8.2）；估算值旁标“估”；缓存/旧值显示“截至”时间。
- 数字开 `font-variant-numeric: tabular-nums`（UI §7.4）；表格/卡片价格金额百分比必须等宽。
- 隐私模式（UI §16.1）：金额 `••••••`，图表纵轴金额隐藏，趋势形状可保留。

## 8. 市场语义与配色硬规则（UI §7.3 §8.4，PRD §12.6）

- 中国市场约定：**上涨红、下跌绿**；红/绿旁必须同时显示 `+/-`/箭头/文字/图标，不能只靠颜色。
- 行动建议**不使用**市场红绿：减少=橙、观察=琥珀、条件式增加=靛蓝、退出观察=洋红、暂停=灰（UI §9.3）。
- 高风险洋红用于风险，不与上涨红混用；大面积背景不用高饱和红绿。
- 状态语义（UI §8.4）：市场状态/数据状态/任务状态/报告状态枚举与后端 `quality_status`、`job_runs.status`、`reports.status` 对齐（见 [5_DATA_INGESTION_AND_QUALITY.md](./5_DATA_INGESTION_AND_QUALITY.md) §7、[6_MODEL_AND_REPORT_PIPELINE.md](./6_MODEL_AND_REPORT_PIPELINE.md) §6.1 §8.2）。

## 9. 核心组件落点（UI §9）

- `DataStatusBar`（UI §9.1）：首页/持仓/助手/报告顶部持续表达市场状态与新鲜度；点击进 `DATA-01`，不只 Toast。
- `AdviceCard`（UI §9.3）：固定信息层级 6 级；`PAUSE_ADVICE` 时不显示目标交易数量与醒目按钮，只显示原因与可用事实（与 [4_ANALYTICS_AND_RISK.md](./4_ANALYTICS_AND_RISK.md) §7 一致）。
- `RiskAlert`（UI §9.4）：Info/Warning/Critical；Critical 固定在重要内容前，含“影响什么/如何处理”，禁仅显示错误码。
- `EvidenceDrawer/Sheet`（UI §9.6）：移动 80~92% Bottom Sheet，桌面 360~420px 右抽屉；显示来源等级/发布主体/时间/片段/定位/原文入口；区分“事实来源”与“模型引用”。
- `Fact/Calculation/Judgment` 标签（UI §9.7）：研究报告中按段落/结论块贴标；`未证实` 禁与 `事实` 混排（与 [6_MODEL_AND_REPORT_PIPELINE.md](./6_MODEL_AND_REPORT_PIPELINE.md) §7.4 一致）。
- Loading/Empty/Error（UI §9.12）：首屏 Skeleton 不用全屏 Spinner；空态说明为何为空 + 下一步；错误显示原因/范围/最后成功时间/重试入口。

## 10. 移动布局与 PWA（技术架构 §14.4，PRD §8.10 FR-PWA-001~002）

- 断点以内容定义，首要支持 360~430px（UI §3.3）。
- 底部导航固定，安全区 `env(safe-area-inset-bottom)`；五个一级入口（UI §4.1）。
- 行动卡首屏只显示动作/风险/仓位区间/时间/有效期；表格小屏转卡片或保留关键列。
- 触控目标 ≥ 44×44 CSS px（PRD §8.10、UI §3.2）。
- 风险不能只靠颜色表达。
- 长报告按章节懒渲染，避免一次性渲染巨大 DOM。
- Manifest + 图标 + SW；可从主流移动浏览器添加到桌面独立窗口启动（FR-PWA-001）。支持浅色/深色主题（UI §17）。

## 11. SSE 与后台更新（技术架构 §14.5，[6_MODEL_AND_REPORT_PIPELINE.md](./6_MODEL_AND_REPORT_PIPELINE.md) §9）

- 研究/报告任务创建后订阅 `GET /events` 认证 SSE 流；事件仅 `{event, job_id, status, progress, ts}`，不含持仓/敏感数值。
- SSE 断开用带退避的 `GET /jobs/:id` 轮询兜底（[3_API_CONTRACT.md](./3_API_CONTRACT.md) §3.13）。
- MVP 不依赖移动浏览器后台长连接；定时报告完成通过外部通知提醒，打开 PWA 后读详情。
- 任务进度页（`RES-02` UI §10.16）展示步骤/当前阶段/开始时间/“可离开此页”。

## 12. 可访问性（UI §15，PRD §12.6）

- 对比度正文 ≥ 4.5:1，大字 ≥ 3:1；触控目标 ≥ 44×44。
- 全键盘可操作，焦点顺序与视觉顺序一致；Focus Ring 明显不移除。
- 红绿/风险级别/任务状态有图标+文字冗余编码；图表提供文字摘要或数据表入口。
- 表单 Label/错误/帮助明确关联；Modal 焦点锁定，关闭后返回触发元素。
- 支持系统字体放大；200% 缩放核心流程不丢；支持 Reduced Motion。
- 图标按钮有可访问名称 + 桌面 Tooltip。

## 13. 必测不变量（前端侧）

- 十进制字段在前端不参与结算（属性测试：随机 string 数值，前端展示值不漂移超过展示精度）。
- 退出登录后私有 PWA 缓存被清除（技术架构 §18.2）。
- 离线时盘中行情/快速建议入口显示不可用（PRD AC-08）。
- `PAUSE_ADVICE` 时 AdviceCard 不显示目标交易数量与醒目按钮。
- OpenAPI generated 类型未被手写覆盖（CI grep：`generated/` 无手改 diff）。
- 建议/行情卡始终显示行情时间、延迟、来源、有效期（PRD §8.5 FR-CHAT-003）。

## 14. 运行配置项（2026-08-11 复核）

> 以下事项确认采用「运行配置」策略，初值如下，按设备/构建预算调整。

| 事项 | 确认策略 | 备注 |
| --- | --- | --- |
| 图表库懒加载阈值 | 仅组合 + 研究页 | 构建后按预算调整 |
| 离线报告缓存数量上限 | 留配置 | 按设备存储定 |
| 桌面左侧栏宽度 | 224px（UI §4.1） | 可折叠 |

> **已确认（2026-08-11）**：CSS 方案选定 **UnoCSS**（原子化按需生成，语义 Token 保持一致）。
