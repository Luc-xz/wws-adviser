"""交割单 PDF → CSV 导入格式转换器（券商"交割单"导出 PDF → 3_API §3.3 CSV）。

用法：
    uv run --with pdfplumber python scripts/jgd_pdf_to_csv.py 交割单.pdf -o transactions.csv

处理规则（按实测交割单结构，2026-08）：
- 证券买入/卖出 → 买入/卖出；费用 = 手续费+印花税（其他杂费实测为 0，如非 0 会并入）
- ETF份额分拆 → 拆股（数量=增加份额，零成本）
- 红利入账 → 分红（qty=1、price=发生金额；qty>0 时 price=金额/qty）
- 上证LOF申购/开放基金申购 → 买入（数量/价格/费用照抄）
- 股份转入：同代码 5 日内有"申购"行 → 视为份额到账配对，跳过（避免双计）；
  否则按 0 成本买入并在跳过清单中警告（成本基准未知，需人工修正）
- 现金事件（银行转账/逆回购/股息红利差异/指定登记/利息归本）→ 不导入，折入初始现金
- 聚合：同（日期,代码,方向,价格）合并一行（数量/费用求和）——消除日内重复成交
  的指纹冲突（导入器按 标的+方向+数量+价格+费用+日期 去重）
- 初始现金 = 最新资金余额 − Σ(导入行回放现金增量)：回放后现金精确对齐交割单
- 输出对账锚点：各代码最终股票余额（导入后与 /positions 逐一对账）
"""

import argparse
import csv
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

LINE_RE = re.compile(r"^(\d{8})\s+(\d{6})\s+(\S+)\s+(\S+)\s+(.+)$")

IMPORT_HEADER = [
    "成交日期", "证券代码", "证券名称", "操作", "成交数量", "成交价格", "手续费", "印花税",
]

_OP_MAP = {
    "证券买入": "买入",
    "证券卖出": "卖出",
    "ETF份额分拆": "拆股",
    "红利入账": "分红",
    "上证LOF申购": "买入",
    "开放基金申购": "买入",
    "股份转入": "买入",
}
SKIP_OPS = {"通用回购逆回", "股息红利差异", "指定登记", "银行转证券", "证券转银行", "利息归本"}


@dataclass
class JgdRow:
    date: str
    code: str
    name: str
    op: str
    qty: Decimal
    price: Decimal
    amount: Decimal
    share_balance: Decimal
    cash_delta: Decimal
    fee: Decimal
    tax: Decimal
    fund_balance: Decimal | None = None


@dataclass
class ConversionResult:
    rows: list[dict[str, str]] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    initial_cash: Decimal = Decimal(0)
    final_cash: Decimal = Decimal(0)
    final_holdings: dict[str, tuple[str, Decimal]] = field(default_factory=dict)
    replay_check: dict[str, str] = field(default_factory=dict)


def parse_line(line: str) -> JgdRow | None:
    """单行 → JgdRow；非数据行返回 None。纯函数可单测。"""
    m = LINE_RE.match(line.strip())
    if m is None:
        return None
    date, code, name, op, rest = m.groups()
    tokens = rest.split()
    if len(tokens) < 7:
        return None
    try:
        nums = [Decimal(t) for t in tokens[:7]]
    except ArithmeticError:
        return None
    qty, price, amount, share_balance, cash_delta, fee, tax = nums
    # 列序：…手续费 印花税 资金余额 其他杂费（行尾按右截断：7 个数字=无余额，≥8=第 8 位是资金余额）
    fund_balance = tokens[7] if len(tokens) >= 8 else None
    misc = tokens[8] if len(tokens) >= 9 else None
    if misc is not None:
        fee += Decimal(misc)  # 其他杂费并入费用（实测为 0，稳妥处理）
    return JgdRow(date=date, code=code, name=name, op=op, qty=qty, price=price,
                  amount=amount, share_balance=share_balance, cash_delta=cash_delta,
                  fee=fee, tax=tax,
                  fund_balance=Decimal(fund_balance) if fund_balance else None)


def _replay_cash_delta(
    kind: str, qty: Decimal, price: Decimal, fee: Decimal, tax: Decimal
) -> Decimal:
    """导入器回放中一行的现金增量（与 portfolio.domain._apply_txn 口径一致）。"""
    if kind == "买入":
        return -(qty * price + fee + tax)
    if kind == "卖出":
        return qty * price - fee - tax
    if kind == "分红":
        return qty * price
    return Decimal(0)  # 拆股：零成本增数


def _signed_qty(r: JgdRow) -> Decimal:
    """该行导致的持股变化（买入/申购/拆股=+，卖出=−）。"""
    return -r.qty if r.op == "证券卖出" else r.qty


