# WWS Adviser · 设计硬规则强制执行契约

> **定位：** 把 [REVIEW_REPORT.md](./REVIEW_REPORT.md) 发现的 Stitch 设计稿违规，转化为**前端代码层可强制执行的契约**。Stitch HTML 是 AI 静态快照，逐张修治标不治本；本契约在前端实现时从 token、格式化、lint、测试四层拦截违规。
>
> **配套：** [COMPONENT_STATES.md](./COMPONENT_STATES.md) 定义"组件有哪些状态"，本文定义"如何强制状态做对"。
> **落位前提：** 本文代码模板在 `frontend/` 骨架建起后移入对应位置即可生效（骨架尚未生成，见仓库根只有 docs/）。
> **工具链：** UnoCSS（§7-329 确认）+ Vitest + ESLint + vue-tsc

---

## 1. Token 契约（解决 §7.3 色彩违规根因）

### 1.1 现有 token（从 Stitch 项目提取，作为基线）

下表是 Stitch 设计系统的 `namedColors`（已 token 化，语义命名规范）。这些是**唯一允许的色值来源**——前端禁止硬编码 hex。

| token | hex | 当前语义 |
|---|---|---|
| `market-up` | #D92D20 | **仅** A 股上涨（红涨）|
| `market-down` | #079455 | **仅** A 股下跌（绿跌）|
| `risk-critical` | #C11574 | Critical 风险（洋红，与上涨红严格区分）|
| `risk-warning` | #DC6803 | Warning 风险（琥珀）|
| `primary` / `primary-container` | #063cbc / #3157d5 | 品牌靛蓝，主操作 + 条件式增加行动 |
| `error` / `error-container` | #ba1a1a / #ffdad6 | 系统错误（非行情）|
| surface/on-surface/outline/... | 见规范 §7.1 | 中性层 |

### 1.2 需补的 token（REVIEW_REPORT 指出的根因）

Stitch 稿违规的根因是**缺这套 token**，导致设计师用 `market-down` 兜底表示"OK"。前端必须补齐：

```ts
// frontend/uno.config.ts —— 新增 token（红色 = 违规重灾区）
theme: {
  colors: {
    // —— 系统状态（解决"下跌绿误作成功/在线"，REVIEW_REPORT §2.2-A）——
    success:        '#079455',  // 注意：与 market-down 同值但语义独立，未来可分色
    'success-container': '#E6F6EC',
    online:         '#079455',  // 在线/连接正常（替代误用的 market-down）
    'online-container':  '#E6F6EC',
    // —— 行动色族（解决"同一减少三色"，REVIEW_REPORT §2.2-D）——
    'action-hold':    '#475467',  // Slate，保持
    'action-watch':   '#DC6803',  // 琥珀，观察（=risk-warning 同值，但语义独立）
    'action-add':     '#3157D5',  // 靛蓝，条件式增加（=primary-container）
    'action-reduce':  '#C2410C',  // 深橙，减少（与 watch 琥珀区分）
    'action-exit':    '#C11574',  // 洋红，退出观察（=risk-critical 同值）
    'action-pause':   '#747685',  // 灰，暂停建议
  }
}
```

> **关键设计：** 即使两个 token 当前同值（如 success 与 market-down 都是 #079455），也必须分开命名——这样 lint 能按**语义**拦截（`text-market-down` 用在非行情处即报错），且未来调色不互相影响。

### 1.3 Token 使用硬规则（对应 §7.3）

| token | 允许场景 | 禁止场景 |
|---|---|---|
| `market-up/down` | 行情价格涨跌、当日盈亏百分比、走势图 | ❌ 系统成功/在线/任务完成/通知红点/分红/资金流 |
| `risk-critical` | Critical 风险标 | ❌ 行情涨跌（与 market-up 混淆）|
| `success/online` | 任务完成、数据源在线、连接正常 | ❌ 行情数字 |
| `action-*` | AdviceCard 行动标签/按钮 | ❌ 行情、风险 |
| `error` | 系统错误、表单校验失败 | ❌ 行情、行动建议 |

---

## 2. 格式化工具契约（解决 §7.4/§8 数字时间违规）

### 2.1 数字格式化（强制 tabular-nums + 精度 + 负号 U+2212）

