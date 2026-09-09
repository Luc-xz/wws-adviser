# 基准卡：SET-04 通知与隐私

> 补卡（审计回填 2026-09-09）：V4 已实现页的追溯基准卡。Web Push 已接后端
> （usePushManager，Phase 3.5）；FR-NOTIFY-003 锁屏脱敏开关。

## 1. 参考稿

- 移动：`stitch/mobile/SET-04-mobile-v2.html`（取 v2）
- 桌面：响应式自适应

## 2. 布局结构

```
1. PageHeader（title「通知与隐私」+ subtitle「渠道状态 · 锁屏脱敏 · 浏览器推送」）
2. 渠道状态卡（各通知渠道开闭一览）
3. 隐私卡（§「锁屏脱敏」+ privacy-toggle 开关 + 保存 privacy-save）
4. Web Push 卡（§「浏览器推送」+ push-enable-set04 按钮）
```

- 栅格/分栏：单列分组卡
- 滚动行为：整页滚动
- 桌面差异：无（响应式同构）

## 3. 关键尺寸

| 位置 | 稿实测 | 落点 token |
| --- | --- | --- |
| 分组卡 | — | `p-4` + `rounded-lg` + shadow-sm |
| 区块标题 | — | `text-h3 font-semibold` |
| 开关 | — | 全局 toggle 基类 |
| Push 按钮 | — | idle / enabling / enabled / denied / unsupported 五态 |

## 4. 组件清单

| 组件 | 需覆盖 variant |
| --- | --- |
| 渠道行 | 开 / 关 |
| privacy-toggle | on / off（FR-NOTIFY-003 说明文案随动） |
| push-enable-set04 | idle / enabling / enabled / denied / unsupported |

## 5. 稿内违例覆盖注记（disregarded）

| 稿位置 | 违例内容 | 覆盖依据 |
| --- | --- | --- |
| v1 稿 Push 形态 | 与 Phase 3.5 实装不符 | 取 v2；以 push API 契约为准 |
| 稿英文文案 | 英文占位 | 中文文案规范 |

## 6. 走查项打勾区

- [ ] 三截图并排贴 PR
- [x] 默认 / 加载 / 空 / 异常四态（denied/unsupported 有专属态）
- [x] 门禁全绿；深色 dark: 核验（V5 扫描清零）
