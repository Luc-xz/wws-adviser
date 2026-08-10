# 4. 分析与风险（凯利资格、护栏、Advice 状态机、信号校准）

> 文档版本：v1.0  
> 文档状态：开发基线  
> 更新日期：2026-07-18  
> 关联：技术架构 §9 · PRD §8.3 §15 · 索引：[0_DEVELOPMENT_GUIDE_INDEX.md](./0_DEVELOPMENT_GUIDE_INDEX.md)

## 1. 目的

把技术架构 §9 与 PRD §8.3/§15 的“分析与建议防线”落为**纯函数契约、状态机定义与可测不变量**。凯利是纯领域函数，模型 Gateway 无权写 `p`；Advice 走有限状态机；信号走校准状态机与回灌闭环。写 analytics/advice 模块前读本文。

## 2. 模块边界与写权限（强制）

| 字段 / 状态 | 唯一写者 | 其他层能否写 |
| --- | --- | --- |
| `signals.p_low/p_mid/p_high` | 回测/校准服务（`analytics.calibration`） | **否**，含 `model_gateway` |
| `signals.calibration_state` | 校准服务 | 否 |
| `signals.n_eff / n_eff_oos / b_avg_win / b_avg_loss / reliability_ece` | 回测/校准服务 | 否 |
| `advice.state` | Advice 状态机 | 否 |
| `advice.target_weight_range / reason_chain` | 凯利纯函数 + Advice 编排 | 否 |
| 模型解释文本（summary 等） | `model_gateway` | 仅文本，不得回写数值字段 |

> 任何让模型文本“影响 `p`”的间接路径都视为违规。lint 规则（见 [1_REPO_STRUCTURE.md](./1_REPO_STRUCTURE.md) §3）应额外 enforce：`modules/model_gateway/**` 不得 import `modules/analytics.calibration` 的写接口。

## 3. 信号分层 L1–L4

来源：PRD §8.3。`signal_class` 是凯利资格的前置维度，写入 `signals` 表。

| 层级 | 信号类型 | `p` 来源 | 凯利资格 | 校准要求 |
| --- | --- | --- | --- | --- |
| L1 | 规则化/机械（如突破 N 日均线 + 量能） | 全市场回测，样本充足 | 默认有资格 | 命中率 + reliability + OOS |
| L2 | 基本面因子（如低估值 + 高质量分位） | 横截面分组回测 | 有资格，需滚动校准 | 滚动窗口 Platt 修正 |
| L3 | 事件驱动（特定公告类型后反应） | 事件匹配回测，样本中等 | 条件性资格，按事件类目 | 按事件类目分别校准 |
| L4 | 模型语言判断 | —— | **永远无资格** | —— |

约定：

- `Signal` 记录 `signal_class ∈ {L1, L2, L3}`；L4 不应作为 `p` 输入来源出现于任何 signals 行。若模型产出“判断”，仅作为证据/触发条件进入 `triggers`，不进 `p`。
- 每个信号版本须记录 `training_window_json`、`applicable_scope_json`、`cost_assumption_json`、`rule_version`、`oos_metrics_json`。

## 4. 校准状态机

状态枚举（与 [2_DATA_MODEL_AND_STORAGE.md](./2_DATA_MODEL_AND_STORAGE.md) §6.6 一致，字符串存 `signals.calibration_state`）：

```text
UNCALIBRATED → CALIBRATING → CALIBRATED(oos) → STALE → DECAYED
                                    │
                                    └──（到期未重跑）──→ STALE
                                    └──（回灌评价持续差）──→ DECAYED
```

| 状态 | 含义 | 凯利可用 |
| --- | --- | --- |
| `UNCALIBRATED` | 未跑过校准 | 否（`calibration_uncalibrated`） |
| `CALIBRATING` | 校准任务运行中 | 否（`calibration_uncalibrated`） |
| `CALIBRATED(oos)` | 样本外通过 + reliability 达标 + 未过期 | 是 |
| `STALE` | 超过有效期（默认 60 交易日，可配） | 否（`calibration_stale`） |
| `DECAYED` | 回灌评价持续差，人工/规则降级 | 否（`calibration_decayed`） |

有效期与到期流转：

