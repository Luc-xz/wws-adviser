# 基准卡：TX-02 新建/编辑交易

> 补卡（审计回填 2026-09-09）：V4 已实现页的追溯基准卡。交易 8 类型统一入口，
> 后端 `TransactionCreate` 契约：fee/tax 必填字符串、direction 仅 BUY/SELL 需要。

## 1. 参考稿

- 移动：`stitch/mobile/TX-02-mobile.html`（最终版）
- 桌面：响应式自适应（表单卡 max-w 收窄）

## 2. 布局结构

```
1. PageHeader（title「记录交易」+ subtitle「8 种交易类型 · 移动加权平均成本即时重算」）
2. 类型选择（TX_KINDS 胶囊/分段组：BUY/SELL/DIVIDEND/…；选中 primary）
3. 方向选择（仅 KIND_NEEDS_DIRECTION=BUY/SELL 显示）
4. 表单字段（标的 ID / 数量 / 价格 / 成交时间 / 费用 / 税费 / 备注）
5. 行内错误条（validate 失败或服务端 4xx：tx-error）
6. 提交按钮（主按钮；成功 → router.push('/transactions')）
```

- 栅格/分栏：单列表单卡；桌面表单居中收窄
- 滚动行为：整页滚动
- 桌面差异：无（响应式同构）

## 3. 关键尺寸

| 位置 | 稿实测 | 落点 token |
| --- | --- | --- |
| 表单卡内边距 | — | `p-4` |
| 卡片圆角 | — | `rounded-lg` |
| 区块标题 | — | `text-h3 font-semibold` |
| 输入框 | — | 全局 input 基类 + `text-body` |
| 数字输入 | — | `num`（tabular-nums） |

## 4. 组件清单

| 组件 | 需覆盖 variant |
| --- | --- |
| 类型胶囊组 | 8 类型；选中/未选 |
| 方向分段 | 买入/卖出（仅 BUY/SELL 出现） |
| 表单字段 | 必填 / 选填（备注、费税可空传 "0"） |
| 错误条 | 前端校验 / 服务端失败 |
| 提交 | idle / submitting |

## 5. 稿内违例覆盖注记（disregarded）

| 稿位置 | 违例内容 | 覆盖依据 |
| --- | --- | --- |
| 稿英文文案 | 英文占位 | 中文文案规范 |
| 稿费税可选项形态 | 与后端必填契约不一致 | 以 OpenAPI 契约为准（fee/tax 必填字符串，空 → "0"） |

## 6. 走查项打勾区

- [ ] 三截图并排贴 PR
- [x] 校验四态（默认/缺字段/服务端错误/成功跳转）
- [x] 门禁全绿；深色 dark: 核验（V5 扫描清零）