```ts
// frontend/src/shared/format/number.ts
import { Decimal } from 'decimal.js'

/** 真正的数学负号 U+2212，替代 ASCII '-'（REVIEW_REPORT §3.3） */
const MINUS = '\u2212'
/** em-dash 空值（REVIEW_REPORT §3.3，§8.2） */
export const EMPTY = '\u2014'

/**
 * 格式化金额。空值返回 —；负数用 U+2212；强制 tabular-nums class。
 * @param scale 小数位（金额=2, A股价格=2, 港股=3, 基金净值=6, 数量=6）
 */
export function formatMoney(v: string | null | undefined, scale = 2): string {
  if (v === null || v === undefined || v === '') return EMPTY
  const d = new Decimal(v)
  const neg = d.isNegative()
  const abs = d.abs().toFixed(scale)
  // 千分位 + 负号替换
  const grouped = abs.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return (neg ? MINUS : '') + grouped
}

/** 涨跌幅，带符号 + tabular-nums（A 股红涨绿跌由 CSS class 决定，不在数值里） */
export function formatPercent(v: string | null | undefined, scale = 2): string {
  if (v === null || v === undefined || v === '') return EMPTY
  const d = new Decimal(v)
  const sign = d.isPositive() ? '+' : (d.isNegative() ? MINUS : '')
  return sign + d.abs().toFixed(scale) + '%'
}
```

### 2.2 全局 tabular-nums（解决 7/12 文件漏开）

```ts
// frontend/src/styles/global.css —— 所有可能含数字的元素全局开启
/* REVIEW_REPORT §3.1：7/12 文件漏开 tnum。全局兜底，组件无需逐个加。 */
table, .num, [data-num] {
  font-variant-numeric: tabular-nums;
  font-feature-settings: 'tnum' 1;
}
```

### 2.3 时间/来源组件（解决 §8.3 footer 缺失）

```vue
<!-- frontend/src/shared/ui/DataFooter.vue -->
<!-- 强制每条行情/净值/建议/报告底部"截至 · 来源 · 有效期"常驻 -->
<script setup lang="ts">
defineProps<{
  quotedAt: string      // 行情时间 ISO
  source: string        // 来源名
  validUntil?: string   // 建议有效期（可选）
}>()
</script>
<template>
  <div class="text-caption text-secondary flex items-center gap-2">
    <span>截至 {{ quotedAt }}</span>
    <span>·</span>
    <span>来源 {{ source }}</span>
    <template v-if="validUntil">
      <span>·</span>
      <span>有效至 {{ validUntil }}</span>
    </template>
  </div>
</template>
```

**用法约束（lint 可检）：** AdviceCard、行情行、报告区块必须包含 `<DataFooter>`，否则构建失败。

---

## 3. ESLint 自定义规则（拦截 token 误用）

### 3.1 规则：禁止行情色用于非行情上下文

```js
// frontend/eslint-rules/no-market-color-misuse.js
// REVIEW_REPORT §2.2-A/B：market-up/down 被误作成功/在线/通知
module.exports = {
  meta: { type: 'error', messages: { misuse: '{{token}} 仅用于行情涨跌，此处应用 {{suggest}}' } },
  create(context) {
    return {
      // 检测 class 属性里的 market-up/market-down
      "VAttribute[name='class'](value=/\\b(text|bg)-(market-up|market-down)\\b/)"(node) {
        const val = node.value.value
        const token = val.match(/(market-up|market-down)/)[0]
        const suggest = token === 'market-down' ? 'success/online' : 'error'
        // 父节点若非 [data-quote] / 价格 / 涨跌上下文，则报错
        const parent = node.parent.parent
        if (!/quote|price|change|pnl|盈亏|涨跌/i.test(parent.attribs?.['data-context'] || '')) {
          context.report({ node, messageId: 'misuse', data: { token, suggest } })
        }
      }
    }
  }
}
```

### 3.2 规则：强制 AdviceCard 含 DataFooter

```js
// frontend/eslint-rules/advicecard-requires-footer.js
// REVIEW_REPORT §3.2：建议卡缺时间来源 footer
module.exports = {
  meta: { type: 'error' },
  create(context) {
    return {
      "VElement[name='AdviceCard']"(node) {
        const has = node.children.some(c => /DataFooter/.test(c.name || ''))
        if (!has) context.report({ node, message: 'AdviceCard 必须含 <DataFooter>' })
      }
    }
  }
}
```

---

## 4. Vitest 断言（COMPONENT_STATES §11 的 12 条落地）

