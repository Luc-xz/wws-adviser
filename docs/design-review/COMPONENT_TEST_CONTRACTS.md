# WWS Adviser · 前端组件测试契约

> **定位：** 把 [`COMPONENT_STATES.md`](./COMPONENT_STATES.md) §11 的验收断言、[`REVIEW_REPORT.md`](./REVIEW_REPORT.md) §6 的整改项，以及 [ADR-0009](../adr/0009-action-and-online-color-tokens.md) 引入的色彩 token，**规格化为可在 Phase 0.4 直接翻译成 vitest 红灯测试的契约**。
>
> **为什么不直接写 vitest：** `frontend/` 工程在 Phase 0.1 / 0.4 才建立（见 [1_REPO_STRUCTURE](../dev-guide/1_REPO_STRUCTURE.md) §2、[10_MILESTONE_PLAN](../dev-guide/10_MILESTONE_PLAN.md) §2）。现在写代码会与 Phase 0 的目录/锁文件/CI 规划重叠返工。本文以**文档形态**固化"测什么、怎么断言"，工程一建好即逐条翻译，零返工。
>
> **上游依据：** [UI §7.3/§8/§9/§10/§14/§18.3](../UI_DESIGN_SPECIFICATION.md) · [COMPONENT_STATES](./COMPONENT_STATES.md) · [REVIEW_REPORT](./REVIEW_REPORT.md)
> **下游消费：** Phase 0.4 `frontend/src/shared/ui/**` + `frontend/tests/unit/`

---

## 1. 消费方式（Phase 0.4 起）

1. 建 `frontend/`（pnpm + Vue3 + TS + vitest + @vue/test-utils，见 [7_FRONTEND_AND_PWA](../dev-guide/7_FRONTEND_AND_PWA.md)）。
2. 每条契约 `TC-XXX-NN` 翻译为一个 `it(...)` 块，**先写红灯**（组件未实现 → 测试失败），再实现组件转绿。
3. 契约 ID 同时作为测试用例标题前缀，便于追溯，例如 `it('TC-ADV-03 pause 态不渲染 targetRange/数量/醒目按钮', ...)`。

### 1.1 通用约定

| 事项 | 约定 |
| --- | --- |
| 挂载 | `mount(Component, { props, global: { plugins: [...] } })`（@vue/test-utils） |
| DOM 查询 | 优先 `data-testid`；无 testid 时退回 `text()` / `role` / `classes()` |
| 色彩断言 | **不断言色值**（脆），改为断言 **token class 名**（如 `classes()` 含 `text-action-reduce`）。token→色值映射在 CSS 层用单独样式表断言，解耦语义与色值 |
| 不渲染断言 | 用 `find('[data-testid=...]').exists()` 为 `false`，而非断言空字符串 |
| 透明度 | `element.style.opacity` 或 computed `opacity` 数值比较 |

---

## 2. 契约清单

### 2.1 AdviceCard（`shared/ui/AdviceCard.vue`）—— 产品红线集中处

| ID | 输入 props | 断言（必须通过） | 规范条款 | 优先级 |
| --- | --- | --- | --- | --- |
| TC-ADV-01 | `action` 遍历 6 值 | 标签容器 class 含对应 `action-*`（hold/watch/conditionalAdd/reduce/exitWatch/pause），**不含** `market-up`/`market-down` | UI §7.3 · ADR-0009 | P0 |
| TC-ADV-02 | `action:'pause'` | **不渲染** `[data-testid=advice-target-range]`、`[data-testid=advice-quantity]`、`[data-testid=advice-primary-action]`；仅渲染 `degradeReason` + 可用事实 | UI §9.3 · CS §3.2 | P0 |
| TC-ADV-03 | `state:'expired'`（`validUntil` 已过） | 卡片 computed `opacity ≤ 0.6`；顶部存在 `[data-testid=expired-badge]` | UI §9.3 · CS §3.2 | P0 |
| TC-ADV-04 | `action:'reduce'` 与 `action:'watch'` 同屏 | 两标签 class 分别为 `action-reduce`、`action-watch`，**色值可辨**（reduce=#C2410C ≠ watch=#DC6803） | UI §7.3 · ADR-0009 | P0 |
| TC-ADV-05 | `action:'conditional-add'` | 标签/按钮文案**不含**"立即买入/立即执行/快速下单/执行调整" | UI §9.8 · REVIEW §4.1 | P0 |
| TC-ADV-06 | 默认态完整 props | 渲染 6 级信息层级，第 5 级含"截至 … · 来源 … · 有效至 …"三要素（`[data-testid=advice-footer]` 文本正则命中三者） | UI §8.3/§9.3 · REVIEW §3.2 | P1 |

