"""研究报告导出渲染（Phase 3 波6）：Markdown → 自包含 HTML（可打印为 PDF）。

不引入 PDF 依赖：容器内无 CJK 字体时 PDF 会乱码；HTML 自带样式，
浏览器「打印为 PDF」即可得到带中字的离线副本。纯函数，禁框架 import。
"""

import html as _html
from typing import Any

_PRINT_CSS = """
body { font-family: -apple-system, 'Segoe UI', 'Microsoft YaHei', sans-serif;
       max-width: 780px; margin: 2rem auto; padding: 0 1rem;
       line-height: 1.7; color: #1f2937; }
h1 { font-size: 1.5rem; border-bottom: 2px solid #d1d5db; padding-bottom: .5rem; }
h2 { font-size: 1.15rem; margin-top: 2rem; }
blockquote { border-left: 3px solid #9ca3af; margin: .5rem 0; padding: .2rem .8rem;
             color: #4b5563; background: #f9fafb; font-size: .85rem; }
table { border-collapse: collapse; margin: 1rem 0; font-size: .9rem; }
th, td { border: 1px solid #d1d5db; padding: .35rem .6rem; }
th { background: #f3f4f6; }
.meta { color: #6b7280; font-size: .85rem; }
@media print { body { margin: 0; } }
"""


def md_to_html(md: str, *, title: str = "研究报告") -> str:
    """将本模块生成的 Markdown 子集渲染为自包含 HTML。

    支持子集（generation.assemble_report_md 的产出）：h1/h2、段落、
    blockquote 引用、| 表格 |、- 列表。其余行按段落转义输出。
    """
    lines = md.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        if stripped.startswith("## "):
            out.append(f"<h2>{_esc(stripped[3:])}</h2>")
            i += 1
        elif stripped.startswith("# "):
            out.append(f"<h1>{_esc(stripped[2:])}</h1>")
            i += 1
        elif stripped.startswith("> "):
            # 连续引用行合并为一个 blockquote
            quote: list[str] = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip().lstrip(">").strip())
                i += 1
            out.append(f"<blockquote>{_esc(' '.join(q for q in quote if q))}</blockquote>")
        elif stripped.startswith("|"):
            rows: list[list[str]] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(set(c) <= {"-", ":"} and c for c in cells):
                    rows.append(cells)
                i += 1
            if rows:
                thead = "".join(f"<th>{_esc(c)}</th>" for c in rows[0])
                body = "".join(
                    "<tr>" + "".join(f"<td>{_esc(c)}</td>" for c in r) + "</tr>"
                    for r in rows[1:]
                )
                out.append(
                    f"<table><thead><tr>{thead}</tr></thead><tbody>{body}</tbody></table>"
                )
        elif stripped.startswith("- "):
            items: list[str] = []
            while i < len(lines) and lines[i].strip().startswith("- "):
                items.append(f"<li>{_esc(lines[i].strip()[2:])}</li>")
                i += 1
            out.append(f"<ul>{''.join(items)}</ul>")
        else:
            out.append(f"<p>{_esc(stripped)}</p>")
            i += 1
    return (
        "<!DOCTYPE html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
        f"<title>{_esc(title)}</title>"
        f"<style>{_PRINT_CSS}</style></head>"
        f"<body>{''.join(out)}</body></html>"
    )


def _esc(text: str) -> str:
    return _html.escape(text, quote=True)


def export_filename(report: Any, fmt: str) -> str:
    """导出文件名：research-{report_id}.{md|html}。"""
    return f"research-{getattr(report, 'id', 'report')}.{fmt}"
