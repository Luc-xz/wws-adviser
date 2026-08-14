import tsParser from "@typescript-eslint/parser";
import vue from "eslint-plugin-vue";

import noMarketColorMisuse from "./src/eslint-rules/no-market-color-misuse.js";

// ESLint（vue 模板规则 + TS script 解析）；TS 类型由 vue-tsc 负责。
// 自定义规则见 src/eslint-rules/（ENFORCEMENT_CONTRACT §3）。
export default [
  { ignores: ["dist/**", "dev-dist/**", "node_modules/**", "src/api/generated/**"] },
  ...vue.configs["flat/recommended"],
  {
    files: ["**/*.vue"],
    languageOptions: { parserOptions: { parser: tsParser } },
  },
  {
    plugins: { local: { rules: { "no-market-color-misuse": noMarketColorMisuse } } },
    rules: {
      // 页面组件允许单词名（Portfolio/Settings 等路由页）
      "vue/multi-word-component-names": "off",
      "local/no-market-color-misuse": "error",
    },
  },
];