- `calibration_expires_at` = 校准通过日 + 60 交易日（命名常量 `CALIBRATION_VALID_TD = 60`，配置范围可调，见 §10）。
- 后台维护任务每日扫描：`CALIBRATED(oos)` 且 `now > expires_at` → 置 `STALE`，记审计。
- `STALE` 信号须重新跑样本外并通过（含 reliability）才能回 `CALIBRATED(oos)`；不允许只重置状态。
- `DECAYED` 须显式人工或规则触发（如该信号类目连续 N 期评价口径低于阈值），不自动恢复。

reliability / Platt 校准（PRD §8.3 FR-ANL-003）：

1. 对历史预测概率分箱，计算每箱实际命中率 `observed_i` 与预测均值 `predicted_i`，得 `reliability_ece = mean(|observed_i - predicted_i|)`。
2. `ece` 超过命名阈值常量 `ECE_REJECT_THRESHOLD`（默认范围由配置给）→ 尝试 Platt scaling 修正；`platt_version` 写入。
3. Platt 修正后重评：仍超阈值 → 拒绝（`calibration_failed`），状态留 `STALE` 或显式 `DECAYED`。
4. 系统性高估概率（`observed < predicted` 持续偏高）优先降级，不靠 Platt 掩盖。

## 5. 凯利资格决策流（纯领域函数）

### 5.1 输入结构（版本化 dataclass）

```text
KellyInput:
  p_low, p_mid, p_high        # Decimal, Wilson 区间，校准服务写入
  b_avg_win, b_avg_loss       # Decimal，b = win/loss
  n_eff, n_eff_oos            # int，重叠信号衰减后
  calibration_state, calibration_expires_at
  reliability_ece, platt_version
  kelly_discount              # Decimal, 默认 0.20，范围 0.10–0.25
  confidence_discount_band    # 由 n_eff 分层取值
  liquidity_discount          # 由标的流动性档位取值
  current_position_value, cash, total_assets
  single_cap, industry_cap, portfolio_vol_cap, max_drawdown_cap, cash_floor
  lot_size, price_scale, fee_schedule
```

> 所有数值字段 `decimal.Decimal`；折扣与上限从运行配置注入，不在本指南写死数值，仅约束范围与命名常量。

### 5.2 决策流（任一关卡拒绝即终止并保留原因链，对应技术架构 §9.3）

```text
gate_calibration:
  if state != CALIBRATED(oos) or now > expires_at:
     return reject([calibration_uncalibrated | calibration_stale | calibration_expired])

gate_samples:
  if n_eff_oos < 30:                return reject([insufficient_samples])
  if 30 <= n_eff_oos < 100:         half_discount = true; reason += [low_confidence]

gate_reliability:
  if ece > ECE_REJECT_THRESHOLD and platt failed:
     return reject([calibration_failed])
  elif platt applied:                reason += [platt_applied, platt_version]

gate_p_interval_width:
  if (p_high - p_low) > WIDE_P_THRESHOLD:
     use p_low only; extra_discount += WIDE_P_PENALTY; reason += [wide_p_interval]

gate_payoff:
  b = b_avg_win / b_avg_loss
  if b <= 0:                        return output_zero([non_positive_payoff])
  if b < 0.1 or b > 10:             f_low only (no mid); reason += [extreme_payoff]

compute:
  f_lower = kelly_fraction(p_low, b)
  f_mid   = kelly_fraction(p_mid, b)        # 仅当非 extreme_payoff
  f_lower *= kelly_discount
  f_mid   *= kelly_discount
  if half_discount:                  f_lower *= 0.5; f_mid *= 0.5; reason += [low_confidence_half_discount]
  if wide_p_penalty:                 f_lower *= (1 - WIDE_P_PENALTY)
  f_lower *= confidence_discount_band(n_eff); f_mid *= same
  f_lower *= liquidity_discount;            f_mid *= liquidity_discount

clip:
  f_lower = clip(f_lower, 0, single_cap)
  f_mid   = clip(f_mid,   0, single_cap)
  honor cash_floor -> single_cap -> industry_cap -> portfolio_vol_cap -> max_drawdown_cap
  
quantize:
  if not safe_to_round_to_lot(f_lower, f_mid, lot_size, price_scale, fees):
     output range only without share count; reason += [indivisible_lot]

return KellyOutput(f_min=f_lower, f_max=f_mid, adjustment_trace=[...], reason_chain)
```

`kelly_fraction(p, b) = (b*p - (1-p)) / b`；`f* < 0` 时归 0（不做空，PRD §8.3 默认规则）。

### 5.3 输出与展示规则（PRD §8.3 输出规则）

