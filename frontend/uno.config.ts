import { defineConfig, presetIcons, presetUno } from "unocss";

// 色值以 UI §7.1 + ADR-0009 + ENFORCEMENT_CONTRACT §1.2 为准（online=teal #0D9488）。
// 版式 token（VISUAL_ALIGNMENT_PLAN §2.3）：fontSize/radius 按 UI §7.4/§7.6 唯一权威；
// spacing 沿用 presetUno 数值档（1=4px，与 §7.5 space.N 同构：2=8/3=12/4=16/6=24/8=32）。
export default defineConfig({
  presets: [presetUno(), presetIcons()],
  theme: {
    colors: {
      // 行情（仅涨跌）
      "market-up": "#D92D20",
      "market-down": "#079455",
      // 风险
      "risk-critical": "#C11574",
      "risk-warning": "#DC6803",
      // 品牌
      primary: "#3157D5",
      // 系统状态（online=teal，区别于 market-down；ADR-0009）
      success: "#067647",
      online: "#0D9488",
      // 行动色族（AdviceCard 六动作，ADR-0009）
      "action-hold": "#475467",
      "action-watch": "#DC6803",
      "action-add": "#3157D5",
      "action-reduce": "#C2410C",
      "action-exit": "#C11574",
      "action-pause": "#667085",
      // 系统错误
      error: "#BA1A1A",
    },
    // 字号档位（UI §7.4）：移动端值为基准；*-d 为桌面档（Display/H1/H2/H3 桌面放大一档）。
    // 每档 [字号, 行高]；字重按用途叠加 font-bold/semibold（§7.4 权重列）。
    fontSize: {
      display: ["28px", { "line-height": "1.2" }],
      "display-d": ["32px", { "line-height": "1.2" }],
      h1: ["24px", { "line-height": "1.3" }],
      "h1-d": ["28px", { "line-height": "1.3" }],
      h2: ["20px", { "line-height": "1.35" }],
      "h2-d": ["22px", { "line-height": "1.35" }],
      h3: ["17px", { "line-height": "1.4" }],
      "h3-d": ["18px", { "line-height": "1.4" }],
      "body-lg": ["16px", { "line-height": "1.6" }],
      body: ["14px", { "line-height": "1.55" }],
      label: ["13px", { "line-height": "1.4" }],
      caption: ["12px", { "line-height": "1.45" }],
      micro: ["11px", { "line-height": "1.35" }],
    },
    // 圆角档位（UI §7.6，覆盖 preset 默认——preset 的 rounded-lg=8px 与规范 14px 不符）
    borderRadius: {
      sm: "6px", // 标签、小控件
      md: "10px", // 输入、按钮
      lg: "14px", // 普通卡片
      xl: "20px", // 重点卡、Bottom Sheet
      full: "999px", // Pill、头像
    },
  },
});