> TC-ADV-02 是**产品红线**：模型/数据不可用时进入 PAUSE，绝不能向用户输出具体交易数量。Phase 1.6 Model Gateway 降级路径强依赖此断言。

### 2.2 DataStatusBar（`shared/ui/DataStatusBar.vue`）

| ID | 输入 props | 断言 | 规范条款 | 优先级 |
| --- | --- | --- | --- | --- |
| TC-DSB-01 | `state` 遍历 fresh/delayed/conflict/offline | 4 态各有独立 class（`dsb-fresh/delayed/conflict/offline`），DOM 文案与 CS §2 文案模板一致 | UI §9.1 · CS §2 | P0 |
| TC-DSB-02 | `state:'fresh'`,`marketPhase:'trading'` | 圆点 class 含 `status-online`，**不含** `market-down`；点击触发 `navigate` 事件指向 DATA-01，**非 toast** | UI §7.3/§9.1 · ADR-0009 · REVIEW §4.2 | P0 |
| TC-DSB-03 | 任意态 | 根元素点击 → emit `{ to: 'DATA-01' }`（验证"跳转入口"存在，CS §2 硬规则"不能只弹 Toast"） | UI §9.1 | P0 |

### 2.3 RiskAlert（`shared/ui/RiskAlert.vue`）

| ID | 输入 props | 断言 | 规范条款 | 优先级 |
| --- | --- | --- | --- | --- |
| TC-RA-01 | `level:'critical'` | 容器 class 含 `status-critical`，**不含** `market-up`；`impact` 与 `action` 文本非空（缺失时组件应抛校验错或渲染占位拒绝） | UI §7.3/§9.4 · REVIEW §2.2C | P0 |
| TC-RA-02 | `level:'critical'`,`impact` 缺省 | 组件**拒绝渲染**纯错误码形态（无"仅显示错误代码"） | UI §9.4 | P0 |

### 2.4 PositionRow（`shared/ui/PositionRow.vue`）

| ID | 输入 props | 断言 | 规范条款 | 优先级 |
| --- | --- | --- | --- | --- |
| TC-POS-01 | `state:'up'` / `state:'down'` | 涨用 `market-up`（红）、跌用 `market-down`（绿），且旁有 +/- 或箭头（不只靠色） | UI §7.3 · REVIEW §2.2 | P1 |
| TC-POS-02 | 金额/百分比节点 | class 含 `tabular-nums` | UI §7.4 · REVIEW §3.1 | P1 |

### 2.5 EvidenceDrawer（`shared/ui/EvidenceDrawer.vue`）

| ID | 输入 props | 断言 | 规范条款 | 优先级 |
| --- | --- | --- | --- | --- |
| TC-ED-01 | `sourceType:'unverified'` | 容器 class 含 `evidence-unverified`（洋红虚线边框），且**不与**"事实"标签同节点混排 | UI §9.6/§9.7 · CS §9 | P2 |
| TC-ED-02 | 移动断点 | 形态为 Bottom Sheet（宽度 80–92%），桌面为右抽屉 360–420px | UI §9.6 · REVIEW §4.4 | P2 |

### 2.6 页面级状态（HOME-01 / CHAT-01）

| ID | 场景 | 断言 | 规范条款 | 优先级 |
| --- | --- | --- | --- | --- |
| TC-PG-01 | HOME-01 空账户 | **不渲染** `[data-testid=hero-net-worth]` 等 ¥0 数值节点；存在引导导入/录入按钮 | UI §10.3/§14.2 · CS §6 | P0 |
| TC-PG-02 | HOME-01 离线 | `[data-testid=refresh-btn]` 属性 `disabled=true`；存在常驻离线条 | UI §14.4 · CS §6/§8 | P0 |
| TC-PG-03 | CHAT-01 生成中 | 存在 4 步时间线节点（获取行情/检查持仓/运行风险规则/生成解释），第 3 步处于脉动态 | UI §10.12 · CS §7 | P1 |
| TC-PG-04 | CHAT-01 行情过期 | 当前回复渲染为 PAUSE 变体（复用 TC-ADV-02 的不渲染断言）；输入框上方存在常驻琥珀提示 | UI §10.12 · CS §7 | P0 |

### 2.7 全局状态（加载 / 空）

