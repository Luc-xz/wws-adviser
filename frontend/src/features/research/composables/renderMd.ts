// 研究报告 Markdown 渲染（后端 assemble_report_md 的子集）：h1/h2/引用/表格/列表/段落。
// 先 HTML 转义再做结构替换（报告内容含模型生成文本，防注入）。
const ESC: Record<string, string> = {
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
};

function esc(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ESC[c] ?? c);
}

export function renderReportMd(md: string): string {
  const lines = md.split("\n");
  const out: string[] = [];
  let i = 0;
  while (i < lines.length) {
    const t = lines[i]!.trim();
    if (!t) { i += 1; continue; }
    if (t.startsWith("## ")) { out.push(`<h2>${esc(t.slice(3))}</h2>`); i += 1; }
    else if (t.startsWith("# ")) { out.push(`<h1>${esc(t.slice(2))}</h1>`); i += 1; }
    else if (t.startsWith("> ")) {
      const quote: string[] = [];
      while (i < lines.length && lines[i]!.trim().startsWith(">")) {
        quote.push(lines[i]!.trim().replace(/^>\s?/, ""));
        i += 1;
      }
      out.push(`<blockquote>${esc(quote.join(" "))}</blockquote>`);
    } else if (t.startsWith("|")) {
      const rows: string[][] = [];
      while (i < lines.length && lines[i]!.trim().startsWith("|")) {
        const cells = lines[i]!.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
        if (!cells.every((c) => /^[-: ]*$/.test(c) && c)) rows.push(cells);
        i += 1;
      }
      if (rows.length) {
        const head = rows[0]!.map((c) => `<th>${esc(c)}</th>`).join("");
        const body = rows
          .slice(1)
          .map((r) => `<tr>${r.map((c) => `<td>${esc(c)}</td>`).join("")}</tr>`)
          .join("");
        out.push(`<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`);
      }
    } else if (t.startsWith("- ")) {
      const items: string[] = [];
      while (i < lines.length && lines[i]!.trim().startsWith("- ")) {
        items.push(`<li>${esc(lines[i]!.trim().slice(2))}</li>`);
        i += 1;
      }
      out.push(`<ul>${items.join("")}</ul>`);
    } else {
      out.push(`<p>${esc(t)}</p>`);
      i += 1;
    }
  }
  return out.join("\n");
}