```ts
// frontend/src/shared/ui/__tests__/design-rules.test.ts
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import AdviceCard from '../AdviceCard.vue'
import DataStatusBar from '../DataStatusBar.vue'
import { formatMoney, formatPercent, EMPTY } from '../../format/number'

describe('§7.3 色彩硬规则', () => {
  it('AdviceCard pause 态不渲染目标数量/醒目按钮', () => {
    const w = mount(AdviceCard, { props: { action: 'pause', state: 'default', summary: '行情延迟' } })
    expect(w.find('[data-testid="target-range"]').exists()).toBe(false)
    expect(w.find('[data-testid="primary-cta"]').exists()).toBe(false)
  })

  it('AdviceCard expired 态透明度 ≤ 60% 且贴红 Badge', () => {
    const w = mount(AdviceCard, { props: { action: 'reduce', state: 'expired' } })
    expect(w.classes().some(c => /opacity-[0-5]/.test(c))).toBe(true)
    expect(w.find('[data-testid="expired-badge"]').exists()).toBe(true)
  })

  it('AdviceCard 六行动作色彼此可辨（无与 market-up/down 同 class）', () => {
    const actions = ['hold','watch','conditional-add','reduce','exit-watch','pause']
    for (const a of actions) {
      const w = mount(AdviceCard, { props: { action: a } })
      const cls = w.find('[data-testid="action-tag"]').classes().join(' ')
      expect(cls).not.toMatch(/market-up|market-down/)  // 行动色 ≠ 行情色
    }
  })
})

describe('§8 数字硬规则', () => {
  it('空值返回 em-dash —，非 0 或空', () => {
    expect(formatMoney(null)).toBe(EMPTY)
    expect(formatMoney('')).toBe(EMPTY)
    expect(formatMoney(undefined)).toBe(EMPTY)
  })

  it('负数用 U+2212 而非 ASCII -', () => {
    expect(formatMoney('-1234.5')).toContain('\u2212')
    expect(formatMoney('-1234.5')).not.toMatch(/^-\d/)  // 不以 ASCII - 开头
  })

  it('正数带 + 号（涨跌幅）', () => {
    expect(formatPercent('1.25')).toBe('+1.25%')
  })
})

describe('§9 组件硬规则', () => {
  it('RiskAlert critical 含影响+处理（非空错误码）', () => {
    const w = mount(RiskAlert, { props: { level: 'critical', impact: '...', action: '...' } })
    expect(w.props('impact')).toBeTruthy()
    expect(w.props('action')).toBeTruthy()
  })

  it('HOME 空账户态不渲染 ¥0 数值', () => {
    const w = mount(HomeOverview, { props: { hasPositions: false } })
    expect(w.text()).not.toContain('¥0')
    expect(w.find('[data-testid="empty-guide"]').exists()).toBe(true)
  })

  it('HOME 离线态刷新按钮 disabled', () => {
    const w = mount(HomeOverview, { props: { offline: true } })
    expect(w.find('[data-testid="refresh"]').attributes('disabled')).toBeDefined()
  })

  it('DataStatusBar 4 态全覆盖', () => {
    for (const s of ['fresh','delayed','conflict','offline']) {
      const w = mount(DataStatusBar, { props: { state: s, marketPhase: 'trading', updatedAt: '2026-08-12T10:32:15+08:00' } })
      expect(w.find(`[data-state="${s}"]`).exists()).toBe(true)
    }
  })

  it('AdviceCard 不含"立即执行/快速下单/执行调整"违规文案', () => {
    const w = mount(AdviceCard, { props: { action: 'reduce' } })
    expect(w.text()).not.toMatch(/立即执行|快速下单|执行调整/)
  })

  it('EvidenceDrawer unverified 态用洋红虚线边框', () => {
    const w = mount(EvidenceDrawer, { props: { type: 'unverified' } })
    expect(w.find('[data-testid="source-card"]').classes()).toContain('border-dashed')
    expect(w.find('[data-testid="source-card"]').classes().join(' ')).toMatch(/risk-critical/)
  })
})
```

---

## 5. 落地清单（骨架建起后的文件位置）

| 文件 | 内容 | 拦截的违规 |
|---|---|---|
| `frontend/uno.config.ts` | §1.2 token 完整定义 | 色彩 §7.3 |
| `frontend/src/styles/global.css` | §2.2 全局 tabular-nums | 数字 §7.4 |
| `frontend/src/shared/format/number.ts` | §2.1 formatMoney/formatPercent | §8.1/§8.2 |
| `frontend/src/shared/ui/DataFooter.vue` | §2.3 时间来源常驻 | §8.3 |
| `frontend/eslint-rules/*.js` | §3 自定义 lint 规则 | §7.3 / §8.3 |
| `frontend/src/shared/ui/__tests__/design-rules.test.ts` | §4 12 条 vitest | 全部 |

---

## 6. 验收方式

骨架建起后，CI 必须满足：
- [ ] `pnpm run lint` 通过（含自定义规则，拦截色彩/footer 违规）
- [ ] `pnpm run test` 通过（12 条 design-rules 断言全绿）
- [ ] `vue-tsc --noEmit` 通过（token 类型校验）
- [ ] 全局 grep `text-market-up\|text-market-down` 命中处均在 `[data-context="quote"]` 内

满足以上四条，即视为 REVIEW_REPORT §2/§3/§4 的系统性违规在前端层被强制消除。

---

*本契约与 [COMPONENT_STATES.md](./COMPONENT_STATES.md)（状态定义）、[REVIEW_REPORT.md](./REVIEW_REPORT.md)（问题清单）配套。三文档闭环：问题在哪 → 状态有哪些 → 代码怎么强制做对。*