| ID | 场景 | 断言 | 规范条款 | 优先级 |
| --- | --- | --- | --- | --- |
| TC-GS-01 | 首次加载 | **不存在**全屏 Spinner（`[role=status]` + 单一 spinner 组合）；存在结构 Skeleton 节点 | UI §14.1 · CS §8.1 | P1 |
| TC-GS-02 | 空风险（无风险触发） | 文案平静（如"当前没有触发风险"），**不存在**庆祝动画 class（confetti/celebrate） | UI §14.2 · CS §8.2 | P1 |

### 2.8 数字格式（全局工具，呼应 REVIEW §3）

| ID | 场景 | 断言 | 规范条款 | 优先级 |
| --- | --- | --- | --- | --- |
| TC-NUM-01 | 负值格式化 | 负号字符为 `−`（U+2212），**非** ASCII `-`（U+002D） | UI §8.2 · REVIEW §3.3 | P1 |
| TC-NUM-02 | 空值 | 渲染为 `—`（em-dash），非 `-` | UI §8.2 · REVIEW §3.3 | P1 |

---

## 3. 色彩 token 强制断言（ADR-0009 落地）

这一节是 [ADR-0009](../adr/0009-action-and-online-color-tokens.md) 的 enforce 点。token→色值映射单独放一份样式/配置（如 UnoCSS preset 或 CSS variables），用一份专门的样式快照测试守住，**不混进组件逻辑测试**。

| ID | 断言 | 说明 |
| --- | --- | --- |
| TC-TOKEN-01 | `action.*` 六 token 色值彼此可辨（任意两两 ΔE ≥ 阈值，初定 12） | 防止 reduce/watch 再次撞色 |
| TC-TOKEN-02 | `status.online`(#0D9488) 与 `market.down`(#079455) ΔE ≥ 阈值 | 违规 A 根因防御 |
| TC-TOKEN-03 | `status.critical`(#C11574) 与 `market.up`(#D92D20) ΔE ≥ 阈值 | REVIEW §2.2C 防御 |
| TC-TOKEN-04 | 组件产物（mount 后的 class）中，凡行动语义节点 class 命名空间属 `action-*`，**禁出现** `market-*` | 静态扫描可辅助 |

> TC-TOKEN-01~03 的 ΔE 阈值为初定，Phase 0.4 落地时用真实色卡校准后固化为命名常量。

---

## 4. 翻译示例（TC-ADV-02，产品红线）

```ts
// frontend/tests/unit/AdviceCard.pause.spec.ts
import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import AdviceCard from '@/shared/ui/AdviceCard.vue'

describe('TC-ADV-02 AdviceCard pause 态', () => {
  it('不渲染 targetRange / 数量 / 醒目行动按钮', () => {
    const w = mount(AdviceCard, {
      props: {
        action: 'pause',
        state: 'degraded',
        instrument: { code: '600519', name: '贵州茅台' },
        riskLevel: 'warning',
        summary: '行情延迟超过阈值，暂停给出具体交易数量',
        degradeReason: 'quote-stale',
      },
    })
    expect(w.find('[data-testid=advice-target-range]').exists()).toBe(false)
    expect(w.find('[data-testid=advice-quantity]').exists()).toBe(false)
    expect(w.find('[data-testid=advice-primary-action]').exists()).toBe(false)
    expect(w.text()).toContain('行情延迟') // 仅原因 + 可用事实
  })
})
```

> 注：`data-testid` 命名、props 字段以 [COMPONENT_STATES.md](./COMPONENT_STATES.md) §3 Props 定义为准；本示例仅示范断言形态。

---

## 5. 与验收清单的映射

| 本契约组 | 对应验收 | Phase |
| --- | --- | --- |
| TC-ADV-02 / TC-PG-04 | AC-03（过期行情停止给具体数量）、AC-07（PAUSE 红线） | Phase 2 |
| TC-DSB-* | AC-02（数据质量可见）、AC-03 | Phase 1/2 |
| TC-RA-* / TC-TOKEN-03 | AC-04（风险规则可见） | Phase 1 |
| TC-PG-01/02 / TC-GS-* | AC-08（PWA 体验） | Phase 0/3 |
| TC-TOKEN-* | REVIEW §6 P0/P1 整改 | Phase 0.4 起 |

---

*本文是 COMPONENT_STATES §11 的可执行延伸：前者定义"组件有什么 props/状态"，本文定义"实现完必须通过哪些断言"。冲突时以 [UI_DESIGN_SPECIFICATION.md](../UI_DESIGN_SPECIFICATION.md) 上游为准。*
