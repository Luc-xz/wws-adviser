// 11_LAUNCH_QUALITY_PLAN W1-4：模板插值禁止裸出数值字段（必须过 formatMoney/formatPercent）。
// 检测 {{ expr }} 顶层为数值字段名的 Identifier/MemberExpression（含 ?? / 三元的叶子）；
// 包裹在函数调用里（formatMoney(...) 等）视为已格式化，放行。
//
// 注意：vue-eslint-parser 的模板节点（V*）不经 ESLint 核心遍历，visitor 必须经
// parserServices.defineTemplateBodyVisitor 注册——直接 return {VXxx(){}} 会被静默忽略
//（2026-09-11 实测发现：既有 no-market-color-misuse 即因此自落地起从未生效）。
// 数值字段按 snake_case 段匹配（子串匹配会误伤 calibration_state 的 "calib-ratio-n"）：
// 段级 token（cost/price/quantity/…）须独立成段；复合字段按全名精确匹配。
const NUMERIC_SEGMENT_RE = /(^|_)(cost|price|quantity|pnl|amount|assets|weight|ratio|cash)($|_)/;
const NUMERIC_EXACT_RE = /^(market_value|avg_cost|value_a|value_b)$/i;

function isNumericField(name) {
  const snake = name.replace(/([a-z0-9])([A-Z])/g, "$1_$2").toLowerCase();
  return NUMERIC_EXACT_RE.test(snake) || NUMERIC_SEGMENT_RE.test(snake);
}

// 豁免已格式化中间变量（命名约定：*Text / *Fmt / *Formatted / *Display 结尾视为已格式化）
const FORMATTED_SUFFIX_RE = /(Text|Fmt|Formatted|Display)$/i;

function leafName(node) {
  if (!node) return null;
  if (node.type === "Identifier") return node.name;
  if (node.type === "MemberExpression") {
    if (node.computed) return null;
    return node.property?.name ?? null;
  }
  if (node.type === "ConditionalExpression") {
    return leafName(node.consequent) ?? leafName(node.alternate);
  }
  if (
    node.type === "LogicalExpression" &&
    (node.operator === "??" || node.operator === "||")
  ) {
    return leafName(node.left) ?? leafName(node.right);
  }
  return null;
}

export default {
  meta: {
    type: "problem",
    schema: [],
    messages: {
      raw: "数值字段 {{field}} 禁止裸插值——请过 formatMoney/formatPercent（超长小数破坏排版，UI §8 / W1-2）",
    },
  },
  create(context) {
    const filename = context.filename ?? context.getFilename();
    if (!filename.endsWith(".vue")) return {};
    const services =
      context.sourceCode?.parserServices ?? context.parserServices;
    if (!services?.defineTemplateBodyVisitor) return {};

    return services.defineTemplateBodyVisitor({
      // 只查 {{ }} 插值：插值的 VExpressionContainer 直接挂在 VElement 下；
      // 指令值（:prop="x" / v-model）的 VExpressionContainer 挂在 VAttribute 下，不查
      VExpressionContainer(node) {
        if (!node.parent || node.parent.type !== "VElement") return;
        const expr = node.expression;
        if (!expr) return;
        const name = leafName(expr);
        if (name && !FORMATTED_SUFFIX_RE.test(name) && isNumericField(name)) {
          context.report({
            node: expr,
            messageId: "raw",
            data: { field: name },
          });
        }
      },
    });
  },
};

