# 基准卡：CHAT-01 助手首页（盘中问询）

## 1. 参考稿

- 移动：`stitch/mobile/CHAT-01-mobile.html`（最终版）
- 桌面：`stitch/CHAT-01-desktop.html`

## 2. 布局结构（从稿人工提取）

```
1. 顶栏（标题「助手」+ 头像）
2. 说明区（一句话能力边界：条件式建议 + 有效期，非精确指令）
3. 问询输入（代码输入 + 主按钮；固定在底导航上方——UI §5.1）
4. 建议卡结果区（AdviceCard 完整形态：动作 + 仓位区间 + 调整轨迹 + 有效期/失效条件）
5. 降级形态（原因码 + 已知事实，零仓位数字）
6. AC-08 离线：入口禁用 + 明示"离线不可用"
```

- 栅格/分栏：移动单列；桌面输入区居中 ≤720px 或左输入右历史
- 滚动行为：结果区滚动，输入固定
- 桌面差异：卡片宽度上限，长轨迹列表完整展开

## 3. 关键尺寸

| 位置 | 稿实测 | 落点 token |
| --- | --- | --- |
| 输入框 | 10px 圆角 | `rounded-md` |
| 动作徽标 | 13px/600 | `text-label font-semibold` |
| 仓位区间数字 | 16px | `text-body-lg num` |
| footer | 12px | `text-caption`（截至 · 来源 · 有效至） |

## 4. 组件清单

| 组件 | 需覆盖 variant |
| --- | --- |
| AdviceCard | 6 动作全 variant（hold/watch/add/reduce/exit/pause）+ DEGRADED/SUSPEND |
| 调整轨迹列表 | 折扣/约束原因链（trail 名称映射） |
| 原因码徽标 | data_conflict（Phase 3.3 新增）/ data_stale / market_abnormal / ledger_unreconciled / no_calibrated_signal / gate:* |

## 5. 稿内违例覆盖注记（disregarded）

| 稿位置 | 违例内容 | 覆盖依据 |
| --- | --- | --- |
| CHAT-01-mobile:231 | 建议卡有有效期缺来源 | §8.3 footer 三段式必填 |
| — | 移动稿 tabular-nums 未全覆盖 | §2.2 全数字面 tabular-nums |

## 6. 走查项打勾区

- [ ] 三截图并排贴 PR
- [ ] PAUSE/SUSPEND 零数量（无目标手数/仓位数字）
- [ ] footer 句式 / 负号 / 空值
- [ ] 离线禁用态（AC-08）+ 限流/错误态文案
- [ ] 门禁全绿；深色 dark: 核验
