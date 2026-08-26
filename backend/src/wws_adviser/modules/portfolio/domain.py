"""Portfolio 领域：交易类型/方向、定点整数助手、指纹、CSV 解析、游标。纯领域，禁框架 import。"""

import base64
import csv
import hashlib
import io
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from wws_adviser.core.errors import DomainError

# 金额（费用/税/现金）定标整数小数位 → 分（2_DATA_MODEL §5/§13）
MONEY_SCALE = 2
# 指纹中各量的量化位（保证 "100" 与 "100.00" 同指纹）
PRICE_QUANTIZE = 4
QTY_QUANTIZE = 6


class TransactionKind(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    DIVIDEND = "DIVIDEND"
    SPLIT = "SPLIT"
    SUBSCRIBE = "SUBSCRIBE"
    REDEEM = "REDEEM"
    ADJUST = "ADJUST"
    FEE = "FEE"


class Direction(StrEnum):
    IN = "IN"  # 持仓数量增加
    OUT = "OUT"  # 持仓数量减少


# 业务方向（持仓增减）：买入/申购/送股/分红 → IN；卖出/赎回/费用 → OUT；调整默认 IN。
_KIND_DIRECTION: dict[TransactionKind, Direction] = {
    TransactionKind.BUY: Direction.IN,
    TransactionKind.SUBSCRIBE: Direction.IN,
    TransactionKind.SPLIT: Direction.IN,
    TransactionKind.DIVIDEND: Direction.IN,
    TransactionKind.ADJUST: Direction.IN,
    TransactionKind.SELL: Direction.OUT,
    TransactionKind.REDEEM: Direction.OUT,
    TransactionKind.FEE: Direction.OUT,
}


def kind_to_direction(kind: TransactionKind) -> Direction:
    return _KIND_DIRECTION[kind]


# CSV「买卖方向」文本 → TransactionKind
_DIRECTION_TEXT: dict[str, TransactionKind] = {
    "买": TransactionKind.BUY,
    "买入": TransactionKind.BUY,
    "卖": TransactionKind.SELL,
    "卖出": TransactionKind.SELL,
    "分红": TransactionKind.DIVIDEND,
    "送股": TransactionKind.SPLIT,
    "拆股": TransactionKind.SPLIT,
    "申购": TransactionKind.SUBSCRIBE,
    "赎回": TransactionKind.REDEEM,
}


class PortfolioError(DomainError):
    """Portfolio 领域错误基类。"""


class ImportPreviewExpiredError(PortfolioError):
    code = "CONFLICT"
    status = 409
    title = "导入预览已过期"


# —— 定点整数助手（金额按分存储，见 2_DATA_MODEL §5）——


def to_scaled_int(value: Decimal, scale: int = MONEY_SCALE) -> int:
    """Decimal → 定标整数（scale=2 时 Decimal('1.50') → 150）。"""
    quantum = Decimal(1).scaleb(-scale)
    quantized = value.quantize(quantum)
    return int(quantized * (Decimal(10) ** scale))


def from_scaled_int(raw: int, scale: int = MONEY_SCALE) -> Decimal:
    """定标整数 → Decimal（150 → Decimal('1.50')）。"""
    quantum = Decimal(1).scaleb(-scale)
    return (Decimal(raw) / (Decimal(10) ** scale)).quantize(quantum)


def decimal_str(value: Decimal) -> str:
    """Decimal → 无指数字符串（存储/传输用）。"""
    return format(value, "f")


# —— 移动加权平均成本法（MWAC）持仓/盈亏计算（波4，确定性核心）——


class PositionError(DomainError):
    """持仓计算错误（如卖空导致数量为负）。"""

    code = "CONFLICT"
    status = 409
    title = "持仓计算错误"


@dataclass
class TxnInput:
    """compute_positions 的输入（由 service 从 ORM Transaction 转换，保持 domain 零 ORM 依赖）。

    id 为同日 tie-break：ULID 创建时单调递增 = 插入序（导入文件序）= 真实日内时间序；
    空串（手工构造/测试）退化为稳定排序保持输入序。
    """

    instrument_id: str
    kind: TransactionKind
    direction: Direction
    quantity: Decimal
    price: Decimal
    fee: Decimal
    tax: Decimal
    trade_at: str
    id: str = ""


@dataclass
class PositionState:
    """单标的回放状态。avg_cost 由 cost_basis/qty 派生（MWAC）。"""

    qty: Decimal = Decimal(0)
    cost_basis: Decimal = Decimal(0)
    realized_pnl: Decimal = Decimal(0)

    @property
    def avg_cost(self) -> Decimal:
        return self.cost_basis / self.qty if self.qty > 0 else Decimal(0)


@dataclass(frozen=True)
class PositionsResult:
    positions: dict[str, PositionState]
    cash: Decimal


def _apply_txn(positions: dict[str, PositionState], t: TxnInput) -> Decimal:
    """对 positions 应用一笔交易，返回现金增量（正=现金入，负=现金出）。规则见波4 计划表。"""
    st = positions.setdefault(t.instrument_id, PositionState())
    amount = t.quantity * t.price
    if t.kind in (TransactionKind.BUY, TransactionKind.SUBSCRIBE):
        st.qty += t.quantity
        st.cost_basis += amount + t.fee + t.tax
        return -(amount + t.fee + t.tax)
    if t.kind in (TransactionKind.SELL, TransactionKind.REDEEM):
        avg = st.avg_cost
        new_qty = st.qty - t.quantity
        if new_qty < 0:
            raise PositionError(f"卖出数量超过持仓：{t.instrument_id} {t.trade_at}")
        st.realized_pnl += t.quantity * (t.price - avg) - t.fee - t.tax
        st.cost_basis -= t.quantity * avg
        st.qty = new_qty
        if st.qty == 0:
            st.cost_basis = Decimal(0)
        return amount - t.fee - t.tax
    if t.kind is TransactionKind.DIVIDEND:
        # 现金分红 = 已实现收益（不动持仓数量与成本）
        net = amount - t.fee - t.tax
        st.realized_pnl += net
        return net
    if t.kind is TransactionKind.SPLIT:
        # 送股/拆股 = 零成本增数（摊薄 avg_cost），不动现金
        st.qty += t.quantity
        return Decimal(0)
    if t.kind is TransactionKind.FEE:
        return -(t.fee + t.tax)
    if t.kind is TransactionKind.ADJUST:
        # 现金调整（IN）：现金入，不动持仓
        return amount - t.fee - t.tax
    raise PositionError(f"未知交易类型：{t.kind}")


def compute_positions(txns: list[TxnInput], *, initial_cash: Decimal) -> PositionsResult:
    """按 trade_at 排序回放交易 → 每标的 PositionState + 账户现金。纯函数、确定性。

    排序 (trade_at, id)：同日按插入序（ULID 单调递增）——日内先卖后买等顺序敏感场景
    的确定性保证（同日 ULID 随机序曾导致回放卖超）。
    """
    positions: dict[str, PositionState] = {}
    cash = initial_cash
    for t in sorted(txns, key=lambda x: (x.trade_at, x.id)):
        cash += _apply_txn(positions, t)
    return PositionsResult(positions=positions, cash=cash)


def compute_position_series(txns: list[TxnInput]) -> list[tuple[str, PositionState]]:
    """逐笔回放，返回 (trade_at, 该笔后累计 PositionState) 序列（供快照重建）。

    传入单标的的交易时，序列即该标的每个 trade_at 的累计持仓快照。
    """
    positions: dict[str, PositionState] = {}
    series: list[tuple[str, PositionState]] = []
    for t in sorted(txns, key=lambda x: (x.trade_at, x.id)):
        _apply_txn(positions, t)
        st = positions[t.instrument_id]
        series.append(
            (
                t.trade_at,
                PositionState(
                    qty=st.qty, cost_basis=st.cost_basis, realized_pnl=st.realized_pnl
                ),
            )
        )
    return series



# —— 指纹（防重复导入，2_DATA_MODEL §6.2）——


def compute_fingerprint(
    *,
    market: str,
    code: str,
    kind: TransactionKind,
    direction: Direction,
    quantity: Decimal,
    price: Decimal,
    fee: Decimal,
    trade_at: str,
) -> str:
    """标的+方向+数量+价格+费用+日期 的稳定哈希。

    使用 (market, code) 作为标的稳定标识（与 instrument_id 一一对应），
    数量/价格/费用分别量化到固定位，避免 "100" 与 "100.00" 产生不同指纹。
    """
    qty_q = quantity.quantize(Decimal(1).scaleb(-QTY_QUANTIZE))
    price_q = price.quantize(Decimal(1).scaleb(-PRICE_QUANTIZE))
    fee_q = fee.quantize(Decimal(1).scaleb(-MONEY_SCALE))
    payload = "|".join(
        [
            market.strip(),
            code.strip(),
            kind.value,
            direction.value,
            format(qty_q, "f"),
            format(price_q, "f"),
            format(fee_q, "f"),
            trade_at.strip(),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# —— 游标分页（base64 of "trade_at|id"，按 trade_at DESC, id DESC）——


def encode_cursor(trade_at: str, row_id: str) -> str:
    raw = f"{trade_at}|{row_id}".encode()
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_cursor(cursor: str) -> tuple[str, str]:
    raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
    trade_at, row_id = raw.split("|", 1)
    return trade_at, row_id


# —— CSV 解析（标准券商导出，3_API §3.3）——

# 规范列名 → 别名集合（小写去空格匹配）
_HEADER_ALIASES: dict[str, set[str]] = {
    "trade_date": {"成交日期", "交易日期", "日期", "trade_date", "date"},
    "code": {"证券代码", "代码", "code", "symbol"},
    "name": {"证券名称", "名称", "name"},
    "direction": {"操作", "买卖方向", "方向", "direction"},
    "quantity": {"成交数量", "数量", "quantity", "qty", "vol"},
    "price": {"成交价格", "成交均价", "价格", "price"},
    "fee": {"手续费", "费用", "fee", "commission"},
    "tax": {"印花税", "税", "tax"},
}

_REQUIRED_COLS = ("trade_date", "code", "direction", "quantity", "price")

_DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d", "%Y.%m.%d")


@dataclass(frozen=True)
class ParsedRow:
    row_no: int
    market: str
    code: str
    name: str
    kind: TransactionKind
    direction: Direction
    quantity: Decimal
    price: Decimal
    fee: Decimal
    tax: Decimal
    trade_at: str
    fingerprint: str


@dataclass(frozen=True)
class RowError:
    row_no: int
    message: str


def _normalize_headers(header_row: list[str]) -> dict[str, str]:
    """原始表头 → {canonical: raw_header}。未识别列忽略。"""
    mapping: dict[str, str] = {}
    for raw in header_row:
        key = raw.strip().lower().replace(" ", "")
        for canonical, aliases in _HEADER_ALIASES.items():
            if key in aliases:
                mapping[canonical] = raw
                break
    return mapping


def _to_decimal(text: str) -> Decimal:
    cleaned = text.strip().replace(",", "")  # 千分位
    if cleaned == "":
        cleaned = "0"
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"数值格式错误：{text!r}") from exc


def _parse_date(text: str) -> str:
    t = text.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(t, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError(f"无法解析日期：{text!r}")


def _cell(row: dict[str, str], mapping: dict[str, str], canonical: str) -> str:
    col = mapping.get(canonical, "")
    return (row.get(col) or "").strip()


def parse_csv_rows(
    text: str,
    *,
    market_for_code: Callable[[str], str] | None = None,
) -> tuple[list[ParsedRow], list[RowError]]:
    """解析券商 CSV 文本 → (有效行, 错误行)。纯函数，不碰 DB。

    - 表头归一化（中文别名兼容）
    - 缺必需列、非数值、未知方向、日期无法解析 → RowError
    - 批次内指纹重复 → 后者记为 RowError
    - market_for_code：由调用方注入的「代码→市场」解析（默认 SSE），保持本函数零跨模块依赖
    """
    rows: list[ParsedRow] = []
    errors: list[RowError] = []
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        return rows, [RowError(1, "空文件或缺少表头")]
    mapping = _normalize_headers(list(reader.fieldnames))
    missing = [c for c in _REQUIRED_COLS if c not in mapping]
    if missing:
        errors.append(RowError(0, f"缺少必需列：{','.join(missing)}"))
        return rows, errors

    resolver = market_for_code or (lambda _code: "SSE")
    seen: set[str] = set()
    for idx, raw_row in enumerate(reader, start=2):  # 表头占第 1 行
        code = _cell(raw_row, mapping, "code")
        direction_text = _cell(raw_row, mapping, "direction")
        try:
            if not code:
                raise ValueError("缺少证券代码")
            if direction_text not in _DIRECTION_TEXT:
                raise ValueError(f"未知买卖方向：{direction_text!r}")
            kind = _DIRECTION_TEXT[direction_text]
            quantity = _to_decimal(_cell(raw_row, mapping, "quantity"))
            price = _to_decimal(_cell(raw_row, mapping, "price"))
            fee = _to_decimal(_cell(raw_row, mapping, "fee"))
            tax = _to_decimal(_cell(raw_row, mapping, "tax"))
            trade_date_raw = _cell(raw_row, mapping, "trade_date")
            if not trade_date_raw:
                raise ValueError("缺少成交日期")
            trade_at = _parse_date(trade_date_raw)
            direction = kind_to_direction(kind)
            market = resolver(code)
            fingerprint = compute_fingerprint(
                market=market,
                code=code,
                kind=kind,
                direction=direction,
                quantity=quantity,
                price=price,
                fee=fee,
                trade_at=trade_at,
            )
        except (ValueError, InvalidOperation) as exc:
            errors.append(RowError(idx, str(exc)))
            continue

        if fingerprint in seen:
            errors.append(RowError(idx, "本批次内重复（指纹冲突）"))
            continue
        seen.add(fingerprint)
        rows.append(
            ParsedRow(
                row_no=idx,
                market=market,
                code=code,
                name=_cell(raw_row, mapping, "name"),
                kind=kind,
                direction=direction,
                quantity=quantity,
                price=price,
                fee=fee,
                tax=tax,
                trade_at=trade_at,
                fingerprint=fingerprint,
            )
        )
    return rows, errors