def _chain_by_share(rows: list[JgdRow]) -> list[JgdRow]:
    """同（日期,代码）内按股票余额链重构时间序。

    PDF 同日行序实测不可靠（既非正序也非倒序）；余额列是唯一可靠的序信息：
    每行 before = after − signed，链头 = before 不在任一 after 中。

    余额环（日内"买 N→卖 N"回到起点，before/after 互为镜像）物理上不可分辨
    "先买后卖"与"先卖（期初 N）后买回"；环回退按「买入优先」排列——保证回放
    不产生负持仓，成本口径在极少数真·先卖场景下略有偏差（余额列无法区分）。
    """
    afters = {r.share_balance: r for r in rows}
    before_map: dict[Decimal, JgdRow] = {}
    for r in rows:
        before_map.setdefault(r.share_balance - _signed_qty(r), r)
    candidates = [r for r in rows if r.share_balance - _signed_qty(r) not in afters]
    # 链头歧义（含余额环 candidates 为空）时买入优先——卖出作头需要期初持仓佐证
    pool = candidates or rows
    head = next((r for r in pool if r.op != "证券卖出"), pool[0])
    order: list[JgdRow] = []
    seen: set[int] = set()
    cur: JgdRow | None = head
    while cur is not None and id(cur) not in seen:
        order.append(cur)
        seen.add(id(cur))
        cur = before_map.get(cur.share_balance)
    if len(order) < len(rows):  # 余额环/链不完整：剩余行买入优先补齐
        rest = [r for r in rows if id(r) not in seen]
        rest.sort(key=lambda r: 0 if r.op != "证券卖出" else 1)  # 稳定排序保原相对序
        order.extend(rest)
    return order


def convert(rows: list[JgdRow], *, final_cash: Decimal | None = None) -> ConversionResult:
    """解析行集合 → 聚合导入行 + 初始现金 + 对账锚点。纯函数可单测。

    final_cash：交割单最终资金余额（由 convert_pdf 经资金余额链定位末笔得出）。
    缺省时取行集合中 fund_balance 的最大可见值（不可靠，仅供测试）。
    """
    if final_cash is None:
        for r in reversed(rows):
            if r.fund_balance is not None:
                final_cash = r.fund_balance
                break
    final_cash = final_cash or Decimal(0)

    rows_asc = sorted(rows, key=lambda r: r.date)
    subscribe_dates: dict[str, list[str]] = defaultdict(list)
    for r in rows_asc:
        if "申购" in r.op:
            subscribe_dates[r.code].append(r.date)

    imported: list[JgdRow] = []
    skipped: list[str] = []
    for r in rows_asc:
        if r.op in SKIP_OPS or r.code == "799999":
            skipped.append(f"{r.date} {r.code} {r.name} {r.op}（现金事件，折入初始现金）")
            continue
        if r.op == "股份转入":
            paired = any(0 <= int(r.date) - int(d) <= 5 for d in subscribe_dates[r.code])
            if paired:
                skipped.append(f"{r.date} {r.code} {r.name} 股份转入=申购份额到账（跳过避免双计）")
            else:
                imported.append(r)
                skipped.append(
            f"警告: {r.date} {r.code} {r.name} 股份转入按 0 成本买入"
            "（成本基准未知，需人工核对）"
        )
            continue
        if r.op not in _OP_MAP:
            skipped.append(f"警告: {r.date} {r.code} {r.name} {r.op}（未知业务，跳过——人工核对）")
            continue
        imported.append(r)

    # 同（日期,代码）内按股票余额链重构时间序（PDF 行序不可靠）
    chained: list[JgdRow] = []
    groups: dict[tuple[str, str], list[JgdRow]] = defaultdict(list)
    for r in imported:
        groups[(r.date, r.code)].append(r)
    for date_key in sorted(groups):
        chained.extend(_chain_by_share(groups[date_key]))
    seq_of = {id(r): i for i, r in enumerate(chained)}

    staged: list[dict[str, Decimal | str]] = []
    for r in chained:
        kind = _OP_MAP[r.op]
        qty, price, fee, tax = r.qty, r.price, r.fee, r.tax
        if kind == "拆股":
            qty, price, fee, tax = r.qty, Decimal(0), Decimal(0), Decimal(0)
        elif kind == "分红":
            total = r.cash_delta if r.cash_delta > 0 else r.amount
            qty = Decimal(1) if r.qty == 0 else r.qty
            price = (total / qty).quantize(Decimal("0.000001"))
            fee, tax = Decimal(0), Decimal(0)
        staged.append(dict(date=r.date, code=r.code, name=r.name, kind=kind,
                           qty=qty, price=price, fee=fee, tax=tax,
                           seq=seq_of[id(r)]))

    # 期初持仓合成：股票余额链反推——某代码时间上首个可导入行的（余额 − 当行增减）> 0
    # 说明窗口开始前已有持仓（旧券商转入/更早买入），合成一笔期初买入行：
    # 数量=反推值，成本=首行价格代理（警告标注，待真实更长交割单修正）。
    # 现金口径不变式保持：初始现金 = 期末余额 − Σ回放增量，虚拟购入成本被
    # 初始现金吸收 → 期末现金仍精确，净值不受影响。
    first_seen: dict[str, JgdRow] = {}
    for r in chained:  # 链序即时间序
        first_seen.setdefault(r.code, r)
    for code, r in first_seen.items():
        pre = r.share_balance - _signed_qty(r)
        if pre > 0:
            skipped.append(
                f"警告: {code} {r.name} 期初持仓 {pre} 份（交割单窗口前已有），"
                f"按首行价格 {r.price} 代理成本合成买入——建议导出更长周期交割单修正成本"
            )
            staged.append(dict(
                date=r.date, code=r.code, name=r.name, kind="买入",
                qty=pre, price=r.price, fee=Decimal(0), tax=Decimal(0),
                # 期初行排在同代码首行之前（时间更早）
                seq=seq_of[id(r)] - Decimal("0.5"),
            ))

    # 聚合：同（日期,代码,方向,价格）→ 数量/费用求和（消除日内重复成交的指纹冲突）
    agg: dict[tuple, dict[str, Decimal | str]] = {}
    for s in staged:
        key = (s["date"], s["code"], s["kind"], s["price"])
        if key in agg:
            for f in ("qty", "fee", "tax"):
                agg[key][f] = Decimal(agg[key][f]) + Decimal(s[f])  # type: ignore[operator]
            agg[key]["seq"] = min(agg[key]["seq"], s["seq"])  # type: ignore[type-var]
        else:
            agg[key] = dict(s)

    out_rows: list[dict[str, str]] = []
    replay_total = Decimal(0)
    # 输出序 = 链重构的时间序
    for s in sorted(agg.values(), key=lambda x: float(x["seq"])):  # type: ignore[arg-type]
        qty, price = Decimal(s["qty"]), Decimal(s["price"])  # type: ignore[arg-type]
        fee, tax = Decimal(s["fee"]), Decimal(s["tax"])  # type: ignore[arg-type]
        out_rows.append({
            "成交日期": str(s["date"]), "证券代码": str(s["code"]), "证券名称": str(s["name"]),
            "操作": str(s["kind"]), "成交数量": str(qty), "成交价格": str(price),
            "手续费": str(fee), "印花税": str(tax),
        })
        replay_total += _replay_cash_delta(str(s["kind"]), qty, price, fee, tax)

    # 对账锚点：各代码最终股票余额（按链序遍历；清仓行移除——PDF 行序不可靠）
    final_holdings: dict[str, tuple[str, Decimal]] = {}
    for r in chained:
        if r.share_balance > 0:
            final_holdings[r.code] = (r.name, r.share_balance)
        else:
            final_holdings.pop(r.code, None)

    initial_cash = (final_cash - replay_total).quantize(Decimal("0.01"))
    return ConversionResult(
        rows=out_rows, skipped=skipped, initial_cash=initial_cash, final_cash=final_cash,
        final_holdings=final_holdings,
        replay_check={
            "导入行数（聚合后）": str(len(out_rows)),
            "回放现金合计": str(replay_total.quantize(Decimal("0.01"))),
            "交割单最终资金余额": str(final_cash),
            "推算初始现金": str(initial_cash),
        },
    )


