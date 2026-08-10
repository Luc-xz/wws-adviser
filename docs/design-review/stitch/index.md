# WWS Adviser · Stitch 桌面设计稿总览

> 来源：Google Stitch 项目 `13544749113582094395`（"Document-Driven Chinese UI"）
> 拉取日期：2026-07-25
> 设计系统：`assets/fe75b81af25f4d0f9479af5de06c426d`（已按 UI 规范 §7 推入品牌色 `#3157D5`、上涨红 `#D92D20` / 下跌绿 `#079455`、Inter 字体、圆角 8）
> 对应规范：[UI_DESIGN_SPECIFICATION.md](../../UI_DESIGN_SPECIFICATION.md)

每个页面有两份产物：

- `<NAME>.html` —— Stitch 导出的原生 HTML，**自带 Tailwind CDN + Inter + Material Symbols**，浏览器双击即可查看完整交互稿。
- `<NAME>.png` —— Stitch 生成的高保真截图（2560 宽），用于快速预览 / 走查对比。

> ⚠️ HTML 依赖 `cdn.tailwindcss.com` 与 Google Fonts 在线加载，需联网打开。

## 桌面端核心页面

| 页面 ID | 标题 | HTML | 截图预览 |
| --- | --- | --- | --- |
| HOME-01 | 首页总览（桌面最终版） | [打开](./HOME-01-desktop.html) | ![](./HOME-01-desktop.png) |
| HOME-01 | 首页总览（桌面端 v1，较早版本） | [打开](./HOME-01-desktop-v1.html) | ![](./HOME-01-desktop-v1.png) |
| PORT-02 | 标的 / 持仓详情 | [打开](./PORT-02-desktop.html) | ![](./PORT-02-desktop.png) |
| TX-01 | 交易流水 | [打开](./TX-01-desktop.html) | ![](./TX-01-desktop.png) |
| ACC-01 | 账户与对账 | [打开](./ACC-01-desktop.html) | ![](./ACC-01-desktop.png) |
| CHAT-01 | 助手对话 | [打开](./CHAT-01-desktop.html) | ![](./CHAT-01-desktop.png) |
| LIB-01 | 研究与报告库 | [打开](./LIB-01-desktop.html) | ![](./LIB-01-desktop.png) |
| REP-01 | 开市前报告 | [打开](./REP-01-desktop.html) | ![](./REP-01-desktop.png) |
| DATA-01 | 数据状态中心 | [打开](./DATA-01-desktop.html) | ![](./DATA-01-desktop.png) |
| SET-01 | 风险与投资约束 | [打开](./SET-01-desktop.html) | ![](./SET-01-desktop.png) |

## 缺口（未在 Stitch 项目中找到桌面稿）

对照 UI 规范 §18.4 桌面必交清单，以下页面目前 Stitch 里**只有移动端稿**，桌面端待补：

- PORT-01 持仓与自选（桌面表格）
- TX-03 CSV 导入向导（桌面）
- REP-02 收市后复盘
- REP-03 公司 / 行业研究报告（桌面三栏 + 证据抽屉）
- SET-02 数据源与质量
- SET-03 模型与任务路由
- SET-08 系统状态

## 走查提示（与 UI 规范硬规则对照）

打开 HTML 后重点检查这几条：

1. **行情红绿 vs 行动色不混用**（§7.3）：上涨红 / 下跌绿只用于行情；减少=橙、观察=琥珀、条件式增加=靛蓝、退出观察=洋红、暂停=灰。
2. **时间 / 来源 / 有效期常驻**（§8.3）：行情、净值、建议、报告底部必须显示"截至 … · 来源 …"。
3. **暂停建议不显示目标数量**（§9.3 硬规则）：PAUSE 变体只显示原因 + 可用事实。
4. **凯利区块反精确化**（§10.13）：一位小数、固定诚实旁注、拒绝原因显式化、折扣原因链。
5. **数字 tabular-nums + 空 `—`**（§8.1 / §7.4）：已确认 HTML 里 `font-feature-settings: 'tnum' on`。

## 目录文件清单

完整元数据见 `manifest.json`（含每个屏幕的 Stitch id、宽高、文件大小）。