- 拒绝：不输出仓位区间，只输出拒绝原因类别（`reason_chain` 至少一条）。
- 折扣：同时输出区间与原因链（如 `n_eff=24 → 拒绝`、`calibration=STALE → 拒绝`、`b=0.05 → extreme_payoff → 仅区间下限`）。
- 数据过期/市场异常：不提供凯利新增仓位，原因 `data_stale` / `market_abnormal`，不静默隐藏。
- 前端展示计算输入、折扣、约束、最终区间、失效条件、原因链；UI 不得将凯利折扣呈现为“精确推导值”（文案见 [7_FRONTEND_AND_PWA.md](./7_FRONTEND_AND_PWA.md)）。

### 5.4 命名常量与范围（不写实现值）

| 常量 | 含义 | 范围/默认归属 |
| --- | --- | --- |
| `KELLY_DISCOUNT` | 分数凯利折扣 | 默认 0.20，范围 0.10–0.25（配置） |
| `N_EFF_REJECT` | 拒绝阈值 | <30 拒绝 |
| `N_EFF_HALF` | 半折扣区间 | 30 ≤ n_eff < 100 |
| `N_EFF_FULL` | 正常 | ≥ 100 |
| `CALIBRATION_VALID_TD` | 校准有效期 | 默认 60 交易日 |
| `ECE_REJECT_THRESHOLD` | reliability 拒绝阈 | 配置 |
| `WIDE_P_THRESHOLD` | `p` 区间过宽阈 | 配置 |
| `B_EXTREME_LOW` / `B_EXTREME_HIGH` | `b` 极端边界 | 0.1 / 10 |

## 6. Advice 状态机（技术架构 §9.4）

状态枚举（字符串存 `advice.state`）：

```text
DRAFT
  → DATA_CHECKED
  → RISK_CHECKED
  → MODEL_EXPLAINED
  → OUTPUT_VALIDATED
  → PUBLISHED
任一步失败 → DEGRADED | BLOCKED
```

| 转换 | 守卫 | 失败去向 |
| --- | --- | --- |
| DRAFT → DATA_CHECKED | 行情新鲜、关键字段齐、账本已对账、市场状态可识别、标的可交易/未停牌 | DEGRADED（`data_stale`/`data_missing`/`ledger_unreconciled`/`market_abnormal`） |
| DATA_CHECKED → RISK_CHECKED | 软/硬上限未触发非法状态；凯利结果与原因链已生成 | DEGRADED（`risk_breach`）/ BLOCKED（硬限） |
| RISK_CHECKED → MODEL_EXPLAINED | 模型仅解释结构化结果与证据；输出经 schema 校验 | DEGRADED（`model_unavailable`，保留确定性摘要） |
| MODEL_EXPLAINED → OUTPUT_VALIDATED | 数值与确定性结果一致、引用 evidence_id ∈ 输入白名单、动作词合法、有效期存在 | BLOCKED（`output_invalid`） |
| OUTPUT_VALIDATED → PUBLISHED | 审计已落库（输入快照、版本、输出），发表 tid 事务提交 | —— |

发布前检查清单（PRD §15 + 技术架构 §9.4）：

1. 账本已对账。
2. 行情新鲜。
3. 标的可交易、非停牌、非异常。
4. 所有数值与确定性结果一致。
5. 未突破硬限制。
6. 含允许动作、有效期、触发/失效条件。
7. 每个关键事实 evidence_id 存在。

冲突处理：模型建议与确定性规则冲突时，**不直接展示冲突文本**；优先用确定性规则重建安全摘要；无法重建则发布 `PAUSE_ADVICE`（PRD §8.5 FR-CHAT-003、§15）。

## 7. 降级与 PAUSE_ADVICE

`PAUSE_ADVICE` 是一个合法 `action`（PRD §9.2），不是错误码。触发任一降级条件时：

- 仍返回 `200` + 业务体（[3_API_CONTRACT.md](./3_API_CONTRACT.md) §5）。
- `target_weight_range` 与交易数量为空。
- `degradation_reasons` 至少一条；`reason_chain` 记录降级根因类别（同 §5.2 的 reason 词表）。

降级条件清单（PRD §8.5 FR-CHAT-003 + §15）：

