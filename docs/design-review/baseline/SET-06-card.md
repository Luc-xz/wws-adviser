# 基准卡：SET-06 安全与会话

> 补卡（审计回填 2026-09-09）：V4 已实现页的追溯基准卡。Passkey 注册走真实
> WebAuthn `credentials.create` 流程（b64ToBuffer 辅助）；改密码撤销其他会话。

## 1. 参考稿

- 移动：`stitch/mobile/SET-06-mobile.html`（最终版）
- 桌面：响应式自适应

## 2. 布局结构

```
1. PageHeader（title「安全与会话」+ subtitle「Passkey · 改密码（撤销其他会话）· 登出」）
2. Passkey 卡（§标题 + 已注册凭证列表（加载中「加载中…」）+ 注册按钮 passkey-register）
3. 改密码卡（§标题 + 当前/新密码表单 + 提交；成功 = 其他会话全撤销提示）
4. 登出区（security-logout 危险动作按钮）
```

- 栅格/分栏：单列分组卡
- 滚动行为：整页滚动
- 桌面差异：无（响应式同构）

## 3. 关键尺寸

| 位置 | 稿实测 | 落点 token |
| --- | --- | --- |
| 分组卡 | — | `p-4` + `rounded-lg` + shadow-sm |
| 区块标题 | — | `text-h3 font-semibold` |
| 危险按钮（登出） | — | 危险色描边/实底（risk-critical 系） |
| 密码输入 | — | `type="password"` 全局 input 基类 |

## 4. 组件清单

| 组件 | 需覆盖 variant |
| --- | --- |
| 凭证列表 | 有 / 无 / 加载中 |
| passkey-register | idle / creating / 成功 / 失败（含 unsupported） |
| 改密码表单 | 校验失败 / 服务端拒绝 / 成功 |
| 登出 | 确认语义 + 危险样式 |

## 5. 稿内违例覆盖注记（disregarded）

| 稿位置 | 违例内容 | 覆盖依据 |
| --- | --- | --- |
| 稿无 Passkey 区块 | 稿早于 Phase 3.5 | 以 WebAuthn 实装为准 |
| 稿英文文案 | 英文占位 | 中文文案规范 |

## 6. 走查项打勾区

- [ ] 三截图并排贴 PR
- [x] 默认 / 加载 / 空 / 异常四态（凭证空、注册失败均有态）
- [x] 门禁全绿；深色 dark: 核验（V5 扫描清零）

---

## 勘误增补：视觉语言字段（2026-09-11 W3-C）

> V1 建卡时未收录视觉语言三要素，致 V3/V4 实现'结构对齐但观感不像'（见 11_LAUNCH_QUALITY_PLAN §0/W3-C）。W3 起以下字段为建卡必填，本卡按已上线的 W3 视觉基线（material-symbols-rounded 图标系 / 卡片 rounded-2xl / 彩色 icon 容器 / 系统字体栈）回填勘误。

| 字段 | 本页基线 |
| --- | --- |
| 图标体系 | material-symbols-rounded（构建期内联）；导航/卡头图标与原型稿一一对位 |
| 圆角档位 | 卡片 rounded-2xl（16px）；按钮/输入 rounded-md/lg；禁用其他档位 |
| 色彩容器 | 摘要/入口卡 icon 容器：语义色 10% 底 + 同色 icon（primary/market/risk 族） |
| 字体 | 系统栈（SF/Segoe + 苹方/雅黑）+ antialias（Q2-A 决策，弃 Inter） |

