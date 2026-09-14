<!-- PR 模板（11_LAUNCH_QUALITY_PLAN W4-4） -->

## 变更说明

（做什么、为什么）

## 门禁自查

- [ ] 后端：`make lint` + `make test` 全绿
- [ ] 前端：`pnpm lint` + `pnpm test` + `pnpm build` 全绿
- [ ] 涉及 UI 交互：`make test-e2e`（Playwright 六链路）全绿

## UI 变更（如有改动页面时必填）

- **入口可达性**：新页面/新按钮列出从哪个既有页面点进来（路径写全，防"功能存在但入口断裂"回归）
- **走查**：桌面 1440 / 移动 375 / 深色 三截图 vs 基准卡对照（docs/design-review/baseline/）
- **硬规则**：数值字段过 formatMoney/formatPercent（lint 已强制）；行情色仅 data-context="quote"

## 新页面专项（如有）

- [ ] 基准卡已建（先于代码，W3-C 规则）且含视觉语言字段
- [ ] 加载/空/异常三态齐备（Skeleton / EmptyIllustration / 错误文案）
