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