def _final_cash_by_fund_chain(rows: list[JgdRow]) -> Decimal | None:
    """最新日期的资金余额链定位末笔：其 after 不出现在任何行的 before 中。

    before(row) = after − cash_delta；末笔 after 即最终资金余额
    （PDF 同日行序不可靠，余额链是唯一可信序信息）。
    """
    newest = max(r.date for r in rows)
    day = [r for r in rows if r.date == newest and r.fund_balance is not None]
    if not day:
        return None
    befores = {r.fund_balance - r.cash_delta for r in day}
    tails = [r.fund_balance for r in day if r.fund_balance not in befores]
    return tails[0] if len(tails) == 1 else max(r.fund_balance for r in day)


def convert_pdf(pdf_path: str) -> ConversionResult:
    """PDF 全文 → ConversionResult（最终现金由资金余额链定位）。"""
    import pdfplumber

    rows: list[JgdRow] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for line in (page.extract_text() or "").splitlines():
                r = parse_line(line)
                if r is not None:
                    rows.append(r)
    return convert(rows, final_cash=_final_cash_by_fund_chain(rows))


def main() -> None:
    ap = argparse.ArgumentParser(description="交割单 PDF → CSV 导入格式")
    ap.add_argument("pdf")
    ap.add_argument("-o", "--output", default="transactions.csv")
    args = ap.parse_args()

    result = convert_pdf(args.pdf)
    with open(args.output, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=IMPORT_HEADER)
        writer.writeheader()
        writer.writerows(result.rows)

    print(f"已写出 {args.output}：{len(result.rows)} 行（聚合后）")
    for k, v in result.replay_check.items():
        print(f"  {k}: {v}")
    print("\n各代码最终股票余额（导入后与 /positions 对账）：")
    for code, (name, bal) in sorted(result.final_holdings.items()):
        print(f"  {code} {name}: {bal}")
    print(f"\n跳过 {len(result.skipped)} 行：")
    for s in result.skipped:
        print(f"  {s}")
    if any("警告" in s for s in result.skipped):
        print("\n注意：存在警告项，导入前请人工核对！", file=sys.stderr)


if __name__ == "__main__":
    main()