| 条件 | reason | 出处 |
| --- | --- | --- |
| 行情超新鲜度阈值 | `data_stale` | [5_DATA_INGESTION_AND_QUALITY.md](./5_DATA_INGESTION_AND_QUALITY.md) |
| 关键数据缺失 | `data_missing` | 数据质量 |
| 多源冲突未消解 | `data_conflict` | [5_DATA_INGESTION_AND_QUALITY.md](./5_DATA_INGESTION_AND_QUALITY.md) |
| 账本未对账 | `ledger_unreconciled` | portfolio |
| 模型与确定性规则冲突 | `model_conflict` | §6 |
| 市场状态异常 | `market_abnormal` | market_data |
| 模型不可用 | `model_unavailable` | [6_MODEL_AND_REPORT_PIPELINE.md](./6_MODEL_AND_REPORT_PIPELINE.md) |
| DB 不可写 | `db_not_writable` | [8_SECURITY_AND_DEPLOYMENT.md](./8_SECURITY_AND_DEPLOYMENT.md) |

## 8. 建议评价与回灌校准闭环（PRD §8.6 FR-REV-003）

`advice_evaluations`（[2_DATA_MODEL_AND_STORAGE.md](./2_DATA_MODEL_AND_STORAGE.md) §6.6）按建议动作类目定义评价口径，**版本化**：

| 动作 | 评价窗口 | 主口径 | 次口径 |
| --- | --- | --- | --- |
| 条件式增加 | 触发后 5–20 交易日或直到失效 | 触发条件是否真出现 + 出现后方向是否对 | 区间内最大不利波动 |
| 减少 | 失效条件前 | 减仓后相对基准超额（避免“卖了就涨”道德化误判） | 是否降低组合波动 |
| 观察 | 不评价收益 | 后续是否进入可操作状态 | 信息是否变充分 |
| 退出观察 | 30–60 交易日 | 假设失效是否被市场证伪 | —— |
| 暂停建议 | 不评价收益 | 数据恢复后是否本该给出建议 | 间接衡量降级频率 |

核心原则：评价“条件设计是否合理 + 触发后方向”，而非“涨没涨”。评价口径随报告 schema 一起版本化（`evaluation_window_json` + 口径版本名）。

回灌校准（PRD §8.6 末段）：

- 评价任务读取该 advice 的 `analysis_snapshot_id`（不可变输入）与设定窗口后的市场结果，计算主/次口径。
- 结果写入 `advice_evaluations`，并产出“某类信号历史建议表现”聚合。
- 聚合低于阈值 → 校准服务降低该信号类目的 `p`（重跑校准）或置 `DECAYED`，写审计与 `platt_version` 变更。
- 闭环：凯利输入 ↔ 建议评价 ↔ 信号校准。`model_gateway` 仍无写 `p` 权限——回灌只经回测/校准服务。

## 9. 必测不变量（对应技术架构 §18.2）

- 凯利纯函数给定固定 `KellyInput` 输出可重复（属性测试）。
- 拒绝时 `f_min/f_max` 为空 / 0，`reason_chain` 非空。
- 任一硬上限（`single_cap`/`industry_cap`/`portfolio_vol_cap`/`max_drawdown_cap`/`cash_floor`）始终能截断 `f_mid`。
- `n_eff_oos` 不达档（<30）绝不输出仓位区间。
- `b <= 0` 输出 0 并只记 `non_positive_payoff`。
- 极端 `b`（>10 或 <0.1）不输出 mid，仅区间下限。
- `calibration_state != CALIBRATED(oos)` 或过期 → 拒绝，状态文本落 `reason_chain`。
- 模型输出数值与确定性字段冲突时不覆盖确定性字段（Advice 转 BLOCKED/重建）。
- 任何模型文本 / 自报置信度不进入 `p`（属性测试：构造含 L4 信号的输入断言拒绝或不进凯利路径）。

## 10. 待确认项

| 事项 | 当前默认 | 备注 |
| --- | --- | --- |
| `KELLY_DISCOUNT` 配置入口 | 默认 0.20，设置页 `settings/risk` | 范围 0.10–0.25 |
| `CALIBRATION_VALID_TD` | 60 交易日 | 可按信号类目细分（L2 滚动） |
| `ECE_REJECT_THRESHOLD` | TODO(calibration-tuning) | 留运行配置 + 测试夹具 |
| `WIDE_P_THRESHOLD` | TODO(calibration-tuning) | 同上 |
| 评价窗口默认值 | 见 §8 表 | 按类目可配 |
| 回灌触发降级阈值 | TODO(backfeed-threshold) | 连续 N 期评价差 → `DECAYED` |
