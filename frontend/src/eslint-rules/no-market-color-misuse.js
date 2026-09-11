// ENFORCEMENT_CONTRACT §3.1：拦截 market-up/down 颜色类用于非行情上下文。
// 检测模板中 class* 含 text-market-up / text-market-down / bg-market-up / bg-market-down
// 且元素（或其祖先元素）未标 data-context="quote"。
//
// 注意：vue-eslint-parser 的模板节点（V*）不经 ESLint 核心遍历，visitor 必须经
// parserServices.defineTemplateBodyVisitor 注册——直接 return {VXxx(){}} 会被静默忽略
//（2026-09-11 修复：本规则自落地起因此从未生效，静默失效）。
const MARKET_RE = /(?:text|bg|border)-market-(?:up|down)/;

export default {
  meta: {
    type: "problem",
    schema: [],
    messages: {
      misuse: "{{token}} 仅用于行情涨跌语境（需 data-context=\"quote\"），此处疑似误用；非行情语义请用 success/error/risk token",
    },
  },
  create(context) {
    const sourceCode = context.sourceCode ?? context.getSourceCode();
    const filename = context.filename ?? context.getFilename();
    if (!filename.endsWith(".vue")) return {};
    const services =
      context.sourceCode?.parserServices ?? context.parserServices;
    if (!services?.defineTemplateBodyVisitor) return {};

    function hasQuoteContext(node) {
      let cur = node;
      while (cur) {
        // 属性挂在 VStartTag 上（VAttribute.parent = VStartTag；VElement.startTag 才有 attributes）
        const attrs =
          cur.type === "VStartTag"
            ? cur.attributes
            : cur.type === "VElement"
              ? cur.startTag?.attributes
              : null;
        if (attrs) {
          const attr = attrs.find(
            (a) =>
              a.directive === false &&
              a.key?.name === "data-context" &&
              a.value?.value === "quote"
          );
          if (attr) return true;
        }
        cur = cur.parent;
      }
      return false;
    }

    const templateVisitor = {
      "VAttribute[directive=false][key.name='class']"(node) {
        if (!node.value || !node.value.value) return;
        const m = node.value.value.match(new RegExp(MARKET_RE, "g"));
        if (!m) return;
        if (hasQuoteContext(node.parent)) return;
        for (const token of m) {
          context.report({ node, messageId: "misuse", data: { token } });
        }
      },
      // :class 动态绑定中的字面量 token（尽力检测）
      "VAttribute[directive=true][key.name.name='bind'][key.argument.name='class']"(node) {
        const text = sourceCode.getText(node);
        const m = text.match(new RegExp(MARKET_RE, "g"));
        if (!m) return;
        if (hasQuoteContext(node.parent)) return;
        for (const token of m) {
          context.report({ node, messageId: "misuse", data: { token } });
        }
      },
    };
    return services.defineTemplateBodyVisitor(templateVisitor);
  },
};
