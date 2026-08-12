// ENFORCEMENT_CONTRACT §3.1：拦截 market-up/down 用于非行情上下文。
// 波 4 骨架（create 返回空，不实际报错）；Phase 1 组件实现后完善 data-context 判断
// 并注册到 eslint.config.js 的 plugins。
export default {
  meta: {
    type: "problem",
    schema: [],
    messages: {
      misuse: "{{token}} 仅用于行情涨跌，此处疑似误用，建议 {{suggest}}",
    },
  },
  create() {
    // TODO Phase 1: 检测 VAttribute class 含 text-market-up/down 且父节点非 [data-context="quote"]
    return {};
  },
};
