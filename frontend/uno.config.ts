import { defineConfig, presetIcons, presetUno } from "unocss";

// 色值以 UI §7.1 + ADR-0009 + ENFORCEMENT_CONTRACT §1.2 为准（online=teal #0D9488）。
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
  },
});
